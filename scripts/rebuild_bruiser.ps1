param(
    [int]$Fps = 6,
    [int]$Size = 346,
    [string]$Blender = $env:BLENDER_EXE
)
# Rebuilds every Bruiser sheet (Mixamo base set, extra Mixamo clips, authored poses).
# Needs Blender 4.5 ($env:BLENDER_EXE) and the FBX files in assets\animations\mixamo.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = ".\.venv\Scripts\python.exe"
$d = "assets\animations\mixamo\"
$char = "assets\animations\Bruiser_idle.fbx"

function Run-Blender([string[]]$BlenderArgs) { & $Blender -b --factory-startup --python-exit-code 1 @BlenderArgs; if ($LASTEXITCODE) { throw "Blender failed" } }

# 1. Base set: idle / jump / punch
Run-Blender @("-P", "scripts\mixamo_demo.py", "--", "--character", $char, "--idle", "${d}fighting_idle.fbx", "--jump", "${d}jump.fbx", "--punch", "${d}punch.fbx", "--fps", $Fps, "--size", $Size, "--output", "temp\Bruiser_mixamo", "--blend", "assets\animations\Bruiser_mixamo.blend")
& $py scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_mixamo\manifest.json --fps $Fps --colors 32

# 1b. Standing idle is smoother at 12 FPS; render it separately and compile over the 6 FPS one
Run-Blender @("-P", "scripts\mixamo_demo.py", "--", "--character", $char, "--idle", "${d}fighting_idle.fbx", "--camera", "temp\Bruiser_mixamo\manifest.json", "--fps", 12, "--size", $Size, "--output", "temp\Bruiser_idle12", "--blend", "temp\Bruiser_idle12.blend")
& $py scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_idle12\manifest.json --fps 12 --colors 32 --palette-from assets\spritesheets\Bruiser_jump_mixamo_sheet.png

# 2. Extra Mixamo clips, framed with the base set's camera
Run-Blender @("-P", "scripts\mixamo_demo.py", "--", "--character", $char, "--camera", "temp\Bruiser_mixamo\manifest.json",
    "--clip", "crouch_idle=${d}Crouch Idle.fbx", "--clip", "mma_kick=${d}Mma Kick.fbx", "--clip", "roundhouse=${d}roudhouse kick.fbx",
    "--clip", "block_react=${d}Standing Block React Large.fbx", "--clip", "stomach_hit=${d}Stomach Hit.fbx",
    "--clip", "falling_down=${d}Falling Down.fbx", "--clip", "getting_up=${d}Getting Up.fbx",
    "--loop", "crouch_idle", "--shift", "falling_down=-0.4", "--shift", "getting_up=-0.4",
    "--fps", $Fps, "--size", $Size, "--output", "temp\Bruiser_mixamo2", "--blend", "temp\Bruiser_mixamo2.blend")
@'
import json
p = "temp/Bruiser_mixamo2/manifest.json"
m = json.load(open(p))
names = {"crouch_idle": "crouched_idle", "mma_kick": "standing_kick", "stomach_hit": "hit_stun",
         "falling_down": "fall_on_back", "getting_up": "get_up", "block_react": "block_hit",
         "roundhouse": "heavy_kick"}
for k, v in names.items():
    m["clips"][k]["sheet"] = f"Bruiser_{v}_sheet.png"
m["set_file"] = "Bruiser_mixamo2_set.json"
json.dump(m, open(p, "w"), indent=2)
'@ | & $py -
& $py scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_mixamo2\manifest.json --fps $Fps --colors 32

# 3. Authored poses for moves without Mixamo clips
Run-Blender @("-P", "scripts\bruiser_authored.py", "--", "--blend", "assets\animations\Bruiser_mixamo.blend", "--clip-set", "temp\Bruiser_mixamo\manifest.json", "--fps", $Fps, "--size", $Size, "--output", "temp\Bruiser_authored")
& $py scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_authored\manifest.json --fps $Fps --colors 32

# 4. Recompile the Mixamo clips last: the authored set also contains a stand-in standing_kick that must not win.
& $py scripts\spritesheet.py mixamo-sheet --clip-set temp\Bruiser_mixamo2\manifest.json --fps $Fps --colors 32

