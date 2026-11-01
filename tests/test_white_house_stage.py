"""Regression checks for the reference-matched White House yard export."""

import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image


JOB = Path(__file__).resolve().parents[1] / "assets" / "levels" / "white_house"
SOURCE = JOB / "source"


class WhiteHouseYardTests(unittest.TestCase):
    def setUp(self):
        self.recipe = json.loads((SOURCE / "assembly_recipe.json").read_text(encoding="utf-8"))
        self.revision = self.recipe["yard_revision"]

    def test_accepted_sources_and_screen_locked_sky_are_unchanged(self):
        for name, approved in self.revision["approved_images"].items():
            with self.subTest(image=name):
                self.assertEqual(
                    hashlib.sha256((SOURCE / approved["source"]).read_bytes()).hexdigest(),
                    approved["sha256"],
                )
        self.assertEqual(hashlib.sha256((JOB / "sky.png").read_bytes()).hexdigest(),
                         self.revision["approved_images"]["sky.png"]["sha256"])

    def test_house_is_set_back_without_changing_its_source_art(self):
        layout = self.recipe["foreground_layout"]
        grounding = layout["house_grounding"]
        pinned = Image.open(SOURCE / self.revision["approved_images"]["far_background.png"]["source"])
        scale = layout["scene_scale"]
        expected = Image.new("RGBA", pinned.size)
        expected.paste(pinned.convert("RGBA").resize(
            (round(pinned.width * scale), round(pinned.height * scale)),
            Image.Resampling.NEAREST),
            (round(1200 * (1 - scale)), layout["scene_y_offset"] + grounding["drop"]))
        expected = np.asarray(expected)
        actual = np.asarray(Image.open(JOB / "far_background.png").convert("RGBA"))
        source = expected[:, :, 3] > 0
        np.testing.assert_array_equal(actual[source], expected[source])
        filled = {tuple(int(v) for v in color[:3]) for color in actual[~source & (actual[:, :, 3] > 0)]}
        self.assertLessEqual(filled, {tuple(grounding["fill"]), tuple(grounding["shadow"])})

    def test_house_sits_on_the_lawn_behind_the_hedges_without_sky_gaps(self):
        grounding = self.recipe["foreground_layout"]["house_grounding"]
        alpha = np.asarray(Image.open(JOB / "far_background.png").convert("RGBA"))[:, :, 3] > 0
        top = grounding["fill_top"] + grounding["drop"]
        columns = np.nonzero(alpha[top - grounding["body_rows"]:top].any(axis=0))[0]
        self.assertGreater(len(columns), 400)
        bottoms = [int(np.nonzero(alpha[:, x])[0].max()) for x in columns]
        for x, bottom in zip(columns, bottoms):
            self.assertTrue(alpha[top:bottom + 1, x].all(), f"Sky gap under the house at x={x}")
        lawn = np.asarray(Image.open(JOB / "midground.png").convert("RGBA"))[:, 1200, 3] > 0
        props = json.loads((JOB / "level.json").read_text(encoding="utf-8"))["props"]
        lowest_hedge_top = 0
        for prop in props:
            if prop["id"].startswith("hedge_"):
                hedge = np.asarray(Image.open(JOB / prop["image"]).convert("RGBA"))[:, :, 3] > 0
                dips = [int(np.nonzero(hedge[:, x])[0].min())
                        for x in np.nonzero(hedge.any(axis=0))[0]]
                lowest_hedge_top = max(lowest_hedge_top, prop["position"][1] + max(dips))
        self.assertGreaterEqual(min(bottoms), int(np.nonzero(lawn)[0].min()) - 1)
        self.assertGreater(min(bottoms), lowest_hedge_top, "House base must sit behind the hedge row")
        hedges = [prop for prop in props if prop["id"].startswith("hedge_")]
        hedge_left = min(prop["position"][0] for prop in hedges)
        hedge_right = max(prop["position"][0] + prop["size"][0] for prop in hedges)
        for camera in (0, 480, 960):
            with self.subTest(camera=camera):
                house_screen = (-624 - camera * 0.2 + columns.min(), -624 - camera * 0.2 + columns.max())
                hedge_screen = (-480 - camera * 0.5 + hedge_left, -480 - camera * 0.5 + hedge_right)
                self.assertLessEqual(hedge_screen[0], house_screen[0])
                self.assertGreaterEqual(hedge_screen[1], house_screen[1])

    def test_fountain_is_compact_and_level(self):
        image = Image.open(JOB / "props" / "fountain.png").convert("RGBA")
        self.assertGreaterEqual(image.width, 430)
        self.assertGreater(image.width / image.height, 3.8)
        pixels = np.asarray(image)
        water = ((pixels[:, :, 0] < 140) & (pixels[:, :, 1] > 110)
                 & (pixels[:, :, 2] > 130) & (pixels[:, :, 3] == 255))
        left = water[:, int(image.width * 0.15):int(image.width * 0.3)]
        right = water[:, int(image.width * 0.7):int(image.width * 0.85)]
        self.assertTrue(left.any() and right.any())
        self.assertLess(abs(np.nonzero(left)[0].mean() - np.nonzero(right)[0].mean()), 4)

    def test_wider_sidewalk_and_road_leave_fighters_on_the_asphalt(self):
        layout = self.recipe["foreground_layout"]
        self.assertGreaterEqual(layout["road_top"] - layout["sidewalk_top"], 64)
        self.assertGreaterEqual(640 - layout["road_top"], 128)
        self.assertEqual(layout["feet_baseline"], 576)
        ground = Image.open(JOB / "ground.png").convert("RGBA")
        pixels = np.asarray(ground)
        self.assertFalse(pixels[:layout["lane_top"], :, 3].any())
        self.assertTrue((pixels[layout["lane_top"]:, :, 3] == 255).all())
        sidewalk = Image.open(JOB / "midground.png").convert("RGBA")
        self.assertEqual(sidewalk.getpixel((480, layout["sidewalk_top"] + 16))[3], 255)
        self.assertNotEqual(sidewalk.getpixel((480, layout["sidewalk_top"] + 16)),
                            ground.getpixel((480, layout["feet_baseline"])))

    def test_street_lights_stand_on_the_sidewalk_behind_the_fighters(self):
        root = JOB.parents[2]
        stage = json.loads((root / "stages" / "white_house" / "stage.json").read_text())
        names = [layer["name"] for layer in stage["layers"]]
        lamps = [layer for layer in stage["layers"] if layer["name"].startswith("street_lamp_")]
        self.assertEqual(len(lamps), len(self.recipe["foreground_layout"]["street_lights"]["positions"]))
        self.assertFalse(any("foreground_lamp" in name for name in names))
        midground = next(layer for layer in stage["layers"] if layer["name"] == "midground")
        for lamp in lamps:
            with self.subTest(lamp=lamp["name"]):
                self.assertFalse(lamp.get("front", False))
                self.assertEqual(lamp["ratio"], midground["ratio"])
                self.assertGreater(names.index(lamp["name"]),
                                   max(i for i, name in enumerate(names) if name.startswith("fence_")))
        layout = self.recipe["foreground_layout"]
        props = json.loads((JOB / "level.json").read_text(encoding="utf-8"))["props"]
        for prop in props:
            if prop["id"].startswith("street_lamp_"):
                base = prop["position"][1] + prop["size"][1]
                self.assertEqual(prop["layer"], "midground")
                self.assertGreater(base, layout["sidewalk_top"])
                self.assertLessEqual(base, layout["lane_top"])

    def test_lamp_sprites_exclude_the_reference_tree_trunk_and_vines(self):
        palette = [tuple(color) for color in self.recipe["palette"]]
        foliage = {palette[index] for index in (11, 12, 13, 14, 16, 30)}
        for name in ("lamp", "street_lamp"):
            with self.subTest(prop=name):
                pixels = np.asarray(Image.open(JOB / "props" / f"{name}.png").convert("RGBA"))
                opaque = {tuple(int(v) for v in color[:3])
                          for color in pixels[pixels[:, :, 3] == 255]}
                self.assertFalse(opaque & foliage)

    def test_front_layer_leaves_the_fighters_unobstructed(self):
        manifest = json.loads((JOB / "level.json").read_text(encoding="utf-8"))
        layer = Image.open(JOB / "foreground.png").convert("RGBA")
        for prop in manifest["props"]:
            if prop["layer"] == "foreground":
                layer.alpha_composite(
                    Image.open(JOB / prop["image"]).convert("RGBA"), tuple(prop["position"]))
        for camera in (0, 480, 960):
            offset = round(-720 - (camera - 480) * 1.15)
            visible = layer.crop((-offset, 0, -offset + 960, 640)).getchannel("A")
            with self.subTest(camera=camera):
                self.assertFalse(visible.crop((208, 320, 368, 576)).getbbox())
                self.assertFalse(visible.crop((592, 320, 752, 576)).getbbox())
                self.assertFalse(visible.crop((0, 512, 960, 640)).getbbox())

    def test_masks_are_scoped_to_their_owned_source_regions(self):
        for name, component in self.revision["components"].items():
            if "mask" not in component:
                continue
            with self.subTest(component=name):
                mask = np.asarray(Image.open(SOURCE / component["mask"])).copy()
                x0, y0, x1, y1 = component["source_box"]
                self.assertEqual(mask.shape, (848, 1264))
                self.assertTrue(mask[y0:y1, x0:x1].any())
                mask[y0:y1, x0:x1] = 0
                self.assertFalse(mask.any())

    def test_painted_trees_and_fence_are_crisp_palette_locked_pixel_art(self):
        palette = {tuple(color) for color in
                   json.loads((JOB / "palette.json").read_text(encoding="utf-8"))["colors"]}
        names = ["fence", *self.recipe["pixel_art"]["trees"]]
        for name in names:
            with self.subTest(prop=name):
                pixels = np.asarray(Image.open(JOB / "props" / f"{name}.png").convert("RGBA"))
                self.assertTrue(np.isin(pixels[:, :, 3], (0, 255)).all())
                opaque = pixels[pixels[:, :, 3] == 255][:, :3]
                self.assertLessEqual({tuple(color) for color in opaque}, palette)
                self.assertEqual(pixels.shape[0] % 2, 0)
                self.assertEqual(pixels.shape[1] % 2, 0)
                cells = pixels[::2, ::2]
                np.testing.assert_array_equal(
                    pixels, cells.repeat(2, axis=0).repeat(2, axis=1))

    def test_painted_trees_are_complete_unique_silhouettes(self):
        digests = set()
        for name in self.recipe["pixel_art"]["trees"]:
            with self.subTest(tree=name):
                image = Image.open(JOB / "props" / f"{name}.png").convert("RGBA")
                alpha = np.asarray(image.getchannel("A"))
                self.assertFalse(alpha[:2].any() or alpha[-2:].any()
                                 or alpha[:, :2].any() or alpha[:, -2:].any(),
                                 "Tree canopy or trunk touches its canvas edge")
                digests.add(hashlib.sha256(image.tobytes()).hexdigest())
        self.assertEqual(len(digests), len(self.recipe["pixel_art"]["trees"]))
        provenance = json.loads((SOURCE / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["pixel_art"]["method"], "deterministic_procedural_pixel_art")
        self.assertEqual(provenance["pixel_art"]["remote_services"], [])

    def test_painted_props_are_reproducible_from_the_recipe(self):
        sys.path.insert(0, str(JOB.parents[2] / "scripts"))
        try:
            from stage_pixel_props import paint_fence, paint_tree
        finally:
            sys.path.pop(0)
        pixel_art = self.recipe["pixel_art"]
        palette = self.recipe["palette"]
        painted = {"fence": paint_fence(pixel_art["fence"], palette)}
        for name, spec in pixel_art["trees"].items():
            painted[name] = paint_tree(spec, palette, pixel_art["light"])[0]
        for name, image in painted.items():
            with self.subTest(prop=name):
                expected = np.asarray(image.convert("RGBA"))
                actual = np.asarray(Image.open(JOB / "props" / f"{name}.png").convert("RGBA"))
                self.assertEqual(expected.shape, actual.shape)
                np.testing.assert_array_equal(expected[:, :, 3] >= 128, actual[:, :, 3] == 255)
                opaque = actual[:, :, 3] == 255
                np.testing.assert_array_equal(expected[opaque][:, :3], actual[opaque][:, :3])

    def test_larger_fence_tiles_seamlessly_on_the_sidewalk_edge(self):
        layout = self.recipe["foreground_layout"]
        base = self.recipe["pixel_art"]["fence"]["base_y"]
        self.assertEqual(base, layout["sidewalk_top"])
        image = Image.open(JOB / "props" / "fence.png").convert("RGBA")
        alpha = np.asarray(image.getchannel("A")) == 255
        self.assertGreaterEqual(image.height, 110)
        self.assertTrue(alpha[-1].all(), "Curb must span the module for seamless tiling")
        self.assertGreaterEqual(int(alpha.all(axis=1).sum()), 3, "Rails must span the module")
        props = json.loads((JOB / "level.json").read_text(encoding="utf-8"))["props"]
        fences = sorted((prop for prop in props if prop["id"].startswith("fence_")),
                        key=lambda prop: prop["position"][0])
        self.assertEqual(fences[0]["position"][0], 0)
        self.assertGreaterEqual(fences[-1]["position"][0] + image.width, 2400)
        for left, right in zip(fences, fences[1:]):
            self.assertEqual(right["position"][0] - left["position"][0], image.width)
        for fence in fences:
            self.assertEqual(fence["position"][1] + image.height, base)

    def test_scenery_props_stay_above_the_combat_lane(self):
        lane = self.recipe["foreground_layout"]["lane_top"]
        props = json.loads((JOB / "level.json").read_text(encoding="utf-8"))["props"]
        for prop in props:
            image = Image.open(JOB / prop["image"]).convert("RGBA")
            box = image.getchannel("A").getbbox()
            with self.subTest(prop=prop["id"]):
                self.assertIsNotNone(box)
                self.assertLessEqual(prop["position"][1] + box[3], lane)

    def test_hedges_do_not_cut_across_nearer_tree_trunks(self):
        props = json.loads((JOB / "level.json").read_text(encoding="utf-8"))["props"]
        ids = [prop["id"] for prop in props]
        last_hedge = max(index for index, name in enumerate(ids) if name.startswith("hedge_"))
        first_tree = min(index for index, name in enumerate(ids) if name.startswith("tree_"))
        last_tree = max(index for index, name in enumerate(ids) if name.startswith("tree_"))
        first_fence = min(index for index, name in enumerate(ids) if name.startswith("fence_"))
        self.assertLess(last_hedge, first_tree)
        self.assertLess(last_tree, first_fence)

    def test_trees_stand_back_on_the_lawn_behind_the_fence(self):
        fence_base = self.recipe["pixel_art"]["fence"]["base_y"]
        for name, _, base in self.recipe["pixel_art"]["tree_placements"]:
            with self.subTest(tree=name):
                self.assertLessEqual(base, fence_base - 40)
        props = {prop["id"]: prop for prop in
                 json.loads((JOB / "level.json").read_text(encoding="utf-8"))["props"]}
        for name, x, base in self.recipe["pixel_art"]["tree_placements"]:
            prop = props[f"{name}_0"]
            with self.subTest(tree=name):
                self.assertEqual(prop["position"][0] + prop["pivot"][0], x)
                self.assertEqual(prop["position"][1] + prop["pivot"][1], base)


if __name__ == "__main__":
    unittest.main()
