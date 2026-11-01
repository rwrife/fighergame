extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _capture(output: String, name: String) -> void:
	if output.is_empty():
		return
	await RenderingServer.frame_post_draw
	assert(root.get_texture().get_image().save_png(output.path_join(name + ".png")) == OK)


func _run() -> void:
	var game := root.get_node("Game")
	assert(game.characters.has("tomoe"), "Tomoe must be registered")
	var tomoe: CharacterData = game.characters.tomoe
	assert(tomoe.errors.is_empty(), str(tomoe.errors))
	assert(tomoe.missing_animations.is_empty(), str(tomoe.missing_animations))
	assert(tomoe.placeholder_animations.is_empty())
	assert(not tomoe.recover_from_knockdown, "No unrequested get-up or automatic idle recovery")
	assert(tomoe.get_animation(&"walk_forward") == &"standing_idle")
	assert(tomoe.get_animation(&"hit_stun") != &"")
	for pair in [["standing_punch", "heavy_punch"], ["standing_kick", "heavy_kick"]]:
		var normal: Dictionary = tomoe.moves[pair[0]]
		var heavy: Dictionary = tomoe.moves[pair[1]]
		var count := tomoe.sprite_frames.get_frame_count(normal.animation)
		var duration: float = count / tomoe.sprite_frames.get_animation_speed(normal.animation) / normal.speed
		assert(duration >= 0.25 and duration <= 0.4)
		assert(heavy.damage > normal.damage)
		assert(heavy.hitboxes[0].rect.end.x > normal.hitboxes[0].rect.end.x)
		assert(heavy.hitboxes[0].from_frame > normal.hitboxes[0].from_frame)
	var output := OS.get_cmdline_user_args()[0] if not OS.get_cmdline_user_args().is_empty() else ""
	if not output.is_empty():
		DirAccess.make_dir_recursive_absolute(output)
	var lab: Control = (load(game.SCENES.lab) as PackedScene).instantiate()
	root.add_child(lab)
	await process_frame
	await process_frame
	assert(lab.error_label.text.is_empty(), lab.error_label.text)
	var count := 0
	var frame_count := 0
	var directory := DirAccess.open("res://assets/spritesheets")
	for file in directory.get_files():
		if not file.begins_with("Tomoe_") or not file.ends_with("_sheet.json"):
			continue
		var name := StringName(file.trim_suffix("_sheet.json"))
		var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			"res://assets/spritesheets".path_join(file)))
		assert(lab.sprite.sprite_frames.has_animation(name), String(name))
		assert(lab.sprite.sprite_frames.get_animation_speed(name) == data.fps)
		assert(data.fps == (12 if name == &"Tomoe_standing_idle" else 6))
		assert(lab.sprite.sprite_frames.get_animation_loop(name) == data.loop)
		assert(lab.sprite.sprite_frames.get_frame_count(name) == data.frame_count)
		lab.sprite.play(name)
		lab.sprite.pause()
		for index in int(data.frame_count):
			lab.sprite.frame = index
			var texture := lab.sprite.sprite_frames.get_frame_texture(name, index) as AtlasTexture
			assert(texture != null and texture.region.size == Vector2(346, 346))
			await process_frame
			frame_count += 1
		if name == &"Tomoe_heavy_kick":
			for picker_index in lab.animation_picker.item_count:
				if lab.animation_picker.get_item_metadata(picker_index) == name:
					lab.animation_picker.select(picker_index)
			lab.sprite.frame = 5
			await _capture(output, "Tomoe_roundhouse_lab")
		count += 1
	assert(count == 22 and frame_count == 169)
	lab.free()
	var select: Node = (load(game.SCENES.character_select) as PackedScene).instantiate()
	root.add_child(select)
	await process_frame
	select._cursor = game.character_ids().find("tomoe")
	select._refresh()
	assert(select._name.text.begins_with("TOMOE"))
	assert(select._preview.sprite_frames == tomoe.sprite_frames)
	var font: Font = select._name.get_theme_font("font")
	var font_size: int = select._name.get_theme_font_size("font_size")
	assert(select._name.position.x + font.get_string_size(
		select._name.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size,
	).x <= float(ProjectSettings.get_setting("display/window/size/viewport_width")) - 24,
		"Tomoe's roster title must fit the logical viewport")
	await _capture(output, "Tomoe_roster")
	select.free()
	game.mode = game.MODE_TRAINING
	game.p1_character = "tomoe"
	game.p2_character = "bruiser"
	game.stage_id = "training_grounds"
	var fight: Node = (load(game.SCENES.fight) as PackedScene).instantiate()
	root.add_child(fight)
	await process_frame
	var a: Fighter = fight.p1
	var b: Fighter = fight.p2
	assert(a.data == tomoe and a.controls_enabled)
	await _capture(output, "Tomoe_training")
	for face in [1, -1]:
		for move_name in tomoe.moves:
			a.input = FighterInput.new()
			b.input = FighterInput.new()
			a.reset(Vector2(960 - 95 * face, a.floor_y), face)
			b.reset(Vector2(960, b.floor_y), -face)
			a._face_opponent()
			fight._since_hit = 0.0
			var move: Dictionary = tomoe.moves[move_name]
			for hit in move.hitboxes:
				assert(hit.from_frame >= 0 and hit.to_frame < tomoe.sprite_frames.get_frame_count(move.animation))
			if move.input.stance == "crouching":
				a.input.held[&"down"] = true
				await create_timer(0.05).timeout
			elif move.input.stance == "air":
				a.position.y -= 100
				a.velocity.y = 0
				a._enter(Fighter.State.JUMP, &"air_idle")
			a.input._set_state(StringName(move.input.button), true)
			var captured := [false]
			var record := func() -> void:
				if a.state == Fighter.State.ATTACK and a.sprite.frame == move.hitboxes[0].from_frame:
					if not captured[0] and move_name in ["standing_punch", "standing_kick", "heavy_kick"]:
						captured[0] = true
						await _capture(output, "Tomoe_%s_facing_%d" % [move_name, face])
			a.sprite.frame_changed.connect(record)
			var duration: float = tomoe.sprite_frames.get_frame_count(move.animation) \
				/ tomoe.sprite_frames.get_animation_speed(move.animation) / move.speed
			await create_timer(duration + 0.3).timeout
			a.sprite.frame_changed.disconnect(record)
			assert(b.health < int(b.data.stats.health), move_name + " must hit the dummy in both facings")
			assert(a.facing == face and a.sprite.flip_h == (face < 0))
			assert(a.state in [Fighter.State.IDLE, Fighter.State.CROUCH], a.debug_summary())
	a.input = FighterInput.new()
	b.input = FighterInput.new()
	a.reset(Vector2(800, a.floor_y), 1)
	b.reset(Vector2(900, b.floor_y), -1)
	a.input.held[&"block"] = true
	b.controls_enabled = true
	await create_timer(0.25).timeout
	assert(a.sprite.animation == &"block_idle")
	b.input._set_state(&"kick", true)
	await create_timer(0.7).timeout
	assert(a.state == Fighter.State.BLOCK and a.health >= 990 and a.health < 1000)
	a.input = FighterInput.new()
	b.input = FighterInput.new()
	b.controls_enabled = false
	a.reset(Vector2(800, a.floor_y), 1)
	a.input._set_state(&"up", true)
	await create_timer(0.1).timeout
	assert(a.is_airborne())
	var deadline := Time.get_ticks_msec() + 2000
	var held := 0
	while a.is_airborne() and Time.get_ticks_msec() < deadline:
		await physics_frame
		if a.is_airborne() and a.sprite.animation == &"air_idle":
			assert(not a.sprite.is_playing() and a.sprite.frame == 0)
			held += 1
	assert(held >= 6 and a.state == Fighter.State.IDLE)
	a.input = FighterInput.new()
	a.reset(Vector2(800, a.floor_y), 1)
	a.position.y -= 600
	a._enter(Fighter.State.JUMP, &"air_idle")
	a._start_move(tomoe.moves.jump_punch)
	await create_timer(0.6).timeout
	assert(a.is_airborne() and a.state == Fighter.State.JUMP and a.sprite.animation == &"air_idle")
	for animation in [&"jump", &"jump_punch", &"fall_on_back"]:
		a._play(animation)
		a.sprite.pause()
		for index in tomoe.sprite_frames.get_frame_count(animation):
			a.sprite.frame = index
			a.facing = -1
			a._apply_offset()
			var offset := tomoe.get_sprite_offset(animation, index)
			assert(a.sprite.offset.is_equal_approx(Vector2(-offset.x, offset.y)))
	a.reset(Vector2(800, a.floor_y), 1)
	a.receive_hit(b.data.moves.heavy_kick.hitboxes[0], b)
	deadline = Time.get_ticks_msec() + 2000
	while a.state != Fighter.State.DOWN and Time.get_ticks_msec() < deadline:
		await process_frame
	assert(a.state == Fighter.State.DOWN)
	await create_timer(1.5).timeout
	assert(a.state == Fighter.State.DOWN and a.sprite.animation == &"fall_on_back")
	assert(not a.sprite.is_playing() and not a.can_be_hit())
	await _capture(output, "Tomoe_downed_candidate")
	for face in [1, -1]:
		b.position.x = a.position.x + face * 300
		a._face_opponent()
		assert(a.facing == face and a.sprite.flip_h == (face < 0))
		var down := tomoe.get_hurtbox("down")
		assert(absf(down.end.y) < 0.01, "Downed hurtbox must share the floor baseline")
		await _capture(output, "Tomoe_downed_facing_" + str(face))
	fight._restart_match()
	assert(a.state == Fighter.State.IDLE and a.health == 1000 and a.controls_enabled)
	fight.free()
	print("PASS Tomoe: 22 sheets, 169 lab frames, eight moves in both facings, blocking, jump, origins and held knockdown.")
	quit()
