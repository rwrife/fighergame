"""Run inside Blender 4.5 LTS to capture guides or deterministic cel-shaded sprites."""

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


def cel_shade(meshes, direction):
    """Preserve FBX base colors, replacing lighting with four normal-based bands."""
    materials = {slot.material for obj in meshes for slot in obj.material_slots}
    if None in materials or any(not obj.material_slots for obj in meshes):
        raise ValueError("Retro rendering requires a material on every mesh.")
    light = (direction + Vector((-direction.y, direction.x, 0)) * 0.5
             + Vector((0, 0, 1))).normalized()
    for material in materials:
        color = tuple(material.diffuse_color)
        material.use_nodes = True
        tree = material.node_tree
        principled = next((node for node in tree.nodes
                           if node.type == "BSDF_PRINCIPLED"), None)
        source = None
        if principled:
            base = principled.inputs["Base Color"]
            color = tuple(base.default_value)
            if base.is_linked:
                source = base.links[0].from_socket
        output = next((node for node in tree.nodes
                       if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
        if output is None:
            output = tree.nodes.new("ShaderNodeOutputMaterial")
        normal = tree.nodes.new("ShaderNodeNewGeometry")
        dot = tree.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        dot.inputs[1].default_value = light
        ramp = tree.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "CONSTANT"
        elements = ramp.color_ramp.elements
        elements.remove(elements[1])
        for index, (position, value) in enumerate(
                ((0, 0.60), (0.25, 0.78), (0.5, 0.93), (0.75, 1.0))):
            element = elements[0] if index == 0 else elements.new(position)
            element.position = position
            element.color = (value, value, value, 1)
        multiply = tree.nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1
        multiply.inputs[1].default_value = color
        vivid = tree.nodes.new("ShaderNodeHueSaturation")
        vivid.inputs["Saturation"].default_value = 1.10
        vivid.inputs["Value"].default_value = 1.10
        vivid.inputs["Color"].default_value = color
        if source:
            tree.links.new(source, vivid.inputs["Color"])
        tree.links.new(vivid.outputs["Color"], multiply.inputs[1])
        emission = tree.nodes.new("ShaderNodeEmission")
        tree.links.new(normal.outputs["Normal"], dot.inputs[0])
        tree.links.new(dot.outputs["Value"], ramp.inputs["Fac"])
        tree.links.new(ramp.outputs["Color"], multiply.inputs[2])
        tree.links.new(multiply.outputs["Color"], emission.inputs["Color"])
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--animated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bone-map", type=Path)
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--azimuth", type=float, default=0)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--mode", choices=("guides", "retro"), default="guides")
    parser.add_argument("--clip-set", type=Path)
    parser.add_argument("--clip-name", choices=("idle", "jump", "punch"))
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if bpy.app.version[:2] != (4, 5):
        raise RuntimeError("Capture currently requires Blender 4.5 LTS.")
    if (args.fps <= 0 or args.size <= 0 or args.frames < 0 or args.frames == 1
            or not math.isfinite(args.azimuth)):
        raise ValueError("FPS/size must be positive, azimuth finite, frames 0 or at least 2.")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    clip_set = None
    clip = None
    if args.clip_set:
        if not args.clip_name:
            raise ValueError("--clip-set requires --clip-name.")
        clip_set = json.loads(args.clip_set.read_text(encoding="utf-8"))
        clip = clip_set["clips"][args.clip_name]
        args.azimuth = clip_set["camera"]["azimuth"]
        args.fps = clip["fps"]
    if args.animated.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(args.animated.resolve()))
    else:
        bpy.ops.import_scene.fbx(filepath=str(args.animated.resolve()))
    scene = bpy.context.scene
    rigs = [obj for obj in scene.objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Animated FBX must contain exactly one character armature.")
    rig = rigs[0]
    if clip:
        if not rig.animation_data or args.clip_name not in bpy.data.actions:
            raise ValueError(f"Character has no baked {args.clip_name} action.")
        rig.animation_data.action = bpy.data.actions[args.clip_name]
    if not rig.animation_data or not rig.animation_data.action:
        raise ValueError("FBX has no active skeletal action. Export a baked animation.")
    start, end = rig.animation_data.action.frame_range
    if end <= start:
        raise ValueError("Animation must contain more than one pose.")
    source_fps = scene.render.fps / scene.render.fps_base
    # Inclusive source range, half-open sampling: do not duplicate the loop endpoint.
    if clip:
        frames = clip["source_frames"]
    elif args.frames:
        # Evenly resample the whole loop to a fixed sprite frame count.
        count = args.frames
        frames = [start + index * (end - start) / count for index in range(count)]
    else:
        count = max(2, math.ceil((end - start) / source_fps * args.fps))
        frames = [start + index * source_fps / args.fps for index in range(count)]
    if not clip:
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
    if missing and args.mode == "guides":
        raise ValueError(f"Missing pose bones: {missing}. Supply --bone-map.")
    resolved = {joint: name if name in rig.pose.bones else by_name[name]
                for joint, name in mapping.items()} if args.mode == "guides" else {}
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
    if clip_set:
        minimum = Vector(clip_set["camera"]["minimum"])
        maximum = Vector(clip_set["camera"]["maximum"])
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
    if args.mode == "retro":
        cel_shade(meshes, direction)
        scene.use_nodes = False
        scene.eevee.taa_render_samples = 1
        args.output.mkdir(parents=True, exist_ok=True)
        manifest = {"fps": args.fps, "size": args.size, "renderer": "cel-shaded", "frames": [],
                    "loop": clip["loop"] if clip else True}
        for index, frame in enumerate(frames):
            set_frame(frame)
            name = f"{index:04d}.png"
            scene.render.filepath = str((args.output / name).resolve())
            bpy.ops.render.render(write_still=True)
            manifest["frames"].append(name)
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return
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
    manifest = {"fps": args.fps, "size": args.size, "frames": [],
                "loop": clip["loop"] if clip else True}
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
