# Fighting game sprite pipeline

This repository contains a resumable 3D-to-2D sprite-sheet pipeline and the
Copilot skill at `.github\skills\sprite-sheet-generator\SKILL.md`.
Defaults are **Bruiser**, **idle**, **12 FPS**, **32 colors including transparency**,
and **512 x 512 pixels per frame**. Sprite sheets are horizontal PNG strips with
adjacent JSON timing and frame-rectangle metadata.

## Install

Use Python 3.12 or newer and **Blender 4.5 LTS**. Capture is version-checked because
Blender 5 changes the compositor API.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
winget install --id BlenderFoundation.Blender --exact --version 4.5.3 --source winget
```

If your configured Python package mirror fails on a wheel `.metadata` request,
retry with `pip install -r requirements.txt --use-deprecated=legacy-resolver`.
This installation workaround avoids the broken metadata request; do not disable
TLS certificate verification. If Blender's installer download returns HTTP 403,
installation remains blocked until a permitted download source is available.

In the existing, ignored `.env`, configure these variables without committing keys:

```dotenv
TRIPO_API_KEY=your_key_here
BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe
COMFYUI_URL=http://127.0.0.1:8188
```

`OPENAI_API_KEY` is not needed for this pipeline. Tripo uses its official 1.x SDK
and API v3 rather than the retiring API v2. Generation is opt-in: it uploads the
reference to Tripo and may incur charges. Task IDs are persisted locally so a
retry can resume without automatically paying for a new model.

## 1. Generate and cache the base mesh

Base generation needs an **orthographic T-pose reference** suitable for auto-rigging.
Bruiser's boxing-stance image is the identity reference, not a T-pose, so the
`tpose` stage asks Tripo to generate one (`assets\references\Bruiser_tpose.png`).
Pass `--tpose <path>` to use an existing T-pose image instead.

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py tpose --reference assets\references\Bruiser.png --allow-paid-api
.\.venv\Scripts\python.exe scripts\spritesheet.py base --allow-paid-api
```

The model is cached at `assets\shared_fbx_cache\Bruiser_base.fbx`. A nonempty cached
file bypasses the API entirely. Failed task IDs remain in `Bruiser_tasks.json`;
inspect the failure before deliberately removing that file to create another task.

## 2. Rig and animate

Mixamo has no public API, so the `animate` stage uses Tripo instead: it rigs the
cached base with a Mixamo-compatible biped skeleton and retargets a Tripo preset
animation (for example `preset:idle`), exporting a skinned, in-place FBX to
`assets\animations\Bruiser_idle.fbx`.

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py animate --allow-paid-api
```

For moves that are not Tripo presets, retarget the local
`assets\custom_moves\<move>.fbx` or `.bvh` onto the character in Blender/Rigify and
bake/export the combined skinned animation to
`assets\animations\<character>_<move>.fbx`, or specify it with `--animated`.
Automatic arbitrary-skeleton retargeting is not implemented.

## 3. Capture depth and pose

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py capture --frames 12 --azimuth 30
```

Blender captures the actual Z pass with a fixed depth range and projects skeleton
joints into OpenPose-style body maps. Camera scale and framing remain fixed across
the animation. Maps and a manifest are saved to `temp\Bruiser_idle\capture` (the
directory is cleared first). `--frames N` evenly resamples the whole loop to N
frames; otherwise frames are stepped at `--fps`. `--size` sets the capture
resolution (default 512). `--azimuth` rotates the camera; 30 gives a
three-quarter fighting-game view with both arms visible.
Use `--animated <path>` to select another baked animation.

Mixamo bone names are recognized with or without their namespace. Other skeletons
require `--bone-map <json>` mapping these keys to actual bone names:
`nose`, `neck`, `right_shoulder`, `right_elbow`, `right_wrist`, `left_shoulder`,
`left_elbow`, `left_wrist`, `right_hip`, `right_knee`, `right_ankle`, `left_hip`,
`left_knee`, `left_ankle`. Maps contain body joints, not fabricated face/hand detail.

## 4. Configure local ComfyUI and render

Install and start [ComfyUI](https://docs.comfy.org/installation) locally using its
instructions for your GPU. Install a compatible checkpoint, IP-Adapter and its
CLIP vision model, and depth/OpenPose ControlNet models. Model licenses, hardware
requirements and downloads must be checked before installing them.

`assets\workflows\sprites_api.json` is a working API-format workflow (output node
`19`) for DreamShaper 8, `ip-adapter-plus_sd15` with the ViT-H CLIP vision model,
and the `control_v11f1p_sd15_depth` / `control_v11p_sd15_openpose` ControlNets via
[ComfyUI_IPAdapter_plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus). Adjust
model filenames to match your installation, or build your own workflow that combines:

- An identity reference loaded into IP-Adapter.
- A depth image and a pose image applied through two ControlNets.
- A positive text prompt, a KSampler, and one single-image SaveImage output.

Export the workflow in **API format**. Replace the appropriate input values with
these exact strings (not substrings): `__REFERENCE__`, `__DEPTH__`, `__POSE__`,
`__PROMPT__`, and `__SEED__`. The runner supplies uploaded image names, the skill's
sprite prompt, and a stable integer seed. Record the SaveImage node's ID.

The workflow must genuinely wire IP-Adapter and both ControlNets into sampling;
the runner checks node types and placeholders, not the semantic correctness of
every possible custom graph.

Sprites must have **no shadows, floor, or background**. The supplied diffusion
workflow does not output transparency, so prompt a plain flat backdrop (it uses
white and negative-prompts shadows, floor, gradients and scenery); the `sheet`
stage then removes it. Use `--description` to append character details (colors,
outfit) to the prompt, then check them against the reference.

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py doctor
.\.venv\Scripts\python.exe scripts\spritesheet.py render --reference assets\references\Bruiser.png --workflow assets\workflows\sprites_api.json --output-node 19 --description "gold boxing gloves, gold boxing shorts, brown spiky hair, short beard"
```

The runner uses local `/upload/image`, `/prompt`, `/history`, and `/view` endpoints.
It reports execution failures and timeouts rather than substituting missing frames.
Frames are written to `temp\Bruiser_idle\renders`; retry rendering starts that
stage over. A timed-out ComfyUI prompt may still be queued: inspect it first.

## 5. Compile the sprite sheet

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py sheet --sprite-size 160
```

Background removal runs in two passes by default:

1. `--chroma-key auto` flood-fills the backdrop from the frame borders (within
   `--tolerance`, default 40), so interior highlights matching the backdrop survive.
   Pass an `RRGGBB` color to key a specific color everywhere instead.
2. Each render is masked to its captured 3D silhouette (depth-pass alpha) dilated by
   `--silhouette-pad` pixels (default 6; `-1` disables). The 3D capture has no
   shadows or ground, so floor shadows outside the padded silhouette are removed.

The compiler fails if any frame corner is still opaque, rejects empty frames, uses
a shared palette across the entire strip, and disables dithering.
`--sprite-size` sets the output frame size (box-downsampled from `--size`).
It writes `assets\spritesheets\Bruiser_idle_sheet.png` and `.json`, then removes
only this character/move's temporary directory after successful compilation.
Pass `--keep-temp` to retain intermediate images.

Once the model, animated export and ComfyUI workflow are ready, `run` executes
all stages with the same options. A cached base does not require the paid-API flag,
but uncached T-pose or animation stages still do.
Review the final loop visually: ControlNet and a fixed seed reduce drift, but
do not guarantee temporal consistency or a seamless idle transition.

## Local checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Checks cover workflow placeholders, pose maps, shared palette limits, frame
ordering, transparency and rejected inputs without contacting external services.
