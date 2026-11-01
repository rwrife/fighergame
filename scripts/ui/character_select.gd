extends Control
## Character select: player 1 picks, then player 2 (or the training dummy).

const SLOTS := 6
const COLUMNS := 3
const TILE := Vector2(130, 130)

var _picking := 1
var _cursor := 0
var _ids: Array = []
var _tiles: Array[Panel] = []
var _header: Label
var _name: Label
var _info: Label
var _picks: Label
var _preview := AnimatedSprite2D.new()


func _ready() -> void:
	_ids = Game.character_ids()
	Arcade.backdrop(self, Color("1d2b53"), Color("7e2553"))
	_header = Arcade.label(self, "", 48, Arcade.YELLOW)
	_header.position = Vector2(0, 24)
	_header.custom_minimum_size = Vector2(960, 0)

	var origin := Vector2(480 - COLUMNS * TILE.x / 2.0 - (COLUMNS - 1) * 8, 100)
	for i in SLOTS:
		var tile := Panel.new()
		tile.size = TILE
		tile.position = origin + Vector2(i % COLUMNS * (TILE.x + 16), i / COLUMNS * (TILE.y + 16))
		add_child(tile)
		_tiles.append(tile)
		if i < _ids.size():
			var data: CharacterData = Game.characters[_ids[i]]
			var icon := TextureRect.new()
			icon.texture = data.portrait()
			icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
			icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			icon.size = Vector2(TILE.x, TILE.y - 28)
			tile.add_child(icon)
			var caption := Arcade.label(tile, data.display_name.to_upper(), 20)
			caption.position = Vector2(0, TILE.y - 30)
			caption.custom_minimum_size = Vector2(TILE.x, 0)
		else:
			var locked := Arcade.label(tile, "???", 44, Color(1, 1, 1, 0.4))
			locked.position = Vector2(0, 50)
			locked.custom_minimum_size = Vector2(TILE.x, 0)

	_preview.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_preview.scale = Vector2(1.76, 1.76)
	_preview.position = Vector2(150, 470)
	add_child(_preview)
	_name = Arcade.label(self, "", 36, Arcade.YELLOW, HORIZONTAL_ALIGNMENT_LEFT)
	_name.position = Vector2(300, 400)
	_info = Arcade.label(self, "", 20, Arcade.WHITE, HORIZONTAL_ALIGNMENT_LEFT)
	_info.position = Vector2(300, 450)
	_picks = Arcade.label(self, "", 22, Arcade.CYAN)
	_picks.position = Vector2(0, 604)
	_picks.custom_minimum_size = Vector2(960, 0)
	_refresh()


func _unhandled_input(event: InputEvent) -> void:
	var action := Game.menu_action(event)
	if action == &"":
		return
	get_viewport().set_input_as_handled()
	match action:
		&"left":
			_cursor = (_cursor + SLOTS - 1) % SLOTS
		&"right":
			_cursor = (_cursor + 1) % SLOTS
		&"up":
			_cursor = (_cursor + SLOTS - COLUMNS) % SLOTS
		&"down":
			_cursor = (_cursor + COLUMNS) % SLOTS
		&"accept":
			if _cursor < _ids.size():
				_confirm(_ids[_cursor])
		&"back":
			if _picking == 2:
				_picking = 1
			else:
				Game.goto("title")
	_refresh()


func _confirm(id: String) -> void:
	if _picking == 1:
		Game.p1_character = id
		_picking = 2
	else:
		Game.p2_character = id
		Game.goto("stage_select")


func _refresh() -> void:
	var p2_label := "DUMMY" if Game.mode == Game.MODE_TRAINING else "PLAYER 2"
	_header.text = "PLAYER 1 - SELECT FIGHTER" if _picking == 1 else p2_label + " - SELECT FIGHTER"
	for i in _tiles.size():
		var style := StyleBoxFlat.new()
		style.bg_color = Color(0, 0, 0, 0.55)
		style.set_border_width_all(6 if i == _cursor else 2)
		style.border_color = Arcade.YELLOW if i == _cursor else Color(1, 1, 1, 0.4)
		_tiles[i].add_theme_stylebox_override("panel", style)
	_picks.text = "P1: %s" % Game.characters[Game.p1_character].display_name if _picking == 2 else "ENTER / J: select    ESC / K: back"
	if _cursor < _ids.size():
		var data: CharacterData = Game.characters[_ids[_cursor]]
		_name.text = "%s - %s" % [data.display_name.to_upper(), data.title]
		var found := CharacterData.REQUIRED_ANIMATIONS.size() - data.missing_animations.size()
		_info.text = "HEALTH %d   SPEED %d\nMoves: %d   Animations: %d/%d%s" % [
			data.stats.health, data.stats.walk_speed, data.moves.size(), found,
			CharacterData.REQUIRED_ANIMATIONS.size(),
			" (placeholder art)" if not data.placeholder_animations.is_empty() else ""]
		_preview.sprite_frames = data.sprite_frames
		_preview.offset = Vector2(0, -78)
		_preview.play(data.get_animation(&"standing_idle"))
		_preview.visible = true
	else:
		_name.text = "COMING SOON"
		_info.text = "Add a folder under characters/ to fill this slot."
		_preview.visible = false
