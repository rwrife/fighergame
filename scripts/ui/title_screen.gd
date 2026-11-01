extends Control
## Title screen: "press start" then the main menu.

const ITEMS := [
	["VERSUS", "versus"],
	["TRAINING", "training"],
	["ANIMATION LAB", "lab"],
	["QUIT", "quit"],
]

var _menu_labels: Array[Label] = []
var _index := 0
var _prompt: Label
var _menu_open := false
var _time := 0.0


func _ready() -> void:
	var art := TextureRect.new()
	art.texture = load("res://assets/ui/title_screen.jpg")
	art.set_anchors_preset(Control.PRESET_FULL_RECT)
	art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	add_child(art)

	_prompt = Arcade.label(self, "PRESS ENTER", 40, Arcade.WHITE)
	_prompt.position = Vector2(0, 470)
	_prompt.custom_minimum_size = Vector2(960, 0)

	for i in ITEMS.size():
		var item := Arcade.label(self, ITEMS[i][0], 36)
		item.position = Vector2(0, 410 + i * 46)
		item.custom_minimum_size = Vector2(960, 0)
		item.visible = false
		_menu_labels.append(item)

	var help := Arcade.label(self, "P1: WASD + J/K/L    P2: ARROWS + , . /    ENTER: select    ESC: back", 16, Arcade.WHITE)
	help.position = Vector2(0, 612)
	help.custom_minimum_size = Vector2(960, 0)
	_refresh()


func _process(delta: float) -> void:
	_time += delta
	_prompt.visible = not _menu_open and fmod(_time, 1.0) < 0.65


func _unhandled_input(event: InputEvent) -> void:
	var action := Game.menu_action(event)
	if action == &"":
		return
	get_viewport().set_input_as_handled()
	if not _menu_open:
		if action == &"accept":
			_open_menu()
		return
	match action:
		&"up":
			_index = (_index + ITEMS.size() - 1) % ITEMS.size()
		&"down":
			_index = (_index + 1) % ITEMS.size()
		&"accept":
			_activate(ITEMS[_index][1])
		&"back":
			_menu_open = false
			for label in _menu_labels:
				label.visible = false
	_refresh()


func _open_menu() -> void:
	_menu_open = true
	for label in _menu_labels:
		label.visible = true
	_refresh()


func _activate(key: String) -> void:
	match key:
		"versus", "training":
			Game.mode = key
			Game.goto("character_select")
		"lab":
			Game.goto("lab")
		"quit":
			get_tree().quit()


func _refresh() -> void:
	for i in _menu_labels.size():
		var selected := i == _index
		_menu_labels[i].text = ("> %s <" if selected else "%s") % ITEMS[i][0]
		_menu_labels[i].add_theme_color_override("font_color", Arcade.YELLOW if selected else Arcade.WHITE)
