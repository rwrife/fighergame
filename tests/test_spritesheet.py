import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image


SPEC = importlib.util.spec_from_file_location(
    "spritesheet", Path(__file__).resolve().parents[1] / "scripts" / "spritesheet.py"
)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class SheetTests(unittest.TestCase):
    def test_render_and_run_use_only_cel_shading_at_eight_fps(self):
        for stage in ("render", "run"):
            with patch.object(sys, "argv", ["spritesheet.py", stage]), \
                    patch.object(pipeline, "retro") as shader, \
                    patch.object(pipeline, "render_ai") as ai, \
                    patch.object(pipeline, "generate_tpose", new_callable=AsyncMock), \
                    patch.object(pipeline, "generate_base", new_callable=AsyncMock), \
                    patch.object(pipeline, "animate", new_callable=AsyncMock):
                pipeline.main()
                shader.assert_called_once()
                self.assertEqual(shader.call_args.args[0].fps, 8)
                self.assertTrue(shader.call_args.args[0].work.name.endswith("_retro"))
                ai.assert_not_called()

    def test_new_generation_requests_and_verifies_twenty_thousand_faces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "tpose.png"
            Image.new("RGB", (8, 8)).save(reference)
            args = argparse.Namespace(cache=root, character="Bruiser", tpose=reference)
            client = argparse.Namespace(
                image_to_model=AsyncMock(return_value="generated"),
                convert_model=AsyncMock(return_value="converted"),
            )

            async def fake_session(_args, work):
                state = {}

                async def task(stage, create):
                    result = await create()
                    state[stage] = result
                    return result

                async def fetch(_result, target, _suffix):
                    target.write_bytes(b"verified-mesh")

                return await work(client, task, fetch, state)

            with patch.object(pipeline, "require_paid_api"), \
                    patch.object(pipeline, "tripo_session", side_effect=fake_session), \
                    patch.object(pipeline, "blender_path", return_value="blender"), \
                    patch.object(pipeline.subprocess, "run") as verify:
                asyncio.run(pipeline.generate_base(args))
            client.image_to_model.assert_awaited_once_with(
                image=str(reference), face_limit=20000,
            )
            client.convert_model.assert_awaited_once_with(
                "generated", "FBX", face_limit=20000,
            )
            command = verify.call_args.args[0]
            self.assertEqual(command[command.index("--max-faces") + 1], "20000")
            self.assertTrue(verify.call_args.kwargs["check"])
            self.assertEqual((root / "Bruiser_base.fbx").read_bytes(), b"verified-mesh")
            self.assertFalse((root / "Bruiser_base_pending.fbx").exists())

    def test_locked_palette_is_reused_and_one_shot_flag_survives(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame = Image.new("RGBA", (12, 12))
            pipeline.ImageDraw.Draw(frame).rectangle((3, 3, 8, 8), fill=(200, 45, 25, 255))
            frame.save(root / "0.png")
            pipeline.write_json(root / "manifest.json", {
                "fps": 12, "loop": False, "frames": ["0.png"],
            })
            palette = [(180, 30, 20), (30, 40, 150), (20, 16, 28)]
            target = root / "sheet.png"
            pipeline.compile_sheet(root, target, 4, None, 0, shared_palette=palette)
            with Image.open(target) as sheet:
                self.assertEqual(sheet.getpalette()[:9], [value for rgb in palette for value in rgb])
                self.assertEqual(sheet.convert("RGBA").getpixel((6, 6)), (180, 30, 20, 255))
            self.assertFalse(json.loads(target.with_suffix(".json").read_text())["loop"])
            with self.assertRaisesRegex(ValueError, "Shared palette"):
                pipeline.compile_sheet(root, target, 4, None, 0, shared_palette=[(999, 0, 0)])

    def test_mixamo_compilation_locks_palette_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            renders = root / "renders"
            manifest = {"camera": {"azimuth": 0}, "clips": {}}
            for name, color in zip(("idle", "jump", "punch"),
                                   ((200, 45, 25, 255), (45, 200, 25, 255), (25, 45, 200, 255))):
                directory = renders / name
                directory.mkdir(parents=True)
                frame = Image.new("RGBA", (12, 12))
                pipeline.ImageDraw.Draw(frame).rectangle((3, 3, 8, 8), fill=color)
                frame.save(directory / "0.png")
                manifest["clips"][name] = {
                    "fps": 12, "loop": name == "idle", "frames": ["0.png"],
                }
            pipeline.write_json(renders / "manifest.json", manifest)
            args = argparse.Namespace(clip_set=renders / "manifest.json", colors=8,
                                      character="Bruiser")
            with patch.object(pipeline, "ROOT", root):
                pipeline.compile_mixamo(args)
                sheets = root / "assets" / "spritesheets"
                before = [(sheets / f"Bruiser_{name}_mixamo_sheet.png").read_bytes()
                          for name in ("idle", "jump", "punch")]
                pipeline.compile_mixamo(args)
                after = [(sheets / f"Bruiser_{name}_mixamo_sheet.png").read_bytes()
                         for name in ("idle", "jump", "punch")]
            self.assertEqual(before, after)
            palettes = []
            for name in ("idle", "jump", "punch"):
                with Image.open(sheets / f"Bruiser_{name}_mixamo_sheet.png") as image:
                    palettes.append(image.getpalette())
            self.assertEqual(palettes[0], palettes[1])
            self.assertEqual(palettes[0], palettes[2])
            with Image.open(renders / "idle" / "0.png") as raw:
                self.assertEqual(raw.getpixel((2, 4))[3], 0)

    def test_retro_outline_is_one_pixel_and_preserves_white_details(self):
        frame = Image.new("RGBA", (12, 12))
        for y in range(4, 8):
            for x in range(4, 8):
                frame.putpixel((x, y), (255, 255, 255, 255))
        frame.putpixel((1, 1), (200, 50, 20, 127))
        outlined = pipeline.outline_sprite(frame)
        self.assertEqual(outlined.getpixel((5, 5)), (255, 255, 255, 255))
        self.assertEqual(outlined.getpixel((3, 5)), (20, 16, 28, 255))
        self.assertEqual(outlined.getpixel((2, 5))[3], 0)
        self.assertEqual(outlined.getpixel((1, 1))[3], 0)
        self.assertEqual(set(outlined.getchannel("A").getdata()), {0, 255})

    def test_retro_compiles_separate_sheet_without_ai_or_background_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            animated = root / "idle.fbx"
            animated.write_bytes(b"cached")
            work = root / "temp" / "Bruiser_idle_retro"
            ai_work = root / "temp" / "Bruiser_idle"
            ai_work.mkdir(parents=True)
            preserved = ai_work / "original.png"
            preserved.write_bytes(b"keep")
            args = argparse.Namespace(
                animated=animated, work=work, fps=12, size=512, sprite_size=16,
                azimuth=30, frames=2, character="Bruiser", animation="idle",
                colors=32, tolerance=40, keep_temp=False,
            )

            def fake_blender(command, **kwargs):
                self.assertIn("--mode", command)
                self.assertEqual(command[command.index("--mode") + 1], "retro")
                self.assertEqual(command[command.index("--size") + 1], "16")
                output = work / "renders"
                output.mkdir(parents=True)
                names = []
                for index in range(2):
                    frame = Image.new("RGBA", (16, 16))
                    pipeline.ImageDraw.Draw(frame).rectangle((5, 5, 10, 10), fill="white")
                    name = f"{index:04d}.png"
                    frame.save(output / name)
                    names.append(name)
                pipeline.write_json(output / "manifest.json", {"fps": 12, "frames": names})

            with patch.object(pipeline, "ROOT", root), \
                    patch.object(pipeline, "blender_path", return_value="blender"), \
                    patch.object(pipeline.subprocess, "run", side_effect=fake_blender), \
                    patch.object(pipeline, "render_ai") as ai_render, \
                    patch.object(pipeline, "generate_base") as generate:
                pipeline.retro(args)
                ai_render.assert_not_called()
                generate.assert_not_called()
            target = root / "assets" / "spritesheets" / "Bruiser_idle_retro_sheet.png"
            with Image.open(target) as sheet:
                self.assertEqual(sheet.size, (32, 16))
                self.assertEqual(sheet.convert("RGBA").getpixel((8, 8)), (255, 255, 255, 255))
                self.assertLessEqual(len(sheet.getcolors()), 32)
            self.assertFalse(work.exists())
            self.assertEqual(preserved.read_bytes(), b"keep")

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
