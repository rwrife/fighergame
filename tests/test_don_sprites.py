"""Validate the delivered Don sheets without requiring raw licensed FBX files."""

import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "assets" / "spritesheets"
REQUIRED = {
    "standing_idle", "crouched_idle", "standing_punch", "crouched_punch",
    "standing_kick", "crouched_kick", "standing_block", "block_idle",
    "jump", "jump_punch", "jump_kick", "knocked_back_air", "fall_on_back",
    "heavy_punch", "heavy_kick",
}
LOOPS = {"standing_idle", "crouched_idle", "block_idle"}


class DonSpritesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheets = {}
        for path in DIRECTORY.glob("Don_*_sheet.json"):
            name = path.name.removeprefix("Don_").removesuffix("_sheet.json")
            cls.sheets[name] = json.loads(path.read_text(encoding="utf-8"))

    def frames(self, name):
        metadata = self.sheets[name]
        with Image.open(DIRECTORY / metadata["image"]) as image:
            image = image.convert("RGBA")
            return [
                image.crop((frame["x"], frame["y"],
                            frame["x"] + frame["width"], frame["y"] + frame["height"]))
                for frame in metadata["frames"]
            ]

    def test_complete_move_set_and_transitions(self):
        self.assertTrue(REQUIRED <= self.sheets.keys())
        self.assertTrue({
            "stand_to_crouch", "crouch_to_stand", "block_to_stand",
            "jump_to_punch", "punch_to_jump", "jump_to_kick", "kick_to_jump",
        } <= self.sheets.keys())
        self.assertIn("get_up", self.sheets)

    def test_get_up_starts_from_fall_end(self):
        self.assert_matching(self.frames("fall_on_back")[-1], self.frames("get_up")[0])

    def test_dimensions_timing_palette_and_every_frame(self):
        shared_palette = None
        for name, metadata in self.sheets.items():
            with self.subTest(name=name):
                self.assertEqual(metadata["fps"], 12 if name == "standing_idle" else 6)
                self.assertEqual(metadata["loop"], name in LOOPS)
                self.assertEqual(metadata["renderer"], "cel-shaded")
                self.assertEqual(metadata["frame_width"], 346)
                self.assertEqual(metadata["frame_height"], 346)
                self.assertEqual(metadata["frame_count"], len(metadata["frames"]))
                self.assertGreaterEqual(metadata["frame_count"], 2)
                with Image.open(DIRECTORY / metadata["image"]) as image:
                    self.assertEqual(image.mode, "P")
                    self.assertEqual(image.size, (346 * metadata["frame_count"], 346))
                    self.assertLessEqual(len(image.getcolors(256)), 32)
                    self.assertEqual(image.info["transparency"], 255)
                    if shared_palette is None:
                        shared_palette = image.getpalette()
                    self.assertEqual(image.getpalette(), shared_palette)
                for index, (frame, rectangle) in enumerate(zip(self.frames(name), metadata["frames"])):
                    self.assertEqual(rectangle, {"x": index * 346, "y": 0, "width": 346, "height": 346})
                    self.assertEqual(set(frame.getchannel("A").get_flattened_data()), {0, 255})
                    bounds = frame.getbbox()
                    self.assertIsNotNone(bounds)
                    self.assertGreaterEqual(min(bounds[:2]), 2)
                    self.assertLessEqual(max(bounds[2:]), 344)

    def assert_matching(self, first, second):
        self.assertIsNone(ImageChops.difference(
            first.getchannel("A"), second.getchannel("A"),
        ).getbbox())
        difference = ImageChops.difference(first, second)
        # Equivalent Blender poses can differ by a few quantization-boundary pixels.
        changed = sum(any(pixel) for pixel in difference.get_flattened_data())
        self.assertLessEqual(changed, 4)

    def test_grounded_entry_and_recovery_poses(self):
        standing = self.frames("standing_idle")[0]
        crouched = self.frames("crouched_idle")[0]
        for name in ("standing_punch", "standing_kick", "heavy_punch", "heavy_kick"):
            frames = self.frames(name)
            with self.subTest(name=name):
                self.assert_matching(frames[0], standing)
                self.assert_matching(frames[-1], standing)
        for name in ("crouched_punch", "crouched_kick"):
            frames = self.frames(name)
            self.assert_matching(frames[0], crouched)
            self.assert_matching(frames[-1], crouched)
        self.assert_matching(self.frames("stand_to_crouch")[0], standing)
        self.assert_matching(self.frames("stand_to_crouch")[-1], crouched)
        self.assert_matching(self.frames("standing_block")[-1], self.frames("block_idle")[0])

    def test_airborne_and_knockdown_endpoints(self):
        jump = self.frames("jump")
        standing = self.frames("standing_idle")[0]
        self.assert_matching(jump[0], standing)
        self.assert_matching(jump[-1], standing)
        for attack, entry, recovery in [
            ("jump_punch", "jump_to_punch", "punch_to_jump"),
            ("jump_kick", "jump_to_kick", "kick_to_jump"),
        ]:
            self.assert_matching(self.frames(entry)[-1], self.frames(attack)[0])
            self.assert_matching(self.frames(attack)[-1], self.frames(recovery)[0])
        self.assert_matching(self.frames("knocked_back_air")[-1], self.frames("fall_on_back")[0])
        fallen = self.frames("fall_on_back")[-1].getbbox()
        upright = standing.getbbox()
        self.assertLess(fallen[3] - fallen[1], (upright[3] - upright[1]) * .65)

    def test_reference_and_animation_source_provenance(self):
        provenance = json.loads((DIRECTORY / "Don_sources.json").read_text(encoding="utf-8"))
        reference = ROOT / "assets" / "references" / "Don_tpose.png"
        self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(), provenance["reference_sha256"])
        self.assertEqual(provenance["render_size"], 346)
        self.assertEqual(provenance["palette_colors"], 32)
        self.assertEqual(provenance["outline_px"], 0)
        self.assertEqual(provenance["camera"],
                         json.loads((DIRECTORY / "Don_mixamo_set.json").read_text())["camera"])
        for name in REQUIRED:
            self.assertTrue(provenance["clips"][name]["source_clips"])
            self.assertTrue(provenance["clips"][name]["adaptation"])
        for digest in provenance["sources"].values():
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
