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

For a supplied character reference, execute one agent-led workflow:
**source image -> game-style action shot -> action-shot-derived T-pose ->
Tripo model (at most 20,000 polygons) -> Blender rigging and local Mixamo FBX
retargeting/baking -> deterministic sprite sheets -> technical and visual
validation in Godot**. Invoke `reference-art-generator`, then
`sprite-sheet-generator` without asking the user to run the next skill.
Show each stage's actual output and wait for the user's preview decision before
advancing. Read both skills and `README.md` before execution.

This is the required agent procedure, not a claim that `spritesheet.py run`
implements the whole chain. That command does not generate the styled action
shot, retrieve Mixamo clips, generally retarget arbitrary characters, or judge
visual correctness. Use existing tooling where applicable and implement missing
local preparation/validation only within the assigned character's scope.

### Execution and authorization contract

Before starting, verify the supplied image decodes, current Tripo API access,
Blender 4.5 LTS, Godot, and a complete, legitimately obtained local Mixamo FBX
source set (including sources for documented adaptations). Prefer the local
source library; do not require new Mixamo uploads or browser interaction when
cached clips suffice. Never substitute Tripo presets for missing Mixamo sources.
For a new character, default `block_idle` to a held **standing** guard, distinct
from the one-shot `standing_block` entry. Preserve an explicitly requested pose.

#### Required environment and animation preflight

Complete these checks before the first image upload or paid generation; do not
wait until Blender preparation to discover missing inputs.

- Resolve the active repository root with `git rev-parse --show-toplevel`.
  Require a readable `.env` at that root, not in the skill folder or another
  checkout. Parse it as dotenv data, never execute it. Verify `TRIPO_API_KEY`
  and `BLENDER_EXE` exist and are nonempty after parsing optional quotes; reject
  obvious example/placeholder values. Do not silently use inherited environment
  variables to mask missing required file settings.
- Verify `.env` is git-ignored and not tracked. Never print its contents, key
  values, authorization headers or credentials in subprocess output/reports.
  Resolve `BLENDER_EXE` to an existing executable and verify it runs Blender
  4.5 LTS; run `spritesheet.py doctor` with the repository virtual-environment
  Python as the existing tooling check. Verify Godot separately. Check Tripo
  authentication/account access with a current documented, non-generating
  request; never spend credits merely to test a key. File presence alone is not
  proof of valid configuration.
- Inventory local Mixamo FBXs and map every required move/transition to an exact
  source file/action or a documented adaptation from those sources. Shared
  source clips are allowed; 15 required animations do not mean 15 source files.
  Require each selected path to be a readable, nonempty `.fbx`, record its hash,
  and verify that raw licensed files and editable animation projects are ignored
  and untracked. A filename/extension alone is not proof of animation content.
- Import each distinct selected FBX in a clean headless Blender scene. Require
  a usable armature, the bones needed by its target mapping, and actual animation
  keyframes with a valid frame range. Enumerate imported actions/takes and
  verify the selected one exists; reject empty, corrupt, static-only or
  incompatible sources. Record source timing and retargeting compatibility;
  confirm the imported motion matches its assigned move during visual review.
  Source FBXs may be without skin; the target Tripo mesh is bound separately.
- Record sanitized preflight outcomes in the local job report. On failure,
  report missing setting **names**, executable/file paths, affected moves and
  import/access errors without secret values. Stop before remote work until
  every prerequisite passes; do not fabricate animations, substitute Tripo
  presets, download files or change credentials without applicable permission.

Obtain one scoped authorization before remote work: the specific source and
derived images/models that may be uploaded, Tripo as destination, paid stages,
a credit/spend ceiling, and the number of paid correction attempts allowed.
Permission to edit these instructions is not permission to upload or spend.
Check current prices and capabilities; if the cost cannot be bounded, stop before
submission. Still pass `--allow-paid-api` to supported paid commands. A flag is
not user consent, and workflow authorization cannot override a tool's separate
confirmation requirements.

With prerequisites and authorization satisfied, make artistic choices, run the
stages, inspect results and show the stage previews described below.
Allow at most two local correction passes per failed stage; paid corrections
require explicit coverage by the remaining authorized attempts and budget.
Resume saved tasks rather than resubmit on timeouts or uncertain responses.
Stop with the failed stage, evidence and exact missing prerequisite when tools,
access, sources, authorization or correction limits block progress; never claim
success or use user approval as a substitute for agent review.

### Stage previews and continue/retry decisions

Default character generation to **preview-and-review mode**. A user can explicitly
request unattended mode for a run; only then omit the preview decision waits,
while retaining all technical/agent visual checks and authorization limits.
Show previews even in unattended mode, but do not ask for routine approvals.

Publish actual saved outputs with `publish_chat_update` attachments, or use an
appropriate available viewer/canvas. Identify the stage, what passed/failed,
remaining budget and any meaningful design or motion deviations. Do not present
prompts, task-success responses, metadata, or one still as a substitute for a
missing image, model view or animation preview.

| Stage | Preview before continuing |
|-------|---------------------------|
| Preflight | Source image and sanitized prerequisite/source coverage results; do not upload until preflight and scoped authorization pass. |
| Action shot | Full generated action shot beside the supplied source, with identity/costume/style findings. |
| T-pose | Full generated T-pose beside the accepted action shot, with pose/identity findings. |
| Tripo model | Front/side/back renders of the actual downloaded model, textures/silhouette findings and measured total polygon count. |
| Blender rig and baked animation | Front/side mesh-and-skeleton overlays and isolated hip/knee/ankle, shoulder/elbow and spine bends before full baking; then normal-speed playback and frame-steppable contact sheets for every required move and transition. Group clips in one stage review if all are available; name individual clips for targeted retries. |
| Compiled sprite sheets | Actual compiled frames on light/dark backgrounds, full-move playback, loop/transition previews and timing/palette/transparency results. |
| Playable Godot character | Real in-engine lab/gameplay captures showing the character, both facings, representative combat, movement and hitbox alignment; state any remaining failures. |

After publishing each stage preview, always use `ask_user` with
**Retry this stage**, **Stop**, and **Continue to the next step**. Wait for the answer; do not submit
the next paid task or start downstream work while the decision is pending.
Show all three choices even when visual review finds defects. Distinguish
quality warnings (pose/style/identity concerns) from hard blockers (missing or
unreadable inputs, invalid file formats, failed API tasks, unavailable tools,
over-budget meshes, missing permissions or exhausted spending limits).
The user may continue with a usable preview despite quality warnings; record
their exact decision and carry the unresolved warnings into downstream checks.
Do not relabel a failed quality check as passed merely because Continue was
selected. Hard blockers still prevent execution: explain them in the prompt,
and if Continue is selected while they remain, report the blocked next stage
instead of bypassing safety, fabricating results or spending outside permission.
Unavailable previews are blockers, not assumed acceptance.

The user can explicitly revise artistic requirements or direct a costume/style
correction into a named next stage. Record that decision and keep the unresolved
criterion visible until the corrected output is reviewed; do not falsely mark
the original output compliant. User-directed continuation allows an exploratory
model from a readable reference with pose warnings; inspect the actual mesh and
retain those warnings for rigging/deformation review. This does not waive hard
technical or safety constraints, or prove the final character is complete.

Continue to the next step records acceptance of that exact output/hash and advances to the next
stage. Retry keeps the rejected output and evidence, corrects only that stage
(or its identified upstream cause), and presents a new preview. Invalidate
acceptance and recheck affected downstream outputs after any upstream change.
A retry decision does not expand upload scope, budget or paid-attempt limits;
report exhausted limits instead of submitting another charge. Stop preserves
accepted outputs and resumable task state without generating further assets.

## Reference art

Use the reference art skill to generate a consistent character identity reference
and an orthographic T-pose suitable for mesh generation and rigging. Preserve the
supplied source unchanged and retain its hash. Use it as the image-to-image input
for the action shot, not merely as inspiration for a text-only generation.
The accepted action shot becomes the styled identity reference and the direct
image-to-image input for the T-pose. Compare the T-pose, model and every rendered
animation against that identity while keeping the source available to detect
unintended design drift. Keep proportions, costume details, and colors consistent
across the full set.

The reference art skill is included at
`.github\skills\reference-art-generator\SKILL.md`. Read it before generating
reference art. If the required generation capability is unavailable, report the
missing prerequisite rather than claiming the skill was executed.

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
| Heavy (back) punch: slow, strong, long reach | `heavy_punch` |
| Heavy (back) kick: roundhouse | `heavy_kick` |

### Attack tiers

Each character has two tiers of standing attacks, bound to separate buttons
(keyboard P1 `J`/`K` normal, `U`/`I` heavy; gamepad X/A normal, Y/RB heavy):

- **Normal punch/kick** (`standing_punch`, `standing_kick`): fast and short
  range. Keep them to roughly 4-6 played frames (about 0.25-0.4 s at 6 FPS after
  the move's `speed`), with low damage and short hitstun.
- **Heavy punch** (`heavy_punch`): slow, strong punch with a visible wind-up,
  longer reach and higher damage/pushback.
- **Heavy kick** (`heavy_kick`): a roundhouse kick, slow with long reach, high
  damage, and launch/knockback.

Trim clips with `frames` and tune `speed` in `character.json` rather than
re-rendering when only timing needs to change. Characters render at about
`sprite_scale` 1.065 for 346 px frames (same on-screen size as 192 px at 1.92); when scaling a sprite, scale hurtboxes
and hitbox rects by the same factor.

Keep `block_idle` as an explicit looping requirement distinct from the one-shot
`standing_block` entry. Use the standing-guard default above unless the request
establishes a different pose; do not pause unattended work to ask about the default.

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
source locally and describe the adaptation. Adobe's Mixamo licensing prohibits
free distribution of raw character or animation files, so do not commit the
downloaded FBXs or editable retargeted animation projects to this public
repository. See the [Mixamo licensing FAQ](https://community.adobe.com/questions-696/mixamo-faq-licensing-royalties-ownership-eula-and-tos-589400).

Include transitions between animations wherever they make sense. At minimum,
account for standing-to-crouched idle and back, attack/block entry and recovery
to the matching idle, jump takeoff and landing, entry/recovery for aerial attacks,
and airborne knockback into falling onto the back. Bake transition motion before
capture, either into the relevant clip or into separately named transition
sheets. Do not force a return to idle after a knockdown without an explicitly
requested recovery animation. Idle loops must also have a clean last-to-first
frame transition.

## Timing and visual style

- Generate all character animations and transitions at **6 FPS** (346 px renders via `--size 346`), except looping idles that need smoothness: `standing_idle` is rendered at **12 FPS** (its own render/compile pass with `--fps 12`).
- Use a **32-color palette including transparency**, consistent across the
  character's sheets.
- Aim for **1990s arcade fighting-game pixel art** with bright, saturated,
  exaggerated and embellished colors, bold readable silhouettes, no baked-in black outline (hard alpha cutout; `--outline-px N` is opt-in),
  and crisp cel-shaded highlights.
- Preserve consistent scale, facing, framing, and ground alignment across moves,
  while retaining intentional airborne movement. Keep backgrounds transparent
  and exclude floors, cast/drop shadows, scenery, text, and stray marks.

Pass `--fps 6 --colors 32` explicitly to the pipeline stages that accept those
options. Use the bright deterministic cel shader, not AI or diffusion, for
sprite rendering. The legacy `--description` prompt does not affect that shader.

## Deliverables and checks

Save each horizontal PNG strip and its matching JSON metadata under
`assets\spritesheets`, following the existing `<character>_<animation>_sheet`
naming convention. JSON timing must specify 6 FPS (12 FPS for `standing_idle`) and valid frame rectangles;
idle/held-pose loops should loop, while attacks, jumps, knockback, falls, and
one-shot transitions should not loop.

Verify the full minimum set and applicable transitions, correct timing and palette
limits, clean transparency, consistent character identity, seamless idle loops,
and sensible transition endpoints. Preview sheets in the Godot animation lab.
Do not describe a character as complete when required animations are missing.

### Agent-owned validation gates

Inspect actual saved images, model views and animation playback; successful API
tasks, PNG decoding, polygon counts or passing tests alone cannot prove poses or
motion are correct. Do not infer animation quality from a single screenshot.
Record `pass`, `fail` or `blocked` for each gate with source/output hashes,
settings, task IDs, evidence paths, defects and corrections in the character's
local job report. Never include credentials, expiring URLs or raw licensed FBXs
in a committed report. These are character agent-review gates, not the separate
human release gates for reference-derived levels.

| Gate | Required evidence and acceptance criteria |
|------|-------------------------------------------|
| Source -> action shot | Compare both images: recognizable identity and costume, intentional arcade stylization, dynamic readable fighting pose, intact anatomy, full visible character and no unwanted text. |
| Action shot -> T-pose | Compare images: matching styled identity/colors, front orthographic view, straight horizontal arms, symmetric stance, visible separated empty hands/fingers and feet, uncropped body, white background, no weapons or scenery. Reject bent-arm guards and A-poses. |
| T-pose -> model/rig | Actual total mesh polygons <= 20,000 for new models; inspect front/side/back views, textures and silhouette; test shoulder/elbow/wrist/hip/knee/ankle bends for correct bone mapping, skin weights and deformation. No detached parts or collapsed joints. |
| Animation semantics | Review every frame and normal-speed playback of every move, plus source motion and startup/active/recovery poses. Punches and kicks extend toward the opponent; heavy punch has wind-up/reach and heavy kick is a roundhouse; guards protect the body; crouches lower it; jumps/aerial attacks remain airborne; knockback enters a back fall that stays down. Reject reversed limbs, intersections, foot skating, jitter and abrupt unintended root jumps. |
| Loops and transitions | Play idle last-to-first joins and each required state boundary; verify matching poses or baked bridges, planted feet where intended, no double limbs/alpha crossfades, no standing resets during aerial recovery and no invented get-up. |
| Sheets and Godot | Inspect every frame on light/dark backgrounds and playback in the Godot lab, including mirrored facing. Verify all required sheets, rectangles, FPS/loop flags, shared <= 32-color palette including transparency, hard alpha, shared camera/scale/origin/baseline and no clipping, floor, shadows or stray pixels. Where gameplay is wired, check hitbox timing and that root motion and physics do not apply jump displacement twice. |

Repair the failed upstream cause (reference, mesh/weights, retargeting, motion,
framing or compilation), then rerun that gate and all affected downstream gates.
For a back-fall endpoint, establish contact from posterior pelvis and back
geometry, not the lowest hand, hat, hair or sprite pixel. Check face-up head/chest
orientation, relaxed limbs, body-support gaps and clearance for every evaluated
vertex. Correct low hands and accessory/fabric contact in the 3D pose or a
fall-only baked corrective, without moving the torso above the floor or hiding
penetration through sprite offsets. Ensure correctives stay inactive in other
actions, survive FBX export/reimport and remain grounded in both Godot facings.
Do not hide pose defects with image edits or passing metadata checks. If visual
inspection or playback is unavailable, mark that gate `blocked`; do not fabricate
review evidence. Deliver final sheets and metadata only after every required gate
passes; partial outputs remain explicitly incomplete.

Follow the existing pipeline's permission and safety requirements: never print or
commit API keys, obtain explicit approval before uploading reference images,
require `--allow-paid-api` for paid Tripo calls, and clean only the current
character/move's temporary directory. Retain source hashes, task IDs, accepted
outputs and review evidence needed for resumption; do not clean these as scratch.
