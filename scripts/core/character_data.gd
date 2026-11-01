class_name CharacterData
extends RefCounted
## Data-driven character definition loaded from characters/<id>/character.json.
## See docs/ADDING_CHARACTERS.md for the schema.

const SHEET_DIR := "res://assets/spritesheets"
const REQUIRED_ANIMATIONS: Array[StringName] = [
	&"standing_idle", &"crouched_idle", &"standing_punch", &"crouched_punch",
	&"standing_kick", &"crouched_kick", &"standing_block", &"block_idle",
	&"jump", &"jump_punch", &"jump_kick", &"knocked_back_air", &"fall_on_back",
	&"heavy_punch", &"heavy_kick",
]
const DEFAULT_HURTBOXES := {
	"standing": [-30, -150, 60, 150], "crouching": [-34, -100, 68, 100],
	"air": [-30, -140, 60, 120], "down": [-80, -40, 150, 40],
}

var id := ""
var display_name := ""
var title := ""
var sprite_scale := 2.0
var frame_size := 160
var feet_inset := 2 # transparent pixel rows below the feet in each frame
var recover_from_knockdown := true
var stats := {}
var hurtboxes := {}
var animations := {}
var fallbacks := {}
var moves := {}
var sprite_frames := SpriteFrames.new()
var sprite_offsets := {} # animation -> sprite offset that puts the feet on the origin
var frame_offsets := {} # animation -> optional per-frame baked root-motion correction
var playback_speed := {} # animation -> speed multiplier from character.json
var placeholder_animations: Array[StringName] = []
var missing_animations: Array[StringName] = []
var errors: Array[String] = []


static func load_from(path: String) -> CharacterData:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		push_error("Invalid character file: " + path)
		return null
	var character := CharacterData.new()
	character._build(parsed)
	return character


func _build(data: Dictionary) -> void:
	id = data.get("id", "")
	display_name = data.get("name", id.capitalize())
	title = data.get("title", "")
	sprite_scale = float(data.get("sprite_scale", 2.0))
	frame_size = int(data.get("frame_size", 160))
	feet_inset = int(data.get("feet_inset", 2))
	recover_from_knockdown = bool(data.get("recover_from_knockdown", true))
	stats = {
		"health": 1000, "walk_speed": 220.0, "back_speed": 170.0, "jump_speed": 1000.0,
		"gravity": 2600.0, "jump_drift": 0.0,
	}
	stats.merge(data.get("stats", {}), true)
	hurtboxes = DEFAULT_HURTBOXES.duplicate()
	hurtboxes.merge(data.get("hurtboxes", {}), true)
	animations = data.get("animations", {})
	fallbacks = data.get("animation_fallbacks", {})
	sprite_frames.remove_animation(&"default")
	for animation_id in animations:
		# An animation is a sheet stem, or {"sheet", "frames": [from, to], "speed"} to trim/retime a sheet.
		var entry: Variant = animations[animation_id]
		var stem: String = entry if entry is String else entry.get("sheet", "")
		var sheet := SpriteSheetLoader.load_sheet(SHEET_DIR.path_join(stem + "_sheet.json"))
		if not sheet.ok:
			errors.append(sheet.error)
			continue
		var key := StringName(animation_id)
		var first := 0
		var last: int = sheet.frames.size() - 1
		if entry is Dictionary:
			first = clampi(int(entry.get("frames", [0, last])[0]), 0, last)
			last = clampi(int(entry.get("frames", [0, last])[1]), first, last)
			playback_speed[key] = float(entry.get("speed", 1.0))
			if entry.has("frame_offsets"):
				var offsets: Variant = entry.frame_offsets
				if not offsets is Array or offsets.size() != last - first + 1:
					errors.append("%s: frame_offsets must match the played frame count" % key)
					continue
				var converted: Array[Vector2] = []
				for offset in offsets:
					if not offset is Array or offset.size() != 2 \
							or not (offset[0] is float or offset[0] is int) \
							or not (offset[1] is float or offset[1] is int):
						errors.append("%s: frame_offsets must contain numeric [x, y] pairs" % key)
						break
					if not is_finite(float(offset[0])) or not is_finite(float(offset[1])):
						errors.append("%s: frame_offsets must be finite" % key)
						break
					converted.append(Vector2(offset[0], offset[1]))
				if converted.size() != offsets.size():
					continue
				frame_offsets[key] = converted
		sprite_frames.add_animation(key)
		sprite_frames.set_animation_speed(key, sheet.fps)
		sprite_frames.set_animation_loop(key, sheet.loop)
		for i in range(first, last + 1):
			sprite_frames.add_frame(key, sheet.frames[i])
		var offset := Vector2(0, -(sheet.frame_height / 2.0 - sheet.feet_inset))
		if entry is Dictionary:
			offset.x = float(entry.get("offset_x", 0))
			offset.y = float(entry.get("offset_y", offset.y))
		sprite_offsets[key] = offset
		if sheet.placeholder:
			placeholder_animations.append(key)
	for required in REQUIRED_ANIMATIONS:
		if not sprite_frames.has_animation(required):
			missing_animations.append(required)
	for move_id in data.get("moves", {}):
		moves[move_id] = _normalize_move(move_id, data.moves[move_id])


func _normalize_move(move_id: String, move: Dictionary) -> Dictionary:
	var normalized := move.duplicate(true)
	normalized.id = move_id
	normalized.animation = move.get("animation", move_id)
	normalized.speed = float(move.get("speed", 1.0))
	var defaults := {"damage": 50, "hitstun": 0.3, "blockstun": 0.2, "pushback": 200.0,
			"knockback": 0.0, "launch": false, "hitstop": 0.07}
	var boxes: Array = []
	for box in move.get("hitboxes", []):
		var merged := defaults.duplicate()
		for key in defaults:
			if move.has(key):
				merged[key] = move[key]
		merged.merge(box, true)
		var rect: Array = merged.rect
		merged.rect = Rect2(rect[0], rect[1], rect[2], rect[3])
		merged.from_frame = int(merged.frames[0])
		merged.to_frame = int(merged.frames[1])
		boxes.append(merged)
	normalized.hitboxes = boxes
	return normalized


func get_animation(animation_id: StringName) -> StringName:
	var current := animation_id
	for _i in 4:
		if sprite_frames.has_animation(current):
			return current
		if not fallbacks.has(String(current)):
			break
		current = StringName(fallbacks[String(current)])
	return &""


func find_move(stance: String, button: String) -> Dictionary:
	for move in moves.values():
		var input: Dictionary = move.get("input", {})
		if input.get("stance", "") == stance and input.get("button", "") == button and not input.has("motion"):
			return move
	return {}


func get_hurtbox(kind: String) -> Rect2:
	var box: Array = hurtboxes.get(kind, DEFAULT_HURTBOXES.standing)
	return Rect2(box[0], box[1], box[2], box[3])


func get_sprite_offset(animation: StringName, frame: int) -> Vector2:
	var offset: Vector2 = sprite_offsets.get(animation, Vector2.ZERO)
	if frame_offsets.has(animation):
		offset += frame_offsets[animation][frame]
	return offset


func portrait() -> Texture2D:
	var animation := get_animation(&"standing_idle")
	return sprite_frames.get_frame_texture(animation, 0) if animation != &"" else null
