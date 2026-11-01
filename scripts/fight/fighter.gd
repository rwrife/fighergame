class_name Fighter
extends Node2D
## One combatant: state machine, physics, data-driven moves and hit reactions.
## All character-specific numbers come from CharacterData.

enum State { IDLE, WALK, CROUCH, JUMP, ATTACK, BLOCK, HITSTUN, BLOCKSTUN, LAUNCHED, DOWN }

const FRICTION := 2400.0
const WAKEUP_TIME := 1.1 # placeholder until a get-up animation exists
const CHIP_FRACTION := 0.1
const NEUTRAL := {&"left": false, &"right": false, &"up": false, &"down": false,
		&"punch": false, &"kick": false, &"heavy_punch": false, &"heavy_kick": false, &"block": false}

var data: CharacterData
var input := FighterInput.new()
var opponent: Fighter
var floor_y := 596.0
var _base_offset := Vector2.ZERO
var min_x := 0.0
var max_x := 1920.0
var facing := 1
var velocity := Vector2.ZERO
var health := 1000
var state := State.IDLE
var state_time := 0.0
var controls_enabled := false
var invulnerable := false
var ko := false
var move := {}
var sprite := AnimatedSprite2D.new()
var shadow := FighterShadow.new()

var _anim_id := &""
var _anim_speed := 1.0
var _freeze := 0.0
var _flash := 0.0
var _stun := 0.0
var _air_attacked := false
var _hit_boxes_done: Array[int] = []


func setup(character: CharacterData, player_input: FighterInput) -> void:
	data = character
	input = player_input
	health = int(data.stats.health)
	sprite.sprite_frames = data.sprite_frames
	sprite.scale = Vector2.ONE * data.sprite_scale
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	sprite.animation_finished.connect(_on_animation_finished)
	add_child(shadow)
	add_child(sprite)
	_play(&"standing_idle")


func reset(start_position: Vector2, face: int) -> void:
	position = start_position
	facing = face
	velocity = Vector2.ZERO
	health = int(data.stats.health)
	ko = false
	invulnerable = false
	move = {}
	_freeze = 0.0
	_stun = 0.0
	_air_attacked = false
	input.clear_buffer()
	_to_neutral()
	_update_shadow(0.0, true)


func is_airborne() -> bool:
	return position.y < floor_y - 0.5


func tick(delta: float) -> void:
	input.poll(delta)
	_flash = maxf(0.0, _flash - delta)
	sprite.modulate = Color(1.6, 0.6, 0.6) if _flash > 0.0 else Color.WHITE
	if _freeze > 0.0:
		_freeze -= delta
		sprite.speed_scale = 0.0
		return
	sprite.speed_scale = _anim_speed * float(data.playback_speed.get(sprite.animation, 1.0))
	state_time += delta
	if not controls_enabled:
		input.clear_buffer()
	match state:
		State.IDLE, State.WALK, State.CROUCH:
			_face_opponent()
			_ground_control()
		State.JUMP:
			_air_control()
		State.BLOCK:
			_face_opponent()
			if not _held(&"block"):
				_to_neutral()
		State.BLOCKSTUN:
			_stun -= delta
			if _stun <= 0.0:
				if _held(&"block"):
					_enter(State.BLOCK, &"block_idle")
				else:
					_to_neutral()
		State.HITSTUN:
			_stun -= delta
			if _stun <= 0.0:
				_to_neutral()
		State.DOWN:
			if not ko and state_time >= WAKEUP_TIME:
				_to_neutral()
		_:
			pass
	_move_body(delta)
	_update_shadow(delta)


func freeze(time: float) -> void:
	_freeze = maxf(_freeze, time)


func get_hurtbox() -> Rect2:
	var kind := "standing"
	match state:
		State.DOWN:
			kind = "down"
		State.CROUCH:
			kind = "crouching"
		State.JUMP, State.LAUNCHED:
			kind = "air"
		State.ATTACK:
			if is_airborne():
				kind = "air"
			elif move.get("input", {}).get("stance", "") == "crouching":
				kind = "crouching"
	return _to_world(data.get_hurtbox(kind))


## Active hitboxes for the current animation frame: [{index, hit, rect}].
func get_active_hitboxes() -> Array:
	var active := []
	if state != State.ATTACK or _freeze > 0.0:
		return active
	var boxes: Array = move.hitboxes
	for i in boxes.size():
		var box: Dictionary = boxes[i]
		if not _hit_boxes_done.has(i) and sprite.frame >= box.from_frame and sprite.frame <= box.to_frame:
			active.append({"index": i, "hit": box, "rect": _to_world(box.rect)})
	return active


func mark_hit(box_index: int) -> void:
	_hit_boxes_done.append(box_index)


func can_be_hit() -> bool:
	return not invulnerable and state != State.DOWN and state != State.LAUNCHED


## Returns &"blocked" or &"hit".
func receive_hit(hit: Dictionary, attacker: Fighter) -> StringName:
	var away := 1 if position.x >= attacker.position.x else -1
	if _can_block():
		health = maxi(1, health - int(hit.damage * CHIP_FRACTION))
		_stun = hit.blockstun
		velocity.x = away * hit.pushback
		_enter(State.BLOCKSTUN, &"block_idle")
		freeze(hit.hitstop)
		return &"blocked"
	health = maxi(0, health - int(hit.damage))
	_flash = 0.12
	freeze(hit.hitstop)
	move = {}
	if health <= 0:
		ko = true
	if hit.launch or is_airborne() or ko:
		velocity = Vector2(away * maxf(hit.knockback, 300.0 if ko else 200.0), -650.0)
		position.y = minf(position.y, floor_y - 1.0)
		_enter(State.LAUNCHED, &"knocked_back_air")
	else:
		_stun = hit.hitstun
		velocity.x = away * hit.pushback
		var crouching := state == State.CROUCH
		_enter(State.HITSTUN, &"crouch_hit_stun" if crouching else &"hit_stun")
	return &"hit"


func debug_summary() -> String:
	return "%s%s  frame %d" % [State.keys()[state], " [" + move.id + "]" if not move.is_empty() else "", sprite.frame]


func _held(button: StringName) -> bool:
	return controls_enabled and input.held[button]


func _consume(button: StringName) -> bool:
	return controls_enabled and input.consume(button)


func _can_block() -> bool:
	return not is_airborne() and (state == State.BLOCK or state == State.BLOCKSTUN
			or ((state == State.IDLE or state == State.WALK or state == State.CROUCH) and _held(&"block")))


func _face_opponent() -> void:
	if opponent != null and not is_airborne():
		facing = 1 if opponent.position.x >= position.x else -1
	sprite.flip_h = facing < 0
	_apply_offset()


func _apply_offset() -> void:
	sprite.offset = Vector2(_base_offset.x * facing, _base_offset.y)

func _ground_control() -> void:
	if _held(&"block"):
		_enter(State.BLOCK, &"standing_block")
		velocity.x = 0.0
		return
	var crouching := _held(&"down")
	for button in FighterInput.BUTTONS:
		if _consume(button):
			var found: Dictionary = data.find_move("crouching" if crouching else "standing", String(button))
			if not found.is_empty():
				_start_move(found)
				return
	if _consume(&"up") and not crouching:
		velocity = Vector2(input.axis() * float(data.stats.jump_drift), -float(data.stats.jump_speed))
		_air_attacked = false
		_enter(State.JUMP, &"jump")
		return
	if crouching:
		velocity.x = 0.0
		_enter(State.CROUCH, &"crouched_idle")
		return
	var direction := input.axis() if controls_enabled else 0
	if direction == 0:
		velocity.x = 0.0
		_enter(State.IDLE, &"standing_idle")
	else:
		var forward := direction == facing
		velocity.x = direction * float(data.stats.walk_speed if forward else data.stats.back_speed)
		_enter(State.WALK, &"walk_forward" if forward else &"walk_back")


func _air_control() -> void:
	if _air_attacked:
		return
	for button in FighterInput.BUTTONS:
		if _consume(button):
			var found: Dictionary = data.find_move("air", String(button))
			if not found.is_empty():
				_air_attacked = true
				_start_move(found)
				return


func _start_move(found: Dictionary) -> void:
	move = found
	_hit_boxes_done.clear()
	_enter(State.ATTACK, StringName(found.animation), found.speed)


func _enter(new_state: State, animation_id: StringName, speed := 1.0) -> void:
	if new_state != state:
		state = new_state
		state_time = 0.0
	_play(animation_id, speed)


func _play(animation_id: StringName, speed := 1.0) -> void:
	_anim_speed = speed
	if animation_id == _anim_id and sprite.is_playing():
		return
	var resolved := data.get_animation(animation_id)
	if resolved == &"":
		return
	_anim_id = animation_id
	_base_offset = data.sprite_offsets.get(resolved, Vector2.ZERO)
	_apply_offset()
	sprite.play(resolved)


func _to_neutral() -> void:
	move = {}
	state = State.CROUCH if _held(&"down") else State.IDLE
	state_time = 0.0
	_anim_id = &""
	_anim_speed = 1.0
	_play(&"crouched_idle" if state == State.CROUCH else &"standing_idle")


func _on_animation_finished() -> void:
	match state:
		State.ATTACK:
			if is_airborne():
				move = {}
				_enter(State.JUMP, &"jump")
				sprite.pause()
				sprite.frame = sprite.sprite_frames.get_frame_count(sprite.animation) - 1
			else:
				_to_neutral()
		State.BLOCK:
			_play(&"block_idle")


func _move_body(delta: float) -> void:
	var was_airborne := is_airborne()
	if was_airborne or velocity.y < 0.0:
		velocity.y += float(data.stats.gravity) * delta
	if not was_airborne and state in [State.HITSTUN, State.BLOCKSTUN, State.DOWN, State.ATTACK, State.LAUNCHED]:
		velocity.x = move_toward(velocity.x, 0.0, FRICTION * delta)
	position += velocity * delta
	position.x = clampf(position.x, min_x, max_x)
	if position.y >= floor_y and velocity.y >= 0.0:
		position.y = floor_y
		velocity.y = 0.0
		if was_airborne:
			_land()


func _land() -> void:
	match state:
		State.LAUNCHED:
			velocity.x *= 0.4
			_enter(State.DOWN, &"fall_on_back")
		State.JUMP, State.ATTACK:
			velocity.x = 0.0
			_to_neutral()


## The shadow footprint follows the current hurtbox (wide when knocked down),
## but is never narrower than the standing stance.
func _update_shadow(delta: float, snap := false) -> void:
	var footprint := get_hurtbox()
	var half_width := maxf(data.get_hurtbox("standing").size.x * 0.8, footprint.size.x * 0.5)
	shadow.update(Vector2(footprint.get_center().x - position.x, floor_y - position.y),
			half_width, delta, snap)


func _to_world(local: Rect2) -> Rect2:
	var rect := local
	if facing < 0:
		rect.position.x = -local.position.x - local.size.x
	rect.position += position
	return rect
