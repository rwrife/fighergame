# Project goals and agent guidance

## Game vision

The goal is to build a **90s-style arcade fighting game in Godot** with bright,
vibrant colors, fast action, and smooth transitions between character animations
and gameplay states. Levels should be vibrant and animated, with layered
backgrounds that use **parallax scrolling** to create depth and bring each arena
to life. Keep combat readable and responsive while maintaining this energetic
retro arcade presentation.

## Asset generation

## Reference-derived levels

For landscape-to-stage work, read
`.github\skills\reference-level-generator\SKILL.md` and
`assets\workflows\reference_level.json`. Use `scripts\level_pipeline.py` for local
job initialization, image/manifest checks and three-position camera previews.
Do not describe image-model editing, Tripo multi-object generation, Blender
assembly or a Godot stage loader as automated by this script.
`scripts\level_derive.py` builds an offline, recipe-driven 2D **draft** (no
remote services); label it as such and not as Tripo/Blender output.

Keep the lightbox screen-locked: sky, distant skyline and an optional subtle
landscape underlay with nearby foreground detail removed. Do not duplicate its
static silhouettes in moving geometry. Nano Banana's
solid-blue sky replacement is a geometry-isolation intermediate, not final sky
art; exclude that blue backdrop from Tripo meshes. Require separable scene
objects, shared cel-shaded arcade styling, reusable prop sprites, parallax
overscan, and a straight full-width protected lane occupying the bottom 15% by
default. Never use sloping reference terrain as the combat collision surface.
No scenery or prop alpha may intrude into that lane. Preserve source hashes,
model task IDs and render settings, and obtain approval before remote uploads
or paid generation. Technical validation does not replace the four visual/game
review gates or authorize setting them to true.

# Character and sprite-sheet generation

New characters can be created using the reference art skill to establish their
design, then the `sprite-sheet-generator` skill to produce their animated sprite
sheets. Read `.github\skills\sprite-sheet-generator\SKILL.md` and `README.md`
before running the pipeline.

## Reference art

Use the reference art skill to generate a consistent character identity reference
and an orthographic T-pose suitable for mesh generation and rigging. Preserve the
original design image as the identity reference for all rendered animations.
Keep proportions, costume details, and colors consistent across the full set.

The reference art skill is not currently included in this repository. If it is
not available in the agent's installed skills, report the missing prerequisite
before generating reference art; do not claim it was used.

## Minimum animation set

Every new character must have sprite sheets for at least these animations:

| Animation | Suggested identifier |
|-----------|----------------------|
| Standing idle | `standing_idle` |
| Crouched idle | `crouched_idle` |
| Standing punch | `standing_punch` |
| Crouched punch | `crouched_punch` |
| Standing kick | `standing_kick` |
| Crouched kick | `crouched_kick` |
| Standing block | `standing_block` |
| Block idle | `block_idle` |
| Jump | `jump` |
| Jump punch | `jump_punch` |
| Jump kick | `jump_kick` |
| Knocked backwards through the air | `knocked_back_air` |
| Falling to the ground on their back | `fall_on_back` |

Keep `block_idle` as an explicit requirement distinct from `standing_block`.
Before generating it, clarify the intended pose if the request or reference does
not establish whether it is a held blocking idle or a crouched blocking idle.

## Animation sources and transitions

Pull the required animations from **Mixamo**. Download the appropriate clips,
retarget them to the character, and bake/export the animated, skinned FBX files
for the sprite-sheet pipeline. Reuse the cached base mesh rather than regenerating
the character for each move.

Mixamo has no public API, and the repository's current `animate` command uses
Tripo presets, not Mixamo downloads. Do not use that command as a substitute for
the required Mixamo source or claim automated Mixamo retrieval is implemented.
Use legitimately obtained Mixamo clips and Blender retargeting/baking; report
missing clips or unavailable access instead of silently substituting another
source. If a required move needs editing or combining clips, retain its Mixamo
source and describe the adaptation.

Include transitions between animations wherever they make sense. At minimum,
account for standing-to-crouched idle and back, attack/block entry and recovery
to the matching idle, jump takeoff and landing, entry/recovery for aerial attacks,
and airborne knockback into falling onto the back. Bake transition motion before
capture, either into the relevant clip or into separately named transition
sheets. Do not force a return to idle after a knockdown without an explicitly
requested recovery animation. Idle loops must also have a clean last-to-first
frame transition.

## Timing and visual style

- Generate all character animations and transitions at **8 FPS**.
- Use a **32-color palette including transparency**, consistent across the
  character's sheets.
- Aim for **1990s arcade fighting-game pixel art** with bright, saturated,
  exaggerated and embellished colors, bold readable silhouettes, dark outlines,
  and crisp cel-shaded highlights.
- Preserve consistent scale, facing, framing, and ground alignment across moves,
  while retaining intentional airborne movement. Keep backgrounds transparent
  and exclude floors, cast/drop shadows, scenery, text, and stray marks.

These requirements override the pipeline/skill's existing 12 FPS default for new
characters. Pass `--fps 8 --colors 32` explicitly to every relevant pipeline stage;
do not rely on defaults. Use `--description` to reinforce the character's bright
palette and embellished 90s styling.

## Deliverables and checks

Save each horizontal PNG strip and its matching JSON metadata under
`assets\spritesheets`, following the existing `<character>_<animation>_sheet`
naming convention. JSON timing must specify 8 FPS and valid frame rectangles;
idle/held-pose loops should loop, while attacks, jumps, knockback, falls, and
one-shot transitions should not loop.

Verify the full minimum set and applicable transitions, correct timing and palette
limits, clean transparency, consistent character identity, seamless idle loops,
and sensible transition endpoints. Preview sheets in the Godot animation lab.
Do not describe a character as complete when required animations are missing.

Follow the existing pipeline's permission and safety requirements: never print or
commit API keys, obtain explicit approval before uploading reference images,
require `--allow-paid-api` for paid Tripo calls, and clean only the current
character/move's temporary directory.
