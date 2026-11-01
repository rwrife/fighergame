extends SceneTree
## Headless smoke test: registry, menu scenes and move/hit behavior.
## Run: godot --headless --path . --script res://tests/test_game_flow.gd


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var game := root.get_node("Game")
	assert(game.characters.has("bruiser"), "bruiser must be registered")
	assert(game.stages.size() >= 3)
	var bruiser: CharacterData = game.characters["bruiser"]
	assert(bruiser.errors.is_empty(), str(bruiser.errors))
	assert(bruiser.missing_animations.is_empty(), "missing: " + str(bruiser.missing_animations))
	for animation in CharacterData.REQUIRED_ANIMATIONS:
		assert(is_equal_approx(bruiser.sprite_frames.get_animation_speed(animation), 6.0) or animation == &"standing_idle")
	for move_name in ["standing_punch", "crouched_punch", "standing_kick", "crouched_kick", "jump_punch", "jump_kick"]:
		assert(bruiser.moves.has(move_name), move_name)
	assert(not bruiser.find_move("standing", "punch").is_empty())

	for path in game.SCENES.values():
		if path.ends_with("fight.tscn") or path.ends_with("animation_lab.tscn"):
			continue
		var screen: Node = (load(path) as PackedScene).instantiate()
		root.add_child(screen)
		await process_frame
		screen.queue_free()
		await process_frame

	game.mode = "training"
	game.p1_character = "bruiser"
	game.p2_character = "bruiser"
	game.stage_id = "training_grounds"
	var fight: Node = (load(game.SCENES.fight) as PackedScene).instantiate()
	root.add_child(fight)
	await process_frame
	var a: Fighter = fight.p1
	var b: Fighter = fight.p2
	a.input = FighterInput.new()
	await create_timer(0.2).timeout
	assert(a.controls_enabled and a.state == Fighter.State.IDLE)

	a.position.x = b.position.x - 120
	var before := b.health
	a.input._set_state(&"punch", true)
	await create_timer(0.8).timeout
	a.input._set_state(&"punch", false)
	assert(b.health < before, "standing punch must damage the dummy")
	assert(a.state == Fighter.State.IDLE, "attacker recovers to idle: %s" % a.debug_summary())

	b.health = 1000
	fight._since_hit = 0.0
	b.input = FighterInput.new()
	a.position.x = b.position.x - 120
	b.controls_enabled = true
	b.input.held[&"block"] = true
	await create_timer(0.2).timeout
	before = b.health
	a.input._set_state(&"kick", true)
	await create_timer(0.8).timeout
	a.input._set_state(&"kick", false)
	assert(b.state in [Fighter.State.BLOCKSTUN, Fighter.State.BLOCK], "kick must be blocked: %s" % b.debug_summary())
	assert(before - b.health < 20, "block should only chip")
	b.input.held[&"block"] = false

	a.input.held[&"up"] = false
	a.input._set_state(&"up", true)
	await create_timer(0.15).timeout
	a.input._set_state(&"up", false)
	assert(a.is_airborne() and a.state == Fighter.State.JUMP)
	await create_timer(1.0).timeout
	assert(not a.is_airborne() and a.state == Fighter.State.IDLE, "jump lands: %s" % a.debug_summary())

	b.health = 1000
	b.input.held[&"block"] = false
	a.input.held[&"down"] = true
	await create_timer(0.2).timeout
	assert(a.state == Fighter.State.CROUCH)
	a.position.x = b.position.x - 130
	a.input._set_state(&"kick", true)
	await create_timer(0.9).timeout
	a.input._set_state(&"kick", false)
	a.input.held[&"down"] = false
	assert(b.state in [Fighter.State.LAUNCHED, Fighter.State.DOWN], "crouch kick launches: %s" % b.debug_summary())
	await create_timer(1.0).timeout
	assert(b.state == Fighter.State.DOWN or b.state == Fighter.State.IDLE)

	fight.queue_free()
	print("Game flow smoke check passed.")
	quit()
