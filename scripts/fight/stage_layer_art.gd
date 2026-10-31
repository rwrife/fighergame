class_name StageLayerArt
extends Node2D
## Draws one stage layer. Uses the layer's "image" if present, otherwise a
## procedural placeholder chosen by "kind" (gradient, skyline, hills, floor, banners).
## The bottom 15% of the screen (y >= 544) is the protected combat lane: only the
## floor layer may draw there.

const LANE_TOP := 544.0

var layer := {}
var art_size := Vector2(960, 640)
var _texture: Texture2D


func setup(layer_data: Dictionary, size: Vector2) -> void:
	layer = layer_data
	art_size = size
	var path: String = layer.get("image", "")
	if path != "" and ResourceLoader.exists(path, "Texture2D"):
		_texture = load(path)
	queue_redraw()


func _draw() -> void:
	if _texture != null:
		draw_texture(_texture, Vector2.ZERO)
		return
	var color := Color(layer.get("color", "#888888"))
	var rng := RandomNumberGenerator.new()
	rng.seed = int(layer.get("seed", 1))
	match layer.get("kind", ""):
		"gradient":
			var colors: Array = layer.get("colors", ["#000000", "#ffffff"])
			var top := Color(colors[0])
			var bottom := Color(colors[1])
			var bands := 24
			for i in bands:
				draw_rect(Rect2(0, art_size.y * i / bands, art_size.x, art_size.y / bands + 1),
						top.lerp(bottom, float(i) / (bands - 1)))
		"skyline":
			var x := 0.0
			while x < art_size.x:
				var width := rng.randf_range(60, 140)
				var height := rng.randf_range(120, 300)
				draw_rect(Rect2(x, LANE_TOP - 60 - height, width, height + 60), color)
				for window in int(height / 40):
					draw_rect(Rect2(x + 12, LANE_TOP - 60 - height + 16 + window * 40, 10, 14), color.lightened(0.35))
				x += width + rng.randf_range(0, 20)
		"hills":
			var points := PackedVector2Array([Vector2(0, LANE_TOP)])
			var x := 0.0
			while x <= art_size.x + 80:
				points.append(Vector2(x, LANE_TOP - 70 - rng.randf_range(0, 140)))
				x += 80
			points.append(Vector2(art_size.x + 80, LANE_TOP))
			draw_colored_polygon(points, color)
		"floor":
			draw_rect(Rect2(0, LANE_TOP, art_size.x, art_size.y - LANE_TOP), color)
			draw_rect(Rect2(0, LANE_TOP, art_size.x, 6), color.darkened(0.4))
			var stripe := Color(layer.get("stripe", "#ffffff"))
			var x := 0.0
			while x < art_size.x:
				draw_rect(Rect2(x, LANE_TOP + 40, 80, 8), stripe)
				x += 200
		"banners":
			var x := 100.0
			while x < art_size.x:
				draw_rect(Rect2(x, 0, 6, 120), Color("1b0a2a"))
				draw_colored_polygon(PackedVector2Array([
					Vector2(x + 6, 10), Vector2(x + 70, 10), Vector2(x + 70, 90), Vector2(x + 38, 70), Vector2(x + 6, 90)]), color)
				x += 480
