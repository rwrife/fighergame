"""Local authoring contract for reference-derived levels; no network or paid calls."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "assets" / "workflows" / "reference_level.json"
REVIEWS = ("style", "sky_clean", "composition", "in_game")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def asset_path(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError("Asset paths must be nonempty relative paths.")
    path = (root / value).resolve()
    if Path(value).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Asset path escapes the level package: {value}")
    return path


def number(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return value


def integer(value, label, minimum, maximum):
    number(value, label, minimum, maximum)
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    return value


def initialize(reference, style_reference, target, world_width=None, camera_travel=None):
    workflow = read_json(WORKFLOW)
    defaults = copy.deepcopy(workflow["defaults"])
    viewport_width = defaults["viewport"][0]
    if world_width is not None:
        defaults["world_width"] = integer(world_width, "world_width", viewport_width, 32768)
    if camera_travel is not None:
        defaults["camera_travel"] = integer(camera_travel, "camera_travel", 0, 32768)
    if defaults["camera_travel"] > defaults["world_width"] - viewport_width:
        raise ValueError(
            "camera_travel cannot exceed world_width minus the viewport width; "
            "pass --camera-travel for a narrower world."
        )
    # Check both sources before creating any persistent job files.
    for path in (reference, style_reference):
        with Image.open(path) as image:
            image.verify()
    target.mkdir(parents=True, exist_ok=False)
    source = target / "source"
    source.mkdir()
    (source / ".gdignore").write_text("", encoding="utf-8")
    provenance = {"workflow_version": workflow["workflow_version"], "inputs": {}}
    for name, path in (("reference", reference), ("style_reference", style_reference)):
        destination = source / f"{name}{path.suffix.lower()}"
        shutil.copyfile(path, destination)
        provenance["inputs"][name] = {
            "file": str(destination.relative_to(target)),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    provenance["generation"] = []
    provenance["render_settings"] = {}
    write_json(source / "provenance.json", provenance)
    layers = defaults.pop("layers")
    for layer in layers:
        layer["image"] = layer["id"] + ".png"
    manifest = {
        "schema_version": 1,
        "workflow_version": workflow["workflow_version"],
        **defaults,
        "sky": {"image": "sky.png", "factor": 0.0, "z": -100},
        "palette": "palette.json",
        "layers": layers,
        "props": [],
        "review": dict.fromkeys(REVIEWS, False),
    }
    write_json(target / "level.json", manifest)
    write_json(target / "palette.json", {"colors": []})
    write_json(target / "prompts.json", {
        "workflow_version": workflow["workflow_version"],
        "canvas": defaults,
        "prompts": workflow["prompts"],
    })
    width, height = defaults["viewport"]
    guide = Image.new("RGB", (width, height), (61, 48, 86))
    draw = ImageDraw.Draw(guide)
    zone = round(height * (1 - defaults["decoration_zone_fraction"]))
    lane = round(height * (1 - defaults["play_area_fraction"]))
    baseline = round(height * defaults["feet_baseline_fraction"])
    draw.rectangle((0, zone, width - 1, lane - 1), fill=(76, 116, 69))
    draw.rectangle((0, lane, width - 1, height - 1), fill=(161, 105, 54))
    draw.line((0, baseline, width - 1, baseline), fill=(255, 226, 92), width=2)
    draw.text((12, 12), "FIXED SKY + PARALLAX SCENERY (guide only, not artwork)", fill="white")
    draw.text((12, zone + 8), "DECORATION ZONE - keep fighters readable", fill="white")
    draw.text((12, lane + 8), "PROTECTED FLAT LANE - no props or scenery alpha", fill="white")
    guide.save(target / "layout.png")
    return manifest


def load_image(root, name, expected_size, palette, *, allow_empty=False):
    with Image.open(asset_path(root, name)) as source:
        image = source.convert("RGBA")
    if image.size != expected_size:
        raise ValueError(f"{name}: expected {expected_size}, got {image.size}.")
    if image.getchannel("A").getbbox() is None and not allow_empty:
        raise ValueError(f"{name}: empty image; omit optional props instead.")
    for _, (red, green, blue, alpha) in image.getcolors(image.width * image.height):
        if alpha not in (0, 255):
            raise ValueError(f"{name}: alpha must be binary, with no matte fringes.")
        if alpha and (red, green, blue) not in palette:
            raise ValueError(f"{name}: opaque color is outside the approved shared palette.")
    return image


def validate(root, release=False):
    manifest = read_json(root / "level.json")
    if (
        integer(manifest["schema_version"], "schema_version", 1, 1) != 1
        or integer(manifest["workflow_version"], "workflow_version", 1, 1) != 1
    ):
        raise ValueError("Unsupported level/workflow version.")
    if len(manifest["viewport"]) != 2:
        raise ValueError("viewport must contain width and height.")
    width, height = [
        integer(value, "viewport dimension", 1, 8192) for value in manifest["viewport"]
    ]
    world = integer(manifest["world_width"], "world_width", width, 32768)
    travel = integer(manifest["camera_travel"], "camera_travel", 0, world - width)
    lane_fraction = number(manifest["play_area_fraction"], "play_area_fraction", .10, .30)
    zone_fraction = number(
        manifest["decoration_zone_fraction"], "decoration_zone_fraction", lane_fraction, .30
    )
    lane_top = round(height * (1 - lane_fraction))
    if lane_top >= height or round(height * (1 - zone_fraction)) > lane_top:
        raise ValueError("Lane/decoration zone has no usable height.")
    number(manifest["feet_baseline_fraction"], "feet_baseline_fraction", 1 - lane_fraction, 1)
    baseline = round(height * manifest["feet_baseline_fraction"])
    if not lane_top <= baseline < height:
        raise ValueError("Feet baseline must lie inside the visible protected lane.")
    budget = integer(
        manifest["palette_colors_including_transparency"], "palette budget", 2, 32
    )
    colors = read_json(asset_path(root, manifest["palette"]))["colors"]
    palette = set()
    for color in colors:
        if not isinstance(color, list) or len(color) != 3:
            raise ValueError("Palette colors must be RGB integer triples.")
        palette.add(tuple(integer(channel, "palette channel", 0, 255) for channel in color))
    if not palette or len(palette) != len(colors) or len(palette) >= budget:
        raise ValueError("Palette needs unique opaque colors and one reserved transparent entry.")
    sky = manifest["sky"]
    if number(sky["factor"], "sky factor", 0, 2) != 0 or sky["z"] != -100:
        raise ValueError("Sky must be screen-locked at factor 0 and z -100.")
    images = {"sky": load_image(root, sky["image"], (width, height), palette)}
    if images["sky"].getchannel("A").getextrema() != (255, 255):
        raise ValueError("Sky lightbox must be fully opaque.")
    expected = {layer["id"]: layer for layer in read_json(WORKFLOW)["defaults"]["layers"]}
    layers = manifest["layers"]
    if len(layers) != len(expected) or {layer["id"] for layer in layers} != set(expected):
        raise ValueError("Exactly far_background, midground, ground and foreground are required.")
    for layer in layers:
        identity = layer["id"]
        factor = number(layer["factor"], f"{identity} factor", 0, 2)
        if factor != expected[identity]["factor"] or layer["z"] != expected[identity]["z"]:
            raise ValueError(f"{identity}: factor/z differs from the locked workflow.")
        if world < width + math.ceil(travel * factor):
            raise ValueError(f"{identity}: artwork too narrow for the full parallax travel.")
        image = load_image(root, layer["image"], (world, height), palette,
                           allow_empty=identity == "foreground")
        alpha = image.getchannel("A")
        if identity == "ground":
            if alpha.crop((0, lane_top, world, height)).getextrema() != (255, 255):
                raise ValueError("Ground must fill the entire flat lane, with no holes.")
            if alpha.crop((0, 0, world, lane_top)).getbbox():
                raise ValueError("Ground top must be straight at the lane boundary.")
        elif alpha.crop((0, lane_top, world, height)).getbbox():
            raise ValueError(f"{identity}: scenery intrudes into the protected lane.")
        images[identity] = image
    identifiers = set()
    for prop in manifest["props"]:
        identity = prop["id"]
        if not isinstance(identity, str) or not identity or identity in identifiers:
            raise ValueError("Prop instance IDs must be unique nonempty strings.")
        identifiers.add(identity)
        if prop["layer"] not in ("far_background", "midground", "foreground"):
            raise ValueError(f"{identity}: props cannot be attached to sky or ground.")
        if prop.get("collision") is not False:
            raise ValueError(f"{identity}: decorative props must explicitly disable collision.")
        size = tuple(integer(value, "prop dimension", 1, 8192) for value in prop["size"])
        if len(size) != 2 or len(prop["position"]) != 2:
            raise ValueError(f"{identity}: size/position must each contain two values.")
        integer(prop["position"][0], "prop x", 0, world - size[0])
        y = integer(prop["position"][1], "prop y", 0, height - size[1])
        image = load_image(root, prop["image"], size, palette)
        bounds = image.getchannel("A").getbbox()
        if y + bounds[3] > lane_top:
            raise ValueError(f"{identity}: prop intrudes into the protected lane.")
        # Positions are sprite top-left in world artwork coordinates; pivot is local.
        if len(prop["pivot"]) != 2:
            raise ValueError(f"{identity}: pivot must contain two values.")
        for pivot, extent in zip(prop["pivot"], size):
            integer(pivot, "prop pivot", 0, extent - 1)
        images["prop:" + identity] = image
    if set(manifest["review"]) != set(REVIEWS) or any(
        not isinstance(value, bool) for value in manifest["review"].values()
    ):
        raise ValueError("All four review gates must be explicit booleans.")
    if release and not all(manifest["review"].values()):
        raise ValueError("Release blocked: style, sky_clean, composition and in_game reviews required.")
    return manifest, images


def compose(manifest, images, camera_x, actors=()):
    """Composite one camera position; actors are (sprite, (x, y)) drawn at z 0, above the floor."""
    width, height = manifest["viewport"]
    number(camera_x, "camera_x", 0, manifest["camera_travel"])
    output = images["sky"].copy()
    pending = list(actors)
    for layer in sorted(manifest["layers"], key=lambda item: item["z"]):
        if layer["z"] > 0:
            for sprite, position in pending:
                output.alpha_composite(sprite, position)
            pending = []
        offset = round(
            -(manifest["world_width"] - width) / 2
            - (camera_x - manifest["camera_travel"] / 2) * layer["factor"]
        )
        canvas = images[layer["id"]].copy()
        for prop in manifest["props"]:
            if prop["layer"] == layer["id"]:
                canvas.alpha_composite(images["prop:" + prop["id"]], tuple(prop["position"]))
        # The visible window is always inside the artwork, so crop it explicitly.
        output.alpha_composite(canvas.crop((-offset, 0, -offset + width, height)))
    for sprite, position in pending:
        output.alpha_composite(sprite, position)
    return output


def load_fighter(sheet_path):
    """First frame of a sprite-sheet JSON, trimmed to its opaque bounds."""
    sheet = read_json(sheet_path)
    frame = sheet["frames"][0]
    with Image.open(asset_path(sheet_path.parent, sheet["image"])) as source:
        sprite = source.convert("RGBA").crop(
            (frame["x"], frame["y"], frame["x"] + frame["width"], frame["y"] + frame["height"])
        )
    bounds = sprite.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"{sheet_path}: the first fighter frame is empty.")
    return sprite.crop(bounds)


def preview(root, output, fighter=None):
    manifest, images = validate(root)
    if output.suffix.lower() != ".png":
        raise ValueError("Preview output must be a PNG.")
    protected = [
        root / "level.json", root / "prompts.json", root / "layout.png",
        asset_path(root, manifest["palette"]),
        asset_path(root, manifest["sky"]["image"]),
        *(asset_path(root, layer["image"]) for layer in manifest["layers"]),
        *(asset_path(root, prop["image"]) for prop in manifest["props"]),
    ]
    if output.resolve() in {path.resolve() for path in protected}:
        raise ValueError("Preview cannot overwrite a manifest or input asset.")
    if output.resolve().is_relative_to((root / "source").resolve()):
        raise ValueError("Preview cannot overwrite source provenance or reference assets.")
    width, height = manifest["viewport"]
    actors = []
    if fighter is not None:
        sprite = load_fighter(fighter)
        baseline = round(height * manifest["feet_baseline_fraction"])
        if sprite.height > baseline or sprite.width * 2 > width:
            raise ValueError("Fighter sprite does not fit the stage viewport above the feet baseline.")
        top = baseline - sprite.height
        actors = [
            (sprite, (round(width * 0.30) - sprite.width // 2, top)),
            (ImageOps.mirror(sprite), (round(width * 0.70) - sprite.width // 2, top)),
        ]
    strip = Image.new("RGBA", (width * 3, height))
    for index, camera in enumerate((0, manifest["camera_travel"] / 2, manifest["camera_travel"])):
        strip.paste(compose(manifest, images, camera, actors), (index * width, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a local draft; no images are generated.")
    init.add_argument("--reference", type=Path, required=True)
    init.add_argument("--style-reference", type=Path, required=True)
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--world-width", type=int, help="Override the default world artwork width.")
    init.add_argument("--camera-travel", type=int, help="Override the default horizontal camera travel.")
    check = commands.add_parser("validate")
    check.add_argument("--level", type=Path, required=True)
    check.add_argument("--release", action="store_true")
    render = commands.add_parser("preview")
    render.add_argument("--level", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument(
        "--fighter", type=Path,
        help="Sprite-sheet JSON; two copies of its first frame are drawn on the feet baseline.",
    )
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.reference, args.style_reference, args.output,
                       args.world_width, args.camera_travel)
            print(f"Draft initialized at {args.output}; artwork and reviews are still required.")
        elif args.command == "validate":
            validate(args.level, args.release)
            print("Release contract valid." if args.release else "Technical contract valid; not a release approval.")
        else:
            preview(args.level, args.output, args.fighter)
            print(f"Saved left/center/right camera preview: {args.output}")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Level pipeline failed: {error}\n")


if __name__ == "__main__":
    main()
