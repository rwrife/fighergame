---
name: reference-level-generator
description: Turn landscape reference images into consistent arcade fighting-game stages with a fixed sky lightbox, cel-shaded multi-object scenery, parallax layers, reusable props, and a protected flat combat lane.
---

# Reference level generator

Read `README.md`, `AGENTS.md`, and `assets\workflows\reference_level.json`.
Use `scripts\level_pipeline.py` for local initialization, validation and previews.
This is an agent-guided production workflow, **not an implemented image-model or
Tripo API runner**. Never claim that a prompt file is generated artwork or that a
multi-object scene is ready before inspecting its actual geometry.

## Inputs and locked decisions

- A landscape reference, a stage identifier, and an approved in-game character
  sheet as the style/scale reference.
- Default canvas: **960 x 640**, matching `project.godot`, not the reference's
  aspect ratio. Recompose/outpaint; do not stretch the image. Changing the game's
  aspect ratio requires a separate user decision.
- Default world artwork: **2400 x 640**, camera travel **960 pixels**. Travel is
  horizontal only, with a fixed zoom and vertical framing.
- Bottom **15%** (y = 544..639) is a straight, flat, full-width combat floor.
  The bottom **30%** is the staging zone: y = 448..543 permits decorative
  objects, while y = 544..639 is protected. Never preserve a sloping reference
  hill as the gameplay floor. The feet baseline defaults to y = 576.
- The sky lightbox is one opaque, viewport-sized image, screen-locked with
  parallax factor **0**. Clouds, sunset glow, the distant skyline and an optional
  subtle low-contrast landscape underlay belong here. This underlay is not a
  playable foreground. Nearby hills, landmark stones, fences, rocks and plants
  belong in moving scenery layers, not the lightbox.
- Far background, middle scenery, floor and foreground have horizontal factors
  **0.2, 0.5, 1.0 and 1.15**. These are ratios to camera motion, not velocities.
  No automatic cloud animation, vertical scrolling or perspective floor.
- Independent props are reusable transparent sprites with layer and position
  metadata, not baked permanently into the floor or landmark.

## Execute the workflow

1. **Initialize locally.** Run `init` using the reference and a representative
   approved character PNG. It creates a job, copies those inputs, records their
   hashes and workflow version, and writes prompts plus a layout guide. Existing
   jobs are never overwritten. Read the reference and guide before generation.
2. **Approve the style and framing.** Compare the character sheet, reference,
   and guide. Establish one stage palette of at most 31 opaque RGB colors plus
   transparency in `palette.json`. Match the character's outline weight, pixel
   density, hard cel-shading, bright saturated embellished 90s arcade aesthetic
   and readable silhouettes. Record `source\layer_plan.json` assigning each
   identifiable reference feature to exactly one static/scenery/prop layer;
   distinguish distant static silhouettes from the nearer moving hill sections.
   Do not interpret this painterly reference as a request to change the game's
   style. Keep sky gradients as deliberate color bands. Set `review.style` only
   after the user approves the style target.
3. **Extract/repaint the lightbox with Nano Banana or an image-editing model.**
   Use `prompts.json` `sky`, the original reference, and masks selecting removable
   objects. The user's method is to remove everything from the foreground,
   leaving the skyline and a subtle foreground. Interpret this as **sky + distant
   skyline + a restrained landscape underlay**, not reusable foreground props or
   combat ground. Remove the stone circle, nearby hills/grass detail, fences,
   rocks and plants, then inpaint their footprints. Preserve the purple/orange
   cloud rhythm and yellow sunset for this example. Recompose to 960 x 640,
   filling exposed regions behind moving scenery with sky/haze and low-contrast
   terrain so parallax cannot uncover cutout holes. A crop is not extraction.
   Distant silhouette detail may remain static by design; label it in the layer
   plan and **do not duplicate it in the moving meshes**. Review for ghost
   landmarks, seams, text and bright foreground distractions. Retain the approved
   mask, prompt, seed, model/version and original output.
4. **Prepare a sky-free geometry reference.** Use `prompts.json` `geometry`.
   The user's proven Nano Banana edit is **"remove the sky from the image and
   replace it with a solid blue sky"**. Keep this as the first-pass isolation
   step, preserving stones, hills, fences and vegetation. Request a single
   uniform blue swatch without clouds, gradients or shadows; record the actual
   sampled RGB rather than assuming a particular blue. Retain the original
   reference for the separate sky lightbox, never extract sky from this blue edit.
   Produce explicit segmentation masks/object crops from the isolated reference.
   A solid-blue image is a valid Tripo preparation input if the chosen mode
   ignores the backdrop; alpha is not an assumed provider requirement. When
   transparent input is supported, remove blue with verified object/sky masks.
   Never globally key all blue pixels (that can erase legitimate object colors);
   border flood-fill alone also misses enclosed sky gaps between the stones.
   Review those gaps, edge halos and thin fence details. Do not assume diffusion
   emits real alpha. Explicitly exclude the blue backdrop from mesh generation
   and exclude the play strip: its deterministic floor comes later.
5. **Generate the multi-object Tripo scene.** Obtain explicit permission to
   upload the named reference/crops to Tripo and separate approval for charges.
   First inspect the stage cache and existing task IDs. Key reuse to the input
   image/mask hashes, provider/model revision and generation settings; a changed
   reference must not silently reuse a mismatched mesh. Use the currently
   available scene/multi-object or segmentation workflow only after verifying
   its actual capability in the account/API; do not invent SDK methods.
   Require independently selectable landmark stones, hill sections, fence
   sections, rocks and vegetation, with logical pivots and no sky dome or blue
   background plane. Inspect the returned model for blue backdrop geometry.
   If generation returns one fused mesh, segmentation is a required repair
   checkpoint, not success. If native multi-object generation is unavailable,
   disclose that and obtain approval for per-object crop generation + assembly.
   Record task IDs before polling, preserve failed/pending IDs, and never
   automatically pay for a retry. Export/cache the original GLB/FBX, masks,
   textures and provider receipt locally under `source`.
6. **Assemble and cel-shade in Blender 4.5 LTS.** Follow the collection/camera
   recipe below. Place meshes using the reference as a composition guide, but
   flatten the combat surface deterministically. Remove baked photoreal
   lighting, sky geometry and unwanted terrain before rendering. Generate props
   separately so later decoration does not require regenerating the whole stage.
7. **Export and style-lock.** Export the named layers and independent props as
   PNGs with true alpha. Quantize every output to the **same approved palette**
   with dithering disabled. High-quality resampling is allowed only before
   quantization; after quantization use nearest-neighbor only. The sky is RGB/opaque;
   scenery and props are RGBA. Store camera, collection membership, object
   transforms, lighting, shader settings and render settings in the `.blend`.
   Keep a stable seed/model revision for any optional image-model polish; depth
   and object masks must lock geometry. Reject polish that moves the flat floor
   or changes the landmark silhouette.
8. **Validate, preview, review.** Run `validate` and `preview`; the latter also
   validates and composites left, center and right camera positions. Inspect
   the entire camera sweep in-engine, with representative fighters, jumps and
   HUD, before setting `review.composition` and `review.in_game`. Set
   `review.sky_clean` only after visually inspecting sky extraction. Run
   `validate --release` after all four reviews. Technical validation cannot
   certify artistic consistency, mesh separability, or gameplay collisions.

## Local 2D derivation fallback

When remote generation is not approved, or no Nano Banana outputs are supplied,
`scripts\level_derive.py derive --level <job>` builds a technically valid
**draft** stage offline from `source\reference.*`. It is driven by
`source\derive_recipe.json` (`recipe_version` 1), which records:

- `lane_anchor_y`: the reference row mapped to the top of the lane. The level
  scales to `544 / lane_anchor_y`, and `world_width` becomes the reference's
  native scaled width. `camera_travel` must fit within that width.
- `sky`: thresholds for the heuristic sky matte (land hue range, value and ink
  limits, halo passes, margin and blur).
- `far_bands`: crest polylines that split distant silhouettes from the midground.
- `lane_patches`: reference rectangles cloned from a horizontal donor offset
  (`dx`), tone-matched row by row and feathered, to clear flowers, weeds and
  rocks out of the lane.
- `props`: ink-outlined objects harvested from boxes, plus seeded procedural
  tufts. Also `placements` and `foreground`, with bases above y=544.
- `palette`: per-group color budgets (sky, scenery, ground) plus reserved colors.
- `layer_plan`: unique feature names per layer.

The output is deterministic, so re-running produces byte-identical files.
Provenance records `method: local_2d_derivation` and `remote_services: []`.
Limitations: there is no 3D geometry, re-lighting or true cel-shading, and
parallax separation is only as good as the authored crests. The matte is a
heuristic, so it still needs the `sky_clean` review. If approved Nano Banana
sky-only or solid-blue outputs become available, use them in place of the
heuristic matte and continue the Tripo and Blender path above. Never present a
derived draft as the Tripo/Blender result, and never set review gates
automatically.

## Blender assembly recipe

- Use an **orthographic**, front-facing camera, fixed vertical scale and fixed
  horizon. Work in image coordinates through a documented world-unit-to-pixel
  mapping; retain the 960 x 640 safe frame inside the 2400 x 640 world frame.
  All collections share the same camera, origin and export size.
- Collections: `far_background`, `midground`, `ground`, `foreground`, plus
  `props`. For this reference: nearer hill sections in far background;
  stone circle and fence sections in midground; a new level dirt strip in
  ground; selected grass/rocks in foreground. The large foreground rocks in the
  reference must be relocated out of the protected lane, not copied literally.
- Build the floor as a cuboid/planar strip with a constant-height top edge,
  spanning the entire world width at y = 544. No hills, displacement, slope,
  holes or rock colliders in this strip. Export `ground.png` transparent above
  y = 544 and fully opaque from that row to the bottom. Surface texture may
  vary in color but cannot imply steps, holes or a sloping contact surface.
- Use Eevee with a diffuse-light-to-`Shader to RGB` stepped color ramp
  (three hard bands) and approved material colors. Use one shared key light
  matching the sky's sunset direction, restrained fill, no photographic PBR
  specular and consistent outlines. Use silhouette/inverted-hull outlines or
  a verified line-rendering setup; inspect the alpha fringes.
- Render one collection at a time with film transparency and the **same**
  projection; disable other visible geometry and shadow contributions. Render
  props separately with explicit pivots and sizes. Do not auto-fit the camera
  independently for each layer. Ground has no objects attached to it.
- Props may be behind or in front of fighters by z-order, but **all non-ground
  alpha must end above y = 544**. Keep silhouettes clear; foreground objects
  cannot obscure the fighter test positions. Decorative props have no collision
  by default; gameplay obstacles require an explicit separate design.

## Runtime contract (Godot 4.3+)

The current project is an animation viewer, not a combat game or stage loader.
This skill exports an engine-neutral `level.json`; **runtime loading is not
implemented by the local tools**. Integrate it using this exact contract:

- Screen-locked sky: a `TextureRect` in a background `CanvasLayer`, below all
  world content, fixed to the letterboxed viewport. It does not illuminate Godot
  objects physically: "lightbox" means visual backdrop and color/light reference.
- Scrolling artwork: `ParallaxBackground` / `ParallaxLayer` (available in Godot
  4.3), or equivalent explicit offset calculation. Do not require `Parallax2D`,
  which is not available in the project's minimum 4.3 version.
- For camera x in `[0, camera_travel]`, draw each layer at
  `x = -(image_width - viewport_width)/2 - (camera_x - camera_travel/2)*factor`.
  Y stays zero. Props use the same origin and factor as their assigned layer.
  Do not also apply a parent `Camera2D` transform to this screen-space formula:
  that would double-scroll. The sky always draws at `(0, 0)`.
- Painter order: sky, far background, midground, ground, fighters, foreground.
  Props inherit the order/factor of their layer. World-space fighters and the
  floor collision use actual camera motion, not a decorative parallax ratio.
  Keep a single straight world collision surface aligned with the manifest's
  feet baseline; visual artwork is not an automatically inferred collider.
- Use nearest filtering, integer-snapped drawing, fixed vertical framing and
  the manifest's aspect ratio. On other display ratios, letterbox rather than
  stretching. Disable repeating/mirroring for the unique stone-circle landmark.
  Extending beyond the declared camera travel requires wider art and revalidation.
- Package `level.json`, `palette.json` and all PNGs explicitly in Godot's export
  preset; JSON is not automatically included as a resource.

## Completion and safety

See the JSON workflow for reusable stage prompts and review gates. Store source
provenance (including mesh task IDs and render settings) in `source\provenance.json`.
Mark missing providers, approval, masks, separable meshes or artistic review as
blocked; do not fake extracted assets or silently substitute a flat reference
image for layered scenery. `init`, `validate`, and `preview` never upload data or
spend credits. Do not add secrets to prompts/manifests, print `.env`, delete cached
models or clear anything outside the current job's explicitly named temporary
files. Never run remote/paid generation just because this skill was invoked.
