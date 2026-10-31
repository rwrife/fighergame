import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image


SPEC = importlib.util.spec_from_file_location(
    "spritesheet", Path(__file__).resolve().parents[1] / "scripts" / "spritesheet.py"
)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class SheetTests(unittest.TestCase):
    def test_palette_transparency_order_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frames = []
            for index, color in enumerate(((180, 50, 20), (20, 50, 180))):
                frame = Image.new("RGB", (16, 16), (255, 0, 255))
                for y in range(4, 12):
                    for x in range(4, 12):
                        frame.putpixel((x, y), color)
                name = f"{index:04d}.png"
                frame.save(root / name)
                frames.append(name)
            (root / "manifest.json").write_text(json.dumps({"fps": 12, "frames": frames}))
            target = root / "sheet.png"
            pipeline.compile_sheet(root, target, 32, (255, 0, 255), 8)
            with Image.open(target) as sheet:
                self.assertEqual(sheet.size, (32, 16))
                self.assertLessEqual(len(sheet.getcolors()), 32)
                rgba = sheet.convert("RGBA")
                self.assertEqual(rgba.getpixel((0, 0))[3], 0)
                self.assertEqual(rgba.getpixel((8, 8)), (180, 50, 20, 255))
                self.assertEqual(rgba.getpixel((24, 8)), (20, 50, 180, 255))
            metadata = json.loads(target.with_suffix(".json").read_text())
            self.assertEqual(metadata["fps"], 12)
            self.assertEqual(metadata["frame_count"], 2)
            self.assertEqual(metadata["frames"][1]["x"], 16)

    def test_rejects_opaque_and_empty_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(json.dumps({"fps": 12, "frames": ["0.png"]}))
            Image.new("RGB", (8, 8), "magenta").save(root / "0.png")
            with self.assertRaisesRegex(ValueError, "no transparent"):
                pipeline.compile_sheet(root, root / "out.png", 32, None, 8)
            with self.assertRaisesRegex(ValueError, "entire frame"):
                pipeline.compile_sheet(root, root / "out.png", 32, (255, 0, 255), 8)

    def test_rejects_bad_palette(self):
        with self.assertRaises(ValueError):
            pipeline.compile_sheet(Path("."), Path("out.png"), 257, None, 8)

    def test_many_source_colors_stay_within_shared_palette_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = []
            for index in range(3):
                frame = Image.new("RGBA", (32, 32))
                frame.putdata([
                    ((x * 11 + index * 19) % 256, (x * 23) % 256, (x * 37) % 256,
                     0 if x % 32 < 4 or x % 32 >= 28 else 255)
                    for x in range(1024)
                ])
                name = f"{index}.png"
                frame.save(root / name)
                names.append(name)
            (root / "manifest.json").write_text(json.dumps({"fps": 12, "frames": names}))
            target = root / "sheet.png"
            pipeline.compile_sheet(root, target, 32, None, 8, size=16)
            with Image.open(target) as sheet:
                self.assertEqual(sheet.size, (48, 16))
                self.assertLessEqual(len(sheet.getcolors(256)), 32)
                self.assertEqual(sheet.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_resize_cannot_silently_remove_transparency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame = Image.new("RGBA", (32, 32), (180, 50, 20, 255))
            for y in range(32):
                frame.putpixel((0, y), (0, 0, 0, 0))
            frame.save(root / "0.png")
            (root / "manifest.json").write_text(json.dumps({"fps": 12, "frames": ["0.png"]}))
            with self.assertRaisesRegex(ValueError, "no transparent"):
                pipeline.compile_sheet(root, root / "out.png", 32, None, 8, size=16)

    def test_cache_reuse_does_not_require_api_permission(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            target = cache / "Bruiser_base.fbx"
            target.write_bytes(b"cached")
            args = argparse.Namespace(cache=cache, character="Bruiser")
            asyncio.run(pipeline.generate_base(args))
            self.assertEqual(target.read_bytes(), b"cached")

    def test_uncached_generation_requires_explicit_permission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tpose = root / "tpose.png"
            Image.new("RGB", (8, 8)).save(tpose)
            args = argparse.Namespace(
                cache=root, character="Bruiser", allow_paid_api=False, tpose=tpose
            )
            with self.assertRaisesRegex(RuntimeError, "allow-paid-api"):
                asyncio.run(pipeline.generate_base(args))

    def test_uncached_generation_requires_t_pose_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = argparse.Namespace(
                cache=root, character="Bruiser", allow_paid_api=True,
                tpose=root / "missing.png",
            )
            with self.assertRaisesRegex(ValueError, "T-pose"):
                asyncio.run(pipeline.generate_base(args))

    def test_silhouette_mask_removes_shadow_and_backdrop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            render = Image.new("RGB", (16, 16), (255, 255, 255))
            for y in range(4, 12):
                for x in range(6, 10):
                    render.putpixel((x, y), (180, 50, 20))
            for x in range(2, 14):
                render.putpixel((x, 13), (90, 90, 120))  # floor shadow
            render.save(root / "0000.png")
            (root / "manifest.json").write_text(json.dumps({"fps": 12, "frames": ["0000.png"]}))
            capture = root / "capture"
            capture.mkdir()
            depth = Image.new("RGBA", (16, 16))
            for y in range(4, 12):
                for x in range(6, 10):
                    depth.putpixel((x, y), (200, 200, 200, 255))
            depth.save(capture / "0000_depth.png")
            target = root / "sheet.png"
            pipeline.compile_sheet(root, target, 32, "auto", 40, capture=capture, pad=1)
            with Image.open(target) as sheet:
                rgba = sheet.convert("RGBA")
                self.assertEqual(rgba.getpixel((8, 8)), (180, 50, 20, 255))
                self.assertEqual(rgba.getpixel((3, 13))[3], 0)
                self.assertEqual(rgba.getpixel((0, 0))[3], 0)

    def test_pose_has_colored_joints(self):
        names = [
            "neck", "nose", "right_shoulder", "right_elbow", "right_wrist",
            "left_shoulder", "left_elbow", "left_wrist", "right_hip",
            "right_knee", "right_ankle", "left_hip", "left_knee", "left_ankle",
        ]
        joints = {name: [5 + index * 3, 5 + index * 3] for index, name in enumerate(names)}
        pose = pipeline.draw_pose(joints, 64)
        self.assertIsNotNone(pose.getbbox())
        self.assertGreater(len(pose.getcolors()), 2)

    def test_placeholder_substitution_keeps_integer_seed(self):
        value = {"inputs": {"seed": "__SEED__", "text": "__PROMPT__"}}
        result = pipeline.substitute(value, {"__SEED__": 42, "__PROMPT__": "sprite"})
        self.assertEqual(result["inputs"]["seed"], 42)
        self.assertEqual(result["inputs"]["text"], "sprite")

    def test_rejects_non_api_workflow(self):
        with self.assertRaisesRegex(ValueError, "class_type"):
            pipeline.validate_workflow({"nodes": []}, "42")


if __name__ == "__main__":
    unittest.main()
