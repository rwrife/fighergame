class_name HumanInput
extends FighterInput
## Reads the p<N>_* input actions registered by the Game autoload.

var player := 1


func _init(player_number: int) -> void:
	player = player_number


func poll(delta: float) -> void:
	super.poll(delta)
	for button in held:
		_set_state(button, Input.is_action_pressed("p%d_%s" % [player, button]))
