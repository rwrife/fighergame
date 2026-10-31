import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw


SPEC = importlib.util.spec_from_file_location(
    "level_pipeline", Path(__file__).resolve().parents[1] / "scripts" / "level_pipeline.py"
)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class LevelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        reference = self.root / "reference.png"
        Image.new("RGB", (12, 8), (90, 30, 60)).save(reference)
        self.job = self.root / "stage"
        self.manifest = pipeline.initialize(reference, reference, self.job)
        self.manifest.update(viewport=[40, 40], world_width=120, camera_travel=40)
        self.sky_color = (90, 30, 60)
        self.art_color = (60, 100, 20)
        pipeline.write_json(self.job / "palette.json", {
            "colors": [list(self.sky_color), list(self.art_color)],
        })
        Image.new("RGB", (40, 40), self.sky_color).save(self.job / "sky.png")
        for layer in self.manifest["layers"]:
            image = Image.new("RGBA", (120, 40))
            draw = ImageDraw.Draw(image)
            if layer["id"] == "ground":
                draw.rectangle((0, 34, 119, 39), fill=(*self.art_color, 255))
            else:
                draw.rectangle((50, 15, 65, 29), fill=(*self.art_color, 255))
            image.save(self.job / layer["image"])
        self.save_manifest()

    def save_manifest(self):
        pipeline.write_json(self.job / "level.json", self.manifest)

    def test_init_is_local_resumable_source_not_overwritten(self):
        source = self.job / "source"
        provenance = pipeline.read_json(source / "provenance.json")
        self.assertEqual(len(provenance["inputs"]["reference"]["sha256"]), 64)
        self.assertTrue((source / ".gdignore").exists())
        self.assertEqual(provenance["generation"], [])
        self.assertFalse(any(self.manifest["review"].values()))
        prompts = pipeline.read_json(self.job / "prompts.json")["prompts"]
        self.assertIn("solid blue sky", prompts["geometry"])
        with self.assertRaises(FileExistsError):
            pipeline.initialize(source / "reference.png", source / "reference.png", self.job)

    def test_technical_validation_does_not_approve_release(self):
        pipeline.validate(self.job)
        with self.assertRaisesRegex(ValueError, "Release blocked"):
            pipeline.validate(self.job, release=True)
        self.manifest["review"] = dict.fromkeys(pipeline.REVIEWS, True)
        self.save_manifest()
        pipeline.validate(self.job, release=True)

    def test_fixed_sky_and_moving_scenery_at_camera_endpoints(self):
        manifest, images = pipeline.validate(self.job)
        left = pipeline.compose(manifest, images, 0)
        right = pipeline.compose(manifest, images, 40)
        for x in range(40):
            self.assertEqual(left.getpixel((x, 0)), (*self.sky_color, 255))
            self.assertEqual(right.getpixel((x, 0)), (*self.sky_color, 255))
            self.assertEqual(left.getpixel((x, 34)), (*self.art_color, 255))
            self.assertEqual(right.getpixel((x, 34)), (*self.art_color, 255))
        self.assertNotEqual(left.crop((0, 15, 40, 30)).tobytes(),
                            right.crop((0, 15, 40, 30)).tobytes())
        output = self.root / "preview.png"
        pipeline.preview(self.job, output)
        with Image.open(output) as image:
            self.assertEqual(image.size, (120, 40))

    def test_rejects_moving_sky_and_insufficient_parallax_overscan(self):
        self.manifest["sky"]["factor"] = .01
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "screen-locked"):
            pipeline.validate(self.job)
        self.manifest["sky"]["factor"] = 0
        self.manifest["camera_travel"] = 80
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "too narrow"):
            pipeline.validate(self.job)

    def test_rejects_floor_holes_slopes_and_scenery_in_lane(self):
        for name, position, color, message in (
            ("ground.png", (0, 34), (0, 0, 0, 0), "no holes"),
            ("ground.png", (0, 33), (*self.art_color, 255), "straight"),
            ("foreground.png", (0, 34), (*self.art_color, 255), "intrudes"),
        ):
            with self.subTest(name=name, position=position):
                path = self.job / name
                with Image.open(path) as source:
                    original = source.convert("RGBA")
                modified = original.copy()
                modified.putpixel(position, color)
                modified.save(path)
                with self.assertRaisesRegex(ValueError, message):
                    pipeline.validate(self.job)
                original.save(path)

    def test_rejects_palette_drift_alpha_fringes_and_transparent_sky(self):
        path = self.job / "sky.png"
        for pixel, message in (
            ((255, 0, 0, 255), "outside"),
            ((*self.sky_color, 128), "binary"),
            ((0, 0, 0, 0), "fully opaque"),
        ):
            image = Image.new("RGBA", (40, 40), (*self.sky_color, 255))
            image.putpixel((0, 0), pixel)
            image.save(path)
            with self.assertRaisesRegex(ValueError, message):
                pipeline.validate(self.job)

    def test_prop_is_reusable_but_cannot_cover_lane_or_add_collision(self):
        Image.new("RGBA", (4, 4), (*self.art_color, 255)).save(self.job / "rock.png")
        prop = {
            "id": "rock_01", "image": "rock.png", "layer": "foreground",
            "size": [4, 4], "position": [30, 30], "pivot": [2, 3], "collision": False,
        }
        self.manifest["props"] = [prop]
        self.save_manifest()
        pipeline.validate(self.job)
        prop["position"][1] = 31
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "intrudes"):
            pipeline.validate(self.job)
        prop["position"][1] = 30
        prop["collision"] = True
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "disable collision"):
            pipeline.validate(self.job)

    def test_rejects_asset_traversal_and_preview_overwrite(self):
        with self.assertRaisesRegex(ValueError, "overwrite"):
            pipeline.preview(self.job, self.job / "ground.png")
        with self.assertRaisesRegex(ValueError, "source provenance"):
            pipeline.preview(self.job, self.job / "source" / "reference.png")
        self.manifest["sky"]["image"] = str(self.root / "reference.png")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "escapes"):
            pipeline.validate(self.job)

    def test_rejects_nonfinite_parameters_and_invalid_reviews(self):
        self.manifest["camera_travel"] = float("nan")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "between"):
            pipeline.validate(self.job)
        self.manifest["camera_travel"] = 40
        self.manifest["review"]["style"] = "approved"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "booleans"):
            pipeline.validate(self.job)

    def test_workflow_dependencies_are_defined_and_acyclic(self):
        steps = pipeline.read_json(pipeline.WORKFLOW)["steps"]
        seen = set()
        for step in steps:
            self.assertNotIn(step["id"], seen)
            self.assertTrue(set(step["needs"]).issubset(seen))
            seen.add(step["id"])


if __name__ == "__main__":
    unittest.main()
