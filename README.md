# Fighting game sprite pipeline

## Godot animation test template

Open the root `project.godot` in **Godot 4.3 or newer** and press **F6** on
`scenes/animation_lab.tscn`, or **F5** to run the project. This is a minimal 2D
animation viewer, not a combat game: it starts with the bright Mixamo Bruiser idle
loop, using nearest-neighbor filtering to keep the sprites crisp.

Select an animation, adjust playback speed and zoom, or flip its facing with the
on-screen controls. **Space** plays/pauses, **Right** pauses and advances one
frame, and **R** restarts the selected animation. Clicking **Next frame** does
the same thing; looping animations wrap, while non-looping ones stop on their
last frame.

The viewer discovers `assets\spritesheets\*_sheet.json` at startup and builds
`AnimatedSprite2D` animations from each file's `image`, `fps`, `loop`, and
`frames` rectangles. To test another move, copy its generated PNG and matching
JSON there and restart the scene. Sheets marked `archived: true` are skipped, so
historical AI comparisons do not enter the active animation picker.
Invalid sheets are reported both on screen
and in Godot's debugger. Raw FBX animation/cache and reference-image folders are
excluded from Godot import; the viewer only needs the compiled sprites.

For a packaged build, include `assets/spritesheets/*.json` in the export preset's
non-resource file filter, and include all sprite-sheet PNG resources. No export
preset or gameplay systems are configured yet.

Run the viewer smoke check after importing the project (replace `godot` with
your Godot executable path if it is not on `PATH`):

```powershell
godot --headless --editor --path . --import
godot --headless --path . --script tests\test_animation_lab.gd
```

This repository contains a resumable 3D-to-2D sprite-sheet pipeline and the
Copilot skill at `.github\skills\sprite-sheet-generator\SKILL.md`.
Defaults are **Bruiser**, **idle**, **8 FPS**, **32 colors including transparency**,
and **cel-shaded rendering only**. The Mixamo demo uses 192 x 192 frames;
`--sprite-size` chooses the native output resolution. Sprite sheets are horizontal PNG strips with
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
```

ComfyUI and `OPENAI_API_KEY` are not needed. Tripo uses its official 1.x SDK
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
New models request `face_limit=20000` at generation and conversion. Blender then
checks the actual total mesh polygon count before the FBX enters the cache.
Over-budget output is rejected without automatically purchasing another model.
Older cached Bruiser assets are preserved; the new budget does not silently
decimate or replace them.

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
bake/export the combined skinned animation to that path first. Automatic
arbitrary-skeleton retargeting is not implemented.

## Optional: inspect depth and pose

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

## 3. Render sprites

### Deterministic shader rendering (no AI)

With the cached animated FBX available, this single stage renders and compiles a
separate sheet without Tripo, ComfyUI, reference uploads, or paid API calls:

```powershell
.\.venv\Scripts\python.exe scripts\spritesheet.py render --fps 8 --azimuth 30 --sprite-size 160
```

This reuses the fixed camera and animation sampling, preserves FBX base-color
textures, and replaces material lighting with four bright normal-based shading
bands (0.60, 0.78, 0.93, 1.00) and a 1.10 saturation/value boost.
Rendering happens directly at the sprite resolution with a fixed single sample,
then binary transparency, a one-pixel dark outline, and one shared undithered
palette are applied. There is no diffusion or randomized frame generation.
Geometry, texture defects, and shading changes caused by moving normals remain;
this is stylized 3D pixel art, not a hand-drawn reconstruction of the reference.
Reproducibility assumes the same FBX, options, Blender version, and rendering hardware.

Output is `assets\spritesheets\Bruiser_idle_retro_sheet.png` and adjacent JSON.
Historical AI sheets are retained as archived comparisons, not active animations.
Retro temporary files use a separate character/move directory.
`retro` is an alias for the same renderer. `run` prepares the cached model and
animation, then renders cel-shaded sprites; neither path calls ComfyUI.
`doctor` checks Blender without requiring an AI server.

To compare both idle loops in a browser:

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/demos/bruiser_idle.html`. The demo includes playback,
frame stepping, speed, and facing controls. Stop the server with Ctrl+C when done.

## Mixamo move and transition demo

Open `http://127.0.0.1:8765/demos/bruiser_moves.html` using the local server above.
The **Transition lab** runs the shader-rendered Mixamo Fighting Idle, Jumping
(Jumping From Action Idle), and Punching (Jab Punch) clips. **J** jumps and **P**
punches. The active clips are resampled at **8 FPS**, preserving source motion
duration: 27 idle frames, 16 jump frames, and 9 punch frames. One-shot clips play through landing/recovery and return to idle.
Requests during an action queue the newest move and pass through two idle frames.
Pause and frame stepping allow inspection of each switch. These are sprite hard
cuts, not runtime skeletal blends; **Reset to idle** deliberately cancels a move.

**Archived punch comparison** preserves the earlier AI/cel-shaded comparison on
the same 13 poses, now replayed at 8 FPS. It is not regenerated and does not use
the newly brightened shader. Open it directly
with `demos/bruiser_moves.html?mode=compare`. The three shader sheets use one palette
learned across the entire move set; the AI punch uses its own shared frame palette.
The original animated FBX is unchanged. Historical idle sheets are also replayed
at 8 FPS and excluded from the active Godot picker.

Mixamo has no public animation-download API. The source clips in
`assets\animations\mixamo` were downloaded through the signed-in Mixamo website
on Bruiser's existing character, as FBX Binary, **With Skin**, **30 FPS**, with no
keyframe reduction. That site's character has no textures and a different skeleton
orientation; its geometry is not used for rendering. `scripts\mixamo_demo.py`
transfers rotation deltas onto the textured rig, aligns facing using the shoulder
line, preserves target bone lengths, scales hip movement by leg length, and
keeps jump elevation while removing the initial horizontal offset.
It supports this named Mixamo biped, not arbitrary skeletons. Adobe's
[Mixamo licensing FAQ](https://community.adobe.com/questions-696/mixamo-faq-licensing-royalties-ownership-eula-and-tos-589400)
prohibits free distribution of raw animation files. The downloaded FBXs and
editable `Bruiser_mixamo.blend` are therefore ignored and remain local; they are
not included in this public repository. Download the three clips yourself to
rebuild them. The finished sprite sheets and browser demo remain available.

To rebuild locally, download **Fighting Idle** (Male Fight Idle Boxing Stance),
**Jumping** (Jumping From Action Idle), and **Punching** (Jab Punch) from Mixamo
using the settings above. Save them as `assets\animations\mixamo\fighting_idle.fbx`,
`jump.fbx`, and `punch.fbx`, respectively. Set `$env:BLENDER_EXE` to your Blender
4.5 executable, then run:

```powershell
& $env:BLENDER_EXE -b --factory-startup --python-exit-code 1 -P scripts\mixamo_demo.py -- --character assets\animations\Bruiser_idle.fbx --idle assets\animations\mixamo\fighting_idle.fbx --jump assets\animations\mixamo\jump.fbx --punch assets\animations\mixamo\punch.fbx --output temp\Bruiser_mixamo --blend assets\animations\Bruiser_mixamo.blend
.\.venv\Scripts\python.exe scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_mixamo\manifest.json
```

The Blender stage saves packed, baked actions before applying the sprite shader.
It fits one camera over all three clips, so jumping never triggers a per-move
resize or recenter. Idle loops; jump and punch include their final recovery pose
and have `loop: false`. Both the browser and existing Godot viewer read those
flags from generated metadata.
The optional Blender retarget tests require those local Mixamo files and the
generated `.blend`; they are skipped until those inputs are present.

## Transition strategy

Use **offline skeletal blending, then crisp runtime sprite switches**. Never
alpha-crossfade the sprite images: overlapping limbs look like ghosting.
This strategy is planned; the current lab still uses hard cuts and a simple queue.

| Surface | Strategy |
|---|---|
| Common pose | Author a canonical boxing guard and match each grounded clip's entry and exit to it. Match an idle phase to that guard rather than always jumping to idle frame zero. |
| Mismatched poses | Bake a short 3D bridge in Blender, using quaternion rotation interpolation and root-position interpolation with planted-foot constraints. Render it with the same camera, palette, and bright shader. |
| Timing | At 8 FPS, one frame is 125 ms. Prefer matching-pose cuts; use one bridge frame only where needed. Two bridge frames cost 250 ms, so do not add them to every attack's startup. Longer settles belong to explicit recovery or landing states. |
| Punch | Split startup, active, and recovery. Start promptly from guard, protect active frames from ordinary cancellation, then return to guard or enter an explicitly allowed cancel. |
| Jump | Separate anticipation, airborne, and landing phases. For a game, drive vertical displacement from physics and choose ascent/apex/descent poses from motion; do not let imported root translation and game physics both apply jump height. |
| Input | Use a short expiring buffer (initial target: 200 ms), consumed only in allowed transition windows. Track expiry in simulation time, independently of sprite frames, and keep input updates faster than the 8 FPS visual cadence. Define cancel rules before adding combat or airborne chaining. |

The first authoring pass should cover guard-to-punch and punch-to-guard, then
guard-to-jump and landing-to-guard. Compare joint discontinuities, foot sliding,
silhouette changes, and added input latency. Shared framing and palette are
already implemented; baked bridges, phase metadata, input expiry, and
physics-driven jumps are not.

## Local checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests\test_animation_player.mjs
```

Checks cover workflow placeholders, pose maps, shared palette limits, frame
ordering, transparency and rejected inputs without contacting external services.
The JavaScript checks cover idle looping, final action frames, queued moves,
recovery boundaries, frame stepping, and resets. For the Blender retarget checks:

```powershell
& $env:BLENDER_EXE -b --factory-startup --python-exit-code 1 -P tests\test_mixamo_retarget.py
```
