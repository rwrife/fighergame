# Extending the game

Flow: Title → Character Select → Stage Select → Fight (`scripts/core/game.gd` owns the flow and the registries).

## Add a character
1. Create `characters/<id>/character.json` (copy `characters/bruiser/character.json`).
2. Put sheets in `assets/spritesheets/<Name>_<anim>_sheet.png/.json` (8 FPS, see `AGENTS.md`).
3. Map animation ids to sheet stems under `animations`; use `animation_fallbacks` for missing ones.
4. Restart: the `Game` autoload discovers it automatically.

Placeholder sheets for any character: `.venv\Scripts\python.exe scripts\placeholder_sheets.py --character <Name>`.
Replace them with real pipeline output using the same file names.

## Add a move
Add an entry to `moves` in `character.json`: `input {stance, button}`, `speed`, damage/hitstun/blockstun/pushback/launch/hitstop defaults, and `hitboxes` (`frames`, `rect` [x,y,w,h] facing right from the feet). Toggle the hitbox overlay with F1 in the fight. The reserved `motion` input key is for future specials.

## Add a stage
Create `stages/<id>/stage.json` (copy an existing one). Layers can use procedural art or an `image`. Keep the combat lane flat (y ≥ 544).

## Controls
P1: WASD + J punch / K kick / L block. P2: arrows + `,` `.` `/`. Esc pauses.

## Tests
`godot --headless --path . --import`, then `--script res://tests/test_animation_lab.gd` and `res://tests/test_game_flow.gd`.
