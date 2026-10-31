---
name: reference-art-generator
description: Generates 90s-style arcade fighting game character concepts using Nano Banana in Tripo Studio, including a dynamic promotional scene and an orthographic T-pose reference for the sprite-sheet-generator skill.
---

# Skill: ReferenceArtGenerator
**Description:** Generates 90s-style arcade fighting game character concepts. Produces both a dynamic in-environment promotional image and a clean, orthographic T-pose reference image required by the SpriteSheetGenerator skill.

## Provider: Tripo Studio with Nano Banana
*   **Unified Workflow:** Tripo Studio integrates Nano Banana for 2D image generation and editing, including character-consistent reference images, alongside Tripo's image-to-3D capabilities. Use Tripo for both reference-art steps; the resulting T-pose can also feed Tripo's downstream 3D model generation through the `sprite-sheet-generator` skill. Do not assume Tripo only generates 3D models or require a separate Gemini API key when using Nano Banana through Tripo Studio.
*   **Credentials:** Always load `TRIPO_API_KEY` from `.env` at the current worktree's repository root, resolved with `git rev-parse --show-toplevel`, not relative to the skill directory. This root means the active checkout, not a separate main checkout. Keep `.env` git-ignored; never print, commit, or include its contents in prompts or artifacts. If the file or key is missing or empty, ask the user to place their `.env` in the current repository root. Do not read another checkout or silently substitute a different provider's key.
*   **API Access:** Tripo's documented image-generation API supports Nano Banana and reference-image inputs; it was used successfully for Deigo's scene and T-pose. Prefer API automation with the root `.env` rather than requiring a Studio login. Verify the current API version, request schema, model availability and account access before submitting tasks. If API access is unavailable, use the integrated Tripo Studio workflow with available UI tools and required user approvals; otherwise report the access blocker explicitly. Do not invent endpoints or silently switch providers.
*   **Versioning:** The successful Deigo run used V2, whose documented retirement is November 1, 2026, 00:00 UTC+8 (October 31, 2026, 16:00 UTC). For new runs, use the current [V3 documentation](https://developers.tripo3d.ai/) and [V2-to-V3 migration guide](https://developers.tripo3d.ai/en/docs/migration-v2-to-v3), not the historical V2 examples below after retirement. V3 splits text-to-image and image-to-image into dedicated endpoints and changes input and response fields.
*   **Reference:** [Using Nano Banana in Tripo Studio](https://www.tripo3d.ai/blog/how-to-use-nano-banana-in-tripo-studio).

## 1. Top-Level Parameters
Configure these parameters before execution:
*   `CHARACTER_NAME`: String (e.g., "Knockout_King"). Used for file naming.
*   `CHARACTER_CONCEPT`: String detailing the fighter's design, clothing, and thematic environment (e.g., "A heavyweight street boxer with gold gloves in a neon-lit underground fighting ring").
*   `OUTPUT_DIR`: Directory path (Default: `./assets/references/`) to save the generated images.

## 2. Global Art Style Injection
Append the following strict style guidelines to all image generation prompts to ensure visual consistency across the roster:
*   **Style:** Exaggerated 80s/90s-inspired cartoonish arcade fighting game aesthetic, highly saturated and vibrant digital coloring.
*   **Linework:** Thick, dark, variable-width outlines encapsulating the character, creating a crisp, sticker-like pop.
*   **Anatomy & Proportions:** Hyper-muscular, top-heavy proportions, oversized chest and shoulders, enlarged hands/fists, intense and expressive facial features.
*   **Shading & Texture:** Modern cel-shading blending sharp shadow boundaries with smooth internal color gradients. High-contrast surface detailing, stylized sweat/grime, and bright specular highlights giving a glossy or metallic finish to equipment.

## 3. Delegation & Execution Workflow

### Step 1: Dynamic Scene Generation
*   **Goal:** Create an inspiring, natural-pose concept art piece in a thematic environment.
*   **Prompt Structure:** Combine `CHARACTER_CONCEPT` with the Global Art Style Injection. Emphasize a "dynamic, natural fighting stance or victory pose" and include the character's native environment in the background.
*   **Output:** Generate the image using Tripo's verified Nano Banana image-generation API, following the submit/poll/download process below, and save it as `{OUTPUT_DIR}/{CHARACTER_NAME}_scene.png`. Inspect the saved scene before continuing.

### Step 2: T-Pose Reference Generation
*   **Goal:** Create the pipeline-ready orthographic reference required by the 3D meshing agent.
*   **Unarmed Combat:** Fighters use fists and feet. T-pose references must have empty hands with visible fingers, no held props, and no weapons or scabbards, even when the source photo or promotional scene includes cosplay accessories. Keep wearable costume details that do not obstruct the pose.
*   **Identity Locking:** Use the image generated in Step 1 as an image-to-image reference. Preserve its face, hair, skin tone, proportions, clothing, palette and wearable costume details explicitly in the prompt while removing held props and weapons. Use Tripo's T-pose option when supported by the current API schema.
*   **Prompt Structure:** Combine the character's visual description with the Global Art Style Injection.
*   **Strict Pose Override:** Explicitly append: "Pure white background, completely flat lighting, front-facing orthographic camera angle, strict T-pose with arms extended straight to the sides, feet shoulder-width apart, no background elements, empty hands with clearly visible fingers, no held props, no weapons or scabbards, symmetrical stance."
*   **Output:** Generate the image using Tripo's verified Nano Banana image-generation API and save it as `{OUTPUT_DIR}/{CHARACTER_NAME}_tpose.png`.

### Step 3: Handoff
*   **Validation:** Check that both files decode as PNG images. Inspect the T-pose for identity consistency, a white background, front-facing orthographic presentation, straight horizontal arms, symmetrical stance, empty hands, no props or weapons, and an uncropped body with visible fingers and feet. Correct failed requirements before declaring completion.
*   **Action:** Show the saved images, confirm their exact paths, and provide a `/sprite-sheet-generator` command with `CHARACTER_NAME`, `REFERENCE_IMG_PATH` pointing to the saved T-pose, and the intended `ANIMATION_TYPE`.

## 4. Verified Submit/Poll/Download Process

The Deigo reference art was generated through Tripo's API on October 30, 2026. Both outputs were 1024 x 1024 PNGs and each task consumed 5 credits; these are observed results, not guaranteed dimensions or pricing for future runs.

### Preflight
1. Resolve the current repository root and load only `TRIPO_API_KEY` from its `.env`. Parse optional surrounding quotes without executing the file as shell code. Authenticate requests to Tripo with `Authorization: Bearer <key>`; never log the header.
2. Check the current image-generation and task documentation. Deigo used `gemini_2.5_flash_image_preview`, documented as Nano Banana. Verify that this model identifier is still supported before reuse.
3. Combine the character concept and all global style requirements within the documented prompt limit. The V2 limit was 1024 characters. Include the whole body, visible hands and feet, and no cropping or text.

### Historical V2 Scene Request
Submit `POST https://api.tripo3d.ai/v2/openapi/task` with this body, substituting the complete scene prompt:

```json
{
  "type": "generate_image",
  "model_version": "gemini_2.5_flash_image_preview",
  "prompt": "<character concept, dynamic jungle scene, and global art style>"
}
```

1. Require `code: 0` and a nonempty `data.task_id` in the response. Preserve the task ID so an interrupted wait can resume without submitting and charging for another generation.
2. Poll `GET https://api.tripo3d.ai/v2/openapi/task/{task_id}` using the same API key every 5 seconds, with a bounded 6-minute wait. Continue only for `queued` or `running`. Report API errors, unsuccessful terminal statuses or timeouts with the task ID; never treat them as successful generation.
3. On `data.status: success`, require `data.output.generated_image`, download it immediately, and save the scene PNG. Download URLs expire; do not commit them or credentials.
4. Decode and visually inspect the saved scene. Before the next request, query the completed scene task again to obtain a fresh reference URL. If unavailable, use the current API's documented upload mechanism for the saved PNG.

### Historical V2 T-Pose Request
Submit to the same V2 task endpoint using the scene as the image reference:

```json
{
  "type": "generate_image",
  "model_version": "gemini_2.5_flash_image_preview",
  "prompt": "<identity-preserving description, global art style, and strict pose override>",
  "t_pose": true,
  "file": {
    "type": "png",
    "url": "<fresh generated_image URL from the completed scene task>"
  }
}
```

Use the same response checks, bounded polling, immediate download and image inspection as for the scene. Remove temporary task metadata once both outputs are saved and verified.

### V3 Adaptation
The migration guide documents `POST /v3/generation/text-to-image` for the scene, `POST /v3/generation/image-to-image` for the reference edit, and `GET /v3/tasks/{task_id}` for polling. V3 removes the task-dispatch `type` field and unifies reference inputs under `input`. Check the current endpoint documentation for the host, model fields, T-pose support, input format and output schema; do not send the V2 bodies unchanged to V3.
