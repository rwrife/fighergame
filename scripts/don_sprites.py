"""Run in Blender 4.5: locally skin Don and adapt the supplied Mixamo moves."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_frames import cel_shade
from mixamo_demo import bone_names, import_fbx, retarget


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "guard": "Fighting Idle.fbx",
    "crouch": "Crouch Idle.fbx",
    "punch": "Punching.fbx",
    "kick": "Mma Kick.fbx",
    "roundhouse": "roudhouse kick.fbx",
    "block": "Standing Block React Large.fbx",
    "jump": "Jumping.fbx",
    "hit": "Stomach Hit.fbx",
    "fall": "Falling Down.fbx",
}
REQUIRED = {
    "standing_idle", "crouched_idle", "standing_punch", "crouched_punch",
    "standing_kick", "crouched_kick", "standing_block", "block_idle",
    "jump", "jump_punch", "jump_kick", "knocked_back_air", "fall_on_back",
    "heavy_punch", "heavy_kick",
}


def set_frame(frame):
    bpy.context.scene.frame_set(math.floor(frame), subframe=frame % 1)


def snapshot(rig, action, frame):
    rig.animation_data.action = action
    set_frame(frame)
    return {bone.name: bone.matrix_basis.copy() for bone in rig.pose.bones}


def apply_pose(rig, pose):
    rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis = pose[bone.name]
    bpy.context.view_layer.update()


def ground_pose(rig, meshes, pose):
    apply_pose(rig, pose)
    graph = bpy.context.evaluated_depsgraph_get()
    ground = min(
        (mesh.matrix_world @ vertex.co).z
        for obj in meshes
        for mesh in [obj.evaluated_get(graph)]
        for vertex in mesh.data.vertices
    )
    result = {name: basis.copy() for name, basis in pose.items()}
    hip = bone_names(rig)["Hips"]
    if abs(ground) > 1e-6:
        result[hip].translation += (
            rig.data.bones[hip].matrix_local.to_3x3().inverted() @ Vector((0, 0, -ground))
        )
    return result


def lying_on_back(rig, meshes, pose):
    apply_pose(rig, pose)
    names = bone_names(rig)
    hip = rig.pose.bones[names["Hips"]]
    spine = rig.pose.bones[names["Head"]].head - hip.head
    horizontal = Vector((spine.x, spine.y, 0))
    if horizontal.length < 1e-6:
        raise ValueError("The Mixamo fall has no backwards direction")
    rotation = spine.rotation_difference(horizontal.normalized()).to_matrix().to_4x4()
    matrix = Matrix.Translation(hip.head) @ rotation @ Matrix.Translation(-hip.head) @ hip.matrix
    result = {name: basis.copy() for name, basis in pose.items()}
    result[hip.name] = hip.bone.convert_local_to_pose(
        matrix, hip.bone.matrix_local, invert=True,
    )
    return ground_pose(rig, meshes, result)


def interpolate(a, b, amount):
    if amount == 0:
        return {name: matrix.copy() for name, matrix in a.items()}
    if amount == 1:
        return {name: matrix.copy() for name, matrix in b.items()}
    output = {}
    for name in a:
        al, ar, asc = a[name].decompose()
        bl, br, bsc = b[name].decompose()
        output[name] = Matrix.LocRotScale(
            al.lerp(bl, amount), ar.slerp(br, amount), asc.lerp(bsc, amount),
        )
    return output


def bake(rig, name, poses):
    action = bpy.data.actions.new(name)
    rig.animation_data.action = action
    for frame, pose in enumerate(poses, 1):
        for bone in rig.pose.bones:
            bone.rotation_mode = "QUATERNION"
            bone.matrix_basis = pose[bone.name]
            for channel in ("location", "rotation_quaternion", "scale"):
                bone.keyframe_insert(channel, frame=frame, group=bone.name)
    action.use_fake_user = True
    return action


def loop_close(poses, count=8):
    poses = [dict(pose) for pose in poses]
    count = min(count, len(poses) - 1)
    for index in range(count):
        weight = (index + 1) / count
        poses[-count + index] = interpolate(poses[-count + index], poses[0], weight)
    return poses


def adapted(poses, baseline, hip, recovery=True):
    initial = poses[0]
    inverse = {name: basis.inverted() for name, basis in initial.items()}
    result = []
    for pose in poses:
        entry = {name: baseline[name] @ inverse[name] @ matrix
                 for name, matrix in pose.items()}
        # Keep clip root travel relative to the new grounded or airborne pose.
        entry[hip].translation = baseline[hip].translation + (
            pose[hip].translation - initial[hip].translation
        )
        result.append(entry)
    if recovery:
        count = min(6, len(result) // 3)
        for index in range(count):
            result[-count + index] = interpolate(
                result[-count + index], baseline, (index + 1) / count,
            )
    return result


def resample(poses, count):
    result = []
    for index in range(count):
        frame = index * (len(poses) - 1) / (count - 1)
        start = math.floor(frame)
        result.append(interpolate(poses[start], poses[min(start + 1, len(poses) - 1)], frame - start))
    return result


def attack_pose(rig, pose, baseline, kind, side="Right", turn=0.0):
    apply_pose(rig, pose)
    yaw = Matrix.Rotation(turn, 3, "Z").to_quaternion()
    rotations = {bone.name: yaw @ bone.matrix.to_quaternion() for bone in rig.pose.bones}
    result = {name: matrix.copy() for name, matrix in baseline.items()}
    apply_pose(rig, result)
    desired = {bone.name: bone.matrix.copy() for bone in rig.pose.bones}
    prefixes = (
        ("Spine", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
         "LeftForeArm", "RightForeArm", "LeftHand", "RightHand") if kind == "punch" else
        tuple(side + part for part in ("UpLeg", "Leg", "Foot", "Toe"))
    )
    # Preserve world-space strike rotations, not compounded per-bone guard deltas.
    for bone in rig.data.bones:
        if not bone.name.split(":")[-1].startswith(prefixes):
            continue
        parent = bone.parent
        position = (desired[parent.name] @ parent.matrix_local.inverted()
                    @ bone.matrix_local).translation
        matrix = Matrix.LocRotScale(position, rotations[bone.name], Vector((1, 1, 1)))
        desired[bone.name] = matrix
        result[bone.name] = bone.convert_local_to_pose(
            matrix, bone.matrix_local, invert=True,
            parent_matrix=desired[parent.name], parent_matrix_local=parent.matrix_local,
        )
    return result


def strike_peak(rig, poses, part):
    names = bone_names(rig)
    distances = []
    for pose in poses:
        apply_pose(rig, pose)
        point = rig.pose.bones[names[part]].head - rig.pose.bones[names["Hips"]].head
        distances.append(-point.y)
    return max(range(len(poses)), key=distances.__getitem__)


def played_keys(poses):
    anchors = [index * 5 for index in range(len(poses) - 1)] + [len(poses) * 5 - 1]
    result = []
    for first, last, a, b in zip(anchors, anchors[1:], poses, poses[1:]):
        result.extend(interpolate(a, b, (index - first) / (last - first))
                      for index in range(first, last))
    result.append({name: matrix.copy() for name, matrix in poses[-1].items()})
    return result


def create_rig(model, source):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(model))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if sum(len(obj.data.polygons) for obj in meshes) > 20000:
        raise ValueError("Don's generated model exceeds its 20,000-polygon budget")
    for mesh in meshes:
        mesh.rotation_euler.z -= math.pi / 2
    bpy.context.view_layer.update()
    for mesh in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    points = [obj.matrix_world @ vertex.co for obj in meshes for vertex in obj.data.vertices]
    ground = min(point.z for point in points)
    height = max(point.z for point in points) - ground
    half_width = max(abs(point.x) for point in points)
    for mesh in meshes:
        mesh.location.z -= ground
    template, imported = import_fbx(source)
    names = bone_names(template)
    hip = template.matrix_world @ template.data.bones[names["Hips"]].head_local
    head = template.matrix_world @ template.data.bones[names["HeadTop_End"]].head_local
    ankle = template.matrix_world @ template.data.bones[names["LeftFoot"]].head_local
    knee = template.matrix_world @ template.data.bones[names["LeftLeg"]].head_local
    shoulder = template.matrix_world @ template.data.bones[names["LeftArm"]].head_local
    neck = template.matrix_world @ template.data.bones[names["Head"]].head_local
    hand = template.matrix_world @ template.data.bones[names["LeftHand"]].tail_local
    anchors = [
        (0, 0), (ankle.z, height * .075), (knee.z, height * .255),
        (hip.z, height * .46), (shoulder.z, height * .77),
        (neck.z, height * .82), (head.z, height * .99),
    ]
    anchors.sort()

    def fit(point):
        point = template.matrix_world @ point
        z = point.z
        for (a, az), (b, bz) in zip(anchors, anchors[1:]):
            if a <= z <= b:
                z = az + (bz - az) * (z - a) / (b - a)
                break
        else:
            z = height * point.z / head.z
        return Vector((
            point.x * half_width / abs(hand.x),
            (point.y - hip.y) * height / head.z * .6,
            z,
        ))

    rest = [(bone.name, bone.parent.name if bone.parent else None,
             fit(bone.head_local), fit(bone.tail_local)) for bone in template.data.bones]
    data = bpy.data.armatures.new("DonMixamoSkeleton")
    rig = bpy.data.objects.new("Don", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, start, end in rest:
        bone = data.edit_bones.new(name)
        bone.head = start
        bone.tail = end
        if parent:
            bone.parent = data.edit_bones[parent]
        if name.endswith(("HeadTop_End", "Toe_End")):
            bone.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    for mesh in meshes:
        unweighted = [vertex.index for vertex in mesh.data.vertices if not vertex.groups]
        if unweighted:
            raise ValueError(f"Don skinning left {len(unweighted)} vertices unweighted")
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new("DonRest")
    for frame in (1, 2):
        for bone in rig.pose.bones:
            bone.keyframe_insert("rotation_quaternion", frame=frame)
    return rig, meshes, height


def mirror_pose(rig, pose):
    rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis = pose[bone.name]
    bpy.context.view_layer.update()
    matrices = {bone.name: bone.matrix.copy() for bone in rig.pose.bones}
    reflection = Matrix.Diagonal(Vector((-1, 1, 1, 1)))
    desired = {}
    result = {}
    for bone in rig.data.bones:
        other = bone.name.replace("Left", "SIDE").replace("Right", "Left").replace("SIDE", "Right")
        deformation = matrices[other] @ rig.data.bones[other].matrix_local.inverted()
        matrix = reflection @ deformation @ reflection @ bone.matrix_local
        desired[bone.name] = matrix
        result[bone.name] = bone.convert_local_to_pose(
            matrix, bone.matrix_local, invert=True,
            parent_matrix=desired[bone.parent.name] if bone.parent else Matrix.Identity(4),
            parent_matrix_local=bone.parent.matrix_local if bone.parent else Matrix.Identity(4),
        )
    return result


def prepare(args):
    temporary = ROOT / "temp"
    temporary.mkdir(parents=True, exist_ok=True)
    (temporary / ".gdignore").touch(exist_ok=True)
    model = ROOT / "assets" / "shared_fbx_cache" / "Don_base.fbx"
    sources = ROOT / "assets" / "animations" / "mixamo"
    for filename in SOURCES.values():
        if not (sources / filename).is_file():
            raise ValueError(f"Missing local Mixamo source: {filename}")
    rig, meshes, height = create_rig(model, sources / SOURCES["guard"])
    actions = {}
    motion = {}
    for name, filename in SOURCES.items():
        source, objects = import_fbx(sources / filename)
        actions[name] = retarget(rig, source, "Don_source_" + name)
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        start, end = actions[name].frame_range
        motion[name] = [snapshot(rig, actions[name], frame)
                        for frame in range(math.ceil(start), math.floor(end) + 1)]
    names = bone_names(rig)
    hip = names["Hips"]
    guard = ground_pose(rig, meshes, motion["guard"][0])
    crouch = ground_pose(rig, meshes, motion["crouch"][0])
    jump = adapted(motion["jump"], guard, hip)
    root_rotation = rig.data.bones[hip].matrix_local.to_3x3()
    apex = max(range(0, len(jump), 5),
               key=lambda index: (root_rotation @ jump[index][hip].translation).z)
    airborne = jump[apex]
    peaks = {"punch": strike_peak(rig, motion["punch"], "LeftHand"),
             "kick": strike_peak(rig, motion["kick"], "RightFoot")}
    clips = {}

    def add(name, poses, loop, source, description):
        if name not in {"jump", "jump_punch", "jump_kick", "knocked_back_air", "fall_on_back",
                        "jump_to_punch", "punch_to_jump", "jump_to_kick", "kick_to_jump"}:
            poses = [ground_pose(rig, meshes, pose) for pose in poses]
        clips[name] = {
            "action": bake(rig, "Don_" + name, poses).name,
            "loop": loop, "fps": 12 if name == "standing_idle" else 6,
            "source_clips": [SOURCES[key] for key in source],
            "adaptation": description,
        }

    add("standing_idle", loop_close(motion["guard"]), True, ["guard"], "Closed Mixamo guard loop")
    add("crouched_idle", loop_close(motion["crouch"]), True, ["crouch"], "Closed Mixamo crouch loop")
    for name, source, baseline in [
        ("standing_punch", "punch", guard), ("crouched_punch", "punch", crouch),
        ("standing_kick", "kick", guard), ("crouched_kick", "kick", crouch),
        ("jump_punch", "punch", airborne), ("jump_kick", "kick", airborne),
    ]:
        # Grounded light kicks use the stance's front (left) leg, so mirror the rear-leg
        # source and turn it out from the hip to extend towards the opponent on screen.
        front = name in ("standing_kick", "crouched_kick")
        source_poses = ([mirror_pose(rig, pose) for pose in motion[source]] if front
                        else motion[source])
        poses = [attack_pose(rig, pose, baseline, source, "Left" if front else "Right",
                             math.radians(35) if front else 0.0)
                 for pose in source_poses]
        peak = strike_peak(rig, source_poses, "LeftFoot") if front else peaks[source]
        chamber = interpolate(baseline, poses[max(0, peak - 5)], .7)
        keys = [
            baseline, chamber,
            poses[peak], poses[min(len(poses) - 1, peak + 2)],
            # Snap back through the chamber; the mirrored source would plant behind the stance.
            chamber if front else poses[min(len(poses) - 1, peak + 7)], baseline,
        ]
        add(name, played_keys(keys), False, [source, "jump" if name.startswith("jump") else
                                            "crouch" if name.startswith("crouch") else "guard"],
            ("Mirrored source world-space kick on the stance's front (left) leg, turned out towards the opponent, with peak extension and chambered recovery"
             if front else
             "Source world-space strike rotations on the matching stance, with peak extension captured and complete entry/recovery"))
    mirrored = [attack_pose(rig, mirror_pose(rig, pose), guard, "punch")
                for pose in motion["punch"]]
    peak = peaks["punch"]
    windup = mirrored[max(0, peak - 8)]
    heavy = played_keys([
        guard, interpolate(guard, windup, .5), windup, windup, windup,
        mirrored[max(0, peak - 4)], mirrored[max(0, peak - 2)],
        mirrored[peak], mirrored[peak], mirrored[min(len(mirrored) - 1, peak + 2)],
        mirrored[min(len(mirrored) - 1, peak + 6)], interpolate(windup, guard, .7), guard,
    ])
    root_inverse = rig.data.bones[hip].matrix_local.to_3x3().inverted()
    for index, pose in enumerate(heavy):
        reach = math.sin(math.pi * index / (len(heavy) - 1)) * height * .06
        pose[hip].translation += root_inverse @ Vector((0, -reach, 0))
    add("heavy_punch", heavy, False, ["punch", "guard"],
        "Mirrored source world-space back-hand punch with deliberate wind-up, held full extension and matched recovery")
    add("heavy_kick", adapted(motion["roundhouse"], guard, hip), False, ["roundhouse", "guard"],
        "Mixamo roundhouse kick with matched guard recovery")
    block_poses = adapted(motion["block"], guard, hip, recovery=False)
    block = block_poses[len(block_poses) // 2]
    block_entry = [interpolate(guard, block, index / 9) for index in range(10)]
    add("standing_block", block_entry, False, ["block", "guard"], "Baked entry into the Mixamo standing block pose")
    add("block_idle", [block] * 30, True, ["block"], "Held standing blocking idle, separate from block entry")
    add("jump", jump, False, ["jump", "guard"], "Mixamo jump with takeoff, elevation and landing/recovery")
    knock = adapted(motion["hit"], airborne, hip, recovery=False)
    for index, pose in enumerate(knock):
        pose[hip].translation.x -= height * .15 * index / (len(knock) - 1)
    add("knocked_back_air", knock, False, ["hit", "jump"],
        "Mixamo hit reaction on the airborne jump pose, with backwards root travel")
    fall = adapted(motion["fall"], guard, hip, recovery=False)
    horizontal_offset = root_rotation @ (knock[-1][hip].translation - guard[hip].translation)
    for index, pose in enumerate(fall):
        weight = index / (len(fall) - 1)
        pose[hip].translation += root_rotation.inverted() @ Vector((
            horizontal_offset.x, horizontal_offset.y, horizontal_offset.z * (1 - weight),
        ))
        if index < 8:
            fall[index] = interpolate(knock[-1], pose, index / 7)
    final = lying_on_back(rig, meshes, fall[-1])
    fall.extend(interpolate(fall[-1], final, index / 18) for index in range(1, 19))
    add("fall_on_back", fall, False, ["fall", "hit", "jump"],
        "Mixamo back fall bridged from airborne knockback and settled flat on the back; no get-up")
    for name, first, last, source in [
        ("stand_to_crouch", guard, crouch, ["guard", "crouch"]),
        ("crouch_to_stand", crouch, guard, ["crouch", "guard"]),
        ("block_to_stand", block, guard, ["block", "guard"]),
        ("jump_to_punch", airborne, snapshot(rig, bpy.data.actions[clips["jump_punch"]["action"]], 1), ["jump", "punch"]),
        ("punch_to_jump", snapshot(rig, bpy.data.actions[clips["jump_punch"]["action"]], 30), airborne, ["punch", "jump"]),
        ("jump_to_kick", airborne, snapshot(rig, bpy.data.actions[clips["jump_kick"]["action"]], 1), ["jump", "kick"]),
        ("kick_to_jump", snapshot(rig, bpy.data.actions[clips["jump_kick"]["action"]], 30), airborne, ["kick", "jump"]),
    ]:
        add(name, [interpolate(first, last, index / 9) for index in range(10)], False, source,
            "Baked skeletal pose bridge; no sprite crossfade")
    if not REQUIRED <= clips.keys():
        raise ValueError("Required Don move set is incomplete")
    rig.animation_data.action = bpy.data.actions[clips["standing_idle"]["action"]]
    bpy.context.scene.render.fps = 30
    bpy.context.scene.render.fps_base = 1
    export_dir = sources / "Don"
    export_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for mesh in meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    for name, clip in clips.items():
        action = bpy.data.actions[clip["action"]]
        rig.animation_data.action = action
        bpy.context.scene.frame_start = int(action.frame_range[0])
        bpy.context.scene.frame_end = int(action.frame_range[1])
        bpy.ops.export_scene.fbx(
            filepath=str(export_dir / f"Don_{name}.fbx"), use_selection=True,
            object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
            bake_anim=True, bake_anim_use_all_actions=False,
            bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0,
            path_mode="COPY", embed_textures=True,
        )
    rig.animation_data.action = bpy.data.actions[clips["standing_idle"]["action"]]
    bpy.ops.file.pack_all()
    args.output.mkdir(parents=True, exist_ok=True)
    blend = ROOT / "assets" / "animations" / "Don_mixamo.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    plan = {
        "character": "Don", "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "reference_sha256": hashlib.sha256((ROOT / "assets" / "references" / "Don_tpose.png").read_bytes()).hexdigest(),
        "rigging": "Local Blender rest-skeleton fitting and automatic skin weights",
        "airborne_pose_frame": apex // 5,
        "sources": {filename: hashlib.sha256((sources / filename).read_bytes()).hexdigest()
                    for filename in SOURCES.values()},
        "blend": "assets/animations/Don_mixamo.blend", "clips": clips,
    }
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Don rig and all required Mixamo-derived moves baked:", blend, flush=True)


def render(args):
    plan = json.loads((args.output / "plan.json").read_text(encoding="utf-8"))
    model = ROOT / "assets" / "shared_fbx_cache" / "Don_base.fbx"
    if hashlib.sha256(model.read_bytes()).hexdigest() != plan["model_sha256"]:
        raise ValueError("Don's cached model changed; prepare the move set again")
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / plan["blend"]))
    scene = bpy.context.scene
    rig = next(obj for obj in scene.objects if obj.type == "ARMATURE")
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    minimum, maximum = Vector((math.inf,) * 3), Vector((-math.inf,) * 3)
    angle = math.radians(args.azimuth)
    right = Vector((math.cos(angle), math.sin(angle), 0))
    projected_minimum, projected_maximum = math.inf, -math.inf
    samples = {}
    for name, clip in plan["clips"].items():
        action = bpy.data.actions[clip["action"]]
        rig.animation_data.action = action
        start, end = action.frame_range
        count = max(2, math.ceil((end - start) / 30 * clip["fps"]))
        frames = [start + index * 30 / clip["fps"] for index in range(count)]
        if not clip["loop"]:
            frames[-1] = end
        samples[name] = frames
        for frame in frames:
            set_frame(frame)
            graph = bpy.context.evaluated_depsgraph_get()
            for mesh in meshes:
                evaluated = mesh.evaluated_get(graph)
                for vertex in evaluated.data.vertices:
                    point = evaluated.matrix_world @ vertex.co
                    projected = point.dot(right)
                    projected_minimum = min(projected_minimum, projected)
                    projected_maximum = max(projected_maximum, projected)
                    for axis in range(3):
                        minimum[axis] = min(minimum[axis], point[axis])
                        maximum[axis] = max(maximum[axis], point[axis])
    extent = maximum - minimum
    if not all(math.isfinite(value) for value in extent) or min(extent) <= 0:
        raise ValueError("Don's animated bounds are invalid")
    center = (minimum + maximum) / 2
    center += right * ((projected_minimum + projected_maximum) / 2 - center.dot(right))
    direction = Vector((math.sin(angle), -math.cos(angle), 0))
    camera_data = bpy.data.cameras.new("DonSharedCamera")
    camera = bpy.data.objects.new("DonSharedCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + direction * extent.length * 3
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(extent.z, projected_maximum - projected_minimum) * 1.10
    camera_data.clip_end = extent.length * 10
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 1
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.use_nodes = False
    cel_shade(meshes, direction)
    manifest = {
        "source": "Mixamo with locally baked adaptations",
        "camera": {"center": list(center), "ortho_scale": camera_data.ortho_scale,
                   "azimuth": args.azimuth, "minimum": list(minimum), "maximum": list(maximum)},
        "set_file": "Don_mixamo_set.json", "clips": {},
    }
    for name, clip in plan["clips"].items():
        directory = args.output / name
        directory.mkdir(parents=True, exist_ok=True)
        rig.animation_data.action = bpy.data.actions[clip["action"]]
        entry = {
            "fps": clip["fps"], "loop": clip["loop"], "renderer": "cel-shaded",
            "frames": [], "source_frames": samples[name], "sheet": f"Don_{name}_sheet.png",
        }
        for index, frame in enumerate(samples[name]):
            set_frame(frame)
            filename = f"{index:04d}.png"
            scene.render.filepath = str(directory / filename)
            bpy.ops.render.render(write_still=True)
            entry["frames"].append(filename)
        (directory / "manifest.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
        manifest["clips"][name] = entry
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    provenance = {key: value for key, value in plan.items() if key != "blend"}
    provenance.update({
        "render_size": args.size, "palette_colors": 32, "outline_px": 0,
        "blender_version": bpy.app.version_string, "camera": manifest["camera"],
    })
    (ROOT / "assets" / "spritesheets" / "Don_sources.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8",
    )
    print("Don move-set renders:", args.output, flush=True)


def game_offsets(args):
    plan = json.loads((args.output / "plan.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
    character_path = ROOT / "characters" / "don" / "character.json"
    character = json.loads(character_path.read_text(encoding="utf-8"))
    hold = plan["airborne_pose_frame"]
    character["animations"]["jump"]["frames"] = [0, hold]
    character["animations"]["air_idle"]["frames"] = [hold, hold]
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / plan["blend"]))
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    hip = bone_names(rig)["Hips"]
    rig.animation_data.action = bpy.data.actions["Don_standing_idle"]
    set_frame(1)
    baseline = rig.matrix_world @ rig.pose.bones[hip].head
    camera = manifest["camera"]
    center = Vector(camera["center"])
    angle = math.radians(camera["azimuth"])
    right = Vector((math.cos(angle), math.sin(angle), 0))
    pixels_per_unit = 346 / camera["ortho_scale"]
    offset_x = -(baseline - center).dot(right) * pixels_per_unit
    sheets = ROOT / "assets" / "spritesheets"

    def bottoms(stem):
        image = bpy.data.images.load(str(sheets / f"{stem}_sheet.png"), check_existing=False)
        width, height = image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        alpha = pixels.reshape((height, width, 4))[:, :, 3]
        result = []
        for start in range(0, width, 346):
            opaque = np.flatnonzero(np.any(alpha[:, start:start + 346] > .1, axis=1))
            if not opaque.size:
                raise ValueError(f"Empty Don frame in {stem}")
            result.append(height - int(opaque[0]))
        bpy.data.images.remove(image)
        return result

    ground = bottoms("Don_standing_idle")[0]
    offset_y = 173 - ground
    airborne = {
        "jump", "air_idle", "jump_punch", "jump_kick", "knocked_back_air",
        "jump_to_punch", "punch_to_jump", "jump_to_kick", "kick_to_jump",
    }
    for name, entry in character["animations"].items():
        clip = entry["sheet"].removeprefix("Don_")
        source_frames = manifest["clips"][clip]["source_frames"]
        first, last = entry.get("frames", [0, len(source_frames) - 1])
        rig.animation_data.action = bpy.data.actions[plan["clips"][clip]["action"]]
        entry["offset_x"] = round(offset_x, 4)
        entry["offset_y"] = offset_y
        if name not in airborne and name != "fall_on_back":
            continue
        floor_bounds = bottoms(entry["sheet"]) if name == "fall_on_back" else None
        offsets = []
        for index in range(first, last + 1):
            set_frame(source_frames[index])
            displacement = rig.matrix_world @ rig.pose.bones[hip].head - baseline
            x = -displacement.dot(right) * pixels_per_unit
            y = displacement.z * pixels_per_unit
            if name == "fall_on_back":
                y = max(0, y)
                y = min(y, ground - floor_bounds[index])
            offsets.append([round(x, 4), round(y, 4)])
        entry["frame_offsets"] = offsets
    character_path.write_text(json.dumps(character, indent=2) + "\n", encoding="utf-8")
    print("Don gameplay origins and baked root-motion corrections:", character_path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "render", "game-offsets"))
    parser.add_argument("--output", type=Path, default=ROOT / "temp" / "Don_mixamo")
    parser.add_argument("--size", type=int, default=346)
    parser.add_argument("--azimuth", type=float, default=-30)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if bpy.app.version[:2] != (4, 5):
        raise ValueError("Don sprites require Blender 4.5 LTS")
    args.output = args.output.resolve()
    {"prepare": prepare, "render": render, "game-offsets": game_offsets}[args.stage](args)


if __name__ == "__main__":
    main()
