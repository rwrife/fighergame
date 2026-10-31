extends Control

const SHEET_DIRECTORY := "res://assets/spritesheets"

var sprite := AnimatedSprite2D.new()
var animation_picker := OptionButton.new()
var play_button := Button.new()
var status_label := Label.new()
var error_label := Label.new()
var stage := Control.new()


func _ready() -> void:
	_build_ui()
	_load_animations()
	if animation_picker.item_count > 0:
		_select_animation(0)
	resized.connect(_layout_sprite)
	_layout_sprite()


func _build_ui() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 24)
	add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	margin.add_child(column)
	var title := Label.new()
	title.text = "Fighter Animation Lab"
	title.add_theme_font_size_override("font_size", 28)
	column.add_child(title)

	var controls := HBoxContainer.new()
	controls.add_theme_constant_override("separation", 12)
	column.add_child(controls)
	animation_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	animation_picker.item_selected.connect(_select_animation)
	controls.add_child(animation_picker)
	play_button.text = "Pause"
	play_button.pressed.connect(_toggle_playback)
	controls.add_child(play_button)
	var step_button := Button.new()
	step_button.text = "Next frame"
	step_button.pressed.connect(_step_frame)
	controls.add_child(step_button)
	var flip_button := CheckButton.new()
	flip_button.text = "Face left"
	flip_button.toggled.connect(func(enabled: bool) -> void: sprite.flip_h = enabled)
	controls.add_child(flip_button)
	var back_button := Button.new()
	back_button.text = "Back (Esc)"
	back_button.pressed.connect(func() -> void: Game.goto("title"))
	controls.add_child(back_button)

	var settings := HBoxContainer.new()
	settings.add_theme_constant_override("separation", 12)
	column.add_child(settings)
	var speed_label := Label.new()
	speed_label.text = "Speed"
	settings.add_child(speed_label)
	var speed := SpinBox.new()
	speed.min_value = 0.1
	speed.max_value = 3.0
	speed.step = 0.1
	speed.value = 1.0
	speed.suffix = "x"
	speed.value_changed.connect(func(value: float) -> void: sprite.speed_scale = value)
	settings.add_child(speed)
	var zoom_label := Label.new()
	zoom_label.text = "Zoom"
	settings.add_child(zoom_label)
	var zoom := SpinBox.new()
	zoom.min_value = 1.0
	zoom.max_value = 4.0
	zoom.step = 0.5
	zoom.value = 2.0
	zoom.suffix = "x"
	zoom.value_changed.connect(func(value: float) -> void: sprite.scale = Vector2.ONE * value)
	settings.add_child(zoom)

	var background := ColorRect.new()
	background.color = Color(0.11, 0.13, 0.18)
	background.clip_contents = true
	background.size_flags_vertical = Control.SIZE_EXPAND_FILL
	background.custom_minimum_size.y = 320
	column.add_child(background)
	stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.add_child(stage)
	stage.resized.connect(_layout_sprite)
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	sprite.scale = Vector2(2, 2)
	sprite.sprite_frames = SpriteFrames.new()
	sprite.sprite_frames.remove_animation(&"default")
	stage.add_child(sprite)

	column.add_child(status_label)
	error_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	error_label.add_theme_color_override("font_color", Color(1, 0.55, 0.5))
	column.add_child(error_label)
	var help := Label.new()
	help.text = "Space: play/pause   |   Right: next frame   |   R: restart"
	column.add_child(help)


func _load_animations() -> void:
	var directory := DirAccess.open(SHEET_DIRECTORY)
	if directory == null:
		_report_error("Cannot open sprite-sheet directory: " + SHEET_DIRECTORY)
		return
	var files := directory.get_files()
	files.sort()
	for file in files:
		if file.ends_with("_sheet.json"):
			_load_sheet(SHEET_DIRECTORY.path_join(file))
	if animation_picker.item_count == 0:
		_report_error("No usable animations found. Add a *_sheet.json and its PNG to assets/spritesheets.")
		play_button.disabled = true


func _load_sheet(path: String) -> void:
	var parser := JSON.new()
	var result := parser.parse(FileAccess.get_file_as_string(path))
	if result != OK:
		_report_error("%s: %s" % [path, parser.get_error_message()])
		return
	var data: Variant = parser.data
	if not data is Dictionary:
		_report_error(path + ": metadata must be a JSON object.")
		return
	if data.get("archived", false) == true:
		return
	if not data.get("image") is String or not data.get("fps") is float \
			or not data.get("loop") is bool or not data.get("frames") is Array:
		_report_error(path + ": expected image, numeric fps, boolean loop and frames array.")
		return
	if data.fps <= 0 or data.frames.is_empty():
		_report_error(path + ": fps and frame count must be positive.")
		return
	var image_path: String = path.get_base_dir().path_join(data.image)
	if not ResourceLoader.exists(image_path, "Texture2D"):
		_report_error(path + ": missing texture " + image_path)
		return
	var texture := load(image_path) as Texture2D
	if texture == null:
		_report_error(path + ": cannot load texture " + image_path)
		return
	var frames: Array[AtlasTexture] = []
	for frame in data.frames:
		if not frame is Dictionary:
			_report_error(path + ": each frame must be an object.")
			return
		for key in ["x", "y", "width", "height"]:
			if not frame.get(key) is float or frame[key] != floor(frame[key]):
				_report_error(path + ": frame rectangles must contain integer x, y, width and height.")
				return
		var rect := Rect2(frame.x, frame.y, frame.width, frame.height)
		if rect.position.x < 0 or rect.position.y < 0 or rect.size.x <= 0 or rect.size.y <= 0 \
				or rect.end.x > texture.get_width() or rect.end.y > texture.get_height():
			_report_error(path + ": frame rectangle is outside the texture.")
			return
		var atlas := AtlasTexture.new()
		atlas.atlas = texture
		atlas.region = rect
		frames.append(atlas)
	var animation := StringName(path.get_file().trim_suffix("_sheet.json"))
	sprite.sprite_frames.add_animation(animation)
	sprite.sprite_frames.set_animation_speed(animation, data.fps)
	sprite.sprite_frames.set_animation_loop(animation, data.loop)
	for frame in frames:
		sprite.sprite_frames.add_frame(animation, frame)
	animation_picker.add_item(String(animation))
	animation_picker.set_item_metadata(animation_picker.item_count - 1, animation)


func _select_animation(index: int) -> void:
	sprite.stop()
	sprite.play(animation_picker.get_item_metadata(index))
	play_button.text = "Pause"


func _toggle_playback() -> void:
	if sprite.animation.is_empty():
		return
	if sprite.is_playing():
		sprite.pause()
	else:
		sprite.play()
	play_button.text = "Pause" if sprite.is_playing() else "Play"


func _step_frame() -> void:
	if sprite.animation.is_empty():
		return
	sprite.pause()
	var count := sprite.sprite_frames.get_frame_count(sprite.animation)
	var next := sprite.frame + 1
	if next >= count:
		next = 0 if sprite.sprite_frames.get_animation_loop(sprite.animation) else count - 1
	sprite.set_frame_and_progress(next, 0.0)
	play_button.text = "Play"


func _layout_sprite() -> void:
	sprite.position = stage.size / 2.0


func _process(_delta: float) -> void:
	if not sprite.animation.is_empty():
		status_label.text = "%s   |   Frame %d / %d   |   %.1f FPS   |   %s" % [
			sprite.animation, sprite.frame + 1,
			sprite.sprite_frames.get_frame_count(sprite.animation),
			sprite.sprite_frames.get_animation_speed(sprite.animation) * sprite.speed_scale,
			"Playing" if sprite.is_playing() else "Paused",
		]
		play_button.text = "Pause" if sprite.is_playing() else "Play"


func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_SPACE:
			_toggle_playback()
		KEY_RIGHT:
			_step_frame()
		KEY_ESCAPE:
			Game.goto("title")
		KEY_R:
			if animation_picker.item_count > 0:
				_select_animation(animation_picker.selected)
		_:
			return
	get_viewport().set_input_as_handled()


func _report_error(message: String) -> void:
	push_error(message)
	error_label.text += message + "\n"
