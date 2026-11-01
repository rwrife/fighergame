"""Run in Blender 4.5 to check locally baked Don motion and ground alignment."""

import math
import json
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "assets" / "animations" / "Don_mixamo.blend"
if not path.is_file():
    print("SKIP Don's locally baked animation project is unavailable")
else:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    assert sum(len(obj.data.polygons) for obj in meshes) <= 20000
    for mesh in meshes:
        for vertex in mesh.data.vertices:
            assert sum(group.weight for group in vertex.groups) > 0

    def pose(name, last=False):
        action = bpy.data.actions["Don_" + name]
        rig.animation_data.action = action
        bpy.context.scene.frame_set(int(action.frame_range[1 if last else 0]))
        return {bone.name: bone.matrix_basis.copy() for bone in rig.pose.bones}

    def match(first, second):
        maximum = max(abs(first[name][row][col] - second[name][row][col])
                      for name in first for row in range(4) for col in range(4))
        assert maximum < 1e-5, maximum

    standing, crouched = pose("standing_idle"), pose("crouched_idle")
    for name in ("standing_punch", "standing_kick", "heavy_punch", "heavy_kick", "jump"):
        match(pose(name), standing)
        match(pose(name, True), standing)
    for name in ("crouched_punch", "crouched_kick"):
        match(pose(name), crouched)
        match(pose(name, True), crouched)
    match(pose("knocked_back_air", True), pose("fall_on_back"))
    match(pose("standing_idle", True), standing)
    match(pose("crouched_idle", True), crouched)
    plan = json.loads((ROOT / "temp" / "Don_mixamo" / "plan.json").read_text())
    manifest = json.loads((ROOT / "temp" / "Don_mixamo" / "manifest.json").read_text())
    character = json.loads((ROOT / "characters" / "don" / "character.json").read_text())
    camera_right = Vector((math.cos(math.radians(manifest["camera"]["azimuth"])),
                           math.sin(math.radians(manifest["camera"]["azimuth"])), 0))
    for name, side, frame in [
        ("standing_punch", "Left", 11), ("crouched_punch", "Left", 11),
        ("jump_punch", "Left", 11), ("heavy_punch", "Right", 41),
        ("standing_kick", "Left", 11), ("crouched_kick", "Left", 11),
        ("jump_kick", "Right", 11),
    ]:
        rig.animation_data.action = bpy.data.actions["Don_" + name]
        bpy.context.scene.frame_set(frame)
        hip = rig.pose.bones["mixamorig:Hips"].head
        limb = "Foot" if "kick" in name else "Hand"
        point = rig.pose.bones["mixamorig:" + side + limb].head
        minimum = .2 if limb == "Foot" else .3
        assert -(point - hip).y > minimum, (name, "strike must go forwards", point - hip)
        assert (point - hip).dot(camera_right) > .12, (name, "must extend towards the opponent")
        if limb == "Hand":
            shoulder = rig.pose.bones["mixamorig:" + side + "Arm"].head
            elbow = rig.pose.bones["mixamorig:" + side + "ForeArm"].head
            extension = (point - shoulder).length / ((elbow - shoulder).length + (point - elbow).length)
            assert extension > .94, (name, "full source punch extension", extension)

    def feet(name, frame):
        rig.animation_data.action = bpy.data.actions["Don_" + name]
        bpy.context.scene.frame_set(frame)
        hip = rig.pose.bones["mixamorig:Hips"].head
        return [rig.pose.bones["mixamorig:" + side + "Foot"].head - hip for side in ("Left", "Right")]

    for stance, kick in (("standing_idle", "standing_kick"), ("crouched_idle", "crouched_kick")):
        stance_front, stance_rear = feet(stance, 1)
        kick_front, kick_rear = feet(kick, 11)
        assert stance_front.dot(camera_right) > stance_rear.dot(camera_right), (stance, "front foot is the left")
        assert kick_front.dot(camera_right) > stance_front.dot(camera_right) + .05, (kick, "extends the front leg")
        assert (kick_rear - stance_rear).length < 1e-3, (kick, "keeps the rear foot planted")
    camera = manifest["camera"]
    center = Vector(camera["center"])
    pixels = character["frame_size"] / camera["ortho_scale"]
    angle = math.radians(camera["azimuth"])
    right = Vector((math.cos(angle), math.sin(angle), 0))
    for name, move in character["moves"].items():
        entry = character["animations"][name]
        first = entry.get("frames", [0])[0]
        rig.animation_data.action = bpy.data.actions["Don_" + name]
        side = "Left" if ("punch" in name and name != "heavy_punch") or name in (
            "standing_kick", "crouched_kick") else "Right"
        limb = rig.pose.bones["mixamorig:" + side + ("Hand" if "punch" in name else "Foot")]
        for hit in move["hitboxes"]:
            x, y, width, height = hit["rect"]
            for frame in range(hit["frames"][0], hit["frames"][1] + 1):
                source_frame = manifest["clips"][name]["source_frames"][first + frame]
                bpy.context.scene.frame_set(math.floor(source_frame), subframe=source_frame % 1)
                correction = entry["frame_offsets"][frame] if "frame_offsets" in entry else [0, 0]
                points = []
                for point in (limb.head, limb.tail):
                    point = rig.matrix_world @ point
                    points.append((
                        ((point - center).dot(right) * pixels + entry["offset_x"] + correction[0])
                        * character["sprite_scale"],
                        ((center.z - point.z) * pixels + entry["offset_y"] + correction[1])
                        * character["sprite_scale"],
                    ))
                assert any(x <= px <= x + width and y <= py <= y + height for px, py in points), (
                    name, frame, "active hitbox must contain the visible striking limb", points, hit["rect"],
                )
    jump = bpy.data.actions["Don_jump"]
    rig.animation_data.action = jump
    bpy.context.scene.frame_set(plan["airborne_pose_frame"] * 5 + 1)
    airborne = {bone.name: bone.matrix_basis.copy() for bone in rig.pose.bones}
    match(pose("jump_punch"), airborne)
    match(pose("jump_kick"), airborne)
    pose("fall_on_back", True)
    hips = rig.pose.bones["mixamorig:Hips"].head
    head = rig.pose.bones["mixamorig:Head"].head
    assert abs(head.z - hips.z) < .015, (head.z, hips.z)
    graph = bpy.context.evaluated_depsgraph_get()
    floor = min((evaluated.matrix_world @ vertex.co).z
                for mesh in meshes for evaluated in [mesh.evaluated_get(graph)]
                for vertex in evaluated.data.vertices)
    assert math.isclose(floor, 0, abs_tol=.001), floor
    print("PASS Don rig: forward strikes, front-leg light kicks, aligned active hitboxes, matching endpoints, loops and back fall")
