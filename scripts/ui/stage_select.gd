extends Control
## Stage select with a live preview of the stage's layers.

var _ids: Array = []
var _index := 0
var _preview_clip := Control.new()
var _preview_root := Node2D.new()
var _name: Label
var _desc: Label
var _hint: Label


func _ready() -> void:
	_ids = Game.stage_ids()
	Arcade.backdrop(self, Color("0b132b"), Color("5bc0be"))
	var header := Arcade.label(self, "SELECT STAGE", 48, Arcade.YELLOW)
	header.position = Vector2(0, 24)
	header.custom_minimum_size = Vector2(960, 0)
	_preview_clip.clip_contents = true
	_preview_clip.position = Vector2(240, 110)
	_preview_clip.size = Vector2(480, 320)
	_preview_clip.add_child(_preview_root)
	_preview_root.scale = Vector2(0.5, 0.5)
	add_child(_preview_clip)
	var frame := Panel.new()
	frame.position = _preview_clip.position - Vector2(6, 6)
	frame.size = _preview_clip.size + Vector2(12, 12)
	frame.show_behind_parent = true
	var style := StyleBoxFlat.new()
	style.bg_color = Arcade.YELLOW
	frame.add_theme_stylebox_override("panel", style)
	add_child(frame)
	move_child(frame, _preview_clip.get_index())
	_name = Arcade.label(self, "", 40, Arcade.WHITE)
	_name.position = Vector2(0, 450)
	_name.custom_minimum_size = Vector2(960, 0)
	_desc = Arcade.label(self, "", 22, Arcade.CYAN)
	_desc.position = Vector2(0, 510)
	_desc.custom_minimum_size = Vector2(960, 0)
	_hint = Arcade.label(self, "LEFT / RIGHT: choose    ENTER / J: fight!    ESC / K: back", 18)
	_hint.position = Vector2(0, 598)
	_hint.custom_minimum_size = Vector2(960, 0)
	_refresh()


func _unhandled_input(event: InputEvent) -> void:
	var action := Game.menu_action(event)
	if action == &"" or _ids.is_empty():
		return
	get_viewport().set_input_as_handled()
	match action:
		&"left", &"up":
			_index = (_index + _ids.size() - 1) % _ids.size()
		&"right", &"down":
			_index = (_index + 1) % _ids.size()
		&"accept":
			Game.stage_id = _ids[_index]
			Game.goto("fight")
		&"back":
			Game.goto("character_select")
	_refresh()


func _refresh() -> void:
	for child in _preview_root.get_children():
		child.queue_free()
	var stage: StageData = Game.stages[_ids[_index]]
	for layer in stage.layers:
		var art := StageLayerArt.new()
		art.setup(layer, StageView.VIEW)
		_preview_root.add_child(art)
	_name.text = "< %s >" % stage.display_name.to_upper()
	_desc.text = stage.description
