import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("level_derive", SCRIPTS / "level_derive.py")
derive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(derive)
pipeline = derive.pipeline


def synthetic_reference(path):
    """Sunset sky, an inked horizon, a distant hill, a green field, a rock and a dirt lane."""
    image = Image.new("RGB", (1000, 400))
    draw = ImageDraw.Draw(image)
    for row in range(150):
        t = row / 149
        draw.line((0, row, 999, row), fill=(int(120 + 130 * t), int(60 + 100 * t), int(170 - 120 * t)))
    draw.polygon([(0, 150), (0, 120), (150, 110), (300, 150)], fill=(40, 90, 50))
    draw.rectangle((0, 151, 999, 299), fill=(60, 140, 40))
    draw.line((0, 150, 999, 150), fill=(20, 15, 25), width=2)
    draw.rectangle((0, 300, 999, 399), fill=(150, 100, 60))
    draw.ellipse((500, 200, 560, 240), fill=(90, 70, 110), outline=(20, 15, 25), width=3)
    image.save(path)


RECIPE = {
    "recipe_version": 1,
    "lane_anchor_y": 300,
    "camera_travel": 300,
    "sky": {"land_hue": [40, 170], "land_value_max": 0.8, "ink_value_max": 0.3,
            "halo_passes": 1, "margin": 2, "blur": 2},
    "far_bands": [{"x": [0, 300], "crest": [[0, 150], [300, 150]]}],
    "lane_patches": [],
    "props": {
        "cut": {"ink_value_max": 0.3, "opening": 1},
        "harvest": [{"id": "rock", "box": [490, 190, 570, 250]}],
        "tufts": [{"id": "tuft", "size": [24, 16], "seed": 5}],
    },
    "foreground": [{"prop": "tuft", "x": 10, "base": 543}],
    "placements": [{"prop": "rock", "layer": "midground", "x": 100, "base": 543}],
    "palette": {"sky": 4, "scenery": 4, "ground": 2, "reserved": []},
    "layer_plan": {"sky": ["sunset"], "far_background": ["hill"], "midground": ["field"],
                   "ground": ["lane"], "props": ["rock", "tuft"]},
}


class PatchLaneTests(unittest.TestCase):
    def test_donor_is_tone_matched_to_surrounding_dirt(self):
        rgb = np.full((40, 200, 3), 100, dtype=np.uint8)
        rgb[:, 120:] = 160  # lighter donor region
        rgb[15:25, 45:55] = (0, 200, 0)  # intrusion, inside the unfeathered core
        patched = derive.patch_lane(rgb, [{"rect": [30, 5, 70, 35], "dx": 100}])
        interior = patched[15:25, 45:55].astype(int)
        self.assertLessEqual(np.abs(interior - 100).max(), 2)

    def test_rejects_donor_outside_reference(self):
        rgb = np.zeros((20, 50, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "outside"):
            derive.patch_lane(rgb, [{"rect": [10, 0, 30, 20], "dx": 30}])


class SegmentationTests(unittest.TestCase):
    def test_sky_matte_keeps_enclosed_glow_as_land(self):
        rgb = np.zeros((60, 60, 3), dtype=np.uint8)
        rgb[:30] = (230, 140, 60)
        rgb[30:] = (60, 140, 40)
        rgb[29:31] = (20, 15, 25)
        rgb[40:45, 20:25] = (230, 140, 60)  # glow pocket enclosed by land
        sky = derive.sky_matte(rgb, RECIPE["sky"])
        self.assertTrue(sky[:28].all())
        self.assertFalse(sky[32:].any())

    def test_cut_prop_requires_closed_outline(self):
        image = Image.new("RGB", (60, 60), (60, 140, 40))
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 50, 50), fill=(90, 70, 110), outline=(20, 15, 25), width=3)
        settings = {"ink_value_max": 0.3, "opening": 1}
        cut = derive.cut_prop(np.asarray(image), [0, 0, 60, 60], settings)
        self.assertEqual(cut[cut.shape[0] // 2, cut.shape[1] // 2, 3], 255)
        self.assertEqual(cut[0, 0, 3], 0)
        blank = np.asarray(Image.new("RGB", (60, 60), (60, 140, 40)))
        with self.assertRaisesRegex(ValueError, "not closed"):
            derive.cut_prop(blank, [0, 0, 60, 60], settings)

    def test_palette_budget_and_quantize_stay_in_palette(self):
        rng = np.random.default_rng(1)
        pixels = rng.integers(0, 256, (30, 30, 3), dtype=np.uint8)
        palette = derive.build_palette({"sky": pixels}, {"sky": 8}, [0, 0, 0], 31)
        self.assertLessEqual(len(palette), 9)
        used = {tuple(color) for color in derive.quantize(pixels, palette).reshape(-1, 3)}
        self.assertTrue(used <= {tuple(color) for color in palette})
        with self.assertRaisesRegex(ValueError, "budget"):
            derive.build_palette({"sky": pixels}, {"sky": 8}, [0, 0, 0], 4)


class DeriveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        reference = root / "reference.png"
        synthetic_reference(reference)
        self.job = root / "level"
        pipeline.initialize(reference, reference, self.job)
        self.write_recipe(RECIPE)

    def write_recipe(self, recipe):
        (self.job / "source" / "derive_recipe.json").write_text(json.dumps(recipe), encoding="utf-8")

    def snapshot(self):
        return {path.relative_to(self.job).as_posix(): path.read_bytes()
                for path in sorted(self.job.rglob("*")) if path.is_file()}

    def test_derive_produces_valid_deterministic_draft(self):
        manifest = derive.derive(self.job)
        self.assertEqual(manifest["world_width"], 1813)
        self.assertFalse(any(manifest["review"].values()))
        _, images = pipeline.validate(self.job)
        ground = np.asarray(images["ground"])
        self.assertTrue((ground[544:, :, 3] == 255).all())
        self.assertFalse(ground[:544, :, 3].any())
        palette = pipeline.read_json(self.job / "palette.json")["colors"]
        self.assertLessEqual(len(palette), 31)
        self.assertEqual([prop["id"] for prop in manifest["props"]], ["rock_1"])
        provenance = pipeline.read_json(self.job / "source" / "provenance.json")
        self.assertEqual(provenance["generation"][-1]["remote_services"], [])
        first = self.snapshot()
        derive.derive(self.job)
        self.assertEqual(first, self.snapshot())

    def test_rejects_duplicate_layer_assignment_and_narrow_world(self):
        recipe = json.loads(json.dumps(RECIPE))
        recipe["layer_plan"]["midground"].append("hill")
        self.write_recipe(recipe)
        with self.assertRaisesRegex(ValueError, "both"):
            derive.derive(self.job)
        recipe = json.loads(json.dumps(RECIPE))
        recipe["camera_travel"] = 900
        self.write_recipe(recipe)
        with self.assertRaisesRegex(ValueError, "too narrow"):
            derive.derive(self.job)


if __name__ == "__main__":
    unittest.main()
