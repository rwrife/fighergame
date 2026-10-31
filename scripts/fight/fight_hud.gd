class_name FightHud
extends CanvasLayer
## Health bars, timer, round pips, center message and training read-out.

const BAR_SIZE := Vector2(380, 28)
const BAR_TOP := 28.0

var _fills: Array[ColorRect] = []
var _wins: Array[Label] = []
var _timer: Label
var _message: Label
var _training: Label
var _root := Control.new()


func _init() -> void:
	layer = 10
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)


func build(p1_name: String, p2_name: String) -> void:
	for side in 2:
		var x := 24.0 if side == 0 else 960.0 - 24.0 - BAR_SIZE.x
		var back := ColorRect.new()
		back.color = Color("1b0a2a")
		back.position = Vector2(x - 4, BAR_TOP - 4)
		back.size = BAR_SIZE + Vector2(8, 8)
		_root.add_child(back)
		var fill := ColorRect.new()
		fill.color = Arcade.YELLOW
		fill.position = Vector2(x, BAR_TOP)
		fill.size = BAR_SIZE
		_root.add_child(fill)
		_fills.append(fill)
		var name_label := Arcade.label(_root, (p1_name if side == 0 else p2_name).to_upper(), 22, Arcade.WHITE,
				HORIZONTAL_ALIGNMENT_LEFT if side == 0 else HORIZONTAL_ALIGNMENT_RIGHT)
		name_label.position = Vector2(x, BAR_TOP + 34)
		name_label.custom_minimum_size = Vector2(BAR_SIZE.x, 0)
		var pips := Arcade.label(_root, "", 22, Arcade.RED,
				HORIZONTAL_ALIGNMENT_LEFT if side == 0 else HORIZONTAL_ALIGNMENT_RIGHT)
		pips.position = Vector2(x, BAR_TOP + 62)
		pips.custom_minimum_size = Vector2(BAR_SIZE.x, 0)
		_wins.append(pips)
	_timer = Arcade.label(_root, "99", 44, Arcade.WHITE)
	_timer.position = Vector2(430, 14)
	_timer.custom_minimum_size = Vector2(100, 0)
	_message = Arcade.label(_root, "", 90, Arcade.YELLOW)
	_message.position = Vector2(0, 200)
	_message.custom_minimum_size = Vector2(960, 0)
	_training = Arcade.label(_root, "", 18, Arcade.CYAN, HORIZONTAL_ALIGNMENT_LEFT)
	_training.position = Vector2(24, 100)


func set_health(side: int, ratio: float) -> void:
	var fill := _fills[side]
	var width := BAR_SIZE.x * clampf(ratio, 0.0, 1.0)
	fill.size.x = width
	if side == 1:
		fill.position.x = 960.0 - 24.0 - width
	fill.color = Arcade.YELLOW if ratio > 0.3 else Arcade.RED


func set_wins(side: int, wins: int) -> void:
	_wins[side].text = "●".repeat(wins)


func set_timer(value: String) -> void:
	_timer.text = value


func set_message(text: String) -> void:
	_message.text = text


func set_training_text(text: String) -> void:
	_training.text = text
