"""Run in Blender 4.5 to retarget Mixamo clips and render a shared-framing set."""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_frames import cel_shade


def import_fbx(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path.resolve()))
    objects = set(bpy.context.scene.objects) - before
    rigs = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(rigs) != 1 or not rigs[0].animation_data or not rigs[0].animation_data.action:
        raise ValueError(f"{path}: expected one rig with a baked action.")
    return rigs[0], objects


def bone_names(rig):
    names = {}
    for bone in rig.data.bones:
        simple = bone.name.split(":")[-1].removeprefix("mixamorig")
        if simple in names:
            raise ValueError(f"Ambiguous bone name: {simple}")
        names[simple] = bone.name
    return names


def retarget(target, source, name):
    scene = bpy.context.scene
    if not math.isclose(scene.render.fps / scene.render.fps_base, 30):
        raise ValueError(f"{name}: download the Mixamo clip at 30 FPS.")
    target_names, source_names = bone_names(target), bone_names(source)
    missing = set(target_names) - {"Root"} - set(source_names)
    if missing:
        raise ValueError(f"{name}: source is missing bones {sorted(missing)}")
    source_action = source.animation_data.action
    start, end = source_action.frame_range
    if end <= start:
        raise ValueError(f"{name}: source has no motion.")
    target.animation_data_clear()
    target.animation_data_create()
    action = bpy.data.actions.new(name)
    target.animation_data.action = action
    target_world = target.matrix_world
    source_world = source.matrix_world
    inverse_target = target_world.inverted()
    source_side = source_world.to_3x3() @ (
        source.data.bones[source_names["LeftArm"]].head_local
        - source.data.bones[source_names["RightArm"]].head_local
    )
    target_side = target_world.to_3x3() @ (
        target.data.bones[target_names["LeftArm"]].head_local
        - target.data.bones[target_names["RightArm"]].head_local
    )
    source_side.z = target_side.z = 0
    if source_side.length < 1e-8 or target_side.length < 1e-8:
        raise ValueError("Cannot determine character facing from the shoulder line.")
    alignment = source_side.normalized().rotation_difference(target_side.normalized())
    source_hip = source.data.bones[source_names["Hips"]]
    target_hip = target.data.bones[target_names["Hips"]]
    source_rest_hip = source_world @ source_hip.head_local
    target_rest_hip = target_world @ target_hip.head_local
    source_leg = sum(source.data.bones[source_names[part]].length
                     for part in ("LeftUpLeg", "LeftLeg")) * source_world.to_scale().x
    target_leg = sum(target.data.bones[target_names[part]].length
                     for part in ("LeftUpLeg", "LeftLeg")) * target_world.to_scale().x
    if source_leg <= 0 or target_leg <= 0:
        raise ValueError("Cannot retarget a degenerate leg chain.")
    scale = target_leg / source_leg
    bpy.context.scene.frame_set(int(start))
    initial_hip = source_world @ source.pose.bones[source_names["Hips"]].head
    horizontal = Vector((initial_hip.x - source_rest_hip.x,
                         initial_hip.y - source_rest_hip.y, 0))
    for index, frame in enumerate(range(math.ceil(start), math.floor(end) + 1), 1):
        bpy.context.scene.frame_set(frame)
        poses = {}
        for bone in target.data.bones:
            pose = target.pose.bones[bone.name]
            pose.rotation_mode = "QUATERNION"
            if bone.name == target_names.get("Root"):
                desired = bone.matrix_local.copy()
            else:
                simple = bone.name.split(":")[-1].removeprefix("mixamorig")
                source_bone = source.data.bones[source_names[simple]]
                source_pose = source.pose.bones[source_names[simple]]
                source_rest_rotation = (source_world @ source_bone.matrix_local).to_quaternion()
                source_pose_rotation = (source_world @ source_pose.matrix).to_quaternion()
                target_rest_rotation = (target_world @ bone.matrix_local).to_quaternion()
                rotation = (target_world.to_quaternion().inverted()
                            @ alignment @ source_pose_rotation @ source_rest_rotation.inverted()
                            @ alignment.inverted()
                            @ target_rest_rotation)
                if simple == "Hips":
                    displacement = source_world @ source_pose.head - source_rest_hip - horizontal
                    position = inverse_target @ (target_rest_hip + alignment @ (displacement * scale))
                else:
                    parent = bone.parent
                    position = (poses[parent.name] @ parent.matrix_local.inverted()
                                @ bone.matrix_local).translation
                desired = Matrix.LocRotScale(position, rotation, Vector((1, 1, 1)))
            poses[bone.name] = desired
            basis = bone.convert_local_to_pose(
                desired, bone.matrix_local, invert=True,
                parent_matrix=poses[bone.parent.name] if bone.parent else Matrix.Identity(4),
                parent_matrix_local=bone.parent.matrix_local if bone.parent else Matrix.Identity(4),
            )
            pose.matrix_basis = basis
            pose.keyframe_insert("location", frame=index, group=bone.name)
            pose.keyframe_insert("rotation_quaternion", frame=index, group=bone.name)
            pose.keyframe_insert("scale", frame=index, group=bone.name)
    action.use_fake_user = True
    return action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", type=Path, required=True)
    parser.add_argument("--idle", type=Path)
    parser.add_argument("--jump", type=Path)
    parser.add_argument("--punch", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--clip", action="append", default=[], help="NAME=PATH")
    parser.add_argument("--loop", action="append", default=[], help="clip names that loop")
    parser.add_argument("--shift", action="append", default=[], help="NAME=dx camera X shift")
    parser.add_argument("--camera", type=Path, help="reuse camera/framing from a manifest")
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--size", type=int, default=192)
    parser.add_argument("--azimuth", type=float, default=0)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if bpy.app.version[:2] != (4, 5):
        raise RuntimeError("Requires Blender 4.5 LTS.")
    if args.fps <= 0 or args.size < 16 or not math.isfinite(args.azimuth):
        raise ValueError("FPS must be positive, size at least 16, and azimuth finite.")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    target, character_objects = import_fbx(args.character)
    scene = bpy.context.scene
    meshes = [obj for obj in character_objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Textured character has no mesh.")
    actions = {}
    sources = {n: getattr(args, n) for n in ("idle", "jump", "punch") if getattr(args, n)}
    for item in args.clip:
        key, _, value = item.partition("=")
        sources[key] = Path(value)
    for name, path in sources.items():
        source, objects = import_fbx(path)
        actions[name] = retarget(target, source, name)
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    scene.render.fps = 30
    scene.render.fps_base = 1
    args.blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.blend.resolve()), compress=True)
    minimum = Vector((math.inf,) * 3)
    maximum = Vector((-math.inf,) * 3)
    samples = {}
    for name, action in actions.items():
        target.animation_data.action = action
        start, end = action.frame_range
        duration = (end - start + 1) / 30
        count = math.ceil(duration * args.fps)
        frames = [min(end, start + index * 30 / args.fps) for index in range(count)]
        # Include the recovery/landing endpoint for one-shot moves.
        if name not in args.loop and name != "idle":
            frames[-1] = end
        samples[name] = frames
        for frame in (frames if not args.camera else ()):
            scene.frame_set(math.floor(frame), subframe=frame % 1)
            graph = bpy.context.evaluated_depsgraph_get()
            for obj in meshes:
                evaluated = obj.evaluated_get(graph)
                for corner in evaluated.bound_box:
                    point = evaluated.matrix_world @ Vector(corner)
                    for axis in range(3):
                        minimum[axis] = min(minimum[axis], point[axis])
                        maximum[axis] = max(maximum[axis], point[axis])
    if args.camera:
        saved = json.loads(args.camera.read_text(encoding="utf-8"))["camera"]
        minimum, maximum = Vector(saved["minimum"]), Vector(saved["maximum"])
        args.azimuth = saved["azimuth"]
    extent = maximum - minimum
    diameter = extent.length
    if not math.isfinite(diameter) or diameter <= 0:
        raise ValueError("Invalid animated character bounds.")
    center = (minimum + maximum) / 2
    angle = math.radians(args.azimuth)
    direction = Vector((math.sin(angle), -math.cos(angle), 0))
    camera_data = bpy.data.cameras.new("SharedCamera")
    camera = bpy.data.objects.new("SharedCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + direction * diameter * 3
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = saved["ortho_scale"] if args.camera else max(
        extent.z, abs(math.cos(angle)) * extent.x + abs(math.sin(angle)) * extent.y
    ) * 1.15
    camera_data.clip_start, camera_data.clip_end = diameter * .01, diameter * 10
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 1
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.use_nodes = False
    cel_shade(meshes, direction)
    manifest = {
        "fps": args.fps, "size": args.size, "source": "Mixamo",
        "camera": {"center": list(center), "ortho_scale": camera_data.ortho_scale,
                   "azimuth": args.azimuth, "minimum": list(minimum),
                   "maximum": list(maximum)},
        "clips": {},
    }
    base_location = camera.location.copy()
    shifts = {k: float(v) for k, _, v in (s.partition("=") for s in args.shift)}
    for name, frames in samples.items():
        target.animation_data.action = actions[name]
        camera.location = base_location + Vector((shifts.get(name, 0), 0, 0))
        directory = args.output / name
        directory.mkdir(parents=True, exist_ok=True)
        clip = {"fps": args.fps, "loop": name == "idle" or name in args.loop, "frames": [],
                "renderer": "cel-shaded",
                "source_frames": frames}
        for index, frame in enumerate(frames):
            scene.frame_set(math.floor(frame), subframe=frame % 1)
            filename = f"{index:04d}.png"
            scene.render.filepath = str((directory / filename).resolve())
            bpy.ops.render.render(write_still=True)
            clip["frames"].append(filename)
        (directory / "manifest.json").write_text(json.dumps(clip, indent=2), encoding="utf-8")
        manifest["clips"][name] = clip
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Mixamo clip set:", args.output)


if __name__ == "__main__":
    main()
