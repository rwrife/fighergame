extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var scene := load("res://scenes/animation_lab.tscn") as PackedScene
	var lab := scene.instantiate()
	root.add_child(lab)
	await process_frame
	await process_frame
	assert(lab.error_label.text.is_empty(), lab.error_label.text)
	assert(lab.animation_picker.item_count >= 1)
	var idle_index := -1
	for i in lab.animation_picker.item_count:
		if lab.animation_picker.get_item_metadata(i) == &"Bruiser_idle_mixamo":
			idle_index = i
	assert(idle_index >= 0, "Mixamo idle must be available in the picker.")
	lab._select_animation(idle_index)
	var frames: SpriteFrames = lab.sprite.sprite_frames
	assert(frames.has_animation(&"Bruiser_idle_mixamo"))
	assert(not frames.has_animation(&"Bruiser_idle"), "Archived AI sheets must stay out of the picker.")
	assert(frames.get_frame_count(&"Bruiser_idle_mixamo") == 40)
	assert(frames.get_animation_speed(&"Bruiser_idle_mixamo") == 12.0)
	assert(frames.get_animation_loop(&"Bruiser_idle_mixamo"))
	assert(not frames.get_animation_loop(&"Bruiser_jump_mixamo"))
	assert(not frames.get_animation_loop(&"Bruiser_punch_mixamo"))
	var first := frames.get_frame_texture(&"Bruiser_idle_mixamo", 0) as AtlasTexture
	assert(first.region == Rect2(0, 0, 346, 346))
	var last := frames.get_frame_texture(&"Bruiser_idle_mixamo", 39) as AtlasTexture
	assert(last.region == Rect2(13494, 0, 346, 346))
	assert(lab.sprite.is_playing())
	await create_timer(0.25).timeout
	assert(lab.sprite.frame > 0, "Playback must advance through the idle frames.")
	lab._select_animation(idle_index)
	lab._toggle_playback()
	assert(not lab.sprite.is_playing())
	await create_timer(0.2).timeout
	assert(lab.sprite.frame == 0, "Paused playback must hold its frame.")
	lab._step_frame()
	assert(lab.sprite.frame == 1)
	lab.sprite.frame = 39
	lab._step_frame()
	assert(lab.sprite.frame == 0)
	frames.set_animation_loop(&"Bruiser_idle_mixamo", false)
	lab.sprite.frame = 39
	lab._step_frame()
	assert(lab.sprite.frame == 39)
	lab._select_animation(idle_index)
	assert(lab.sprite.frame == 0)
	assert(lab.sprite.is_playing())
	var settings := lab.find_children("*", "SpinBox", true, false)
	settings[0].value = 0.5
	assert(lab.sprite.speed_scale == 0.5)
	settings[1].value = 3.0
	assert(lab.sprite.scale == Vector2(3, 3))
	var facing := lab.find_children("*", "CheckButton", true, false)
	facing[0].button_pressed = true
	assert(lab.sprite.flip_h)
	lab._process(0.0)
	assert("6.0 FPS" in lab.status_label.text)
	assert(lab.sprite.position == lab.stage.size / 2.0)
	lab.free()
	print("Animation lab smoke check passed.")
	quit()
