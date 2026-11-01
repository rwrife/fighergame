extends SceneTree
## Run headless for assertions, or pass an output directory after -- for screenshots.


func _initialize() -> void:
	create_timer(30.0).timeout.connect(func() -> void:
		push_error("White House check timed out after an assertion or render failure.")
		quit(1))
	call_deferred("_run")


func _run() -> void:
	var game := root.get_node("Game")
	assert(game.stages.has("white_house"), "White House must be selectable")
	var stage: StageData = game.stages["white_house"]
	var manifest: Dictionary = JSON.parse_string(
			FileAccess.get_file_as_string("res://assets/levels/white_house/level.json"))
	var width := int(manifest.viewport[0])
	var travel := int(manifest.camera_travel)
	assert(stage.width == width + travel)
	assert(stage.floor_y == 576)
	assert(not manifest.review.in_game, "Agent checks must not approve the human review")
	var view := StageView.new()
	root.add_child(view)
	view.build(stage)
	var camera := Camera2D.new()
	root.add_child(camera)
	camera.make_current()
	camera.position = Vector2(width / 2.0, 320)
	await process_frame
	var back: ParallaxBackground = view.get_child(0)
	var front: ParallaxBackground = view.get_child(1)
	var parallax_layers := back.get_children()
	parallax_layers.append_array(front.get_children())
	assert(parallax_layers.size() == stage.layers.size())
	for index in stage.layers.size():
		var layer: Dictionary = stage.layers[index]
		var parallax: ParallaxLayer = parallax_layers[index]
		var art: StageLayerArt = parallax.get_child(0)
		assert(is_equal_approx(parallax.motion_scale.x, float(layer.ratio)))
		assert(art.texture_filter == CanvasItem.TEXTURE_FILTER_NEAREST)
		assert(art._texture != null, "Missing stage texture: " + str(layer.image))
		var offset: Array = layer.get("offset", [0, 0])
		assert(art._texture_offset == Vector2(offset[0], offset[1]))
	var arguments := OS.get_cmdline_user_args()
	if not arguments.is_empty():
		var directory: String = arguments[0]
		assert(DirAccess.make_dir_recursive_absolute(directory) == OK)
		for x in [0, travel / 2, travel]:
			camera.position.x = width / 2.0 + x
			camera.force_update_scroll()
			await process_frame
			await RenderingServer.frame_post_draw
			var image := root.get_texture().get_image()
			assert(image.get_size() == Vector2i(960, 640))
			assert(image.save_png(directory.path_join("camera_%d.png" % x)) == OK)
	view.queue_free()
	camera.queue_free()
	await process_frame
	game.mode = "training"
	game.stage_id = "white_house"
	game.p1_character = "bruiser"
	game.p2_character = "bruiser"
	var fight := (load(game.SCENES.fight) as PackedScene).instantiate()
	root.add_child(fight)
	await process_frame
	assert(fight.p1.floor_y == stage.floor_y and fight.p2.floor_y == stage.floor_y)
	var shadow: FighterShadow = fight.p1.shadow
	assert(shadow.get_parent() == fight.p1 and shadow.z_index == -1)
	assert(shadow.get_index() < fight.p1.sprite.get_index(), "Shadow must draw under the sprite")
	assert(absf(shadow.global_position.y - stage.floor_y) < 0.01)
	var standing_size := shadow.current_size()
	assert(standing_size.x >= 30.0 and standing_size.y >= FighterShadow.PIXEL)
	fight.p1.input = FighterInput.new()
	fight.p1.input._set_state(&"up", true)
	await create_timer(0.2).timeout
	fight.p1.input._set_state(&"up", false)
	assert(fight.p1.is_airborne(), "Fighter must jump on the new flat lane")
	assert(absf(shadow.global_position.y - stage.floor_y) < 0.01, "Shadow stays on the floor")
	assert(shadow.current_size().x < standing_size.x, "Airborne shadow must shrink")
	assert(shadow.current_color().a < FighterShadow.COLOR.a, "Airborne shadow must fade")
	await create_timer(1.2).timeout
	assert(not fight.p1.is_airborne())
	assert(is_equal_approx(fight.p1.position.y, stage.floor_y))
	assert(absf(shadow.current_size().x - standing_size.x) < 1.0)
	if not arguments.is_empty():
		fight.overlay.visible = false
		fight.hud._training.visible = false
		await process_frame
		await RenderingServer.frame_post_draw
		assert(root.get_texture().get_image().save_png(
				arguments[0].path_join("fight.png")) == OK)
	fight.queue_free()
	await process_frame
	print("White House stage registry, textures, parallax and flat-lane checks passed.")
	quit()
