"""Generate PLACEHOLDER move sprite sheets for a character from its idle sheet.

The real pipeline (scripts/spritesheet.py + Mixamo clips, Blender, ComfyUI) needs
external services. Until those clips exist, this script poses the character's
real idle art (squash, lean, jump arcs, crude limbs) so every move in the
minimum animation set can be tested in the game and the animation lab.

Outputs follow the production naming/metadata convention
(`<Character>_<animation>_sheet.png/.json`, 8 FPS, 160x160 frames, 31 colors +
transparency), with `"placeholder": true` in the JSON. Replace a placeholder by
running the real pipeline for the same animation id; it overwrites the files.

    .venv\\Scripts\\python.exe scripts\\placeholder_sheets.py --character Bruiser
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

FRAME = 160
FPS = 8
COLORS = 31  # plus transparency = 32
GROUND = 158
OUTLINE = (40, 20, 20, 255)
SKIN = (214, 142, 100, 255)
GOLD = (240, 190, 40, 255)
GOLD_HI = (255, 235, 140, 255)
BLUE = (50, 80, 170, 255)
GUARD = (120, 200, 255, 255)


def load_base(sheet_dir, character):
    sheet = Image.open(sheet_dir / f"{character}_idle_sheet.png").convert("RGBA")
    base = sheet.crop((0, 0, FRAME, FRAME))
    return base.crop(base.getbbox())


def body(base, sx=1.0, sy=1.0, rot=0.0, dx=0, dy=0):
    """Return a FRAME canvas with the body scaled/rotated around its feet."""
    size = (max(1, round(base.width * sx)), max(1, round(base.height * sy)))
    part = base.resize(size, Image.NEAREST)
    big = Image.new("RGBA", (FRAME * 2, FRAME * 2), (0, 0, 0, 0))
    pivot = (FRAME + dx, FRAME + GROUND + dy)
    big.paste(part, (pivot[0] - part.width // 2, pivot[1] - part.height), part)
    if rot:
        big = big.rotate(rot, center=pivot, resample=Image.NEAREST)
    return big.crop((FRAME // 2, FRAME + GROUND - FRAME + 2, FRAME // 2 + FRAME, FRAME + GROUND + 2))


def limb(draw, start, end, width, tip):
    draw.line([start, end], fill=OUTLINE, width=width + 4)
    draw.line([start, end], fill=SKIN, width=width)
    x, y = end
    if tip == "glove":
        draw.ellipse([x - 12, y - 12, x + 12, y + 12], fill=GOLD, outline=OUTLINE, width=2)
        draw.ellipse([x - 7, y - 8, x + 1, y], fill=GOLD_HI)
    else:
        draw.ellipse([x - 8, y - 9, x + 16, y + 9], fill=BLUE, outline=OUTLINE, width=2)
        draw.rectangle([x - 8, y - 9, x + 2, y + 9], fill=GOLD, outline=OUTLINE)


def with_overlay(img, fn):
    draw = ImageDraw.Draw(img)
    fn(draw)
    return img


def guard_arc(draw, x, y, h):
    draw.arc([x - 14, y - h, x + 30, y + h], 270, 90, fill=GUARD, width=4)


def pose(base, **kw):
    return body(base, **kw)


def punch(base, shoulder, reach, **kw):
    return with_overlay(body(base, **kw), lambda d: limb(d, shoulder, (shoulder[0] + reach, shoulder[1]), 9, "glove"))


def kick(base, hip, reach, lift, **kw):
    return with_overlay(body(base, **kw), lambda d: limb(d, hip, (hip[0] + reach, hip[1] - lift), 11, "boot"))


def block(base, **kw):
    guard_y = kw.pop("_gy", 70)
    return with_overlay(body(base, **kw), lambda d: guard_arc(d, 100, guard_y, 36))


def animations(base):
    crouch = dict(sy=0.72, sx=1.05)
    sh, hp = (92, 56), (84, 96)
    cs, ch = (92, 84), (86, 112)
    return {
        "crouched_idle": (True, [pose(base, sy=0.74 - 0.01 * (i % 2), sx=1.05) for i in (0, 1, 2, 1)]),
        "standing_punch": (False, [
            pose(base, dx=-4), punch(base, sh, 20, dx=-6),
            punch(base, sh, 52, dx=6), punch(base, sh, 56, dx=8),
            punch(base, sh, 30), pose(base)]),
        "crouched_punch": (False, [
            pose(base, **crouch), punch(base, cs, 22, **crouch),
            punch(base, cs, 50, dx=6, **crouch), punch(base, cs, 54, dx=6, **crouch),
            punch(base, cs, 26, **crouch)]),
        "standing_kick": (False, [
            pose(base, rot=3), kick(base, hp, 22, 12, rot=4, dx=-4),
            kick(base, hp, 50, 34, rot=-6, dx=-4), kick(base, hp, 54, 36, rot=-8, dx=-4),
            kick(base, hp, 34, 16), pose(base)]),
        "crouched_kick": (False, [
            pose(base, **crouch), kick(base, ch, 24, 2, **crouch),
            kick(base, ch, 54, 2, dx=-4, **crouch), kick(base, ch, 58, 2, dx=-4, **crouch),
            kick(base, ch, 30, 2, **crouch), pose(base, **crouch)]),
        "standing_block": (False, [
            pose(base, dx=-2), block(base, dx=-4, rot=3, _gy=70), block(base, dx=-6, rot=5, _gy=70)]),
        "block_idle": (True, [block(base, dx=-6 - (i % 2), rot=5, _gy=70) for i in (0, 1, 2, 1)]),
        "jump": (False, [
            pose(base, sy=0.8, sx=1.05), pose(base, sy=1.04), pose(base, sy=1.02),
            pose(base), pose(base, sy=1.03), pose(base, sy=0.85, sx=1.05)]),
        "jump_punch": (False, [
            punch(base, sh, 20, rot=-3), punch(base, sh, 52, dx=6),
            punch(base, sh, 56, dx=6), punch(base, sh, 30)]),
        "jump_kick": (False, [
            kick(base, hp, 22, 8, rot=-4), kick(base, hp, 50, 30, rot=-12),
            kick(base, hp, 54, 32, rot=-14), kick(base, hp, 34, 14, rot=-6)]),
        "knocked_back_air": (False, [
            pose(base, dx=8, rot=14), pose(base, dx=20, rot=30),
            pose(base, dx=36, rot=48), pose(base, dx=48, rot=62)]),
        "fall_on_back": (False, [
            pose(base, sx=0.9, sy=0.9, dx=52, rot=72), pose(base, sx=0.9, sy=0.9, dx=60, rot=82),
            pose(base, sx=0.9, sy=0.9, dx=66, rot=90), pose(base, sx=0.9, sy=0.9, dx=66, rot=90)]),
    }


def quantized(strip):
    alpha = strip.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    flat = Image.new("RGB", strip.size, (255, 255, 255))
    flat.paste(strip.convert("RGB"), mask=alpha)
    reduced = flat.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    result = reduced.convert("RGBA")
    result.putalpha(alpha)
    return result


def write_sheet(directory, character, name, loop, frames):
    strip = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        strip.paste(frame, (i * FRAME, 0))
    strip = quantized(strip)
    stem = f"{character}_{name}_sheet"
    strip.save(directory / f"{stem}.png")
    meta = {
        "image": f"{stem}.png", "fps": FPS, "loop": loop,
        "frame_width": FRAME, "frame_height": FRAME, "frame_count": len(frames),
        "palette_colors": COLORS + 1, "placeholder": True, "animation": name,
        "frames": [{"x": i * FRAME, "y": 0, "width": FRAME, "height": FRAME} for i in range(len(frames))],
    }
    (directory / f"{stem}.json").write_text(json.dumps(meta, indent=2) + "\n")
    return stem


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--character", default="Bruiser")
    parser.add_argument("--directory", default="assets/spritesheets", type=Path)
    parser.add_argument("--only", nargs="*", help="Animation ids to (re)generate.")
    args = parser.parse_args()
    base = load_base(args.directory, args.character)
    for name, (loop, frames) in animations(base).items():
        if args.only and name not in args.only:
            continue
        print("wrote", write_sheet(args.directory, args.character, name, loop, frames))


if __name__ == "__main__":
    main()
