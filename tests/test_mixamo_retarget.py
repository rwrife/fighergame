"""Integration checks for the packed Bruiser Mixamo actions; run inside Blender."""

from pathlib import Path
import sys
import unittest

try:
    import bpy
except ModuleNotFoundError:
    bpy = None


ROOT = Path(__file__).resolve().parents[1]
LOCAL_INPUTS = (
    ROOT / "assets" / "animations" / "Bruiser_mixamo.blend",
    ROOT / "assets" / "animations" / "mixamo" / "punch.fbx",
)


@unittest.skipUnless(bpy, "Run with Blender 4.5 LTS")
@unittest.skipUnless(
    all(path.is_file() for path in LOCAL_INPUTS),
    "Download the local Mixamo clips and build Bruiser_mixamo.blend first",
)
class MixamoRetargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bpy.ops.wm.open_mainfile(filepath=str(LOCAL_INPUTS[0]))
        rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        if len(rigs) != 1:
            raise AssertionError("Expected only the textured target rig, not the Mixamo source meshes")
        cls.rig = rigs[0]

    def test_all_clips_preserve_bone_lengths_and_texture(self):
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        self.assertEqual(len(meshes), 1)
        self.assertGreater(len(meshes[0].data.vertices), 100000)
        textures = [node.image for slot in meshes[0].material_slots
                    for node in slot.material.node_tree.nodes if node.type == "TEX_IMAGE"]
        self.assertTrue(textures)
        self.assertTrue(all(image.packed_file for image in textures))
        for name in ("idle", "jump", "punch"):
            self.rig.animation_data.action = bpy.data.actions[name]
            start, end = self.rig.animation_data.action.frame_range
            self.assertGreater(end, start)
            for frame in (start, (start + end) / 2, end):
                bpy.context.scene.frame_set(int(frame), subframe=frame % 1)
                for bone in self.rig.pose.bones:
                    self.assertAlmostEqual(bone.length, self.rig.data.bones[bone.name].length,
                                           places=5, msg=f"{name}/{bone.name}")

    def test_jump_keeps_vertical_motion_and_lands(self):
        self.rig.animation_data.action = bpy.data.actions["jump"]
        start, end = self.rig.animation_data.action.frame_range
        heights = []
        for frame in range(int(start), int(end) + 1):
            bpy.context.scene.frame_set(frame)
            heights.append((self.rig.matrix_world @ self.rig.pose.bones["mixamorig:Hips"].head).z)
        self.assertGreater(max(heights) - min(heights), .15)
        self.assertLess(abs(heights[-1] - heights[0]), .1)

    def test_punch_has_visible_extension_and_returns_to_guard(self):
        self.rig.animation_data.action = bpy.data.actions["punch"]
        start, end = self.rig.animation_data.action.frame_range
        positions = []
        for frame in range(int(start), int(end) + 1):
            bpy.context.scene.frame_set(frame)
            hand = self.rig.matrix_world @ self.rig.pose.bones["mixamorig:LeftHand"].head
            positions.append(hand.copy())
        self.assertGreater(max(point.x for point in positions) - positions[0].x, .15)
        self.assertLess((positions[-1] - positions[0]).length, .02)

    def test_transfer_reproduces_the_baked_character_facing(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from mixamo_demo import import_fbx, retarget

        probe = self.rig.copy()
        probe.data = self.rig.data.copy()
        bpy.context.scene.collection.objects.link(probe)
        source, objects = import_fbx(LOCAL_INPUTS[1])
        try:
            action = retarget(probe, source, "test_jab_transfer")
            self.rig.animation_data.action = bpy.data.actions["punch"]
            probe.animation_data.action = action
            for frame in (1, 16, 32):
                bpy.context.scene.frame_set(frame)
                for name in ("Hips", "LeftHand", "RightHand", "Head"):
                    original = self.rig.matrix_world @ self.rig.pose.bones["mixamorig:" + name].head
                    transferred = probe.matrix_world @ probe.pose.bones["mixamorig:" + name].head
                    self.assertLess((original - transferred).length, 1e-5, name)
        finally:
            for obj in objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.objects.remove(probe, do_unlink=True)


if __name__ == "__main__":
    unittest.main(argv=[__file__])
