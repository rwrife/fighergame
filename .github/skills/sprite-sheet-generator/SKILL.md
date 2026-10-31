---
name: sprite-sheet-generator
description: Automates the creation of 90s-style 2D fighting game sprite sheets using a 3D-to-2D rotoscoping pipeline with local Python scripts, headless Blender rendering, and AI image generation APIs.
---

# Skill: SpriteSheetGenerator

Create 90s-style fighting game sprites using the repository's full
Tripo 3D -> Blender capture -> ComfyUI -> Pillow pipeline. Use
`scripts\spritesheet.py` and see `README.md` for setup; do not substitute a
2D-only generation when a full 3D workflow is requested.

## Parameters and prerequisites

- Choose `--character`, `--animation`, and the original identity `--reference`.
  The original image and the separate orthographic T-pose used for mesh
  generation are different inputs; a fighting stance is not a T-pose.
- Defaults are Bruiser, idle, 12 FPS, 512 x 512 capture/render input, and
  32 colors including transparency. `--frames` chooses a fixed number of
  samples, `--sprite-size` chooses the final per-frame size, and `--colors`
  changes the palette limit. `--cache` selects the shared FBX and task cache.
- Use the repository's Python environment, Blender **4.5 LTS**, and a local
  ComfyUI server. Configure `TRIPO_API_KEY`, `BLENDER_EXE`, and `COMFYUI_URL`
  in the ignored `.env`; never print or commit its contents. Run
  `.\.venv\Scripts\python.exe scripts\spritesheet.py doctor` to check the
  Blender version, whether a Tripo key is configured, and server responsiveness.
  This does not verify the key, GPU, installed models, or workflow wiring.
- Get explicit approval before uploading references or using paid Tripo
  operations. Uncached paid stages require `--allow-paid-api`. Reuse existing
  assets and persisted task IDs instead of paying to regenerate them.

### ComfyUI setup lessons

- Install a compatible checkpoint, IP-Adapter, its CLIP vision model, both
  depth and OpenPose ControlNets, and `ComfyUI_IPAdapter_plus`. The supplied
  `assets\workflows\sprites_api.json` was used with
  `DreamShaper_8_pruned.safetensors`, `ip-adapter-plus_sd15.safetensors`,
  `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`,
  `control_v11f1p_sd15_depth_fp16.safetensors`, and
  `control_v11p_sd15_openpose_fp16.safetensors`. Match workflow filenames to
  the installed models and check their licenses.
- On the tested Windows ARM64 machine, ComfyUI used a separate native ARM64
  Python 3.12 environment and NVIDIA CUDA PyTorch `2.15.0+cu134` with
  torchvision `0.29.0+cu134`, obtained from NVIDIA's
  `https://pypi.nvidia.com/nvtorch_oot/` index. Select packages compatible
  with the actual Python architecture, GPU, and driver; an emulated x64
  repository environment does not establish that ComfyUI can use the GPU.
  When GPU acceleration is expected, check it from the ComfyUI directory with
  `.\venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"`.
- That machine's ComfyUI 0.43.0 installation used mirror-available frontend
  1.57.5, templates 0.11.96, and embedded docs 0.5.14 instead of its original
  pins. These local dependency adjustments are not part of this repository;
  prefer compatible, approved packages for the ComfyUI version being installed.
- The prior machine encountered Windows Application Control blocks on SciPy
  and PyAV DLLs. Its successful run used SciPy 1.16.3 and nonstandard local
  PyAV and image-loader changes outside this repository; those are not a
  portable or supported setup and may be lost on updates. If security policy
  blocks a dependency, use administrator-approved binaries or ask the
  administrator; do not disable security controls, stub dependencies, or
  silence load errors. If a package mirror fails on wheel metadata, the
  README documents a legacy-resolver retry; do not disable TLS verification.
- Start ComfyUI listening locally, for example from its installation directory:

  ```powershell
  .\venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
  ```

  The pipeline accepts only a localhost `COMFYUI_URL`.

## Workflow

The commands below reproduce the Bruiser idle run in PowerShell. Substitute the
character, animation, and paths for other requests, and preserve the same
character/animation options across stages. The `run` stage also executes all
stages in sequence, but may invoke paid T-pose or animation generation even
when the base mesh is cached. Use the individual stages to inspect their
outputs and costs before proceeding.

### 1. Generate or reuse the T-pose and base mesh

Check `assets\shared_fbx_cache\{character}_base.fbx` first. If it exists and is
nonempty, the `base` stage reuses it. Otherwise obtain an orthographic T-pose:
the `tpose` stage uses the original image with Tripo's T-pose generation, while
`--tpose <path>` selects an existing T-pose instead. Keep the original image
for IP-Adapter. The Tripo SDK 1.x pipeline uses API v3 and a minimal `T-pose`
request with its T-pose option.

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py tpose --character Bruiser --reference assets\references\Bruiser.png --allow-paid-api
.\.venv\Scripts\python.exe scripts\spritesheet.py base --character Bruiser --allow-paid-api
```

The default T-pose is `assets\references\{character}_tpose.png`. Pass a custom
`--tpose` to `base` when using a different file. Tripo task IDs are persisted in
`assets\shared_fbx_cache\{character}_tasks.json`; inspect a failed task and
its cost implications before deliberately replacing it. Do not blindly delete
task state or retry a rejected request. Confirm cached assets and task IDs
belong to the intended reference before reusing a character name.

### 2. Rig and animate with Tripo

Mixamo does not provide the automated API assumed by the original workflow.
The `animate` stage instead checks riggability, creates a Mixamo-compatible
biped rig through Tripo, and retargets a supported Tripo preset such as
`preset:idle`. It exports the skinned animation in place to
`assets\animations\{character}_{animation}.fbx` and reuses an existing file.

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py animate --character Bruiser --animation idle --allow-paid-api
```

For an unsupported custom move, manually retarget and bake the animation in
Blender and export a skinned FBX to that output path, or select it with
`--animated <path>`. Automatic custom-move retargeting is not implemented.

### 3. Capture depth and pose in Blender

The `capture` stage invokes `scripts\capture_frames.py` headlessly, fits one
orthographic camera over the motion, renders a transparent Z-depth pass with
a tight character depth range, and projects the rig's joints into OpenPose-style
maps. It writes the maps and manifest to `temp\{character}_{animation}\capture`.
The capture directory is cleared at the start of every capture.

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py capture --character Bruiser --animation idle --frames 12 --size 512 --azimuth 30
```

Bruiser's original animation produced 184 samples at the default sampling
rate; `--frames 12` evenly samples the entire loop without duplicating its
endpoint. It does not change `--fps`, which determines playback timing in the
sheet metadata. Pass a different `--fps` to `capture`; `sheet` reads the
captured timing. `--azimuth 30` gave Bruiser a three-quarter view with both
arms visible; adjust it for other models. Use `--bone-map <json>` for rigs
whose bone names do not match the supported Mixamo names. Inspect the depth
and pose maps before rendering. Keep `--size 512` with the supplied workflow:
its latent image is fixed at 512 x 512, so another size requires updating the
workflow as well.

### 4. Render with local ComfyUI

Use the supplied API-format workflow and SaveImage node `19`, or provide a
verified equivalent. It must connect the original identity reference through
IP-Adapter and apply both depth and OpenPose ControlNets before sampling.
The supplied workflow uses IP-Adapter weight 1.0, depth strength 0.9,
pose strength 0.8, and a fixed seed (default 42). The runner checks node types
and exact `__REFERENCE__`, `__DEPTH__`, `__POSE__`, `__PROMPT__`, and
`__SEED__` placeholders, but does not prove that the graph is wired correctly.
Its additional prompt specifies a single full-body character facing right;
adjust it when another orientation is required.

The supplied workflow outputs opaque frames, not actual transparency. Prompt a
plain flat white background with no shadow, floor, ground, or scenery, and
negative-prompt shadows, gradients, scenery, and vignettes. Include distinctive
colors and outfit details with `--description` to reduce identity drift:

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py render --character Bruiser --animation idle --reference assets\references\Bruiser.png --workflow assets\workflows\sprites_api.json --output-node 19 --description "gold boxing gloves, gold boxing shorts, brown spiky hair, short beard, olive green boots, bare muscular chest"
```

Renders go to `temp\{character}_{animation}\renders`, which is cleared when
rendering starts. If a ComfyUI prompt times out, inspect its queue before
retrying; it may still be running. Descriptions and a fixed seed improve
consistency but do not guarantee it: Bruiser's gloves improved to gold while
some shorts and boots still drifted blue.

### 5. Remove backgrounds, compile, and verify

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py sheet --character Bruiser --animation idle --size 512 --sprite-size 160 --keep-temp
```

The default `--chroma-key auto` flood-fills from frame borders with
`--tolerance 40`, preserving disconnected interior highlights. The compiler
then masks each render with the matching depth-pass alpha, dilated by
`--silhouette-pad 6` pixels at render resolution. This removes backdrop,
floor shadows, and stray pixels outside that silhouette. It box-downsamples,
quantizes all frames to one palette, and writes the horizontal PNG and JSON
timing/rectangles to `assets\spritesheets\{character}_{animation}_sheet.*`.

The compiler rejects empty or opaque frames and nontransparent corners, but
corners alone do not prove that every shadow or remnant is gone: artifacts can
remain inside the padded silhouette, and an overly tight mask can crop the
character. Inspect every frame on both light and dark backgrounds, check the
requested colors and silhouette, and preview the loop for drift, clipping, and
timing. If any backdrop, shadow, or stray mark remains, adjust the render or
mask and recompile; do not deliver the sheet as clean until verified. Compare
the output and JSON frame count, dimensions, and FPS with the request.

`--keep-temp` retains intermediates for inspection. Without it, successful sheet
compilation removes only `temp\{character}_{animation}`; never clear unrelated
characters' work.
