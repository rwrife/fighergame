class_name ArcadeBackdrop
extends Control
## Vertical gradient with scrolling diagonal stripes.

var _top: Color
var _bottom: Color
var _time := 0.0


func _init(top: Color, bottom: Color) -> void:
	_top = top
	_bottom = bottom
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(delta: float) -> void:
	_time += delta
	queue_redraw()


func _draw() -> void:
	var bands := 32
	for i in bands:
		var t := float(i) / (bands - 1)
		draw_rect(Rect2(0, size.y * i / bands, size.x, size.y / bands + 1), _top.lerp(_bottom, t))
	var offset := fmod(_time * 40.0, 120.0)
	for i in range(-8, int(size.x / 120.0) + 8):
		var x := i * 120.0 + offset
		draw_colored_polygon(PackedVector2Array([
			Vector2(x, 0), Vector2(x + 40, 0), Vector2(x - 200 + 40, size.y), Vector2(x - 200, size.y)]),
			Color(1, 1, 1, 0.05))
