"""Deterministic, palette-locked pixel-art painters for stage props.

Shapes are authored in art pixels, relative to the prop's ground pivot (y up is
negative), then upscaled with nearest-neighbour. Output colors are palette
indices only; no image model, remote service or random unseeded input is used.
"""

import math

import numpy as np
from PIL import Image

TINTS = {
    "deep": (30, 11, 12, 13),
    "green": (30, 11, 12, 13, 14),
    "lime": (11, 12, 13, 14),
}
THRESHOLDS = {4: (0.02, 0.36, 0.66), 5: (-0.08, 0.2, 0.46, 0.7)}
BARK_DARK, BARK_LIT, LAWN_SHADOW = 16, 17, 12
PADDING = 2


def _shift(array, dy, dx, fill):
    """Return a copy moved by (dy, dx): result[y + dy, x + dx] = array[y, x]."""
    out = np.full_like(array, fill)
    h, w = array.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = \
        array[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def _image(indices, palette, pixel):
    rgba = np.zeros(indices.shape + (4,), np.uint8)
    used = indices >= 0
    rgba[used, :3] = np.asarray(palette, np.uint8)[indices[used]]
    rgba[used, 3] = 255
    height, width = indices.shape
    return Image.fromarray(rgba).resize((width * pixel, height * pixel), Image.Resampling.NEAREST)


def _clumps(spec, rng):
    """Scalloped canopy puffs: a back ring around each crown, then interior puffs."""
    back, front = [], []
    for crown in spec["crowns"]:
        cx, cy = crown["center"]
        rx, ry = crown["radius"]
        size = crown["clump"]
        perimeter = math.pi * (3 * (rx + ry) - math.sqrt((3 * rx + ry) * (rx + 3 * ry)))
        count = max(6, round(perimeter / (size * 1.1)))
        for index in range(count):
            theta = 2 * math.pi * (index + rng.uniform(-0.25, 0.25)) / count
            radius = size * rng.uniform(0.85, 1.1)
            back.append((cx + math.cos(theta) * (rx - radius * 0.85),
                         cy + math.sin(theta) * (ry - radius * 0.85), radius))
        for _ in range(max(2, round(rx * ry / (size * size) * 0.6))):
            while True:
                u, v = rng.uniform(-1, 1, 2)
                if u * u + v * v <= 1:
                    break
            radius = size * rng.uniform(1.0, 1.25)
            front.append((cx + u * max(rx - radius, 1) * 0.8,
                          cy + v * max(ry - radius, 1) * 0.8, radius))
    order = lambda clump: clump[1] + clump[2] * rng.uniform(-0.3, 0.3)
    return sorted(back, key=order), sorted(front, key=order)


def _scaled(spec):
    """Apply the optional uniform `scale` (perspective depth) to all tree geometry."""
    scale = spec.get("scale", 1)
    if scale == 1:
        return spec
    scaled = dict(spec)
    scaled["shadow"] = [value * scale for value in spec["shadow"]]
    for key in ("stems", "limbs"):
        if key in spec:
            scaled[key] = [[value * scale for value in segment] for segment in spec[key]]
    scaled["crowns"] = [
        dict(crown, center=[value * scale for value in crown["center"]],
             radius=[value * scale for value in crown["radius"]],
             clump=crown["clump"] * scale)
        for crown in spec["crowns"]]
    return scaled


def paint_tree(spec, palette, light, pixel=2):
    """Paint one complete tree. Returns (RGBA image, pivot in screen pixels)."""
    spec = _scaled(spec)
    rng = np.random.default_rng(spec["seed"])
    back, front = _clumps(spec, rng)
    wobble = 1.1
    limbs = spec["stems"] + spec.get("limbs", [])
    xs_all = [x for clump in back + front for x in (clump[0] - clump[2] * wobble, clump[0] + clump[2] * wobble)]
    ys_all = [y for clump in back + front for y in (clump[1] - clump[2] * wobble, clump[1] + clump[2] * wobble)]
    for x0, y0, x1, y1, w0, w1 in limbs:
        xs_all += [x0 - w0, x1 - w1, x0 + w0, x1 + w1]
        ys_all += [y0 - w0, y1 - w1, y0 + w0, y1 + w1]
    sx, sy, srx, sry = spec["shadow"]
    xs_all += [sx - srx, sx + srx]
    ys_all += [sy - sry, sy + sry]
    left = math.floor(min(xs_all)) - PADDING
    top = math.floor(min(ys_all)) - PADDING
    width = math.ceil(max(xs_all)) + PADDING - left
    height = math.ceil(max(ys_all)) + PADDING - top
    ys, xs = np.mgrid[0:height, 0:width].astype(float) + 0.5
    xs += left
    ys += top

    color = np.full((height, width), -1)
    owner = np.full((height, width), -1)
    band = np.full((height, width), -1)
    tint = np.asarray(TINTS[spec["tint"]])
    thresholds = THRESHOLDS[len(tint)]
    light = np.asarray(light, float) / np.linalg.norm(light)
    toward_light = light[:2] / np.linalg.norm(light[:2])

    shadow = ((xs - sx) / srx) ** 2 + ((ys - sy) / sry) ** 2 <= 1
    color[shadow] = LAWN_SHADOW

    def draw_limb(segment):
        x0, y0, x1, y1, w0, w1 = segment
        dx, dy = x1 - x0, y1 - y0
        t = np.clip(((xs - x0) * dx + (ys - y0) * dy) / (dx * dx + dy * dy), 0, 1)
        px, py = x0 + t * dx, y0 + t * dy
        half = (w0 + (w1 - w0) * t) / 2
        inside = np.hypot(xs - px, ys - py) <= half
        lit = ((xs - px) * toward_light[0] + (ys - py) * toward_light[1]) > half * 0.2
        color[inside] = np.where(lit, BARK_LIT, BARK_DARK)[inside]
        owner[inside] = -2

    crowns = spec["crowns"]
    ccx = float(np.mean([crown["center"][0] for crown in crowns]))
    ccy = float(np.mean([crown["center"][1] for crown in crowns]))
    crx = max(abs(crown["center"][0] - ccx) + crown["radius"][0] for crown in crowns)
    cry = max(abs(crown["center"][1] - ccy) + crown["radius"][1] for crown in crowns)
    gx = np.clip((xs - ccx) / crx, -1, 1)
    gy = np.clip((ys - ccy) / cry, -1, 1)
    gz = np.sqrt(np.clip(1 - gx ** 2 - gy ** 2, 0.05, 1))
    occlusion = 0.28 * np.clip((ys - ccy) / cry, 0, 1)
    counter = [0]

    def draw_clump(clump, bias):
        px, py, radius = clump
        angle = np.arctan2(ys - py, xs - px)
        lobes = int(rng.integers(5, 8))
        edge = radius * (1 + 0.07 * np.sin(lobes * angle + rng.uniform(0, 2 * math.pi)))
        rho = np.hypot(xs - px, ys - py) / edge
        inside = rho <= 1
        rho = np.clip(rho, 0, 1)
        normal = np.stack([np.cos(angle) * rho, np.sin(angle) * rho, np.sqrt(1 - rho ** 2)])
        normal = 0.58 * normal + 0.42 * np.stack([gx, gy, gz])
        normal /= np.linalg.norm(normal, axis=0)
        value = (normal * light[:, None, None]).sum(axis=0) - occlusion + bias
        levels = np.digitize(value, thresholds)
        band[inside] = levels[inside]
        color[inside] = tint[levels[inside]]
        owner[inside] = counter[0]
        counter[0] += 1

    for segment in spec["stems"]:
        draw_limb(segment)
    for clump in back:
        draw_clump(clump, -0.12)
    for segment in spec.get("limbs", []):
        draw_limb(segment)
    for clump in front:
        draw_clump(clump, 0.0)

    # A nearer puff drops a one-band contact shadow down-right onto the puff behind it.
    leaves = owner >= 0
    nearer = np.zeros_like(leaves)
    for dy, dx in ((-1, 0), (0, -1), (-1, -1), (-2, -1)):
        neighbour = _shift(owner, -dy, -dx, -1)
        nearer |= neighbour > owner
    contact = leaves & nearer
    band[contact] = np.maximum(band[contact] - 1, 0)
    color[contact] = tint[band[contact]]

    if (color[:PADDING] >= 0).any() or (color[-PADDING:] >= 0).any() \
            or (color[:, :PADDING] >= 0).any() or (color[:, -PADDING:] >= 0).any():
        raise ValueError("Tree silhouette touches its canvas edge")
    image = _image(color, palette, pixel)
    return image, [-left * pixel, -top * pixel]


def paint_fence(spec, palette):
    """Paint one seamlessly tiling iron-fence module with a post, spear bars and curb."""
    pixel = spec["pixel"]
    width, height = spec["module"]
    spacing = spec["bar_spacing"]
    curb = spec["curb_rows"]
    if width % spacing:
        raise ValueError("Fence module width must be a multiple of the bar spacing")
    iron, iron_lit = spec["iron"], spec["iron_lit"]
    color = np.full((height, width), -1)
    base = height - curb
    post = 1
    color[4:base, post] = iron_lit
    color[4:base, post + 1] = iron
    for row, columns in ((0, (1, 2)), (1, (0, 1, 2, 3)), (2, (0, 1, 2, 3)), (3, (1, 2)), (5, (0, 1, 2, 3))):
        color[row, list(columns)] = iron
    color[1:3, 0] = iron_lit
    for x in range(post + spacing, width, spacing):
        color[3, x] = iron
        color[4, x - 1:x + 2] = iron
        color[5:base, x] = iron
    for row in spec["rails"]:
        color[row, :] = iron_lit
        color[row + 1, :] = iron
    color[base, :] = spec["curb"][0]
    color[base + 1:height - 1, :] = spec["curb"][1]
    color[height - 1, :] = spec["curb"][2]
    return _image(color, palette, pixel)
