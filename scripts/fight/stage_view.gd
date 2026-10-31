class_name StageView
extends Node2D
## Builds parallax backgrounds from StageData. Layers with ratio 0 are
## screen-locked; "front": true layers draw over the fighters.

const VIEW := Vector2(960, 640)


func build(stage: StageData) -> void:
	var back := ParallaxBackground.new()
	var front := ParallaxBackground.new()
	front.layer = 1
	for layer in stage.layers:
		var ratio := float(layer.get("ratio", 1.0))
		var parallax := ParallaxLayer.new()
		parallax.motion_scale = Vector2(ratio, 1.0)
		var art := StageLayerArt.new()
		var travel := maxf(0.0, stage.width - VIEW.x)
		art.setup(layer, Vector2(VIEW.x + travel * ratio, VIEW.y))
		parallax.add_child(art)
		(front if layer.get("front", false) else back).add_child(parallax)
	add_child(back)
	add_child(front)
