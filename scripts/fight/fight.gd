extends Node2D
## The fight scene: stage, two fighters, camera, hit resolution and round flow.

enum Phase { INTRO, FIGHT, ROUND_END, MATCH_END }

const ROUND_TIME := 99.0
const WINS_NEEDED := 2
const MIN_SEPARATION := 70.0
const MAX_DISTANCE := 780.0
const INTRO_TIME := 1.6

var stage: StageData
var p1: Fighter
var p2: Fighter
var hud := FightHud.new()
var overlay := DebugOverlay.new()
var phase := Phase.INTRO
var wins := [0, 0]
var round_number := 1
var time_left := ROUND_TIME
var paused := false

var _camera := Camera2D.new()
var _phase_time := 0.0
var _message_time := 0.0
var _training := false
var _since_hit := 0.0


func _ready() -> void:
	_training = Game.mode == Game.MODE_TRAINING
	if Game.stages.is_empty() or Game.characters.is_empty():
		push_error("No stages or characters registered.")
		return
	if not Game.stages.has(Game.stage_id):
		Game.stage_id = Game.stage_ids()[0]
	if not Game.characters.has(Game.p1_character):
		Game.p1_character = Game.character_ids()[0]
	if not Game.characters.has(Game.p2_character):
		Game.p2_character = Game.p1_character
	stage = Game.stages[Game.stage_id]

	var view := StageView.new()
	add_child(view)
	view.build(stage)

	p1 = _spawn(Game.characters[Game.p1_character], HumanInput.new(1))
	p2 = _spawn(Game.characters[Game.p2_character], FighterInput.new() if _training else HumanInput.new(2))
	p1.opponent = p2
	p2.opponent = p1

	overlay.fighters = [p1, p2]
	overlay.floor_y = stage.floor_y
	overlay.width = stage.width
	overlay.visible = _training
	add_child(overlay)

	_camera.limit_left = 0
	_camera.limit_right = int(stage.width)
	_camera.limit_top = 0
	_camera.limit_bottom = int(StageView.VIEW.y)
	add_child(_camera)
	_camera.make_current()

	add_child(hud)
	hud.build(p1.data.display_name, p2.data.display_name + (" (DUMMY)" if _training else ""))
	_start_round()


func _spawn(character: CharacterData, input: FighterInput) -> Fighter:
	var fighter := Fighter.new()
	fighter.floor_y = stage.floor_y
	fighter.min_x = 60.0
	fighter.max_x = stage.width - 60.0
	add_child(fighter)
	fighter.setup(character, input)
	return fighter


func _start_round() -> void:
	var mid := stage.width / 2.0
	p1.reset(Vector2(mid - 200, stage.floor_y), 1)
	p2.reset(Vector2(mid + 200, stage.floor_y), -1)
	p1.controls_enabled = false
	p2.controls_enabled = false
	time_left = ROUND_TIME
	_phase_time = 0.0
	_since_hit = 0.0
	if _training:
		phase = Phase.FIGHT
		p1.controls_enabled = true
		hud.set_message("")
	else:
		phase = Phase.INTRO
		hud.set_message("ROUND %d" % round_number)
	hud.set_wins(0, wins[0])
	hud.set_wins(1, wins[1])


func _physics_process(delta: float) -> void:
	if p1 == null or paused:
		return
	_phase_time += delta
	if _message_time > 0.0:
		_message_time -= delta
		if _message_time <= 0.0 and phase == Phase.FIGHT:
			hud.set_message("")
	match phase:
		Phase.INTRO:
			if _phase_time >= INTRO_TIME:
				phase = Phase.FIGHT
				_phase_time = 0.0
				p1.controls_enabled = true
				p2.controls_enabled = true
				hud.set_message("FIGHT!")
				_message_time = 0.8
		Phase.FIGHT:
			_update_fight(delta)
		Phase.ROUND_END:
			if _phase_time >= 2.5:
				if _training or wins[0] >= WINS_NEEDED or wins[1] >= WINS_NEEDED:
					if _training:
						_start_round()
					else:
						phase = Phase.MATCH_END
						hud.set_message("ENTER: REMATCH")
				else:
					round_number += 1
					_start_round()
	p1.tick(delta)
	p2.tick(delta)
	if phase == Phase.FIGHT or phase == Phase.ROUND_END:
		_resolve_combat()
	_separate_fighters()
	_update_camera()
	_update_hud()


func _update_fight(delta: float) -> void:
	_since_hit += delta
	if _training:
		time_left = ROUND_TIME
		if _since_hit > 2.0 and not p1.ko and not p2.ko:
			p1.health = int(p1.data.stats.health)
			p2.health = int(p2.data.stats.health)
		if (p1.ko and p1.state == Fighter.State.DOWN) or (p2.ko and p2.state == Fighter.State.DOWN):
			phase = Phase.ROUND_END
			_phase_time = 0.0
			hud.set_message("K.O.")
		return
	time_left -= delta
	var p1_down := p1.ko and p1.state == Fighter.State.DOWN
	var p2_down := p2.ko and p2.state == Fighter.State.DOWN
	if p1_down or p2_down or time_left <= 0.0:
		var winner := -1
		if p1_down and p2_down:
			winner = -1
		elif p2_down:
			winner = 0
		elif p1_down:
			winner = 1
		elif p1.health != p2.health:
			winner = 0 if p1.health > p2.health else 1
		if winner >= 0:
			wins[winner] += 1
		phase = Phase.ROUND_END
		_phase_time = 0.0
		p1.controls_enabled = false
		p2.controls_enabled = false
		var text := "K.O." if (p1_down or p2_down) else "TIME OVER"
		if winner < 0:
			text += "\nDRAW"
		elif wins[winner] >= WINS_NEEDED:
			text = "PLAYER %d WINS!" % (winner + 1)
		hud.set_message(text)
		hud.set_wins(0, wins[0])
		hud.set_wins(1, wins[1])


func _resolve_combat() -> void:
	var first := _find_hit(p1, p2)
	var second := _find_hit(p2, p1)
	for pair in [[p1, p2, first], [p2, p1, second]]:
		var found: Dictionary = pair[2]
		if found.is_empty():
			continue
		pair[0].mark_hit(found.index)
		pair[1].receive_hit(found.hit, pair[0])
		pair[0].freeze(found.hit.hitstop)
		_since_hit = 0.0


func _find_hit(attacker: Fighter, defender: Fighter) -> Dictionary:
	if not defender.can_be_hit():
		return {}
	var hurtbox := defender.get_hurtbox()
	for box in attacker.get_active_hitboxes():
		if box.rect.intersects(hurtbox):
			return box
	return {}


func _separate_fighters() -> void:
	var gap := p2.position.x - p1.position.x
	if not p1.is_airborne() and not p2.is_airborne() and absf(gap) < MIN_SEPARATION:
		var push := (MIN_SEPARATION - absf(gap)) / 2.0 * (1.0 if gap >= 0.0 else -1.0)
		p1.position.x -= push
		p2.position.x += push
	gap = p2.position.x - p1.position.x
	if absf(gap) > MAX_DISTANCE:
		var pull := (absf(gap) - MAX_DISTANCE) / 2.0 * signf(gap)
		p1.position.x += pull
		p2.position.x -= pull
	p1.position.x = clampf(p1.position.x, p1.min_x, p1.max_x)
	p2.position.x = clampf(p2.position.x, p2.min_x, p2.max_x)


func _update_camera() -> void:
	var half := StageView.VIEW.x / 2.0
	_camera.position = Vector2(clampf((p1.position.x + p2.position.x) / 2.0, half, stage.width - half),
			StageView.VIEW.y / 2.0)


func _update_hud() -> void:
	hud.set_health(0, float(p1.health) / float(p1.data.stats.health))
	hud.set_health(1, float(p2.health) / float(p2.data.stats.health))
	hud.set_timer("--" if _training else str(ceili(maxf(time_left, 0.0))))
	if _training:
		hud.set_training_text("P1 %s\nP1 missing animations: %s\nKeys: WASD + J punch / K kick / L block   Pad: stick/D-pad + X punch / A kick / B block\nF1: hitboxes   R: reset   ESC: pause" % [
			p1.debug_summary(), ", ".join(PackedStringArray(p1.data.missing_animations)) if not p1.data.missing_animations.is_empty() else "none"])


func _unhandled_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_F1:
			overlay.visible = not overlay.visible
		KEY_ESCAPE:
			paused = not paused
			hud.set_message("PAUSED\n(R restart  C select  T title)" if paused else "")
		KEY_R:
			if paused or _training or phase == Phase.MATCH_END:
				_restart_match()
		KEY_ENTER:
			if phase == Phase.MATCH_END:
				_restart_match()
		KEY_C:
			if paused or phase == Phase.MATCH_END:
				Game.goto("character_select")
		KEY_T:
			if paused or phase == Phase.MATCH_END:
				Game.goto("title")
		_:
			return
	get_viewport().set_input_as_handled()


func _restart_match() -> void:
	paused = false
	wins = [0, 0]
	round_number = 1
	_start_round()
