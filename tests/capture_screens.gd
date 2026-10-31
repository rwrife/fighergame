extends SceneTree
## Renders menu and fight scenes to PNGs for visual review (needs a display, not --headless).
## Run: godot --path . --script res://tests/capture_screens.gd -- <output_dir>


func _initialize() -> void:
	call_deferred("_run")


func _save(name: String, dir: String) -> void:
	await process_frame
	await process_frame
	root.get_texture().get_image().save_png(dir.path_join(name + ".png"))


func _run() -> void:
	var dir := OS.get_cmdline_user_args()[0] if OS.get_cmdline_user_args().size() > 0 else "user://"
	var game := root.get_node("Game")
	for key in ["title", "character_select", "stage_select"]:
		var screen: Node = (load(game.SCENES[key]) as PackedScene).instantiate()
		if screen is Control:
			screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		root.add_child(screen)
		await create_timer(0.5).timeout
		if screen.has_method("_open_menu"):
			screen._open_menu()
		await _save(key, dir)
		screen.queue_free()
		await process_frame
	for stage_id in game.stages:
		game.mode = "training"
		game.p1_character = "bruiser"
		game.p2_character = "bruiser"
		game.stage_id = stage_id
		var fight: Node = (load(game.SCENES.fight) as PackedScene).instantiate()
		root.add_child(fight)
		await create_timer(1.5).timeout
		await _save("fight_" + stage_id, dir)
		if stage_id == "stonehenge":
			fight.p1.input._set_state(&"punch", true)
			await create_timer(0.35).timeout
			await _save("fight_punch", dir)
		fight.queue_free()
		await process_frame
	quit()
