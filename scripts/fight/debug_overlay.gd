class_name DebugOverlay
extends Node2D
## Draws hurtboxes (blue), active hitboxes (red) and the floor line over the world.

var fighters: Array[Fighter] = []
var floor_y := 596.0
var width := 1920.0


func _process(_delta: float) -> void:
	if visible:
		queue_redraw()


func _draw() -> void:
	draw_line(Vector2(0, floor_y), Vector2(width, floor_y), Color(1, 1, 1, 0.5), 1.0)
	for fighter in fighters:
		draw_rect(fighter.get_hurtbox(), Color(0.2, 0.5, 1.0, 0.25))
		draw_rect(fighter.get_hurtbox(), Color(0.3, 0.6, 1.0), false, 2.0)
		draw_line(fighter.position + Vector2(-8, 0), fighter.position + Vector2(8, 0), Color.WHITE, 2.0)
		draw_line(fighter.position + Vector2(0, -8), fighter.position + Vector2(0, 8), Color.WHITE, 2.0)
		for box in fighter.get_active_hitboxes():
			draw_rect(box.rect, Color(1, 0.15, 0.15, 0.45))
			draw_rect(box.rect, Color(1, 0.3, 0.3), false, 2.0)
