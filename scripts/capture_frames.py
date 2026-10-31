"""Run inside Blender 4.5 LTS to capture Z-depth and projected body joints."""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


# OpenPose COCO body order; face joints are omitted when the rig has no face bones.
BONES = {
    "nose": "Head", "neck": "Neck",
    "right_shoulder": "RightArm", "right_elbow": "RightForeArm",
    "right_wrist": "RightHand", "left_shoulder": "LeftArm",
    "left_elbow": "LeftForeArm", "left_wrist": "LeftHand",
    "right_hip": "RightUpLeg", "right_knee": "RightLeg",
    "right_ankle": "RightFoot", "left_hip": "LeftUpLeg",
    "left_knee": "LeftLeg", "left_ankle": "LeftFoot",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--animated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bone-map", type=Path)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--azimuth", type=float, default=0)
    parser.add_argument("--frames", type=int, default=0)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if bpy.app.version[:2] != (4, 5):
        raise RuntimeError("Capture currently requires Blender 4.5 LTS.")
    if args.fps <= 0 or args.size <= 0 or args.frames < 0:
        raise ValueError("FPS and size must be positive; frames must not be negative.")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(args.animated.resolve()))
    scene = bpy.context.scene
    rigs = [obj for obj in scene.objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Animated FBX must contain exactly one character armature.")
    rig = rigs[0]
    if not rig.animation_data or not rig.animation_data.action:
        raise ValueError("FBX has no active skeletal action. Export a baked animation.")
    start, end = rig.animation_data.action.frame_range
    if end <= start:
        raise ValueError("Animation must contain more than one pose.")
    source_fps = scene.render.fps / scene.render.fps_base
    # Inclusive source range, half-open sampling: do not duplicate the loop endpoint.
    if args.frames:
        # Evenly resample the whole loop to a fixed sprite frame count.
        count = args.frames
        frames = [start + index * (end - start) / count for index in range(count)]
    else:
        count = max(2, math.ceil((end - start) / source_fps * args.fps))
        frames = [start + index * source_fps / args.fps for index in range(count)]
    frames = [frame for frame in frames if frame < end]
    if len(frames) < 2:
        raise ValueError("Animation is too short for the requested FPS.")
    mapping = dict(BONES)
    if args.bone_map:
        custom = json.loads(args.bone_map.read_text(encoding="utf-8"))
        if set(custom) != set(BONES):
            raise ValueError(f"Bone map must define exactly these joints: {list(BONES)}")
        mapping = custom
    by_name = {}
    for bone in rig.pose.bones:
        simple = bone.name.split(":")[-1]
        if simple.startswith("mixamorig"):
            simple = simple[len("mixamorig"):]
        by_name[simple] = bone.name
    missing = [name for name in mapping.values()
               if name not in rig.pose.bones and name not in by_name]
    if missing:
        raise ValueError(f"Missing pose bones: {missing}. Supply --bone-map.")
    resolved = {joint: name if name in rig.pose.bones else by_name[name]
                for joint, name in mapping.items()}
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Animated FBX contains no skinned mesh.")

    def set_frame(frame):
        whole = math.floor(frame)
        scene.frame_set(whole, subframe=frame - whole)

    # Fit once across the whole motion, rather than changing scale each frame.
    minimum = Vector((math.inf,) * 3)
    maximum = Vector((-math.inf,) * 3)
    for frame in frames:
        set_frame(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        for obj in meshes:
            evaluated = obj.evaluated_get(graph)
            for corner in evaluated.bound_box:
                point = evaluated.matrix_world @ Vector(corner)
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], point[axis])
                    maximum[axis] = max(maximum[axis], point[axis])
    center = (minimum + maximum) / 2
    extent = maximum - minimum
    diameter = extent.length
    if diameter <= 0:
        raise ValueError("Character has degenerate bounds.")
    angle = math.radians(args.azimuth)
    direction = Vector((math.sin(angle), -math.cos(angle), 0))
    camera_data = bpy.data.cameras.new("CaptureCamera")
    camera = bpy.data.objects.new("CaptureCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + direction * diameter * 3
    camera.rotation_euler = (center-camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    horizontal = abs(math.cos(angle)) * extent.x + abs(math.sin(angle)) * extent.y
    camera_data.ortho_scale = max(extent.z, horizontal) * 1.15
    camera_data.clip_start = diameter * 0.01
    camera_data.clip_end = diameter * 10
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE_NEXT"
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
    scene.view_layers[0].use_pass_z = True
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    layers = tree.nodes.new("CompositorNodeRLayers")
    depth = tree.nodes.new("CompositorNodeMapRange")
    # Map only the character's own depth span so ControlNet sees strong relief.
    thickness = abs(math.sin(angle)) * extent.x + abs(math.cos(angle)) * extent.y
    near = diameter * 3 - thickness * 0.6
    far = diameter * 3 + thickness * 0.6
    depth.inputs["From Min"].default_value = near
    depth.inputs["From Max"].default_value = far
    depth.inputs["To Min"].default_value = 1
    depth.inputs["To Max"].default_value = 0
    depth.use_clamp = True
    alpha = tree.nodes.new("CompositorNodeSetAlpha")
    composite = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(layers.outputs["Depth"], depth.inputs["Value"])
    tree.links.new(depth.outputs["Value"], alpha.inputs["Image"])
    tree.links.new(layers.outputs["Alpha"], alpha.inputs["Alpha"])
    tree.links.new(alpha.outputs["Image"], composite.inputs["Image"])
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"fps": args.fps, "size": args.size, "frames": []}
    for index, frame in enumerate(frames):
        set_frame(frame)
        projected = {}
        for joint, name in resolved.items():
            bone = rig.pose.bones[name]
            point = rig.matrix_world @ bone.head
            screen = world_to_camera_view(scene, camera, point)
            projected[joint] = [screen.x * args.size, (1-screen.y) * args.size]
        depth_name = f"{index:04d}_depth.png"
        scene.render.filepath = str((args.output / depth_name).resolve())
        bpy.ops.render.render(write_still=True)
        manifest["frames"].append({
            "index": index, "source_frame": frame, "depth": depth_name,
            "pose": f"{index:04d}_pose.png", "joints": projected,
        })
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
