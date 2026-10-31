class_name Arcade
extends RefCounted
## Shared 90s-arcade UI helpers (outlined text, animated backdrop).

const YELLOW := Color("ffd23f")
const RED := Color("ee4266")
const CYAN := Color("3bceac")
const WHITE := Color("fffbf0")


static func label(parent: Node, text: String, size: int, color := WHITE, align := HORIZONTAL_ALIGNMENT_CENTER) -> Label:
	var node := Label.new()
	node.text = text
	node.horizontal_alignment = align
	node.add_theme_font_size_override("font_size", size)
	node.add_theme_color_override("font_color", color)
	node.add_theme_color_override("font_outline_color", Color("1b0a2a"))
	node.add_theme_constant_override("outline_size", maxi(4, size / 6))
	parent.add_child(node)
	return node


static func backdrop(parent: Control, top := Color("2b1055"), bottom := Color("7597de")) -> void:
	parent.add_child(ArcadeBackdrop.new(top, bottom))
