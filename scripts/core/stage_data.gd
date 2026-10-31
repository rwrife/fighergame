class_name StageData
extends RefCounted
## Stage definition loaded from stages/<id>/stage.json. See docs/ADDING_STAGES.md.

var id := ""
var display_name := ""
var description := ""
var width := 1920.0
var floor_y := 596.0
var layers: Array = []


static func load_from(path: String) -> StageData:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		push_error("Invalid stage file: " + path)
		return null
	var stage := StageData.new()
	stage.id = parsed.get("id", "")
	stage.display_name = parsed.get("name", stage.id.capitalize())
	stage.description = parsed.get("description", "")
	stage.width = float(parsed.get("width", 1920))
	stage.floor_y = float(parsed.get("floor_y", 596))
	stage.layers = parsed.get("layers", [])
	return stage
