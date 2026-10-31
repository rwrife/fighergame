class_name FighterInput
extends RefCounted
## Input source for a Fighter. This base class is an idle dummy; subclass it
## (HumanInput, a future AIInput, a replay player...) and override poll().

const BUTTONS: Array[StringName] = [&"punch", &"kick"]
const BUFFER_TIME := 0.12

var held := {&"left": false, &"right": false, &"up": false, &"down": false,
		&"punch": false, &"kick": false, &"block": false}
var _buffered := {&"punch": 0.0, &"kick": 0.0, &"up": 0.0}


func poll(delta: float) -> void:
	for key in _buffered:
		_buffered[key] = maxf(0.0, _buffered[key] - delta)


func axis() -> int:
	return int(held.right) - int(held.left)


## True once per fresh press (within a short buffer window) of a button.
func consume(button: StringName) -> bool:
	if _buffered.get(button, 0.0) > 0.0:
		_buffered[button] = 0.0
		return true
	return false


func clear_buffer() -> void:
	for key in _buffered:
		_buffered[key] = 0.0


func _set_state(button: StringName, down: bool) -> void:
	if down and not held[button] and _buffered.has(button):
		_buffered[button] = BUFFER_TIME
	held[button] = down
