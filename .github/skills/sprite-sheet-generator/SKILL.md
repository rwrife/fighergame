---
name: sprite-sheet-generator
description: Creates bright deterministic cel-shaded fighting-game sprites at 8 FPS from cached 3D models and animation, with a 20,000-polygon budget for newly generated Tripo models.
---

# Skill: SpriteSheetGenerator
**Description:** Render cached animated 3D characters into bright, consistent arcade
sprites with deterministic local Blender shaders. AI may generate the upstream
Tripo model, but **never use AI, ComfyUI, or diffusion for sprite rendering going
forward**. Existing AI comparisons are historical artifacts, not the workflow.

## Repository implementation

See `README.md` for setup and run `scripts\spritesheet.py` with the repository's
virtual-environment Python. Stages are `doctor`, `base`, `capture`, `render`,
`sheet`, and `run`, plus `tpose`, `animate`, `retro`, and `mixamo-sheet`.
`render` and `retro` both render and compile cel-shaded sprites; `run` uses the
same renderer after model/animation preparation. Use Blender 4.5 LTS. Never print API
keys or upload references without explicit approval; paid Tripo calls additionally
require `--allow-paid-api`. Check the FBX cache before generating another model.

A non-T-pose reference (e.g., a fighting stance) is converted by the `tpose` stage;
retain the original as the character design reference. Mixamo has no public API, so
the `animate` stage rigs and animates with Tripo presets instead; it does not
satisfy the Mixamo-source requirement for a new character. Custom animation
retargeting must be performed and baked in Blender first. Report missing models,
animation, or Blender rather than fabricating output.
Cleanup must target only the current character/move's temporary directory.

For a complete new character, follow the minimum animation set, source and
transition requirements in the repository's `AGENTS.md`. The three Bruiser clips
are a demo, not a complete character. The reference-art skill described there is
not currently included; report it as missing if it is unavailable before
generating new reference art. Clarify `block_idle` if its intended pose is unclear.

For sprites from an existing animated FBX, use `render --fps 8
--azimuth 30 --sprite-size 160`. It preserves FBX colors with a bright four-band
shader and a modest saturation/value boost, adds a one-pixel outline, and compiles
a shared palette with real transparency. No AI service is used in this stage.
Output uses `_retro_sheet` so the AI sheet remains intact. See
`demos\bruiser_idle.html` for the side-by-side idle comparison.

For Mixamo clips, download FBX Binary at 30 FPS through the user's signed-in
browser; there is no public download API. Keep downloaded FBX files and editable
retargeted animation projects out of this public repository; Adobe's Mixamo
licensing prohibits free distribution of raw character or animation files.
The files under `assets\animations\mixamo` and `*_mixamo.blend` are local and
ignored. `scripts\mixamo_demo.py` specifically retargets the three supplied
idle/jump/punch clips onto textured Bruiser with shared framing; it is not a
general-purpose retargeter for the complete character set.
Compile with `spritesheet.py mixamo-sheet --clip-set temp\Bruiser_mixamo\manifest.json`.
`demos\bruiser_moves.html` tests queued transitions and a matched AI/shader punch.
Do not regenerate the historical AI punch. See README for shader rebuild commands.

## 1. Top-Level Parameters
Configure these parameters before execution:
*   `CHARACTER_NAME`: String (e.g., "CyberNinja"). Used for file naming and identity.
*   `REFERENCE_IMG_PATH`: Path to the 2D orthographic T-pose reference image.
*   `ANIMATION_TYPE`: String (e.g., "idle", "roundhouse_kick").
*   `SHARED_CACHE_DIR`: Directory path (e.g., `./assets/shared_fbx_cache/`) to store and retrieve base 3D models to prevent redundant API calls.
*   `TARGET_FPS`: Integer (Default: **8**) for retro timing. Resample source motion
    at 8 FPS to preserve its duration, rather than just slowing a 12 FPS sheet.
*   `PALETTE_COLORS`: Integer (Default: 32) for quantization.
*   `MODEL_FACE_LIMIT`: **20,000 polygons maximum** for newly generated Tripo models.
*   `RENDER_STYLE`: Bright, vivid cel-shading, readable midtones, four hard shading
    bands, dark one-pixel outlines, transparent background. Avoid muddy shading.

## 2. Delegation & Execution Workflow

### Step 1: Base Mesh Caching & Generation (Tripo3D)
*   **Check Cache:** Before invoking 3D generation, check `SHARED_CACHE_DIR` for `{CHARACTER_NAME}_base.fbx`.
*   **Generate (If Missing):** Pass `face_limit=20000` to both Tripo image-to-model
    generation and FBX conversion. Verify the sum of mesh polygons in Blender
    with `scripts\check_model.py` before promoting the download into the base
    cache. Fail if it exceeds 20,000 polygons; an API request alone is not proof.
    Never automatically pay for a replacement after a rejected result.
*   **Reuse (If Present):** Skip generation and load the cached `.fbx` directly into the next step.
*   **Existing Models:** Preserve older cached models even if they exceed this
    budget. Do not regenerate, decimate, or replace them without the user's request.

### Step 2: Rigging & Animation (Mixamo & Custom Move Expansion)
*   **Standard Moves:** Use the signed-in Mixamo browser to select motions for
    the character. Download FBX Binary at 30 FPS without keyframe reduction.
    Obtain explicit approval for new character uploads; never request credentials.
    Retarget and bake Mixamo clips in Blender, using `scripts\mixamo_demo.py`
    only for the supported Bruiser demo. `animate` uses Tripo presets and is not
    a substitute for required Mixamo clips.
*   **Specialized Moves (Expansion Slot):** If `ANIMATION_TYPE` is flagged as a custom special move (e.g., "dragon_punch"), bypass Mixamo and load custom local `.bvh` or `.fbx` animation data from `./assets/custom_moves/{ANIMATION_TYPE}.fbx` and retarget it to the base mesh using Blender's Rigify.
*   **Output:** Save the combined animated skeleton mesh as `{CHARACTER_NAME}_{ANIMATION_TYPE}.fbx`.

### Step 3: Deterministic Cel-Shaded Rendering (Headless Blender)
*   Import the baked animated character and sample at **8 FPS**. Render at native
    sprite resolution; do not render smooth video and resize it into pixel art.
*   Preserve material base-color textures, with saturation/value at 1.10 and
    four normal-based lighting bands: 0.60, 0.78, 0.93, 1.00.
*   Use a fixed orthographic camera, fixed sample settings, no floor, no cast
    shadows, and real alpha. Do not use diffusion or chroma-key generated scenery.
*   For move sets, fit one camera over all sequences and share the palette,
    sprite dimensions, facing, origin, and ground baseline.

### Step 4: Transition Authoring
*   Author a shared guard pose and entry/exit poses. Blend mismatched skeletal
    poses in Blender, then bake and render the bridge with the same shader.
    Never alpha-crossfade 2D sprites: it produces double limbs and ghosting.
*   At 8 FPS, each frame is 125 ms. Prefer direct matching-pose cuts; use a
    one-frame bridge where necessary and reserve longer bridges for deliberate
    recovery. Do not add a fixed two-frame delay to every attack.
*   Runtime transitions should follow startup/active/recovery and jump/landing
    windows, with a short expiring input buffer. Do not cancel punches in their
    active frames or reset airborne characters to idle by default.
*   Cover the standing/crouched transitions, attack and block entry/recovery,
    jump and aerial attack transitions, and airborne knockback into a back fall
    described in `AGENTS.md`. Do not add a knockdown recovery without a request.
    Verify clean idle loop endpoints rather than assuming they are seamless.
*   The current browser lab is a hard-cut, queued-transition testbed. Baked
    bridges, cancel windows, and physics-driven jump phases are the next stage,
    not features already implemented.

### Step 5: Post-Processing & Sheet Compilation
*   Use the repository's Pillow compiler.
*   **Actions:**
    1. Threshold alpha and add a one-pixel outline. Reject empty frames and
       opaque corners. Never remove white highlights with a chroma key.
    2. Quantize to one shared `PALETTE_COLORS` palette across the entire move set,
       with dithering disabled, so transitions do not change character colors.
    3. Stitch frames horizontally into a single `.png`.
*   **Final Output:** Save the PNG and timing/rectangle JSON to `assets\spritesheets`.
    Idle loops; jump and punch are one-shots including their final recovery pose.
    Keep archived comparisons out of the active Godot animation picker.
