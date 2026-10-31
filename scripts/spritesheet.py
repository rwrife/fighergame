"""Resumable Tripo -> animated FBX -> Blender -> ComfyUI sprite pipeline."""

import argparse
import asyncio
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlparse
import uuid

from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageDraw, ImageFilter
import requests


ROOT = Path(__file__).resolve().parents[1]
PROMPT = (
    "90s 2D fighting game arcade sprite, pixel art style, distinct dark outlines, "
    "cel-shaded, flat lighting, transparent background."
)


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Must be greater than zero.")
    return number


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise argparse.ArgumentTypeError("Use letters, digits, hyphens and underscores.")
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def blender_path():
    configured = os.getenv("BLENDER_EXE") or shutil.which("blender")
    if configured and Path(configured).is_file():
        return configured
    foundation = Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    installed = sorted(foundation.glob("Blender */blender.exe"))
    if installed:
        return str(installed[-1])
    raise RuntimeError("Blender not found. Install Blender and set BLENDER_EXE in .env.")


def local_comfy_url():
    url = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "localhost", "127.0.0.1", "::1"
    ):
        raise ValueError("COMFYUI_URL must point to a local ComfyUI server.")
    return url


def tpose_path(args):
    return args.tpose or ROOT / "assets" / "references" / f"{args.character}_tpose.png"


def animated_path(args):
    return args.animated or ROOT / "assets" / "animations" / (
        f"{args.character}_{args.animation}.fbx"
    )


def require_paid_api(args, action):
    if not args.allow_paid_api:
        raise RuntimeError(
            f"{action} uploads data to Tripo and uses credits. "
            "Inspect the input, then explicitly pass --allow-paid-api."
        )
    if not os.getenv("TRIPO_API_KEY"):
        raise RuntimeError("Set TRIPO_API_KEY in .env.")


async def tripo_session(args, work):
    """Run Tripo tasks whose IDs persist, so retries resume rather than repay."""
    from tripo3d import TripoClient
    from tripo3d.models import TaskStatus

    args.cache.mkdir(parents=True, exist_ok=True)
    state_path = args.cache / f"{args.character}_tasks.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    async with TripoClient() as client:
        async def task(stage, create):
            if stage not in state:
                state[stage] = await create()
                write_json(state_path, state)
            result = await client.wait_for_task(state[stage], timeout=1800, verbose=True)
            if result.status != TaskStatus.SUCCESS:
                raise RuntimeError(
                    f"Tripo {stage} failed: {result.status}; "
                    f"{result.error_code}: {result.error_msg}. "
                    f"Task ID is preserved in {state_path}; inspect before removing it."
                )
            return result

        async def fetch(result, target, suffix):
            downloads = Path(tempfile.mkdtemp(dir=args.cache))
            try:
                files = await client.download_task_models(result, str(downloads))
                path = next((Path(value) for value in files.values()
                             if value and Path(value).suffix.lower() == suffix
                             and Path(value).stat().st_size), None)
                if not path:
                    raise RuntimeError(f"Tripo returned no {suffix} output: {files}")
                target.parent.mkdir(parents=True, exist_ok=True)
                path.replace(target)
            finally:
                shutil.rmtree(downloads, ignore_errors=True)
            print(f"Saved {target}")

        return await work(client, task, fetch, state)


async def generate_tpose(args):
    target = tpose_path(args)
    if target.is_file() and target.stat().st_size:
        print(f"Reusing T-pose reference: {target}")
        return
    if not args.reference or not args.reference.is_file():
        raise ValueError("--reference must name an existing character image.")
    require_paid_api(args, "T-pose generation")

    async def work(client, task, fetch, state):
        # Tripo's content filter rejected descriptive prompts for this reference; the
        # t_pose flag carries the intent, so keep the prompt minimal.
        result = await task("tpose", lambda: client.generate_image(
            prompt="T-pose", file=str(args.reference), t_pose=True,
        ))
        url = result.output.image
        if not url:
            raise RuntimeError("Tripo T-pose task returned no image.")
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        temporary = target.with_suffix(".part")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(response.content)
        with Image.open(temporary) as image:
            image.convert("RGB").save(target, format="PNG")
        temporary.unlink()
        print(f"Saved {target}")

    await tripo_session(args, work)


async def generate_base(args):
    target = args.cache / f"{args.character}_base.fbx"
    if target.is_file() and target.stat().st_size:
        print(f"Reusing cached model: {target}")
        return
    reference = tpose_path(args)
    if not reference.is_file():
        raise ValueError(f"T-pose reference missing: {reference}. Run the tpose stage first.")
    require_paid_api(args, "Model generation")

    async def work(client, task, fetch, state):
        await task("generation", lambda: client.image_to_model(image=str(reference)))
        converted = await task(
            "conversion", lambda: client.convert_model(state["generation"], "FBX")
        )
        await fetch(converted, target, ".fbx")

    await tripo_session(args, work)


async def animate(args):
    """Automated rigging stand-in for Mixamo, which offers no public API."""
    target = animated_path(args)
    if target.is_file() and target.stat().st_size:
        print(f"Reusing animation: {target}")
        return
    from tripo3d.models import Animation

    preset = f"preset:{args.animation}"
    if preset not in {item.value for item in Animation}:
        raise RuntimeError(
            f"{args.animation} is not a Tripo preset. Retarget "
            f"assets/custom_moves/{args.animation}.fbx in Blender and save it to {target}."
        )
    base = args.cache / f"{args.character}_base.fbx"
    if not base.is_file():
        raise RuntimeError(f"Base model missing: {base}. Run the base stage first.")
    require_paid_api(args, "Rigging and animation")

    async def work(client, task, fetch, state):
        if "generation" not in state:
            await task("import", lambda: client.import_model(str(base)))
        source = state.get("generation") or state["import"]
        check = await task("rig_check", lambda: client.check_riggable(source))
        if not check.output.riggable:
            raise RuntimeError(f"Tripo cannot rig this model: {check.output.raw}")
        await task("rig", lambda: client.rig_model(
            source, out_format="fbx", rig_type="biped", spec="mixamo"
        ))
        result = await task(f"animation_{args.animation}", lambda: client.retarget_animation(
            state["rig"], preset, out_format="fbx",
            export_with_geometry=True, animate_in_place=True,
        ))
        await fetch(result, target, ".fbx")

    await tripo_session(args, work)


def capture(args):
    animated = animated_path(args)
    if not animated.is_file():
        raise RuntimeError(
            f"Animated FBX missing: {animated}. Run the animate stage, or export "
            "a skinned, baked FBX from Mixamo or Blender to that path."
        )
    capture_dir = args.work / "capture"
    shutil.rmtree(capture_dir, ignore_errors=True)
    command = [
        blender_path(), "-b", "--factory-startup", "--python-exit-code", "1",
        "-P", str(ROOT / "scripts" / "capture_frames.py"), "--",
        "--animated", str(animated.resolve()), "--output", str(capture_dir),
        "--fps", str(args.fps), "--size", str(args.size),
        "--azimuth", str(args.azimuth), "--frames", str(args.frames),
    ]
    if args.bone_map:
        command.extend(["--bone-map", str(args.bone_map.resolve())])
    subprocess.run(command, check=True, cwd=ROOT)
    manifest = json.loads((capture_dir / "manifest.json").read_text(encoding="utf-8"))
    for frame in manifest["frames"]:
        draw_pose(frame["joints"], args.size).save(capture_dir / frame["pose"])


def draw_pose(joints, size):
    edges = [
        ("neck", "right_shoulder"), ("neck", "left_shoulder"),
        ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
        ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
        ("neck", "right_hip"), ("right_hip", "right_knee"),
        ("right_knee", "right_ankle"), ("neck", "left_hip"),
        ("left_hip", "left_knee"), ("left_knee", "left_ankle"), ("neck", "nose"),
    ]
    # Standard OpenPose COCO limb colors.
    colors = [
        (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0),
        (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85),
        (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
        (0, 0, 255),
    ]
    pose = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(pose)
    radius = max(2, size // 128)
    for (first, second), color in zip(edges, colors):
        draw.line([tuple(joints[first]), tuple(joints[second])],
                  fill=color, width=radius * 2)
        for joint in (first, second):
            x, y = joints[joint]
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    return pose


def substitute(value, replacements):
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [substitute(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, replacements) for key, item in value.items()}
    return value


def validate_workflow(workflow, output_node):
    if not isinstance(workflow, dict) or not workflow:
        raise ValueError("Export a ComfyUI workflow in API format, not UI format.")
    for node in workflow.values():
        if not isinstance(node, dict) or "class_type" not in node or "inputs" not in node:
            raise ValueError("Each API node must have class_type and inputs.")
    serialized = json.dumps(workflow)
    for token in ("__REFERENCE__", "__DEPTH__", "__POSE__", "__PROMPT__", "__SEED__"):
        if f'"{token}"' not in serialized:
            raise ValueError(f"Workflow must contain the exact input placeholder {token}.")
    types = [node["class_type"].lower() for node in workflow.values()]
    if not any("ipadapter" in name for name in types):
        raise ValueError("Workflow must include IP-Adapter for reference identity.")
    if sum("controlnetapply" in name for name in types) < 2:
        raise ValueError("Workflow must apply both depth and pose ControlNets.")
    if output_node not in workflow or workflow[output_node]["class_type"] != "SaveImage":
        raise ValueError("--output-node must identify a SaveImage node.")


def render(args):
    if not args.reference or not args.reference.is_file():
        raise ValueError("--reference must name an existing identity reference image.")
    if not args.workflow or not args.workflow.is_file() or not args.output_node:
        raise ValueError("Rendering requires --workflow and --output-node.")
    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    validate_workflow(workflow, args.output_node)
    manifest_path = args.work / "capture" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest["frames"]:
        raise ValueError("Capture manifest contains no frames.")
    output = args.work / "renders"
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)
    url = local_comfy_url()
    with requests.Session() as session:
        def request(method, route, **kwargs):
            response = session.request(method, url + route, timeout=60, **kwargs)
            response.raise_for_status()
            return response

        def upload(path):
            with path.open("rb") as image:
                result = request(
                    "POST", "/upload/image",
                    files={"image": (f"{uuid.uuid4().hex}_{path.name}", image, "image/png")},
                    data={"type": "input", "overwrite": "false"},
                ).json()
            return "/".join(filter(None, [result.get("subfolder"), result["name"]]))

        request("GET", "/system_stats")
        reference = upload(args.reference)
        rendered = []
        for frame in manifest["frames"]:
            replacements = {
                "__REFERENCE__": reference,
                "__DEPTH__": upload(manifest_path.parent / frame["depth"]),
                "__POSE__": upload(manifest_path.parent / frame["pose"]),
                "__PROMPT__": ", ".join(filter(None, [PROMPT, args.description])),
                "__SEED__": args.seed,
            }
            prompt = substitute(copy.deepcopy(workflow), replacements)
            result = request("POST", "/prompt", json={"prompt": prompt}).json()
            if result.get("error") or result.get("node_errors"):
                raise RuntimeError(f"ComfyUI rejected workflow: {result}")
            prompt_id = result["prompt_id"]
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                history = request("GET", f"/history/{prompt_id}").json().get(prompt_id)
                if history:
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise RuntimeError(f"ComfyUI execution failed: {status}")
                    if status.get("completed"):
                        break
                time.sleep(2)
            else:
                raise TimeoutError(
                    f"ComfyUI prompt {prompt_id} timed out; it may still be queued. "
                    "Inspect the ComfyUI queue before retrying."
                )
            images = history.get("outputs", {}).get(args.output_node, {}).get("images", [])
            if len(images) != 1:
                raise RuntimeError("Selected SaveImage node must produce exactly one frame.")
            filename = f"{frame['index']:04d}.png"
            destination = output / filename
            response = request("GET", "/view", params=images[0])
            temporary = destination.with_suffix(".png.part")
            temporary.write_bytes(response.content)
            with Image.open(temporary) as image:
                image.verify()
            temporary.replace(destination)
            rendered.append(filename)
            print(f"Rendered {filename}")
        write_json(output / "manifest.json", {
            "fps": manifest["fps"], "frames": rendered,
        })


def remove_background(frame, key, tolerance, silhouette=None, pad=0):
    """Make key-colored (or border-connected, for key="auto") pixels transparent."""
    frame = frame.copy()
    alpha = frame.getchannel("A")
    if key == "auto":
        # Flood from the borders so interior highlights matching the backdrop survive.
        rgb = frame.convert("RGB")
        sentinel = (1, 2, 3)
        width, height = rgb.size
        step = max(1, min(width, height) // 32)
        seeds = [(x, y) for x in range(0, width, step) for y in (0, height - 1)]
        seeds += [(x, y) for y in range(0, height, step) for x in (0, width - 1)]
        for seed in seeds:
            if rgb.getpixel(seed) != sentinel:
                ImageDraw.floodfill(rgb, seed, sentinel, thresh=tolerance)
        cleared = Image.new("L", rgb.size)
        cleared.putdata([0 if pixel == sentinel else 255 for pixel in rgb.getdata()])
        alpha = ImageChops.multiply(alpha, cleared)
    elif key:
        cleared = Image.new("L", frame.size)
        cleared.putdata([
            0 if max(abs(r-key[0]), abs(g-key[1]), abs(b-key[2])) <= tolerance else 255
            for r, g, b, _ in frame.getdata()
        ])
        alpha = ImageChops.multiply(alpha, cleared)
    if silhouette is not None:
        # Keep only pixels near the captured 3D silhouette (drops floor shadows/strays).
        shape = silhouette.getchannel("A").resize(frame.size, Image.Resampling.NEAREST)
        shape = shape.point(lambda value: 255 if value else 0)
        if pad:
            shape = shape.filter(ImageFilter.MaxFilter(pad * 2 + 1))
        alpha = ImageChops.multiply(alpha, shape)
    frame.putalpha(alpha)
    return frame


def compile_sheet(directory, destination, colors, key, tolerance, size=None,
                  capture=None, pad=0):
    if not 2 <= colors <= 256:
        raise ValueError("Palette colors must be between 2 and 256, including transparency.")
    if not 0 <= tolerance <= 255:
        raise ValueError("Chroma-key tolerance must be between 0 and 255.")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["frames"]:
        raise ValueError("Render manifest contains no frames.")
    frames = []
    for index, name in enumerate(manifest["frames"]):
        if Path(name).name != name:
            raise ValueError("Frame names must not contain directory components.")
        with Image.open(directory / name) as image:
            frame = image.convert("RGBA")
        silhouette = None
        if capture:
            with Image.open(capture / f"{index:04d}_depth.png") as depth:
                silhouette = depth.convert("RGBA")
        if key or silhouette is not None:
            frame = remove_background(frame, key, tolerance, silhouette, pad)
        if size:
            # Box-filter downsampling yields chunky pixel clusters before quantizing.
            frame = frame.resize((size, size), Image.Resampling.BOX)
        if frame.getextrema()[3][0] != 0:
            raise ValueError(
                "Frame has no transparent pixels. Configure a flat chroma-key "
                "background in ComfyUI and pass --chroma-key RRGGBB."
            )
        corners = [(0, 0), (frame.width - 1, 0), (0, frame.height - 1),
                   (frame.width - 1, frame.height - 1)]
        if any(frame.getpixel(corner)[3] for corner in corners):
            raise ValueError(f"Frame {name} still has background at its corners.")
        if not frame.getbbox():
            raise ValueError("Chroma key removed the entire frame.")
        if frames and frame.size != frames[0].size:
            raise ValueError("Rendered frames must have equal dimensions.")
        frames.append(frame)
    width, height = frames[0].size
    atlas = Image.new("RGBA", (width * len(frames), height))
    for index, frame in enumerate(frames):
        atlas.paste(frame, (width * index, 0))
    # Learn one palette from opaque pixels, so colors stay consistent across frames.
    opaque = [(r, g, b) for r, g, b, a in atlas.getdata() if a >= 128]
    if not opaque:
        raise ValueError("No opaque pixels remain after masking.")
    samples = Image.new("RGB", (len(opaque), 1))
    samples.putdata(opaque)
    palette = samples.quantize(colors=colors-1, method=Image.Quantize.MEDIANCUT)
    rgb_palette = palette.getpalette()[:(colors-1)*3]
    palette_image = Image.new("P", (1, 1))
    entries = [tuple(rgb_palette[i:i+3]) for i in range(0, len(rgb_palette), 3)]
    entries.extend([entries[0]] * (256-len(entries)))
    palette_image.putpalette([component for entry in entries for component in entry])
    indexed = atlas.convert("RGB").quantize(
        palette=palette_image, dither=Image.Dither.NONE
    )
    # Pillow can select duplicate padding entries; map them to the real color indices.
    indices = {color: index for index, color in enumerate(entries[:colors-1])}
    lookup = [indices[color] for color in entries]
    indexed.putdata([
        lookup[value] if alpha >= 128 else 255
        for value, alpha in zip(indexed.getdata(), atlas.getchannel("A").getdata())
    ])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".png.part")
    indexed.save(temporary, format="PNG", transparency=255)
    with Image.open(temporary) as saved:
        if saved.size != atlas.size or len(saved.getcolors(256) or []) > colors:
            raise RuntimeError("Compiled sheet failed dimension or palette validation.")
    temporary.replace(destination)
    write_json(destination.with_suffix(".json"), {
        "image": destination.name, "fps": manifest["fps"], "loop": True,
        "frame_width": width, "frame_height": height,
        "frame_count": len(frames), "palette_colors": colors,
        "frames": [{"x": index * width, "y": 0, "width": width, "height": height}
                   for index in range(len(frames))],
    })
    print(f"Sprite sheet: {destination}")


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=[
        "doctor", "tpose", "base", "animate", "capture", "render", "sheet", "run",
    ])
    parser.add_argument("--character", type=identifier, default="Bruiser")
    parser.add_argument("--animation", type=identifier, default="idle")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--tpose", type=Path)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--cache", type=Path, default=ROOT / "assets" / "shared_fbx_cache")
    parser.add_argument("--animated", type=Path)
    parser.add_argument("--bone-map", type=Path)
    parser.add_argument("--fps", type=positive, default=12)
    parser.add_argument("--size", type=positive, default=512)
    parser.add_argument("--azimuth", type=float, default=0)
    parser.add_argument("--frames", type=int, default=0,
                        help="Resample the whole loop to N frames (0 = use --fps).")
    parser.add_argument("--colors", type=int, default=32)
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--output-node")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=positive, default=1800)
    parser.add_argument("--chroma-key", default="auto",
                        help="RRGGBB backdrop color, or 'auto' to flood-fill from the borders.")
    parser.add_argument("--tolerance", type=int, default=40)
    parser.add_argument("--silhouette-pad", type=int, default=6,
                        help="Mask renders to the captured silhouette dilated by N px (-1 = off).")
    parser.add_argument("--sprite-size", type=positive,
                        help="Output frame size in the sheet (default: --size).")
    parser.add_argument("--description", default="",
                        help="Character details (colors, outfit) appended to the render prompt.")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()
    args.work = ROOT / "temp" / f"{args.character}_{args.animation}"
    if not math.isfinite(args.azimuth):
        parser.error("--azimuth must be finite.")
    if args.frames < 0 or args.frames == 1:
        parser.error("--frames must be 0 or at least 2.")
    if args.chroma_key and args.chroma_key != "auto" and not re.fullmatch(
            r"[0-9a-fA-F]{6}", args.chroma_key):
        parser.error("--chroma-key must be six hexadecimal digits or 'auto'.")
    if args.chroma_key == "auto":
        key = "auto"
    else:
        key = tuple(bytes.fromhex(args.chroma_key)) if args.chroma_key else None
    if args.stage == "doctor":
        executable = blender_path()
        version = subprocess.run(
            [executable, "--version"], check=True, capture_output=True, text=True
        ).stdout.splitlines()[0]
        if not version.startswith("Blender 4.5."):
            raise RuntimeError(f"Capture requires Blender 4.5 LTS, found {version}.")
        print(f"Blender: {executable} ({version})")
        print(f"Tripo key configured: {bool(os.getenv('TRIPO_API_KEY'))}")
        response = requests.get(local_comfy_url() + "/system_stats", timeout=10)
        response.raise_for_status()
        print("ComfyUI: responsive")
        return
    if args.stage in ("tpose", "run"):
        asyncio.run(generate_tpose(args))
    if args.stage in ("base", "run"):
        asyncio.run(generate_base(args))
    if args.stage in ("animate", "run"):
        asyncio.run(animate(args))
    if args.stage in ("capture", "run"):
        capture(args)
    if args.stage in ("render", "run"):
        render(args)
    if args.stage in ("sheet", "run"):
        destination = ROOT / "assets" / "spritesheets" / (
            f"{args.character}_{args.animation}_sheet.png"
        )
        compile_sheet(args.work / "renders", destination, args.colors, key,
                      args.tolerance, args.sprite_size or args.size,
                      args.work / "capture" if args.silhouette_pad >= 0 else None,
                      max(0, args.silhouette_pad))
        if not args.keep_temp:
            # Only this invocation's character/move directory is eligible for cleanup.
            shutil.rmtree(args.work)


if __name__ == "__main__":
    main()
