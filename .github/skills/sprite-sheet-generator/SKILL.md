---
name: sprite-sheet-generator
description: Continues an accepted character T-pose through a verified 20k-polygon Tripo model, Blender and local Mixamo FBX animation, sprite sheets and Godot validation, with output previews and continue/retry decisions at every stage.
---

# Skill: SpriteSheetGenerator
**Description:** Render cached animated 3D characters into bright, consistent arcade
sprites with deterministic local Blender shaders. AI may generate the upstream
Tripo model, but **never use AI, ComfyUI, or diffusion for sprite rendering going
forward**. Existing AI comparisons are historical artifacts, not the workflow.
For a supplied character image, first invoke `reference-art-generator` to obtain
the validated game-style action shot and its derived T-pose. Continue the full
minimum move set without a manual handoff. Follow the execution/authorization
contract, stage previews and all agent-owned validation gates in `AGENTS.md`.
Default to preview-and-review; always offer Retry this stage, Stop, and Continue
to the next step, and wait for each output's decision.
Only an explicit unattended request removes decision waits, not previews/checks.

## Repository implementation

See `README.md` for setup and run `scripts\spritesheet.py` with the repository's
virtual-environment Python. Stages are `doctor`, `base`, `capture`, `render`,
`sheet`, and `run`, plus `tpose`, `animate`, `retro`, and `mixamo-sheet`.
`render` and `retro` both render and compile cel-shaded sprites; `run` uses the
same renderer after model/animation preparation. Use Blender 4.5 LTS. Never print API
keys or upload references without explicit approval; paid Tripo calls additionally
require `--allow-paid-api`. Check the FBX cache before generating another model.
`run` can invoke uncached paid T-pose or animation stages even with a cached base;
use individual stages to inspect their outputs and costs before proceeding.
Confirm cached assets and persisted task IDs belong to the intended reference.
Do not blindly delete failed task state or pay for a replacement outside the
explicitly authorized correction allowance and remaining budget.

A standalone non-T-pose reference can be converted by the `tpose` stage;
that stage's minimal prompt does not implement the full source-to-styled-action
workflow. In the complete workflow, pass the already validated T-pose with
`--tpose` and retain the accepted action shot as the styled identity reference.
Mixamo has no public API, so
the `animate` stage rigs and animates with Tripo presets instead; it does not
satisfy the Mixamo-source requirement for a new character. Custom animation
retargeting must be performed and baked in Blender first. Report missing models,
animation, or Blender rather than fabricating output.
Cleanup must target only the current character/move's temporary directory.

For a complete new character, follow the minimum animation set, source and
transition requirements in the repository's `AGENTS.md`, including the two attack tiers (fast short-range normal punch/kick, plus slow `heavy_punch` and roundhouse `heavy_kick`). The three Bruiser clips
are a demo, not a complete character. The reference-art skill is included at
`.github\skills\reference-art-generator\SKILL.md`; read it before generating new
reference art. Default `block_idle` to a looping held standing guard, distinct
from the one-shot `standing_block` entry, unless the user specifies otherwise.

For sprites from an existing animated FBX, use `render --fps 6 --size 346 --colors 32
--azimuth 30 --sprite-size 160`. It preserves FBX colors with a bright four-band
shader and a modest saturation/value boost, uses a hard alpha cutout with no baked outline (opt in with `--outline-px N`), and compiles
a shared palette with real transparency. No AI service is used in this stage.
Output uses `_retro_sheet` so the AI sheet remains intact. See
`demos\bruiser_idle.html` for the side-by-side idle comparison.

For unattended work, reuse legitimately obtained local Mixamo FBX clips first.
If new downloads are needed, use FBX Binary at 30 FPS through the user's signed-in
browser with applicable tool permissions; there is no public download API.
Missing clips or login/access that requires user action are explicit blockers.
Keep downloaded FBX files and editable
retargeted animation projects out of this public repository; Adobe's Mixamo
licensing prohibits free distribution of raw character or animation files.
The files under `assets\animations\mixamo` and `*_mixamo.blend` are local and
ignored. `scripts\mixamo_demo.py` specifically retargets the three supplied
idle/jump/punch clips onto textured Bruiser with shared framing; it is not a
general-purpose retargeter for the complete character set.
Compile with `spritesheet.py mixamo-sheet --clip-set temp\Bruiser_mixamo\manifest.json --fps 6 --colors 32` (render with `mixamo_demo.py --fps 6 --size 346`; use `--fps 12` for standing idle).
`demos\bruiser_moves.html` tests queued transitions and a matched AI/shader punch.
Do not regenerate the historical AI punch. See README for shader rebuild commands
and historical ComfyUI setup lessons, which are not current rendering prerequisites.

## 1. Top-Level Parameters
Configure these parameters before execution:
*   `CHARACTER_NAME`: String (e.g., "CyberNinja"). Used for file naming and identity.
*   `REFERENCE_IMG_PATH`: Path to the 2D orthographic T-pose reference image.
*   `DESIGN_REFERENCE_IMG_PATH`: Accepted styled action shot, with the original source path/hash retained for identity comparisons.
*   `ANIMATION_SET`: Full minimum set and applicable transitions from `AGENTS.md` by default for a new character.
*   `ANIMATION_TYPE`: Optional single-move selector only when the user explicitly requests a partial set.
*   `ANIMATION_SOURCES`: Local Mixamo FBX paths, hashes, source actions, bone mapping, and adaptations for every required move. These are procedure inputs, not new CLI flags.
*   `AUTHORIZATION`: Remaining scoped upload permission, paid-stage budget and paid correction allowance from the reference-art stage.
*   `REVIEW_MODE`: Inherit `preview-and-review` or the user's explicit `unattended` choice from reference-art-generator. This is a procedure input, not a CLI flag.
*   `SHARED_CACHE_DIR`: Directory path (e.g., `./assets/shared_fbx_cache/`) to store and retrieve base 3D models to prevent redundant API calls.
*   `TARGET_FPS`: **6**, except **12** for `standing_idle`. Pass these explicitly;
    historical CLI/demo defaults of 8 FPS do not apply to new characters. Resample source motion
    at 6 FPS to preserve its duration, rather than just slowing a 12 FPS sheet.
*   `PALETTE_COLORS`: Integer (Default: 32) for quantization.
*   `MODEL_FACE_LIMIT`: **20,000 polygons maximum** for newly generated Tripo models.
*   `RENDER_STYLE`: Bright, vivid cel-shading, readable midtones, four hard shading
    bands, no baked black outline, transparent background. Avoid muddy shading.

## 2. Agent-Led Execution Workflow

### Preview Contract for Every Stage
After each stage's checks, publish actual outputs and findings following
`AGENTS.md`'s stage-preview table. For model generation show front/side/back views
and the measured polygon count; for rigging/animation show deformation tests,
every move's playback and frame-steppable contact sheets; for compilation show
the final sprites on light/dark backgrounds with loop/transition playback; for
Godot show real lab/gameplay captures and hitbox alignment.

Use `ask_user` with **Retry this stage**, **Stop**, and **Continue to the next
step**, then wait before downstream work. Always show all three choices.
Disclose quality warnings and preserve them when the user directs continuation;
do not mark those checks passed. Hard blockers remain non-bypassable under
`AGENTS.md`'s preview contract. Target retries
to named clips/defects rather than rebuilding unrelated moves. Record acceptance
against the exact output hashes, preserve rejected attempts and invalidate
affected downstream acceptances after repairs. Retrying cannot exceed the
existing paid budget/attempt allowance. In explicit unattended mode, publish
the same previews and use agent gates without user decision waits.

### Step 0: Preflight and Provenance
*   Verify the accepted T-pose/action shot and all local FBX sources, Blender
    4.5 LTS, Godot, API access and authorization before remote generation.
*   Execute the required environment and animation preflight in `AGENTS.md`,
    or reuse its recorded results only while the `.env`, executable and source
    inputs are unchanged and account access remains valid. Require the active
    root's ignored, untracked `.env` with nonempty, non-placeholder
    `TRIPO_API_KEY` and a working Blender 4.5 LTS `BLENDER_EXE`; do not print
    values. Require readable, nonempty, ignored/untracked local FBXs and a
    complete move-to-source/adaptation map. Import each distinct FBX in Blender
    to check selected actions, keyframes/frame ranges, armature and mapped
    bones; file existence alone is insufficient. Missing or invalid inputs
    block generation, with sanitized setting names, paths and affected moves.
*   Plan all moves and transitions, including source-derived adaptations.
    Reuse the local source library without uploading a new character to Mixamo.
    Neither `mixamo_demo.py` nor `don_sprites.py` is a universal retargeter:
    inspect supported skeleton assumptions before reuse and prepare a
    character-specific mapping/bake when necessary.
*   Keep a resumable local job report and task state keyed to source hashes and
    settings. Cached filenames alone do not prove the model belongs to this
    reference. Do not present `spritesheet.py run` as the end-to-end workflow.

### Step 1: Base Mesh Caching & Generation (Tripo3D)
*   **Check Cache:** Before invoking 3D generation, check `SHARED_CACHE_DIR` for `{CHARACTER_NAME}_base.fbx`.
*   **Generate (If Missing):** Pass `face_limit=20000` to both Tripo image-to-model
    generation and FBX conversion. Verify the sum of mesh polygons in Blender
    with `scripts\check_model.py` before promoting the download into the base
    cache. Fail if it exceeds 20,000 polygons; an API request alone is not proof.
    A replacement after rejection requires an unused explicitly authorized paid
    correction attempt and sufficient remaining budget; otherwise stop.
*   **Reuse (If Present):** Verify matching provenance, skip generation and load the cached `.fbx`.
*   **Visual Gate:** Import into Blender and inspect front/side/back views against
    the accepted T-pose/action shot for identity, proportions, textures and mesh
    defects. Polygon validation alone does not pass this gate. Repair local
    defects within scope or use an authorized correction; never promote a
    visually rejected candidate to the accepted cache.
*   **Existing Models:** Preserve older cached models even if they exceed this
    budget. Do not regenerate, decimate, or replace them without the user's request.

### Step 2: Rigging & Animation (Mixamo & Custom Move Expansion)
*   **Standard Moves:** Import the cached Tripo mesh and local Mixamo FBX clips
    into Blender. Fit/reuse a compatible biped armature, map rest-pose axes and
    bones, bind and inspect skin weights, then retarget and bake all required
    actions onto the character. Preserve target bone lengths and intentional
    root travel; choose one root-motion/physics policy before capture.
    Fit hip/knee/ankle centers to the actual mesh and its rest stance, not just
    height percentages or the arm-span scale. Inspect skeleton overlays from
    front and side. Test isolated hip, knee, ankle, shoulder, elbow and spine
    bends at a readable scale before baking the full move set. Check opposite
    limb influence and torso weight contamination; use appropriate volume
    preservation and verify the result visually. Rest-pose orientation
    differences must not be compounded into animated limb/body rotations.
    Fully weighted vertices and matching bone endpoints do not prove that legs
    retain their shape or that a torso is not twisted. Rejected deformation
    previews invalidate the rig and all downstream animations/sheets.
    Test joint bends and compare source/target playback for flipped bones,
    collapsed joints, detached parts, foot sliding and misplaced attack reach.
    Automatic weights are a starting point, not proof of correct deformation.
    Use `scripts\mixamo_demo.py` only for its supported Bruiser demo.
    `animate` uses Tripo presets and is not a substitute for Mixamo sources.
*   **Specialized Moves (Expansion Slot):** If `ANIMATION_TYPE` is flagged as a custom special move (e.g., "dragon_punch"), bypass Mixamo and load custom local `.bvh` or `.fbx` animation data from `./assets/custom_moves/{ANIMATION_TYPE}.fbx` and retarget it to the base mesh using Blender's Rigify.
*   **Output:** Save each combined skinned, baked animation as
    `{CHARACTER_NAME}_{ANIMATION_TYPE}.fbx` in an ignored local licensed-animation
    directory, with local source/adaptation provenance. Verify both frame
    stepping and normal-speed playback before rendering final sheets.

### Step 3: Deterministic Cel-Shaded Rendering (Headless Blender)
*   Import the baked animated character and sample at **6 FPS** (standing idle: **12 FPS**). Render at native
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
*   At 6 FPS, each frame is about 167 ms (standing idle uses 12 FPS, 83 ms, so the breathing loop stays smooth). Prefer direct matching-pose cuts; use a
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
    not features already implemented in that lab.

### Step 5: Post-Processing & Sheet Compilation
*   Use the repository's Pillow compiler.
*   **Actions:**
    1. Threshold alpha (no outline unless `--outline-px` is set). Reject empty frames and
       opaque corners. Never remove white highlights with a chroma key.
    2. Quantize to one shared `PALETTE_COLORS` palette across the entire move set,
       with dithering disabled, so transitions do not change character colors.
    3. Stitch frames horizontally into a single `.png`.
*   **Final Output:** Save the PNG and timing/rectangle JSON to `assets\spritesheets`.
    Idle loops; jump and punch are one-shots including their final recovery pose.
    Keep archived comparisons out of the active Godot animation picker.
*   Inspect every frame on light and dark backgrounds for clipping, shadows,
    stray marks, identity drift, and requested colors. Check JSON timing and
    rectangles and visually review loop and transition endpoints; transparent
    corners alone do not prove the entire sprite is clean.

### Step 6: Agent-Owned Validation and Correction
*   Execute every gate in `AGENTS.md`: image identity/pose, actual polygon count,
    rig deformation, all move semantics, loops/transitions, sheet integrity and
    Godot lab playback. Include every frame and normal-speed motion; a few
    representative stills or a successful headless load are insufficient.
*   Check especially punch/kick direction and full extension, heavy wind-up and
    roundhouse motion, standing/crouched guards, aerial recovery, planted support
    feet, back-fall endpoints, and mirrored facing. Compare source FBX playback,
    the baked rig and final sprites to locate the first defective stage.
    For a back fall, inspect chest/head facing, neck posture, relaxed limb
    alignment and ground contact. Equal head/hip heights or a grounded hand do
    not establish that the character is lying on their back.
    Ground the posterior pelvis/back together; measure body-support gaps and
    clearance for hands, boots, hair, hat and clothing on the evaluated mesh.
    Repair low limbs and accessory/fabric contact upstream, not by shifting the
    whole sprite or clipping pixels. Scope any corrective to the fall action,
    verify exported FBX parity, and review the final downed pose in both facings.
*   Repair that stage, recapture/recompile affected moves, and repeat its gate
    and all affected downstream gates. Use at most two local correction passes
    per failed stage; paid retries must fit explicit authorization. Never fix a
    deformed limb by painting over deterministic sprite frames.
*   Record `pass`, `fail` or `blocked`, evidence paths, hashes/settings and
    corrections in the local job report. Unavailable visual inspection/playback
    is `blocked`, not an assumed pass. Stop with actionable evidence when limits
    or prerequisites block completion. User preview acceptance can direct
    continued work with quality warnings, but does not mark failed checks passed
    or waive hard technical/safety constraints.
*   Deliver the full validated PNG/JSON set under `assets\spritesheets`, accepted
    action shot/T-pose and review outcome. Preserve the downed ending unless a
    recovery was requested. Do not declare completeness for missing/failed
    moves or promote partial output into the active character set. Require the
    final Godot preview acceptance before declaring the reviewed run complete.
