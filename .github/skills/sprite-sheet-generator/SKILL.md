---
name: sprite-sheet-generator
description: Automates the creation of 90s-style 2D fighting game sprite sheets using a 3D-to-2D rotoscoping pipeline with local Python scripts, headless Blender rendering, and AI image generation APIs.
---

# Skill: SpriteSheetGenerator
**Description:** Automates the creation of 90s-style 2D fighting game sprite sheets by driving a 3D-to-2D rotoscoping pipeline. Delegates tasks across local Python scripts, Blender headless rendering, and AI image generation APIs.

## 1. Top-Level Parameters
Configure these parameters before execution:
*   `CHARACTER_NAME`: String (e.g., "CyberNinja"). Used for file naming and identity.
*   `REFERENCE_IMG_PATH`: Path to the 2D orthographic T-pose reference image.
*   `ANIMATION_TYPE`: String (e.g., "idle", "roundhouse_kick").
*   `SHARED_CACHE_DIR`: Directory path (e.g., `./assets/shared_fbx_cache/`) to store and retrieve base 3D models to prevent redundant API calls.
*   `TARGET_FPS`: Integer (Default: 12) for retro timing.
*   `PALETTE_COLORS`: Integer (Default: 32) for quantization.

## 2. Delegation & Execution Workflow

### Step 1: Base Mesh Caching & Generation (Tripo3D)
*   **Check Cache:** Before invoking 3D generation, check `SHARED_CACHE_DIR` for `{CHARACTER_NAME}_base.fbx`.
*   **Generate (If Missing):** Pass the `REFERENCE_IMG_PATH` to the Tripo3D API. Upon success, download the generated mesh and save it strictly to `{SHARED_CACHE_DIR}/{CHARACTER_NAME}_base.fbx`.
*   **Reuse (If Present):** Skip generation and load the cached `.fbx` directly into the next step.

### Step 2: Rigging & Animation (Mixamo & Custom Move Expansion)
*   **Standard Moves:** Upload `{CHARACTER_NAME}_base.fbx` to Mixamo via automated script. Retrieve the targeted `ANIMATION_TYPE` (e.g., "idle").
*   **Specialized Moves (Expansion Slot):** If `ANIMATION_TYPE` is flagged as a custom special move (e.g., "dragon_punch"), bypass Mixamo and load custom local `.bvh` or `.fbx` animation data from `./assets/custom_moves/{ANIMATION_TYPE}.fbx` and retarget it to the base mesh using Blender's Rigify.
*   **Output:** Save the combined animated skeleton mesh as `{CHARACTER_NAME}_{ANIMATION_TYPE}.fbx`.

### Step 3: Frame & Pose Capture (Headless Blender)
*   Delegate to the local Python script: `blender -b -P capture_frames.py`.
*   **Instructions:** Import `{CHARACTER_NAME}_{ANIMATION_TYPE}.fbx`. Set the orthographic camera to a true 2D fighting game perspective. Step through the timeline at `TARGET_FPS`.
*   **Export:** For each frame, render a Depth map (`Z-pass`) and an OpenPose map (colored skeleton). Save to `./temp/capture/`.

### Step 4: 2D AI Rendering (ComfyUI / Stable Diffusion API)
*   Delegate to the vision rendering agent.
*   **Inputs:** `REFERENCE_IMG_PATH` (via IP-Adapter for identity retention), plus the Depth and OpenPose maps from Step 3 (via ControlNet for geometric locking).
*   **Prompt Override:** "90s 2D fighting game arcade sprite, pixel art style, distinct dark outlines, cel-shaded, flat lighting, transparent background."
*   **Process:** Batch render all frames in `./temp/capture/` and output to `./temp/renders/`.

### Step 5: Post-Processing & Sheet Compilation
*   Delegate to ImageMagick or Pillow Python script.
*   **Actions:**
    1. Strip backgrounds using chroma-key masking.
    2. Quantize the frames to `PALETTE_COLORS` to enforce the retro aesthetic.
    3. Stitch frames horizontally into a single `.png`.
*   **Final Output:** Save to `./assets/spritesheets/{CHARACTER_NAME}_{ANIMATION_TYPE}_sheet.png` and clear `./temp/` directories.
