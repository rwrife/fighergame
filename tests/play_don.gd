extends SceneTree


func _initialize() -> void:
	call_deferred("_start")


func _start() -> void:
	var game := root.get_node("Game")
	assert(game.characters.has("don") and game.characters.has("bruiser"))
	game.mode = game.MODE_TRAINING
	game.p1_character = "don"
	game.p2_character = "bruiser"
	game.stage_id = "training_grounds"
	assert(change_scene_to_file(game.SCENES.fight) == OK)
	await process_frame
	await process_frame
	assert(current_scene.p1.data.id == "don" and current_scene.p1.controls_enabled)
	print("Don training ready (PID %d)" % OS.get_process_id())
