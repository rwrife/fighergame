import json
from pathlib import Path
import unittest

from PIL import Image


SHEETS = Path(__file__).resolve().parents[1] / "assets" / "spritesheets"


class GeneratedMixamoTests(unittest.TestCase):
    def test_moves_have_shared_palette_and_correct_one_shot_metadata(self):
        palettes = []
        for name, count in (("idle", 40), ("jump", 12), ("punch", 7)):
            metadata = json.loads((SHEETS / f"Bruiser_{name}_mixamo_sheet.json").read_text())
            self.assertEqual(metadata["fps"], 12 if name == "idle" else 6)
            self.assertEqual(metadata["frame_count"], count)
            self.assertEqual(metadata["loop"], name == "idle")
            with Image.open(SHEETS / metadata["image"]) as sheet:
                self.assertEqual(sheet.size, (count * 346, 346))
                self.assertLessEqual(len(sheet.getcolors(256)), 32)
                palettes.append(sheet.getpalette())
                rgba = sheet.convert("RGBA")
                for index in range(count):
                    frame = rgba.crop((index * 346, 0, (index + 1) * 346, 346))
                    self.assertIsNotNone(frame.getbbox())
                    for corner in ((0, 0), (345, 0), (0, 345), (345, 345)):
                        self.assertEqual(frame.getpixel(corner)[3], 0)
        self.assertEqual(palettes[0], palettes[1])
        self.assertEqual(palettes[0], palettes[2])

    def test_punch_comparison_has_identical_timing_and_output_size(self):
        ai = json.loads((SHEETS / "Bruiser_punch_mixamo_ai_sheet.json").read_text())
        shader = json.loads((SHEETS / "Bruiser_punch_mixamo_comparison_sheet.json").read_text())
        for key in ("fps", "frame_count", "frame_width", "frame_height", "frames", "loop"):
            self.assertEqual(ai[key], shader[key], key)
        self.assertTrue(ai["archived"])
        self.assertTrue(shader["archived"])
        with Image.open(SHEETS / ai["image"]) as image:
            self.assertLessEqual(len(image.getcolors(256)), 32)
            rgba = image.convert("RGBA")
            for index in range(ai["frame_count"]):
                frame = rgba.crop((index * 192, 0, (index + 1) * 192, 192))
                self.assertIsNotNone(frame.getbbox())
                for corner in ((0, 0), (191, 0), (0, 191), (191, 191)):
                    self.assertEqual(frame.getpixel(corner)[3], 0)


if __name__ == "__main__":
    unittest.main()
