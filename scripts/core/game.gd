extends Node
## Autoload "Game": content registry, match selections, input map and scene flow.

const TITLE := "FIGHTER GAME"
const SCENES := {
	"title": "res://scenes/title_screen.tscn",
	"character_select": "res://scenes/character_select.tscn",
	"stage_select": "res://scenes/stage_select.tscn",
	"fight": "res://scenes/fight.tscn",
	"lab": "res://scenes/animation_lab.tscn",
}
const MODE_VERSUS := "versus"
const MODE_TRAINING := "training"
const BINDINGS := {
	1: {"left": KEY_A, "right": KEY_D, "up": KEY_W, "down": KEY_S, "punch": KEY_J, "kick": KEY_K, "block": KEY_L},
	2: {"left": KEY_LEFT, "right": KEY_RIGHT, "up": KEY_UP, "down": KEY_DOWN,
			"punch": KEY_COMMA, "kick": KEY_PERIOD, "block": KEY_SLASH},
}
const PAD_BUTTONS := {
	"left": JOY_BUTTON_DPAD_LEFT, "right": JOY_BUTTON_DPAD_RIGHT, "up": JOY_BUTTON_DPAD_UP,
	"down": JOY_BUTTON_DPAD_DOWN, "punch": JOY_BUTTON_X, "kick": JOY_BUTTON_A, "block": JOY_BUTTON_B,
}

var characters := {}
var stages := {}
var mode := MODE_VERSUS
var p1_character := ""
var p2_character := ""
var stage_id := ""

var _fade := ColorRect.new()
var _changing := false


func _ready() -> void:
	_register_input()
	_scan("res://characters", "character.json", func(path: String) -> void:
		var data := CharacterData.load_from(path)
		if data != null:
			for error in data.errors:
				push_warning(error)
			characters[data.id] = data)
	_scan("res://stages", "stage.json", func(path: String) -> void:
		var data := StageData.load_from(path)
		if data != null:
			stages[data.id] = data)
	var layer := CanvasLayer.new()
	layer.layer = 100
	_fade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_fade.color = Color(0, 0, 0, 0)
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_fade)
	add_child(layer)


func character_ids() -> Array:
	var ids := characters.keys()
	ids.sort()
	return ids


func stage_ids() -> Array:
	var ids := stages.keys()
	ids.sort()
	return ids


func goto(scene_key: String) -> void:
	if _changing:
		return
	_changing = true
	var tween := create_tween()
	tween.tween_property(_fade, "color:a", 1.0, 0.15)
	await tween.finished
	get_tree().paused = false
	get_tree().change_scene_to_file(SCENES[scene_key])
	tween = create_tween()
	tween.tween_property(_fade, "color:a", 0.0, 0.2)
	await tween.finished
	_changing = false


## Normalizes menu input from ui_* actions and player 1's fight controls.
func menu_action(event: InputEvent) -> StringName:
	if not event.is_pressed() or event.is_echo():
		return &""
	for pair in [[&"left", &"ui_left", &"p1_left"], [&"right", &"ui_right", &"p1_right"],
			[&"up", &"ui_up", &"p1_up"], [&"down", &"ui_down", &"p1_down"],
			[&"accept", &"ui_accept", &"p1_punch"], [&"back", &"ui_cancel", &"p1_kick"]]:
		if event.is_action(pair[1]) or event.is_action(pair[2]):
			return pair[0]
	return &""


func _scan(root: String, file_name: String, loader: Callable) -> void:
	var directory := DirAccess.open(root)
	if directory == null:
		push_error("Cannot open " + root)
		return
	var names := directory.get_directories()
	names.sort()
	for folder in names:
		var path := root.path_join(folder).path_join(file_name)
		if FileAccess.file_exists(path):
			loader.call(path)


func _register_input() -> void:
	for player in BINDINGS:
		var device: int = player - 1
		for action in BINDINGS[player]:
			var name := "p%d_%s" % [player, action]
			if not InputMap.has_action(name):
				InputMap.add_action(name)
			var key := InputEventKey.new()
			key.physical_keycode = BINDINGS[player][action]
			InputMap.action_add_event(name, key)
			var button := InputEventJoypadButton.new()
			button.device = device
			button.button_index = PAD_BUTTONS[action]
			InputMap.action_add_event(name, button)
