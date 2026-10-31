"""Run in Blender 4.5: author and render Bruiser moves that have no Mixamo clip.

Poses are authored procedurally (analytic two-bone IK for limbs, aimed spine) on
the Mixamo-rigged Bruiser from assets/animations/Bruiser_mixamo.blend. These are
adaptations of the Mixamo skeleton, not Mixamo-sourced motion. They reuse the
camera of the Mixamo clip set so scale and ground alignment match.
"""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_frames import cel_shade

DEFAULTS = dict(
    hx=0, hz=-.03, pitch=0, lean=.1, twist=0, head=0,
    rfx=.07, rfz=0, rfp=0, lfx=-.07, lfz=0, lfp=0, kp=0,
    rhx=.5, rhy=.12, rhz=.25, lhx=.4, lhy=.1, lhz=.2,
)

STAND = {}
CROUCH = dict(hz=-.14, lean=.35, rfx=.1, lfx=-.1, rhx=.45, rhz=.1, lhx=.35, lhz=.05)
BLOCK = dict(hz=-.05, lean=.2, rhx=.35, rhy=.0, rhz=.55, lhx=.3, lhy=0, lhz=.5)
AIR = dict(hz=.08, lean=.15, rfx=.14, rfz=.14, lfx=-.02, lfz=.1,
           rhx=.4, rhy=.15, rhz=.3, lhx=.35, lhy=.1, lhz=.25)
KNOCK = dict(hx=-.04, hz=.08, pitch=-.45, lean=-.15, rfx=.2, rfz=.14, lfx=.12, lfz=.2,
             rhx=.2, rhy=.55, rhz=.55, lhx=.1, lhy=.6, lhz=.5, head=-.2)
LYING = dict(hx=-.2, hz=-.34, pitch=-1.5, lean=0, rfx=.3, rfz=.0, lfx=.22, lfz=.0, kp=3,
             rhx=.6, rhy=.35, rhz=-.15, lhx=.6, lhy=.35, lhz=-.15, head=0)


def mix(*parts, **overrides):
    merged = {}
    for part in parts:
        merged.update(part)
    merged.update(overrides)
    return merged


# Each clip: (loop, frame count, [(frame, pose overrides)]). Poses are blended
# between keys so transitions are baked into the sampled frames.
CLIPS = {
    "crouched_idle": (True, 4, [(0, CROUCH), (1, mix(CROUCH, hz=-.15, lean=.37)),
                                (2, CROUCH), (3, mix(CROUCH, hz=-.13, lean=.33))]),
    "stand_to_crouch": (False, 3, [(0, STAND), (1, mix(CROUCH, hz=-.08, lean=.22)), (2, CROUCH)]),
    "crouch_to_stand": (False, 3, [(0, CROUCH), (1, mix(CROUCH, hz=-.08, lean=.22)), (2, STAND)]),
    "crouched_punch": (False, 6, [
        (0, CROUCH), (1, mix(CROUCH, twist=-.35, rhx=.1, rhz=.1)),
        (2, mix(CROUCH, twist=.4, rhx=1.0, rhy=0, rhz=.1, lean=.4)),
        (3, mix(CROUCH, twist=.4, rhx=1.0, rhy=0, rhz=.1, lean=.4)),
        (4, mix(CROUCH, twist=.1, rhx=.6)), (5, CROUCH)]),
    "standing_kick": (False, 7, [
        (0, STAND), (1, mix(STAND, rfx=.18, rfz=.22, lean=0, hz=-.03)),
        (2, mix(STAND, rfx=.42, rfz=.3, lean=-.25, hx=-.03)),
        (3, mix(STAND, rfx=.42, rfz=.3, lean=-.25, hx=-.03)),
        (4, mix(STAND, rfx=.18, rfz=.22, lean=0)), (5, mix(STAND, rfx=.1, rfz=.04)), (6, STAND)]),
    "crouched_kick": (False, 6, [
        (0, CROUCH), (1, mix(CROUCH, rfx=.2, rfz=.08, lean=.3)),
        (2, mix(CROUCH, rfx=.46, rfz=.06, lean=.2, hx=-.03)),
        (3, mix(CROUCH, rfx=.46, rfz=.06, lean=.2, hx=-.03)),
        (4, mix(CROUCH, rfx=.2, rfz=.04)), (5, CROUCH)]),
    "standing_block": (False, 4, [(0, STAND), (1, mix(BLOCK, hz=-.04, rhz=.4, lhz=.35)),
                                  (2, BLOCK), (3, BLOCK)]),
    "block_idle": (True, 4, [(0, BLOCK), (1, mix(BLOCK, hz=-.06, lean=.22)),
                             (2, BLOCK), (3, mix(BLOCK, hz=-.04, lean=.18))]),
    "jump_punch": (False, 6, [
        (0, AIR), (1, mix(AIR, twist=-.3, rhx=.1, rhz=.2)),
        (2, mix(AIR, twist=.35, rhx=1.0, rhy=0, rhz=.15)),
        (3, mix(AIR, twist=.35, rhx=1.0, rhy=0, rhz=.15)),
        (4, mix(AIR, twist=.1, rhx=.6)), (5, AIR)]),
    "jump_kick": (False, 6, [
        (0, AIR), (1, mix(AIR, rfx=.16, rfz=.2, rhx=.3)),
        (2, mix(AIR, rfx=.42, rfz=.22, lean=-.1, lfx=-.08, lfz=.18)),
        (3, mix(AIR, rfx=.42, rfz=.22, lean=-.1, lfx=-.08, lfz=.18)),
        (4, mix(AIR, rfx=.16, rfz=.16)), (5, AIR)]),
    "knocked_back_air": (False, 4, [
        (0, mix(KNOCK, pitch=-.2, hz=.02)), (1, mix(KNOCK, pitch=-.4, hz=.08)),
        (2, mix(KNOCK, pitch=-.55, hz=.1)), (3, mix(KNOCK, pitch=-.65, hz=.08))]),
    "fall_on_back": (False, 6, [
        (0, mix(KNOCK, pitch=-.65, hz=.06)), (1, mix(KNOCK, pitch=-.95, hx=-.1, hz=-.12, rfz=.05, lfz=.08)),
        (2, mix(LYING, pitch=-1.3, hz=-.28, hx=-.16, kp=1, rfz=.04, lfz=.06)),
        (3, mix(LYING, pitch=-1.5, hz=-.33)),
        (4, mix(LYING, pitch=-1.45, hz=-.31, rfz=.02, lfz=.02)), (5, LYING)]),
    "hit_stun": (False, 3, [
        (0, mix(STAND, lean=-.05, hx=-.02, head=-.3, rhx=.3, rhz=.1, lhx=.2)),
        (1, mix(STAND, lean=-.22, hx=-.05, head=-.4, twist=-.15, rhx=.2, rhz=0, lhx=.1)),
        (2, mix(STAND, lean=-.12, hx=-.03, head=-.25))]),
}


def smooth(t):
    return t * t * (3 - 2 * t)


def sample(keys, frame):
    keys = sorted(keys, key=lambda key: key[0])
    if frame <= keys[0][0]:
        return {**DEFAULTS, **keys[0][1]}
    for (f0, p0), (f1, p1) in zip(keys, keys[1:]):
        if f0 <= frame <= f1:
            t = smooth((frame - f0) / (f1 - f0)) if f1 > f0 else 1
            a, b = {**DEFAULTS, **p0}, {**DEFAULTS, **p1}
            return {name: a[name] + (b[name] - a[name]) * t for name in DEFAULTS}
    return {**DEFAULTS, **keys[-1][1]}


class Poser:
    def __init__(self, rig):
        self.rig = rig
        self.bones = list(rig.data.bones)
        self.rest = {bone.name: bone.matrix_local.copy() for bone in self.bones}
        self.rest_dir = {bone.name: (bone.tail_local - bone.head_local).normalized()
                         for bone in self.bones}

    def n(self, name):
        return "Root" if name == "Root" else f"mixamorig:{name}"

    def head(self, poses, name):
        bone = self.rig.data.bones[self.n(name)]
        parent = bone.parent
        return (poses[parent.name] @ self.rest[parent.name].inverted() @ self.rest[bone.name]).translation

    def ik(self, hip, target, upper, lower, pole):
        d = (target - hip)
        reach = max(abs(upper - lower) + 1e-4, min(upper + lower - 1e-4, d.length))
        u = d.normalized()
        x = (upper ** 2 + reach ** 2 - lower ** 2) / (2 * upper * reach)
        h = upper * math.sqrt(max(0, 1 - x * x))
        side = pole - u * pole.dot(u)
        side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
        return hip + u * (upper * x) + side * h, hip + u * reach

    def apply(self, p):
        rig, rest = self.rig, self.rest
        poses, arcs = {}, {}
        up = Vector((0, 0, 1))
        y_axis = Vector((0, 1, 0))
        pending = {}
        names = {self.n(s): s for s in (
            "Hips", "Spine", "Spine1", "Spine2", "Head")}
        for bone in self.bones:
            name = bone.name
            if bone.parent is None:
                poses[name] = rest[name].copy()
                arcs[name] = Quaternion()
                continue
            parent = bone.parent.name
            short = name.split(":")[-1].removeprefix("mixamorig")
            arc = arcs[parent]
            position = (poses[parent] @ rest[parent].inverted() @ rest[name]).translation
            if short == "Hips":
                position = rest[name].translation + Vector((p["hx"], 0, p["hz"]))
                arc = Quaternion(y_axis, p["pitch"])
            elif short in ("Spine", "Spine1", "Spine2"):
                frac = {"Spine": 1 / 3, "Spine1": 2 / 3, "Spine2": 1}[short]
                arc = (Quaternion(up, p["twist"] * frac)
                       @ Quaternion(y_axis, p["pitch"] + p["lean"] * frac))
            elif short == "Head":
                arc = Quaternion(y_axis, p["head"]) @ arcs[parent]
            elif short in ("LeftFoot", "RightFoot"):
                arc = Quaternion(y_axis, p["lfp" if short[0] == "L" else "rfp"])
            elif short in ("LeftUpLeg", "RightUpLeg", "LeftArm", "RightArm"):
                side = short[0]
                leg = "UpLeg" in short
                lower_name = side_name = None
                lower_bone = bone.children[0]
                end_bone = lower_bone.children[0]
                upper_len = (lower_bone.head_local - bone.head_local).length
                lower_len = (end_bone.head_local - lower_bone.head_local).length
                anchor = position
                if leg:
                    key = "l" if side == "L" else "r"
                    foot_rest = end_bone.head_local
                    target = foot_rest + Vector((p[key + "fx"], 0, p[key + "fz"]))
                    pole = Vector((1, 0, p["kp"]))
                else:
                    sign = 1 if side == "L" else -1
                    key = "l" if side == "L" else "r"
                    target = anchor + Vector((p[key + "hx"], sign * p[key + "hy"],
                                              p[key + "hz"])) * (upper_len + lower_len)
                    pole = Vector((-.3, sign * .6, -1))
                knee, end = self.ik(anchor, target, upper_len, lower_len, pole)
                arc = self.rest_dir[name].rotation_difference((knee - anchor).normalized())
                arcs_lower = self.rest_dir[lower_bone.name].rotation_difference(
                    (end - knee).normalized())
                pending[lower_bone.name] = arcs_lower
                # Remember the lower bone's (rest-relative) absolute arc.
            arcs[name] = arc
            if name in pending:
                arcs[name] = pending.pop(name)
                arc = arcs[name]
            rotation = arc @ rest[name].to_quaternion()
            desired = Matrix.LocRotScale(position, rotation, Vector((1, 1, 1)))
            poses[name] = desired
            pose = rig.pose.bones[name]
            pose.rotation_mode = "QUATERNION"
            pose.matrix_basis = bone.convert_local_to_pose(
                desired, bone.matrix_local, invert=True,
                parent_matrix=poses[parent], parent_matrix_local=bone.parent.matrix_local)
        bpy.context.view_layer.update()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--clip-set", type=Path, required=True,
                        help="Existing Mixamo clip manifest whose camera is reused.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--character", default="Bruiser")
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--size", type=int, default=192)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if bpy.app.version[:2] != (4, 5):
        raise RuntimeError("Requires Blender 4.5 LTS.")
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    scene = bpy.context.scene
    rig = next(obj for obj in scene.objects if obj.type == "ARMATURE")
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    rig.animation_data_clear()
    reference = json.loads(args.clip_set.read_text(encoding="utf-8"))
    cam = reference["camera"]
    center = Vector(cam["center"])
    angle = math.radians(cam["azimuth"])
    direction = Vector((math.sin(angle), -math.cos(angle), 0))
    diameter = (Vector(cam["maximum"]) - Vector(cam["minimum"])).length
    camera_data = bpy.data.cameras.new("SharedCamera")
    camera = bpy.data.objects.new("SharedCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + direction * diameter * 3
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = cam["ortho_scale"]
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
    poser = Poser(rig)
    manifest = {
        "fps": args.fps, "size": args.size, "camera": cam,
        "source": "Authored pose adaptation of the Mixamo skeleton",
        "set_file": f"{args.character}_authored_set.json", "clips": {},
    }
    for name, (loop, count, keys) in CLIPS.items():
        if args.only and name not in args.only:
            continue
        directory = args.output / name
        directory.mkdir(parents=True, exist_ok=True)
        clip = {"fps": args.fps, "loop": loop, "frames": [], "renderer": "cel-shaded",
                "source": "authored", "sheet": f"{args.character}_{name}_sheet.png"}
        for index in range(count):
            poser.apply(sample(keys, index))
            filename = f"{index:04d}.png"
            scene.render.filepath = str((directory / filename).resolve())
            bpy.ops.render.render(write_still=True)
            clip["frames"].append(filename)
        (directory / "manifest.json").write_text(json.dumps(clip, indent=2), encoding="utf-8")
        manifest["clips"][name] = clip
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Authored clip set:", args.output)


if __name__ == "__main__":
    main()
