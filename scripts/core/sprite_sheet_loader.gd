class_name SpriteSheetLoader
extends RefCounted
## Loads a `<name>_sheet.json` + PNG strip pair (see assets/spritesheets).
## Returns {ok, error, fps, loop, placeholder, frames: Array[AtlasTexture]}.


static func load_sheet(json_path: String) -> Dictionary:
	var result := {"ok": false, "error": "", "fps": 8.0, "loop": false, "placeholder": false, "frames": []}
	if not FileAccess.file_exists(json_path):
		result.error = "missing sheet metadata " + json_path
		return result
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(json_path)) != OK:
		result.error = "%s: %s" % [json_path, parser.get_error_message()]
		return result
	var data: Variant = parser.data
	if not data is Dictionary or not data.get("image") is String or not data.get("fps") is float \
			or not data.get("loop") is bool or not data.get("frames") is Array:
		result.error = json_path + ": expected image, numeric fps, boolean loop and frames array."
		return result
	if data.fps <= 0 or data.frames.is_empty():
		result.error = json_path + ": fps and frame count must be positive."
		return result
	var image_path: String = json_path.get_base_dir().path_join(data.image)
	var texture: Texture2D = null
	if ResourceLoader.exists(image_path, "Texture2D"):
		texture = load(image_path) as Texture2D
	if texture == null:
		result.error = json_path + ": cannot load texture " + image_path
		return result
	var frames: Array[AtlasTexture] = []
	for frame in data.frames:
		if not frame is Dictionary:
			result.error = json_path + ": each frame must be an object."
			return result
		var rect := Rect2(frame.get("x", -1), frame.get("y", -1), frame.get("width", 0), frame.get("height", 0))
		if rect.position.x < 0 or rect.position.y < 0 or rect.size.x <= 0 or rect.size.y <= 0 \
				or rect.end.x > texture.get_width() or rect.end.y > texture.get_height():
			result.error = json_path + ": frame rectangle is outside the texture."
			return result
		var atlas := AtlasTexture.new()
		atlas.atlas = texture
		atlas.region = rect
		frames.append(atlas)
	result.ok = true
	result.fps = data.fps
	result.loop = data.loop
	result.placeholder = bool(data.get("placeholder", false))
	result.frames = frames
	return result
