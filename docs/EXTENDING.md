# Extending the game

Flow: Title → Character Select → Stage Select → Fight (`scripts/core/game.gd` owns the flow and the registries).

## Add a character
1. Create `characters/<id>/character.json` (copy `characters/bruiser/character.json`).
2. Put sheets in `assets/spritesheets/<Name>_<anim>_sheet.png/.json` (6 FPS, 346 px frames; standing idle 12 FPS, see `AGENTS.md`).
3. Map animation ids to sheet stems under `animations`; use `animation_fallbacks` for missing ones.
4. Restart: the `Game` autoload discovers it automatically.

Bruiser's non-Mixamo moves (crouch, kicks, blocks, jump attacks, knockback, fall, hit stun) are authored poses on the Mixamo rig, not Mixamo clips. Regenerate with Blender 4.5 (`$env:BLENDER_EXE`): `& $env:BLENDER_EXE -b --factory-startup --python-exit-code 1 -P scripts\bruiser_authored.py -- --blend assets\animations\Bruiser_mixamo.blend --clip-set temp\Bruiser_mixamo\manifest.json --fps 6 --size 346 --output temp\Bruiser_authored`, then `.venv\Scripts\python.exe scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_authored\manifest.json --fps 6 --colors 32`. Edit `CLIPS` in the script to change poses; replace with real Mixamo clips when available.

Real Mixamo clips now cover crouched_idle (Crouch Idle), standing_kick (Mma Kick, trimmed to frames 3-10), hit_stun (Stomach Hit), fall_on_back (Falling Down), plus extras get_up, block_hit (Standing Block React Large) and roundhouse_kick. Still authored (no Mixamo source yet): crouched_punch, crouched_kick, standing_block, block_idle, jump_punch, jump_kick, knocked_back_air and the stand/crouch transitions. To render more clips: `scripts\mixamo_demo.py -- --character assets\animations\Bruiser_idle.fbx --camera temp\Bruiser_mixamo\manifest.json --clip name=path.fbx [--loop name] [--shift name=dx] --output temp\Bruiser_mixamo2 --blend ...`, add a `sheet` filename (e.g. `Bruiser_<anim>_sheet.png`) per clip in the output manifest, then run `mixamo-sheet` as above. `--camera` keeps framing identical to the existing sheets; `--shift` moves the camera in X for clips that travel (falls).

Placeholder sheets for any character: `.venv\Scripts\python.exe scripts\placeholder_sheets.py --character <Name>`.
Replace them with real pipeline output using the same file names.

## Add a move
Add an entry to `moves` in `character.json`: `input {stance, button}`, `speed`, damage/hitstun/blockstun/pushback/launch/hitstop defaults, and `hitboxes` (`frames`, `rect` [x,y,w,h] facing right from the feet). Toggle the hitbox overlay with F1 in the fight. The reserved `motion` input key is for future specials.

## Add a stage
Create `stages/<id>/stage.json` (copy an existing one). Layers can use procedural art or an `image`. Keep the combat lane flat (y ≥ 544).

## Controls
P1: WASD + J punch / K kick / U heavy punch / I heavy kick / L block. P2: arrows + `,` `.` `;` `'` `/`. Esc pauses.
Gamepad (device 0 = P1, device 1 = P2): left stick or D-pad, X punch, A kick, Y heavy punch, RB heavy kick, B block. Heavy moves are `heavy_punch` / `heavy_kick` (input button `heavy_punch`/`heavy_kick`); Bruiser's reuse the Punching clip (slowed) and the roundhouse clip.

Animation entries can be a sheet stem or `{"sheet", "frames": [from, to], "speed", "offset_x", "offset_y"}` to trim, retime or
center a sheet. Each sheet's foot anchor is detected from its pixels by default, so frame sizes can differ.
Use `offset_y` for an explicit shared-camera ground origin. Optional `frame_offsets`
contains one unscaled `[x, y]` correction per played frame (after trimming);
it is added to the origin and mirrored with the fighter. Don's generated
corrections cancel baked airborne root travel so only gameplay physics moves him.
Hitboxes and hurtboxes are world-space rectangles: scale them when changing `sprite_scale`.
An optional `air_idle` animation holds the appropriate pose after jump takeoff or
an aerial attack until physical landing. Trim the gameplay `jump` to its takeoff
and apex frames; retain the full non-looping source sheet for the animation lab.
`recover_from_knockdown` defaults to `true` for existing characters; set it to
`false` when no recovery was authored. Don then holds his final back-fall pose
until the round/training reset rather than inventing a get-up.
Move hitbox `frames` index into the (trimmed) animation.

## Tests
`godot --headless --path . --import`, then `--script res://tests/test_animation_lab.gd` and `res://tests/test_game_flow.gd`.

To rebuild every Bruiser sheet at once: `powershell -ExecutionPolicy Bypass -File scripts\rebuild_bruiser.ps1 -Fps 6 -Size 346` (needs `BLENDER_EXE`). Re-check each animation's `frames` trim and hitbox `frames` in `character.json` afterward.
