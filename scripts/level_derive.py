"""Derive a level's layers from its reference image with deterministic offline 2D processing.

This is the fallback for the Nano Banana -> Tripo -> Blender workflow when approved services
or assets are unavailable. It uses no network, API key or paid service. Every choice that is
specific to one reference lives in ``source/derive_recipe.json`` (in reference pixels), so a
derivation is repeatable. The result is a draft: review gates are never set.
"""

import argparse
import hashlib
import math
from pathlib import Path
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import level_pipeline as pipeline  # noqa: E402

METHOD = "local_2d_derivation"
RESAMPLE = Image.Resampling.LANCZOS
LAYER_PLAN_KEYS = ("sky", "far_background", "midground", "ground", "foreground", "props")
HALO_MIN_VALUE = 0.55
RESERVED_RADIUS = 0.05
LMS = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
LAB = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])


def hsv(rgb):
    """Hue (degrees), saturation and value (0..1) of an (..., 3) uint8 array."""
    data = rgb.astype(np.float64)
    red, green, blue = data[..., 0], data[..., 1], data[..., 2]
    top = data.max(axis=-1)
    span = top - data.min(axis=-1)
    safe = np.where(span > 0, span, 1.0)
    hue = np.where(
        top == red, ((green - blue) / safe) % 6,
        np.where(top == green, (blue - red) / safe + 2, (red - green) / safe + 4),
    ) * 60
    hue = np.where(span > 0, hue, 0.0)
    saturation = np.where(top > 0, span / np.where(top > 0, top, 1.0), 0.0)
    return hue, saturation, top / 255


def dilate(mask, radius=1):
    out = mask.copy()
    for step in range(1, radius + 1):
        out[step:] |= mask[:-step]
        out[:-step] |= mask[step:]
    wide = out.copy()
    for step in range(1, radius + 1):
        out[:, step:] |= wide[:, :-step]
        out[:, :-step] |= wide[:, step:]
    return out


def erode(mask, radius=1):
    return ~dilate(~mask, radius)


def flood(open_mask, seeds):
    """4-connected flood fill through True cells of open_mask from (x, y) seeds."""
    height, width = open_mask.shape
    stride = width + 2
    cells = np.pad(open_mask, 1).ravel().tolist()
    seen = bytearray(len(cells))
    stack = []
    for x, y in seeds:
        index = (y + 1) * stride + x + 1
        if cells[index] and not seen[index]:
            seen[index] = 1
            stack.append(index)
    while stack:
        index = stack.pop()
        for neighbour in (index - 1, index + 1, index - stride, index + stride):
            if cells[neighbour] and not seen[neighbour]:
                seen[neighbour] = 1
                stack.append(neighbour)
    grid = np.frombuffer(seen, dtype=np.uint8).reshape(height + 2, stride)
    return grid[1:-1, 1:-1].astype(bool)


def largest_component(mask):
    remaining = mask.copy()
    best, best_size = np.zeros_like(mask), 0
    while remaining.any():
        rows, columns = np.nonzero(remaining)
        component = flood(remaining, [(int(columns[0]), int(rows[0]))])
        if component.sum() > best_size:
            best, best_size = component, int(component.sum())
        remaining &= ~component
    return best


def sky_matte(rgb, settings):
    """Boolean sky mask: flood from the top edge, stopped by ink lines and land colors."""
    hue, saturation, value = hsv(rgb)
    low, high = settings["land_hue"]
    land_color = (
        (hue >= low) & (hue <= high) & (saturation >= 0.2) & (value < settings["land_value_max"])
    )
    peak = np.asarray(Image.fromarray(rgb.max(axis=2)).filter(ImageFilter.MaxFilter(7)))
    thin_ink = ((peak / 255 - value) > 0.30) & (value < 0.45)
    barrier = dilate(land_color | thin_ink | (value < settings["ink_value_max"]), 1)
    height, width = value.shape
    sky = flood(~barrier, [(x, 0) for x in range(width)])
    for _ in range(settings["halo_passes"]):
        sky |= dilate(sky, 1) & ~land_color & (value >= HALO_MIN_VALUE)
    # Land is whatever connects to the bottom edge; enclosed pockets (the glow between
    # stones) stay land and stray specks inside the sky return to the sky.
    land = flood(~sky, [(x, height - 1) for x in range(width)])
    return ~land


def fill_sky(rgb, sky, settings):
    """Remove land from the lightbox by row interpolation of nearby clean sky."""
    known = erode(sky, settings["margin"])
    columns = np.arange(rgb.shape[1])
    filled = rgb.astype(np.float64)
    anchor = None
    for row in range(rgb.shape[0]):
        present = np.flatnonzero(known[row])
        if present.size:
            for channel in range(3):
                filled[row, :, channel] = np.interp(columns, present, rgb[row, present, channel])
            anchor = row
        elif anchor is not None:
            filled[row] = filled[anchor]
    soft = np.asarray(
        Image.fromarray(np.rint(filled).astype(np.uint8)).filter(ImageFilter.GaussianBlur(settings["blur"]))
    )
    return np.where(known[..., None], rgb, soft)


def crest_line(value, points, start, stop, radius=8, window=9):
    """Snap an authored polyline to the darkest nearby row, then median-smooth it."""
    xs = np.arange(start, stop)
    guess = np.rint(np.interp(xs, [p[0] for p in points], [p[1] for p in points])).astype(int)
    soft = (np.roll(value, 1, axis=0) + value + np.roll(value, -1, axis=0)) / 3
    rows = np.empty(len(xs), dtype=int)
    for index, (x, y) in enumerate(zip(xs, guess)):
        low = max(1, y - radius)
        high = min(value.shape[0] - 1, y + radius + 1)
        rows[index] = low + int(np.argmin(soft[low:high, x]))
    padded = np.pad(rows, window // 2, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, window)
    return np.median(windows, axis=1).astype(int)


def split_layers(rgb, land, bands, anchor):
    """Distant trees above an authored crest become far background; all other land is midground."""
    value = hsv(rgb)[2]
    trees = np.zeros_like(land)
    fill = np.zeros_like(land)
    far_rgb = rgb.copy()
    crests = []
    for band in bands:
        start, stop = band["x"]
        crest = crest_line(value, band["crest"], start, min(stop, land.shape[1]))
        crests.append((start, crest))
        for x, row in zip(range(start, start + len(crest)), crest):
            cut = int(row) - 1
            above = np.flatnonzero(land[:cut, x])
            if above.size == 0:
                continue
            trees[above, x] = True
            # Hidden by the midground at rest; extruded so parallax never exposes a hole.
            fill[cut:anchor, x] = True
            far_rgb[cut:anchor, x] = rgb[max(above[0], above[-1] - 5), x]
    far_mask = trees | fill
    mid_mask = land & ~trees
    far_mask[anchor:] = False
    mid_mask[anchor:] = False
    far = np.dstack([far_rgb, far_mask.astype(np.uint8) * 255])
    mid = np.dstack([rgb, mid_mask.astype(np.uint8) * 255])
    return far, mid, crests


def edge_ramp(length, feather, open_start, open_end):
    ramp = np.ones(length)
    steps = np.arange(1, feather + 1) / (feather + 1)
    size = min(feather, length)
    if not open_start:
        ramp[:size] = np.minimum(ramp[:size], steps[:size])
    if not open_end:
        ramp[length - size:] = np.minimum(ramp[length - size:], steps[:size][::-1])
    return ramp


def smooth_rows(values, window):
    kernel = np.ones(window) / window
    padded = np.pad(values, ((window // 2, window // 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(padded[:, c], kernel, "valid") for c in range(3)], axis=1)


def patch_lane(rgb, patches, feather=8, ring=12, window=15):
    """Replace lane intrusions with clean-dirt copies, tone-matched to the surrounding dirt.

    The donor strip is offset by a per-row color correction measured on columns just
    outside each side of the patch, interpolated across the patch, so a lighter or darker
    donor region does not leave a visible rectangle.
    """
    patched = rgb.copy()
    width = rgb.shape[1]
    for patch in patches:
        x0, y0, x1, y1 = patch["rect"]
        shift = patch["dx"]
        if x0 + shift < 0 or x1 + shift > width:
            raise ValueError(f"lane patch {patch['rect']} reads outside the reference.")
        sides = []
        for start, stop in ((x0 - ring, x0), (x1, x1 + ring)):
            if start < 0 or stop > width or start + shift < 0 or stop + shift > width:
                sides.append(None)
                continue
            target = np.median(patched[y0:y1, start:stop].astype(np.float64), axis=1)
            donor = np.median(rgb[y0:y1, start + shift:stop + shift].astype(np.float64), axis=1)
            sides.append(smooth_rows(target - donor, window))
        if sides[0] is None and sides[1] is None:
            raise ValueError(f"lane patch {patch['rect']} has no measurable surrounding dirt.")
        left = sides[0] if sides[0] is not None else sides[1]
        right = sides[1] if sides[1] is not None else sides[0]
        t = np.linspace(0, 1, x1 - x0)[None, :, None]
        correction = left[:, None, :] * (1 - t) + right[:, None, :] * t
        donor = np.clip(rgb[y0:y1, x0 + shift:x1 + shift] + correction, 0, 255)
        weight = np.outer(
            edge_ramp(y1 - y0, feather, False, False),
            edge_ramp(x1 - x0, feather, x0 == 0, x1 == width),
        )[..., None]
        blend = donor * weight + patched[y0:y1, x0:x1] * (1 - weight)
        patched[y0:y1, x0:x1] = np.rint(blend).astype(np.uint8)
    return patched


def cut_prop(rgb, box, settings):
    """Cut a closed-outline object from its surroundings by border flood fill."""
    x0, y0, x1, y1 = box
    crop = rgb[y0:y1, x0:x1]
    height, width = crop.shape[:2]
    ink = dilate(hsv(crop)[2] < settings["ink_value_max"], 1)
    sides = settings.get("seed_sides", ["top", "bottom", "left", "right"])
    seeds = []
    if "top" in sides:
        seeds += [(x, 0) for x in range(width)]
    if "bottom" in sides:
        seeds += [(x, height - 1) for x in range(width)]
    if "left" in sides:
        seeds += [(0, y) for y in range(height)]
    if "right" in sides:
        seeds += [(width - 1, y) for y in range(height)]
    body = largest_component(erode(~flood(~ink, seeds), 1))
    opening = settings["opening"]
    body = largest_component(dilate(erode(body, opening), opening) & body)
    if body.sum() < 0.1 * width * height:
        raise ValueError(f"prop box {box}: outline is not closed; adjust the box or ink threshold.")
    rows, columns = np.nonzero(body)
    window = (slice(rows.min(), rows.max() + 1), slice(columns.min(), columns.max() + 1))
    return np.dstack([crop, body.astype(np.uint8) * 255])[window]


def resize(array, size):
    return np.asarray(Image.fromarray(np.ascontiguousarray(array)).resize(size, RESAMPLE))


def binary_alpha(rgba):
    out = rgba.copy()
    solid = out[..., 3] >= 128
    out[..., 3] = np.where(solid, 255, 0)
    out[~solid, :3] = 0
    return out


def crop_alpha(rgba):
    rows, columns = np.nonzero(rgba[..., 3])
    return rgba[rows.min():rows.max() + 1, columns.min():columns.max() + 1]


def oklab(rgb):
    linear = rgb.astype(np.float64) / 255
    linear = np.where(linear <= 0.04045, linear / 12.92, ((linear + 0.055) / 1.055) ** 2.4)
    return np.cbrt(linear @ LMS.T) @ LAB.T


def unique_colors(rgb):
    flat = rgb.reshape(-1, 3).astype(np.uint32)
    values, counts = np.unique((flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2], return_counts=True)
    colors = np.stack([(values >> 16) & 255, (values >> 8) & 255, values & 255], axis=1)
    return colors.astype(np.uint8), counts


def nearest(points, centers):
    owner = np.empty(len(points), dtype=np.int64)
    for start in range(0, len(points), 50000):
        block = points[start:start + 50000]
        owner[start:start + 50000] = ((block[:, None, :] - centers[None]) ** 2).sum(axis=2).argmin(axis=1)
    return owner


def median_cut(points, weights, count):
    boxes = [np.arange(len(points))]

    def spread(box):
        mean = np.average(points[box], axis=0, weights=weights[box])
        return np.average((points[box] - mean) ** 2, axis=0, weights=weights[box])

    while len(boxes) < count:
        scores = [spread(box).sum() * weights[box].sum() if len(box) > 1 else -1 for box in boxes]
        best = int(np.argmax(scores))
        if scores[best] <= 0:
            break
        box = boxes.pop(best)
        order = box[np.argsort(points[box, int(np.argmax(spread(box)))], kind="stable")]
        cumulative = np.cumsum(weights[order])
        cut = int(np.searchsorted(cumulative, cumulative[-1] / 2)) + 1
        cut = min(max(cut, 1), len(order) - 1)
        boxes += [order[:cut], order[cut:]]
    return boxes


def group_palette(pixels, count, reserved_lab):
    colors, counts = unique_colors(pixels)
    lab = oklab(colors)
    if len(reserved_lab):
        distance = ((lab[:, None, :] - reserved_lab[None]) ** 2).sum(axis=2).min(axis=1)
        keep = distance > RESERVED_RADIUS ** 2
        if keep.sum() >= count:
            colors, counts, lab = colors[keep], counts[keep], lab[keep]
    weights = counts.astype(np.float64) ** 0.75
    boxes = median_cut(lab, weights, min(count, len(lab)))
    centers = np.array([np.average(lab[box], axis=0, weights=weights[box]) for box in boxes])
    for _ in range(6):
        owner = nearest(lab, centers)
        for index in range(len(centers)):
            if (owner == index).any():
                centers[index] = np.average(lab[owner == index], axis=0, weights=weights[owner == index])
    owner = nearest(lab, centers)
    return [
        np.rint(np.average(colors[owner == index], axis=0, weights=weights[owner == index])).astype(np.uint8)
        for index in range(len(centers)) if (owner == index).any()
    ]


def build_palette(groups, settings, ink, budget):
    reserved = [np.array(ink, dtype=np.uint8)] + [
        np.array(color, dtype=np.uint8) for color in settings.get("reserved", [])
    ]
    reserved_lab = oklab(np.array(reserved))
    colors = list(reserved)
    for name, pixels in groups.items():
        colors += group_palette(pixels, settings[name], reserved_lab)
    unique = {tuple(int(channel) for channel in color) for color in colors}
    if len(unique) > budget:
        raise ValueError(f"Palette needs {len(unique)} colors; the budget allows {budget}.")
    palette = np.array(sorted(unique, key=lambda color: tuple(oklab(np.array(color))))).astype(np.uint8)
    return palette


def quantize(rgb, palette):
    """Nearest palette color per pixel, without dithering."""
    colors, _ = unique_colors(rgb)
    flat = rgb.reshape(-1, 3).astype(np.uint32)
    packed = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    values, inverse = np.unique(packed, return_inverse=True)
    unique = np.stack([(values >> 16) & 255, (values >> 8) & 255, values & 255], axis=1).astype(np.uint8)
    mapped = palette[nearest(oklab(unique), oklab(palette))]
    return mapped[inverse.reshape(-1)].reshape(rgb.shape)


def quantize_rgba(rgba, palette):
    out = np.zeros_like(rgba)
    solid = rgba[..., 3] == 255
    if solid.any():
        out[solid, :3] = quantize(rgba[solid][:, :3].reshape(-1, 1, 3), palette).reshape(-1, 3)
        out[solid, 3] = 255
    return out


def green_roles(palette):
    hue, saturation, value = hsv(palette.reshape(1, -1, 3))
    greens = [
        index for index in range(len(palette))
        if 60 <= hue[0, index] <= 150 and saturation[0, index] >= 0.3 and value[0, index] >= 0.25
    ]
    if not greens:
        raise ValueError("Palette has no green entries for procedural tufts.")
    greens.sort(key=lambda index: value[0, index])
    ink = palette[int(np.argmin(value[0]))]
    return [ink, palette[greens[0]], palette[greens[len(greens) // 2]], palette[greens[-1]]]


def draw_tuft(size, seed, colors, palette):
    """Procedural grass tuft: outlined blades, drawn supersampled, then palette-quantized."""
    width, height = size
    scale = 4
    rng = random.Random(seed)
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink, *greens = colors
    blades = max(4, width // 8)
    outline = 1.6 * scale
    for index in range(blades):
        base = (index + 0.5) / blades * width * scale
        half = width / blades * scale * rng.uniform(0.7, 1.1)
        tip_x = base + rng.uniform(-0.45, 0.45) * height * scale
        tip_y = height * scale * (1 - rng.uniform(0.55, 1.0))
        floor = height * scale
        draw.polygon([(base - half, floor), (tip_x, tip_y), (base + half, floor)], fill=(*map(int, ink), 255))
        inner = [(base - half + outline, floor), (tip_x, tip_y + 2.2 * outline), (base + half - outline, floor)]
        draw.polygon(inner, fill=(*map(int, greens[index % 3]), 255))
    small = binary_alpha(resize(np.asarray(image), (width, height)))
    return quantize_rgba(small, palette)


def paste(canvas, sprite, x, y):
    height, width = sprite.shape[:2]
    if x < 0 or y < 0 or x + width > canvas.shape[1] or y + height > canvas.shape[0]:
        raise ValueError(f"sprite {width}x{height} at {x},{y} falls outside its layer.")
    region = Image.fromarray(np.ascontiguousarray(canvas[y:y + height, x:x + width]))
    region.alpha_composite(Image.fromarray(np.ascontiguousarray(sprite)))
    canvas[y:y + height, x:x + width] = np.asarray(region)


def save_png(path, array):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(array)).save(path)


def write_debug(directory, rgb, sky, crests, lane_source):
    directory.mkdir(parents=True, exist_ok=True)
    overlay = rgb.copy()
    overlay[sky] = (0.35 * overlay[sky] + 0.65 * np.array([0, 255, 255])).astype(np.uint8)
    for start, crest in crests:
        overlay[crest, np.arange(start, start + len(crest))] = (255, 0, 255)
    Image.fromarray(overlay).save(directory / "matte_overlay.png")
    Image.fromarray(lane_source).save(directory / "lane_patched.png")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_recipe(root):
    path = root / "source" / "derive_recipe.json"
    recipe = pipeline.read_json(path)
    if recipe.get("recipe_version") != 1:
        raise ValueError("Unsupported derive recipe version.")
    plan, seen = recipe["layer_plan"], {}
    if set(plan) - set(LAYER_PLAN_KEYS):
        raise ValueError(f"layer_plan keys must be within {LAYER_PLAN_KEYS}.")
    for layer, features in plan.items():
        for feature in features:
            if feature in seen:
                raise ValueError(f"Feature '{feature}' is assigned to both {seen[feature]} and {layer}.")
            seen[feature] = layer
    return recipe, sha256(path)


def derive(root, debug_dir=None):
    root = Path(root)
    manifest = pipeline.read_json(root / "level.json")
    recipe, recipe_hash = load_recipe(root)
    provenance = pipeline.read_json(root / "source" / "provenance.json")
    reference_path = pipeline.asset_path(root, provenance["inputs"]["reference"]["file"])
    with Image.open(reference_path) as source:
        rgb = np.asarray(source.convert("RGB"))
    reference_height, reference_width = rgb.shape[:2]
    viewport_width, viewport_height = manifest["viewport"]
    lane_top = round(viewport_height * (1 - manifest["play_area_fraction"]))
    anchor = recipe["lane_anchor_y"]
    scale = lane_top / anchor
    world = round(reference_width * scale)
    scaled_height = round(reference_height * scale)
    travel = recipe["camera_travel"]
    fastest = max(layer["factor"] for layer in manifest["layers"])
    if scaled_height < viewport_height or not anchor < reference_height:
        raise ValueError("Reference is too short for the lane anchor and viewport height.")
    if world < viewport_width + math.ceil(travel * fastest) or travel > world - viewport_width:
        raise ValueError(f"World {world}px is too narrow for camera_travel {travel}; reduce it.")
    target = (world, scaled_height)

    sky = sky_matte(rgb, recipe["sky"])
    land = ~sky
    sky_full = resize(fill_sky(rgb, sky, recipe["sky"]), target)
    left = (world - viewport_width) // 2
    sky_rgb = sky_full[:viewport_height, left:left + viewport_width]

    far_ref, mid_ref, crests = split_layers(rgb, land, recipe["far_bands"], anchor)
    lane_source = patch_lane(rgb, recipe.get("lane_patches", []))
    if debug_dir:
        write_debug(Path(debug_dir), rgb, sky, crests, lane_source)

    def scenery(layer):
        scaled = binary_alpha(resize(layer, target))[:viewport_height]
        scaled[lane_top:] = 0
        return scaled

    far, mid = scenery(far_ref), scenery(mid_ref)
    lane_rgb = resize(lane_source, target)[lane_top:viewport_height]

    harvested = {}
    for item in recipe["props"].get("harvest", []):
        cut = cut_prop(rgb, item["box"], {**recipe["props"]["cut"], **item})
        height, width = cut.shape[:2]
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        harvested[item["id"]] = crop_alpha(binary_alpha(resize(cut, size)))

    ink_mask = (hsv(rgb)[2] < recipe["sky"]["ink_value_max"]) & land
    ink = np.median(rgb[ink_mask], axis=0).astype(int).tolist()
    groups = {
        "sky": sky_rgb,
        "scenery": np.concatenate(
            [layer[layer[..., 3] == 255][:, :3] for layer in (far, mid, *harvested.values())]
        ),
        "ground": lane_rgb,
    }
    palette = build_palette(
        groups, recipe["palette"], ink, manifest["palette_colors_including_transparency"] - 1
    )

    sky_q = quantize(sky_rgb, palette)
    far_q, mid_q = quantize_rgba(far, palette), quantize_rgba(mid, palette)
    ground = np.zeros((viewport_height, world, 4), dtype=np.uint8)
    ground[lane_top:, :, :3] = quantize(lane_rgb, palette)
    ground[lane_top:, :, 3] = 255
    props = {name: quantize_rgba(image, palette) for name, image in harvested.items()}
    roles = green_roles(palette)
    for item in recipe["props"].get("tufts", []):
        props[item["id"]] = draw_tuft(item["size"], item["seed"], roles, palette)

    foreground = np.zeros((viewport_height, world, 4), dtype=np.uint8)
    for item in recipe["foreground"]:
        sprite = props[item["prop"]]
        paste(foreground, sprite, item["x"], item["base"] - sprite.shape[0] + 1)

    placed, counts = [], {}
    for item in recipe["placements"]:
        sprite = props[item["prop"]]
        height, width = sprite.shape[:2]
        counts[item["prop"]] = counts.get(item["prop"], 0) + 1
        placed.append({
            "id": f"{item['prop']}_{counts[item['prop']]}",
            "layer": item["layer"],
            "image": f"props/{item['prop']}.png",
            "size": [width, height],
            "position": [item["x"], item["base"] - height + 1],
            "pivot": [width // 2, height - 1],
            "collision": False,
        })

    save_png(root / "sky.png", sky_q)
    for name, layer in (("far_background", far_q), ("midground", mid_q),
                        ("ground", ground), ("foreground", foreground)):
        save_png(root / f"{name}.png", layer)
    for name, image in props.items():
        save_png(root / "props" / f"{name}.png", image)
    manifest.update(world_width=world, camera_travel=travel, props=placed)
    pipeline.write_json(root / "level.json", manifest)
    pipeline.write_json(root / "palette.json", {"colors": palette.tolist()})
    prompts_path = root / "prompts.json"
    if prompts_path.exists():
        prompts = pipeline.read_json(prompts_path)
        prompts.get("canvas", {}).update(world_width=world, camera_travel=travel)
        pipeline.write_json(prompts_path, prompts)
    pipeline.write_json(root / "source" / "layer_plan.json", {
        "schema_version": 1, "method": METHOD, "assignments": recipe["layer_plan"],
    })
    provenance["generation"] = [
        entry for entry in provenance["generation"] if entry.get("method") != METHOD
    ] + [{
        "method": METHOD,
        "tool": "scripts/level_derive.py",
        "tool_sha256": sha256(Path(__file__)),
        "recipe_sha256": recipe_hash,
        "reference_sha256": provenance["inputs"]["reference"]["sha256"],
        "remote_services": [],
        "limitations": "Deterministic 2D segmentation of the reference; not Nano Banana, "
                       "Tripo or Blender output. Artistic review gates remain false.",
    }]
    pipeline.write_json(root / "source" / "provenance.json", provenance)
    pipeline.validate(root)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("derive", help="Generate layers, props and the shared palette.")
    run.add_argument("--level", type=Path, required=True)
    run.add_argument("--debug-dir", type=Path, help="Write matte/crest overlays for recipe authoring.")
    args = parser.parse_args()
    try:
        manifest = derive(args.level, args.debug_dir)
        print(f"Derived draft layers for {args.level} ({manifest['world_width']}px world); review gates unchanged.")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Level derivation failed: {error}\n")


if __name__ == "__main__":
    main()
