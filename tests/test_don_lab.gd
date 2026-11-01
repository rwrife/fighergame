extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var lab: Control = (load("res://scenes/animation_lab.tscn") as PackedScene).instantiate()
	root.add_child(lab)
	await process_frame
	await process_frame
	assert(lab.error_label.text.is_empty(), lab.error_label.text)
	var frames: SpriteFrames = lab.sprite.sprite_frames
	var directory := DirAccess.open("res://assets/spritesheets")
	var count := 0
	var output := ""
	if not OS.get_cmdline_user_args().is_empty():
		output = OS.get_cmdline_user_args()[0]
		DirAccess.make_dir_recursive_absolute(output)
	for spin in lab.find_children("*", "SpinBox", true, false):
		if spin.max_value == 4.0:
			spin.value = 1.0
	for file in directory.get_files():
		if not file.begins_with("Don_") or not file.ends_with("_sheet.json"):
			continue
		var name := StringName(file.trim_suffix("_sheet.json"))
		var data: Dictionary = JSON.parse_string(
			FileAccess.get_file_as_string("res://assets/spritesheets".path_join(file))
		)
		assert(frames.has_animation(name), String(name))
		assert(frames.get_animation_speed(name) == data.fps, String(name))
		assert(frames.get_animation_loop(name) == data.loop, String(name))
		assert(frames.get_frame_count(name) == data.frame_count, String(name))
		lab.sprite.play(name)
		lab.sprite.pause()
		for index in int(data.frame_count):
			lab.sprite.frame = index
			var texture := frames.get_frame_texture(name, index) as AtlasTexture
			assert(texture != null and texture.region.size == Vector2(346, 346), String(name))
			await process_frame
		if not output.is_empty() and name in [
			&"Don_standing_idle", &"Don_standing_punch", &"Don_standing_kick", &"Don_fall_on_back",
		]:
			lab.sprite.frame = int(data.frame_count) - 1 if name == &"Don_fall_on_back" else int(data.frame_count / 2)
			for picker_index in lab.animation_picker.item_count:
				if lab.animation_picker.get_item_metadata(picker_index) == name:
					lab.animation_picker.select(picker_index)
			await process_frame
			await RenderingServer.frame_post_draw
			assert(root.get_texture().get_image().save_png(
				output.path_join(String(name) + "_lab.png")
			) == OK)
		count += 1
	assert(count == 23, "All 15 Don moves, get_up and seven bridges must load.")
	lab.free()
	print("PASS Don animation lab: all 23 sheets and every frame loaded.")
	quit()
