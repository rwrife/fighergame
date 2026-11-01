class_name FighterShadow
extends Node2D
## Chunky translucent ground shadow drawn under both fighters. It stays on the
## floor while its fighter is airborne, shrinking and fading with height.

const COLOR := Color(0.04, 0.05, 0.1, 0.42)
const PIXEL := 2.0
const FADE_HEIGHT := 320.0
const MIN_SCALE := 0.55
const MIN_OPACITY := 0.45
const HEIGHT_RATIO := 0.18
const MAX_HALF_HEIGHT := 16.0
const RESIZE_RATE := 10.0

var half_width := 0.0
var height := 0.0


func _init() -> void:
	z_index = -1


## offset is relative to the fighter: x = footprint centre, y = floor below it.
func update(offset: Vector2, target_half_width: float, delta: float, snap := false) -> void:
	if snap or half_width <= 0.0:
		half_width = target_half_width
	else:
		half_width = lerpf(half_width, target_half_width, minf(1.0, delta * RESIZE_RATE))
	position = Vector2(roundf(offset.x), offset.y)
	height = maxf(0.0, offset.y)
	queue_redraw()


func current_size() -> Vector2:
	var lift := clampf(height / FADE_HEIGHT, 0.0, 1.0)
	var radius_x := half_width * lerpf(1.0, MIN_SCALE, lift)
	return Vector2(radius_x, minf(radius_x * HEIGHT_RATIO, MAX_HALF_HEIGHT))


func current_color() -> Color:
	var color := COLOR
	color.a *= lerpf(1.0, MIN_OPACITY, clampf(height / FADE_HEIGHT, 0.0, 1.0))
	return color


func _draw() -> void:
	var radius := current_size()
	if radius.y < PIXEL:
		return
	var color := current_color()
	var rows := ceili(radius.y / PIXEL)
	for row in range(-rows, rows):
		var t := (row + 0.5) * PIXEL / radius.y
		if absf(t) >= 1.0:
			continue
		var half := snappedf(radius.x * sqrt(1.0 - t * t), PIXEL)
		if half > 0.0:
			draw_rect(Rect2(-half, row * PIXEL, half * 2.0, PIXEL), color)
