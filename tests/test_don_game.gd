extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var game := root.get_node("Game")
	assert(game.characters.has("don"), "Don must be registered")
	var don: CharacterData = game.characters.don
	assert(don.errors.is_empty(), str(don.errors))
	assert(don.missing_animations.is_empty(), str(don.missing_animations))
	assert(don.placeholder_animations.is_empty())
	assert(not don.recover_from_knockdown)
	assert(don.get_animation(&"hit_stun") != &"")
	assert(don.get_animation(&"walk_forward") == &"standing_idle")
	assert(don.sprite_frames.get_animation_speed(&"standing_idle") == 12.0)
	var invalid := CharacterData.new()
	invalid._build({"id": "invalid", "animations": {"standing_idle": {
		"sheet": "Don_standing_idle", "frames": [0, 0], "frame_offsets": [["bad", 0]],
	}}})
	assert(not invalid.errors.is_empty())
	assert(not invalid.sprite_frames.has_animation(&"standing_idle"))
	for move_name in don.moves:
		var move: Dictionary = don.moves[move_name]
		var count := don.sprite_frames.get_frame_count(move.animation)
		for hit in move.hitboxes:
			assert(hit.from_frame >= 0 and hit.to_frame < count, move_name)
		if move_name in ["standing_punch", "standing_kick"]:
			var duration: float = count / don.sprite_frames.get_animation_speed(move.animation) / move.speed
			assert(duration >= 0.25 and duration <= 0.4, str(duration))
	for pair in [["standing_punch", "heavy_punch"], ["standing_kick", "heavy_kick"]]:
		var normal: Dictionary = don.moves[pair[0]]
		var heavy: Dictionary = don.moves[pair[1]]
		assert(heavy.damage > normal.damage)
		assert(heavy.hitboxes[0].rect.end.x > normal.hitboxes[0].rect.end.x)
		assert(heavy.hitboxes[0].from_frame > normal.hitboxes[0].from_frame)

	var select: Node = (load(game.SCENES.character_select) as PackedScene).instantiate()
	root.add_child(select)
	await process_frame
	select._cursor = game.character_ids().find("don")
	select._refresh()
	assert(select._name.text.begins_with("DON"))
	assert(select._preview.sprite_frames == don.sprite_frames)
	var font: Font = select._name.get_theme_font("font")
	var font_size: int = select._name.get_theme_font_size("font_size")
	assert(select._name.position.x + font.get_string_size(
		select._name.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size,
	).x <= float(ProjectSettings.get_setting("display/window/size/viewport_width")) - 24,
		"Don's roster title must fit the logical game viewport")
	var output := OS.get_cmdline_user_args()[0] if not OS.get_cmdline_user_args().is_empty() else ""
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
		await RenderingServer.frame_post_draw
		assert(root.get_texture().get_image().save_png(output.path_join("Don_roster.png")) == OK)
	select.free()

	game.mode = game.MODE_TRAINING
	game.p1_character = "don"
	game.p2_character = "bruiser"
	game.stage_id = "training_grounds"
	var fight: Node = (load(game.SCENES.fight) as PackedScene).instantiate()
	root.add_child(fight)
	await process_frame
	var a: Fighter = fight.p1
	var b: Fighter = fight.p2
	assert(a.data == don and a.controls_enabled)
	await create_timer(0.1).timeout
	a.input = FighterInput.new()
	b.input = FighterInput.new()
	a.input._set_state(&"up", true)
	await create_timer(0.1).timeout
	assert(a.is_airborne() and a.sprite.animation == &"jump", a.debug_summary())
	var held_frames := 0
	var holding := false
	var deadline := Time.get_ticks_msec() + 2000
	while a.is_airborne() and Time.get_ticks_msec() < deadline:
		await physics_frame
		if not a.is_airborne():
			break
		if a.sprite.animation == &"air_idle":
			holding = true
			held_frames += 1
			assert(not a.sprite.is_playing() and a.sprite.frame == 0)
		if holding:
			assert(a.state == Fighter.State.JUMP and a.sprite.animation == &"air_idle",
				"Jump must hold the tucked pose until physical landing")
	assert(held_frames >= 6, "The airborne pose must visibly hold, not play through landing")
	assert(a.state == Fighter.State.IDLE and a.sprite.animation == &"standing_idle")
	await create_timer(0.15).timeout
	assert(a.state == Fighter.State.IDLE, "Holding jump must not restart it after landing")
	fight._restart_match()
	if not output.is_empty():
		await RenderingServer.frame_post_draw
		assert(root.get_texture().get_image().save_png(output.path_join("Don_training.png")) == OK)
	var cases: Array = []
	for face in [1, -1]:
		for move_name in don.moves:
			cases.append([move_name, face])
	for case in cases:
		var move_name: String = case[0]
		var face: int = case[1]
		a.input = FighterInput.new()
		b.input = FighterInput.new()
		a.reset(Vector2(960 - 105 * face, a.floor_y), face)
		b.reset(Vector2(960, b.floor_y), -face)
		a._face_opponent()
		fight._since_hit = 0.0
		var move: Dictionary = don.moves[move_name]
		var stance: String = move.input.stance
		var played: Array[int] = [0]
		var record_frame := func() -> void:
			if a.state == Fighter.State.ATTACK and a.sprite.animation == StringName(move.animation):
				if played[-1] != a.sprite.frame:
					played.append(a.sprite.frame)
				if not output.is_empty() and a.sprite.frame == 2 and move_name in [
					"standing_punch", "standing_kick", "crouched_kick",
				]:
					await RenderingServer.frame_post_draw
					assert(root.get_texture().get_image().save_png(output.path_join(
						"Don_%s_facing_%d.png" % [move_name, face],
					)) == OK)
		a.sprite.frame_changed.connect(record_frame)
		if stance == "crouching":
			a.input.held[&"down"] = true
			await create_timer(0.05).timeout
		elif stance == "air":
			a.position.y -= 100
			a.velocity.y = 0
		a.input._set_state(StringName(move.input.button), true)
		if stance == "air":
			a._enter(Fighter.State.JUMP, &"air_idle")
		var duration: float = don.sprite_frames.get_frame_count(move.animation) \
				/ don.sprite_frames.get_animation_speed(move.animation) / move.speed
		await create_timer(duration + 0.25).timeout
		a.sprite.frame_changed.disconnect(record_frame)
		assert(b.health < int(b.data.stats.health), move_name + " must hit the dummy")
		assert(a.facing == face and a.sprite.flip_h == (face < 0))
		assert(a.state in [Fighter.State.IDLE, Fighter.State.CROUCH], a.debug_summary())
		if stance != "air" and "punch" in move_name:
			assert(played.size() == don.sprite_frames.get_frame_count(move.animation),
				move_name + " must play wind-up, strike and full recovery")
			for index in played.size():
				assert(played[index] == index, "Punch frames must not restart or be skipped")

	a.input = FighterInput.new()
	b.input = FighterInput.new()
	a.reset(Vector2(800, a.floor_y), 1)
	b.reset(Vector2(905, b.floor_y), -1)
	a.input.held[&"block"] = true
	b.controls_enabled = true
	await create_timer(0.25).timeout
	assert(a.sprite.animation == &"block_idle", "Don holds his standing guard")
	b.input._set_state(&"kick", true)
	await create_timer(0.7).timeout
	assert(a.state == Fighter.State.BLOCK)
	assert(a.health < 1000 and a.health >= 990, "Block must only chip")

	a.input = FighterInput.new()
	a.reset(Vector2(800, a.floor_y), 1)
	b.controls_enabled = false
	a._enter(Fighter.State.JUMP, &"air_idle")
	a.position.y -= 600
	a._start_move(don.moves.jump_punch)
	await create_timer(0.55).timeout
	assert(a.is_airborne() and a.state == Fighter.State.JUMP)
	assert(a.sprite.animation == &"air_idle", "Aerial attacks recover to the airborne pose")
	a._play(&"jump")
	a.sprite.pause()
	for frame in don.sprite_frames.get_frame_count(&"jump"):
		a.sprite.frame = frame
		var offset := don.get_sprite_offset(&"jump", frame)
		assert(a.sprite.offset.is_equal_approx(offset))
		a.facing = -1
		a._apply_offset()
		assert(a.sprite.offset.is_equal_approx(Vector2(-offset.x, offset.y)))
		a.facing = 1
	a.reset(Vector2(800, a.floor_y), 1)
	a.receive_hit(b.data.moves.heavy_kick.hitboxes[0], b)
	await create_timer(2.0).timeout
	assert(a.state == Fighter.State.DOWN, "Don must not invent a get-up recovery")
	assert(a.sprite.animation == &"fall_on_back")
	assert(a.sprite.frame == don.sprite_frames.get_frame_count(&"fall_on_back") - 1)
	fight._restart_match()
	assert(a.state == Fighter.State.IDLE and a.health == 1000 and a.controls_enabled)
	fight.free()
	print("PASS Don moves, blocking, held jump pose, airborne recovery, origins and knockdowns")
	quit()
