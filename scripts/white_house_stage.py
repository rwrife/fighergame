"""Render the cached White House Tripo scene in Blender 4.5, then compile its layers.

Blender: --background --python scripts\\white_house_stage.py -- render
Python:  python scripts\\white_house_stage.py compile
No remote generation or paid calls are performed by this assembly tool.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "assets" / "levels" / "white_house"
SOURCE = JOB / "source"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _components(mask):
    """4-connected labels and sizes for a small boolean array (no SciPy dependency)."""
    import numpy as np
    from collections import deque

    labels = np.full(mask.shape, -1)
    sizes = []
    for y, x in zip(*np.nonzero(mask)):
        if labels[y, x] >= 0:
            continue
        queue = deque([(y, x)])
        labels[y, x] = len(sizes)
        count = 0
        while queue:
            cy, cx = queue.popleft()
            count += 1
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if (0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1]
                        and mask[ny, nx] and labels[ny, nx] < 0):
                    labels[ny, nx] = len(sizes)
                    queue.append((ny, nx))
        sizes.append(count)
    return labels, sizes


def _fill_pinholes(path, max_size=8):
    """Fill small fully enclosed transparent holes with an adjacent opaque color."""
    from PIL import Image
    import numpy as np

    pixels = np.asarray(Image.open(path).convert("RGBA")).copy()
    labels, sizes = _components(pixels[:, :, 3] == 0)
    border = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
    for index, size in enumerate(sizes):
        if size > max_size or index in border:
            continue
        for y, x in zip(*np.nonzero(labels == index)):
            for ny, nx in ((y, x - 1), (y - 1, x), (y, x + 1), (y + 1, x)):
                if pixels[ny, nx, 3] == 255:
                    pixels[y, x] = pixels[ny, nx]
                    break
    Image.fromarray(pixels).save(path)


def ground_house(canvas, grounding):
    """Close the open portico/foundation gaps so no sky shows beneath the house.

    Only previously transparent pixels inside the house's own columns change; the
    approved house pixels are untouched. A one-row darker band reads as the shadow
    under the porch and wall overhangs.
    """
    from PIL import Image
    import numpy as np

    pixels = np.asarray(canvas.convert("RGBA")).copy()
    opaque = pixels[:, :, 3] > 0
    top = grounding["fill_top"] + grounding["drop"]
    columns = np.nonzero(opaque[top - grounding["body_rows"]:top].any(axis=0))[0]
    base = max(int(np.nonzero(opaque[:, x])[0].max()) for x in columns)
    region = np.zeros_like(opaque)
    region[top:base + 1, columns] = True
    holes = region & ~opaque
    under_overhang = holes & np.roll(opaque, 1, axis=0)
    pixels[holes, :3] = grounding["fill"]
    pixels[under_overhang, :3] = grounding["shadow"]
    pixels[holes, 3] = 255
    return Image.fromarray(pixels)


def prepare_yard():
    """Extract explicitly owned yard silhouettes, not a flat reference backdrop."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np

    recipe = read(SOURCE / "assembly_recipe.json")
    reference = Image.open(SOURCE / "geometry_generated_image.png").convert("RGB")
    if reference.size != (1264, 848):
        raise ValueError("Yard reference changed; its object masks require review")
    output = SOURCE / "yard_cards"
    output.mkdir(exist_ok=True)
    if "yard_revision" not in recipe:
        fixed = {}
        for name in ("sky.png", "far_background.png", "ground.png", "props/flag.png"):
            pinned = SOURCE / ("approved_" + Path(name).name)
            pinned.write_bytes((JOB / name).read_bytes())
            fixed[name] = {
                "source": pinned.name,
                "sha256": hashlib.sha256(pinned.read_bytes()).hexdigest(),
            }
        manifest = read(JOB / "level.json")
        recipe["yard_revision"] = {
            "method": "reference_textured_2_5d_blender",
            "reference": "geometry_generated_image.png",
            "reference_sha256": hashlib.sha256(
                (SOURCE / "geometry_generated_image.png").read_bytes()).hexdigest(),
            "approved_images": fixed,
            "approved_flag": next(prop for prop in manifest["props"] if prop["id"] == "flag_0"),
            "reason": "The original Tripo yard distorted the fountain and foliage. "
                      "Retain the cached meshes, but replace yard exports with separate "
                      "reference-textured Blender cards; not a new 3D yard generation.",
        }
        used = set()
        for fixed_image in fixed.values():
            image = Image.open(SOURCE / fixed_image["source"]).convert("RGBA")
            used.update(pixel[:3] for pixel in image.get_flattened_data() if pixel[3])
        replacements = {(16, 62, 36): [16, 206, 8], (178, 230, 109): [108, 160, 23]}
        if used.intersection(replacements):
            raise ValueError("Cannot replace a palette color used by the approved artwork")
        recipe["palette"] = [replacements.get(tuple(color), color) for color in recipe["palette"]]
    rgb = np.asarray(reference).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    if hashlib.sha256((SOURCE / "geometry_generated_image.png").read_bytes()).hexdigest() != recipe["yard_revision"]["reference_sha256"]:
        raise ValueError("Yard source changed; do not reuse the existing object masks")
    recipe["palette"] = [[16, 62, 36] if color == [255, 228, 154] else color
                         for color in recipe["palette"]]
    recipe["yard_revision"]["render_scale"] = 1.0
    leaves = (g >= r * 0.9) & (g > b * 1.25) & ~((g > 180) & (r < 35))
    bark = (r > g * 1.12) & (g > b * 1.2) & (r < 170)
    dark = rgb.max(axis=2) < 65
    seed = Image.fromarray((leaves | bark).astype(np.uint8) * 255)
    adjacent = np.asarray(seed.filter(ImageFilter.MaxFilter(5))) > 0
    plants = leaves | bark | (dark & adjacent)

    def polygon(points):
        image = Image.new("L", reference.size)
        ImageDraw.Draw(image).polygon(points, fill=255)
        return np.asarray(image) > 0

    components = {}

    def extract(name, box, mask, size, position):
        x0, y0, x1, y1 = box
        owned = np.zeros(mask.shape, dtype=bool)
        owned[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
        rgba = reference.convert("RGBA")
        rgba.putalpha(Image.fromarray(owned.astype(np.uint8) * 255))
        image = rgba.crop(box).resize(size, Image.Resampling.NEAREST)
        if not image.getchannel("A").getbbox():
            raise ValueError(f"Empty yard silhouette: {name}")
        image.save(output / f"{name}.png")
        Image.fromarray(owned.astype(np.uint8) * 255).save(output / f"{name}_mask.png")
        components[name] = {
            "image": f"yard_cards/{name}.png", "mask": f"yard_cards/{name}_mask.png",
            "source_box": list(box), "size": list(size), "position": list(position),
        }

    # Trees and the fence are painted by stage_pixel_props.py during compile.
    extract("hedge", (385, 384, 531, 431), plants, (146, 47), (850, 343))
    fountain = polygon([
        (427, 485), (437, 474), (464, 466), (510, 460), (564, 456),
        (615, 456), (674, 459), (732, 467), (766, 477), (779, 485),
        (762, 495), (713, 503), (649, 507), (574, 508), (513, 504),
        (463, 498), (438, 492),
    ]) | polygon([
        (589, 480), (591, 460), (596, 448), (598, 429), (604, 426),
        (610, 447), (614, 462), (617, 480),
    ])
    extract("fountain", (425, 424, 781, 510), fountain, (304, 74), (1048, 380))
    fountain_image = Image.open(output / "fountain.png").convert("RGBA")
    fountain_rgb = np.asarray(fountain_image).copy()
    rows = np.indices(fountain_rgb.shape[:2])[0]
    occluded = ((rows >= 59) & (fountain_rgb[:, :, :3].max(axis=2) < 90)
                & (fountain_rgb[:, :, 3] > 0))
    fountain_rgb[occluded, :3] = (128, 88, 58)
    Image.fromarray(fountain_rgb).save(output / "fountain.png")
    components["fountain"]["repair"] = "Paint out fence pixels occluding the lower brown surround."
    lamp = polygon([
        (1096, 438), (1110, 429), (1126, 440), (1136, 431),
        (1152, 429), (1163, 446), (1165, 482), (1153, 495),
        (1143, 500), (1138, 714), (1149, 736), (1149, 747),
        (1110, 747), (1101, 736), (1116, 713), (1115, 510),
        (1099, 498), (1096, 477),
    ])
    grass_or_sky = ((g > r * 1.25) & (g > b * 1.25) & (g > 110)) | (b > r * 1.4) & (b > g * 1.15)
    # The reference lamp stands in front of a tree: drop its bark, vines and dark warm
    # outline, then keep only substantial pieces so no trunk stub or fringe remains.
    vine = (g > r * 1.15) & (g > b * 1.1) & (rgb.max(axis=2) < 150)
    dark_warm = (r > b + 8) & (rgb.max(axis=2) < 100)
    lamp_box = (1094, 427, 1167, 749)
    lamp &= ~(grass_or_sky | bark | vine | dark_warm)
    labels, sizes = _components(lamp[lamp_box[1]:lamp_box[3], lamp_box[0]:lamp_box[2]])
    lamp[lamp_box[1]:lamp_box[3], lamp_box[0]:lamp_box[2]] = np.isin(
        labels, [index for index, size in enumerate(sizes) if size >= 40])
    extract("lamp", lamp_box, lamp, (51, 224), (1660, 316))
    _fill_pinholes(output / "lamp.png")
    components["lamp"]["repair"] = ("Remove the reference tree trunk, vines and stray fringe "
                                    "behind the lamp; fill enclosed pinholes.")
    lights = recipe.get("foreground_layout", {}).get("street_lights")
    if lights:
        size = lights["size"]
        Image.open(output / "lamp.png").resize(
            tuple(size), Image.Resampling.NEAREST).save(output / "street_lamp.png")
        components["street_lamp"] = {
            "image": "yard_cards/street_lamp.png",
            "mask": components["lamp"]["mask"],
            "source_box": components["lamp"]["source_box"],
            "size": size, "position": [lights["positions"][0], lights["base_y"] - size[1]],
            "method": "larger reusable reference streetlight on the sidewalk plane, "
                      "midground parallax behind the fighters; no collision",
        }
    lawn =  Image.new("RGBA", (2400, 184), (16, 206, 8, 255))
    ImageDraw.Draw(lawn).rectangle((0, 0, 2399, 8), fill=(54, 148, 49, 255))
    lawn.save(output / "lawn.png")
    components["lawn"] = {
        "image": "yard_cards/lawn.png", "size": [2400, 184], "position": [0, 360],
        "method": "locally painted flat lawn backing; no reference collision terrain",
    }
    recipe["yard_revision"]["components"] = components
    referenced = {Path(component[key]).name for component in components.values()
                  for key in ("image", "mask") if key in component}
    for stale in output.glob("*.png"):
        if stale.name not in referenced:
            stale.unlink()
    write(SOURCE / "assembly_recipe.json", recipe)
    print("Prepared separate reference-textured yard silhouettes; approved artwork pinned.")


def render():
    import bpy
    from mathutils import Matrix, Vector

    if bpy.app.version[:2] != (4, 5):
        raise RuntimeError("White House assembly requires Blender 4.5 LTS")
    recipe = read(SOURCE / "assembly_recipe.json")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE / recipe["model"]))
    original = {int(obj.name.rsplit("_", 1)[1]): obj
                for obj in bpy.context.scene.objects if obj.type == "MESH"}
    if len(original) != 20:
        raise RuntimeError("Expected the inspected 20-part Tripo model")
    collections = {}
    for name in ("far_background", "midground", "ground", "foreground",
                 "prop_fence", "prop_lamp", "prop_fountain", "prop_hedge", "prop_flag"):
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
        collections[name] = collection

    def move(obj, name):
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        collections[name].objects.link(obj)

    def bounds(obj):
        points = [obj.matrix_world @ Vector(point) for point in obj.bound_box]
        return (Vector([min(point[axis] for point in points) for axis in range(3)]),
                Vector([max(point[axis] for point in points) for axis in range(3)]))

    # The reviewed model's front is +X; rotate it toward the fixed -Y camera.
    transform = (Matrix.Translation((1200, 0, 0))
                 @ Matrix.Rotation(-math.pi / 2, 4, "Z")
                 @ Matrix.Scale(recipe["model_scale"], 4))

    def place(obj, collection, spec):
        source_name = obj.name
        obj.matrix_world = transform @ obj.matrix_world
        bpy.context.view_layer.update()
        low, high = bounds(obj)
        if "height" in spec:
            factor = spec["height"] / (high.z - low.z)
            obj.matrix_world = (Matrix.Translation((0, 0, low.z))
                                @ Matrix.Diagonal(Vector((1, 1, factor, 1)))
                                @ Matrix.Translation((0, 0, -low.z)) @ obj.matrix_world)
            bpy.context.view_layer.update()
            low, high = bounds(obj)
        obj.location.z += 640 - spec["base_y"] - low.z
        obj["source_part"] = source_name
        obj["source_model"] = recipe["model"]
        obj.name = spec.get("name", collection)
        move(obj, collection)
        if len(obj.data.polygons) > 40000:
            modifier = obj.modifiers.new("Local_stage_budget", "DECIMATE")
            modifier.ratio = 40000 / len(obj.data.polygons)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        return obj

    for collection in ("far_background", "midground"):
        for index, spec in recipe[collection].items():
            place(original[int(index)], collection, spec)

    fence = place(original[14], "prop_fence", recipe["props"]["fence"])
    fence.name = "Permanent_Iron_Fence_Module"
    lamp = original[15]
    bpy.ops.object.select_all(action="DESELECT")
    lamp.select_set(True)
    bpy.context.view_layer.objects.active = lamp
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    components = list(bpy.context.selected_objects)
    retained = []
    for component in components:
        low, high = bounds(component)
        if (low.x + high.x) / 2 > 0.445:
            retained.append(component)
        else:
            bpy.data.objects.remove(component, do_unlink=True)
    if not retained:
        raise RuntimeError("Reviewed lamp separation produced no lamp geometry")
    bpy.ops.object.select_all(action="DESELECT")
    for component in retained:
        component.select_set(True)
    bpy.context.view_layer.objects.active = retained[0]
    bpy.ops.object.join()
    lamp = place(retained[0], "prop_lamp", recipe["props"]["lamp"])
    lamp.name = "Double_Globe_Lamp"

    fountain = original[13]
    fountain.matrix_world = transform @ fountain.matrix_world
    bpy.context.view_layer.update()
    low, high = bounds(fountain)
    center = (low + high) / 2
    fountain.matrix_world = (Matrix.Translation(center)
                            @ Matrix.Rotation(math.radians(18), 4, "X")
                            @ Matrix.Translation(-center) @ fountain.matrix_world)
    bpy.context.view_layer.update()
    low, high = bounds(fountain)
    factor = recipe["props"]["fountain"]["height"] / (high.z - low.z)
    fountain.matrix_world = (Matrix.Translation((0, 0, low.z))
                            @ Matrix.Diagonal(Vector((1, 1, factor, 1)))
                            @ Matrix.Translation((0, 0, -low.z)) @ fountain.matrix_world)
    bpy.context.view_layer.update()
    low, high = bounds(fountain)
    fountain.location.z += 640 - recipe["props"]["fountain"]["base_y"] - low.z
    fountain["source_part"] = "tripo_part_13"
    fountain.name = "Fountain_Basin"
    move(fountain, "prop_fountain")
    for index in recipe["removed_parts"]:
        bpy.data.objects.remove(original[index], do_unlink=True)

    def solid(name, color):
        material = bpy.data.materials.new(name)
        material.diffuse_color = (*[channel / 255 for channel in color], 1)
        material.use_nodes = True
        material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = material.diffuse_color
        return material

    lawn = solid("Lawn_Bright", (87, 188, 54))
    lawn_dark = solid("Lawn_Shade", (54, 148, 49))
    road = solid("Street", (70, 84, 105))
    curb = solid("Curb", (165, 185, 201))
    stripe = solid("Street_Seam", (101, 116, 138))
    hedge = solid("Hedge", (54, 148, 49))
    water = solid("Fountain_Jet", (124, 225, 220))
    foam = solid("Fountain_Foam", (252, 250, 240))
    iron = solid("Permanent_Iron", (35, 62, 74))
    globe = solid("Lamp_Globes", (255, 228, 154))
    flag_red = solid("Flag_Red", (206, 49, 73))
    flag_blue = solid("Flag_Canton", (16, 37, 46))
    fence.data.materials.clear()
    fence.data.materials.append(iron)
    lamp.data.materials.clear()
    lamp.data.materials.append(iron)
    lamp.data.materials.append(globe)
    bpy.context.view_layer.update()
    _, lamp_high = bounds(lamp)
    for polygon in lamp.data.polygons:
        center_z = (lamp.matrix_world @ polygon.center).z
        polygon.material_index = 1 if center_z > lamp_high.z - 35 else 0

    def panel(name, x, y, width, height, depth, material, collection):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x + width / 2, depth, 640 - y - height / 2))
        obj = bpy.context.object
        obj.name = name
        obj.scale = (width, 2, height)
        obj.data.materials.append(material)
        move(obj, collection)
        return obj

    panel("Flat_Lawn_Backing", 0, recipe["lawn_top"], 2400,
          544 - recipe["lawn_top"], 1000, lawn, "midground")
    panel("Lawn_Horizon_Band", 0, recipe["lawn_top"], 2400, 12, 998, lawn_dark, "midground")
    layout = recipe.get("foreground_layout")
    if layout:
        sidewalk = solid("Wide_Sidewalk", (135, 149, 165))
        panel("Protected_Flat_Street", 0, layout["road_top"], 2400,
              640 - layout["road_top"], 0, road, "ground")
        panel("Straight_Curb", 0, layout["road_top"], 2400, 5, -2, curb, "ground")
    else:
        panel("Protected_Flat_Street", 0, 544, 2400, 96, 0, road, "ground")
        panel("Straight_Curb", 0, 544, 2400, 5, -2, curb, "ground")
        panel("Street_Upper_Seam", 0, 570, 2400, 2, -2, stripe, "ground")
        for x in range(120, 2400, 240):
            panel("Paving_Joint", x, 549, 2, 21, -2, stripe, "ground")
    panel("Rooftop_Flagpole", 1200, 66, 2, 80, 0, iron, "prop_flag")
    for index in range(13):
        panel("Flag_Stripe", 1202, 66 + index * 2, 48, 2, -2,
              flag_red if index % 2 == 0 else foam, "prop_flag")
    panel("Flag_Canton", 1202, 66, 22, 14, -4, flag_blue, "prop_flag")
    for row in range(4):
        for column in range(5):
            panel("Flag_Star", 1204 + column * 4, 68 + row * 3,
                  1, 1, -6, foam, "prop_flag")

    for index in range(7):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8,
                                           location=(1140 + index * 20, -100, 222))
        obj = bpy.context.object
        obj.name = "Reusable_Hedge_Lobe"
        obj.scale = (24, 12, 17 + (index % 3) * 2)
        obj.data.materials.append(hedge)
        move(obj, "prop_hedge")
    low, high = bounds(fountain)
    fountain_center = (low + high) / 2
    bpy.ops.mesh.primitive_circle_add(vertices=48, radius=1, fill_type="NGON",
                                     location=(fountain_center.x, low.y - 5,
                                               fountain_center.z + 3))
    surface = bpy.context.object
    surface.name = "Repaired_Fountain_Water_Surface"
    surface.rotation_euler = (math.pi / 2, 0, 0)
    surface.scale = (100, 10, 1)
    surface.data.materials.append(water)
    move(surface, "prop_fountain")
    for name, radius, height, material in (
        ("Water_Jet", 9, 34, water), ("Foam_Core", 5, 30, foam),
    ):
        bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=radius, radius2=2,
                                       depth=height,
                                       location=(fountain_center.x, low.y - 7,
                                                 high.z + height / 2 - 9))
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(material)
        move(obj, "prop_fountain")

    if "yard_revision" in recipe:
        for name in ("midground", "prop_fence", "prop_lamp", "prop_fountain", "prop_hedge"):
            for obj in list(collections[name].objects):
                bpy.data.objects.remove(obj, do_unlink=True)
        for name, component in recipe["yard_revision"]["components"].items():
            collection_name = "midground" if name == "lawn" else f"prop_{name}"
            if collection_name not in collections:
                collection = bpy.data.collections.new(collection_name)
                bpy.context.scene.collection.children.link(collection)
                collections[collection_name] = collection
            x, y = component["position"]
            width, height = component["size"]
            depth = 1000 if name == "lawn" else 0
            mesh = bpy.data.meshes.new(f"Reference_{name}")
            mesh.from_pydata([
                (x, depth, 640 - y - height), (x + width, depth, 640 - y - height),
                (x + width, depth, 640 - y), (x, depth, 640 - y),
            ], [], [(0, 1, 2, 3)])
            mesh.uv_layers.new()
            for loop, uv in zip(mesh.uv_layers.active.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
                loop.uv = uv
            obj = bpy.data.objects.new(f"Reference_Textured_{name}", mesh)
            collections[collection_name].objects.link(obj)
            material = bpy.data.materials.new(f"Reference_Cel_Art_{name}")
            material.use_nodes = True
            material["reference_card"] = True
            tree = material.node_tree
            tree.nodes.clear()
            texture = tree.nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(str(SOURCE / component["image"]))
            texture.interpolation = "Closest"
            emission = tree.nodes.new("ShaderNodeEmission")
            transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
            mix = tree.nodes.new("ShaderNodeMixShader")
            output_node = tree.nodes.new("ShaderNodeOutputMaterial")
            tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
            tree.links.new(texture.outputs["Alpha"], mix.inputs[0])
            tree.links.new(transparent.outputs[0], mix.inputs[1])
            tree.links.new(emission.outputs[0], mix.inputs[2])
            tree.links.new(mix.outputs[0], output_node.inputs["Surface"])
            mesh.materials.append(material)
            obj["source_reference"] = recipe["yard_revision"]["reference_sha256"]
            obj["method"] = "reference_textured_2_5d_blender"
        # The fence and trees are painted pixel art now; drop their emptied collections.
        for name in [name for name, collection in collections.items()
                     if name.startswith("prop_") and not collection.objects]:
            bpy.data.collections.remove(collections.pop(name))

    if layout:
        scale = layout["scene_scale"]
        scenery_transform = (
            Matrix.Translation((1200 * (1 - scale), 0,
                                640 * (1 - scale) - layout["scene_y_offset"]))
            @ Matrix.Diagonal(Vector((scale, 1, scale, 1))))
        for name, collection in collections.items():
            if name in ("ground", "prop_street_lamp"):
                continue
            for obj in collection.objects:
                if name == "prop_fountain":
                    low, high = bounds(obj)
                    center = (low + high) / 2
                    factor = layout["fountain_scale"]
                    obj.matrix_world = (
                        Matrix.Translation(center)
                        @ Matrix.Diagonal(Vector((factor, 1, factor, 1)))
                        @ Matrix.Translation(-center) @ obj.matrix_world)
                obj.matrix_world = scenery_transform @ obj.matrix_world

        panel("Wide_Flat_Sidewalk", 0, layout["sidewalk_top"], 2400,
              layout["road_top"] - layout["sidewalk_top"], 0, sidewalk, "midground")
        panel("Sidewalk_Long_Joint", 0, (layout["road_top"] + layout["sidewalk_top"]) / 2,
              2400, 1, -2, stripe, "midground")
        for x in range(120, 2400, 240):
            panel("Sidewalk_Paving_Joint", x, layout["sidewalk_top"], 1,
                  layout["road_top"] - layout["sidewalk_top"], -2, stripe, "midground")

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    materials = {slot.material for obj in meshes for slot in obj.material_slots}
    for material in materials:
        if material is None:
            raise RuntimeError("Every stage mesh must have a material")
        if material.get("reference_card"):
            continue
        material.use_nodes = True
        tree = material.node_tree
        principled = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
        base = principled.inputs["Base Color"]
        base_source = base.links[0].from_socket if base.is_linked else None
        base_color = tuple(base.default_value)
        output = next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL")
        diffuse = tree.nodes.new("ShaderNodeBsdfDiffuse")
        diffuse.inputs["Color"].default_value = (1, 1, 1, 1)
        shader_rgb = tree.nodes.new("ShaderNodeShaderToRGB")
        ramp = tree.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "CONSTANT"
        elements = ramp.color_ramp.elements
        elements.remove(elements[1])
        for index, (position, value) in enumerate(((0, 0.65), (0.32, 0.84), (0.65, 1.0))):
            element = elements[0] if index == 0 else elements.new(position)
            element.position = position
            element.color = (value, value, value, 1)
        vivid = tree.nodes.new("ShaderNodeHueSaturation")
        vivid.inputs["Color"].default_value = base_color
        vivid.inputs["Saturation"].default_value = 1.12
        if base_source:
            tree.links.new(base_source, vivid.inputs["Color"])
        multiply = tree.nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1
        emission = tree.nodes.new("ShaderNodeEmission")
        tree.links.new(diffuse.outputs["BSDF"], shader_rgb.inputs["Shader"])
        tree.links.new(shader_rgb.outputs["Color"], ramp.inputs["Fac"])
        tree.links.new(vivid.outputs["Color"], multiply.inputs[1])
        tree.links.new(ramp.outputs["Color"], multiply.inputs[2])
        tree.links.new(multiply.outputs["Color"], emission.inputs["Color"])
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 2400
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100 if "yard_revision" in recipe else 50
    scene.eevee.taa_render_samples = 1
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.world.color = (0.04, 0.04, 0.04)
    bpy.ops.object.light_add(type="SUN", location=(-1000, -2000, 3000))
    sun = bpy.context.object
    sun.name = "Shared_Daylight_Key"
    sun.rotation_euler = (math.radians(28), math.radians(-30), math.radians(-25))
    sun.data.energy = 2
    camera_data = bpy.data.cameras.new("Fixed_Stage_Camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2400
    camera_data.clip_end = 20000
    camera = bpy.data.objects.new("Fixed_Stage_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (1200, -5000, 320)
    camera.rotation_euler = (Vector((1200, 0, 320)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    camera_data.show_background_images = True
    background = camera_data.background_images.new()
    background.image = bpy.data.images.load(str(SOURCE / "sky_repaint_generated_image.png"))
    output = SOURCE / "renders"
    output.mkdir(exist_ok=True)
    for stale in output.glob("prop_*.png"):
        if stale.stem not in collections:
            stale.unlink()
    for name, collection in collections.items():
        visible = set(collection.objects)
        for obj in meshes:
            obj.hide_render = obj not in visible
        scene.render.filepath = str(output / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    for obj in meshes:
        obj.hide_render = False
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "stage.blend"))
    write(SOURCE / "render_settings.json", {
        "blender": bpy.app.version_string, "engine": scene.render.engine,
        "camera": dict(recipe["camera"], render_scale=scene.render.resolution_percentage / 100),
        "shader": "3D house: diffuse -> Shader to RGB -> three constant bands. "
                  "2.5D yard: alpha-preserving reference-color emission; shared palette.",
        "bands": [0.65, 0.84, 1.0], "sun_energy": 2, "dithering": False,
        "meshes": [{"name": obj.name, "collection": obj.users_collection[0].name,
                    "source_part": obj.get("source_part"), "polygons": len(obj.data.polygons),
                    "matrix_world": [list(row) for row in obj.matrix_world]} for obj in meshes],
    })


def compile():
    from PIL import Image
    import numpy as np

    recipe = read(SOURCE / "assembly_recipe.json")
    palette = recipe["palette"]
    layout = recipe.get("foreground_layout")
    lane_top = layout["lane_top"] if layout else 544
    if len(palette) != 31 or len({tuple(color) for color in palette}) != 31:
        raise ValueError("Expected 31 unique opaque shared palette colors")
    quantizer = Image.new("P", (1, 1))
    flattened = [channel for color in palette for channel in color]
    quantizer.putpalette(flattened + palette[-1] * (256 - len(palette)))

    def quantize(image):
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
        color = rgba.convert("RGB").quantize(palette=quantizer, dither=Image.Dither.NONE).convert("RGBA")
        color.putalpha(alpha)
        return color

    def save_image(name, image):
        approved = recipe.get("yard_revision", {}).get("approved_images", {}).get(name)
        if approved:
            data = (SOURCE / approved["source"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != approved["sha256"]:
                raise ValueError(f"Approved artwork changed: {name}")
            if layout and name == "ground.png":
                image.save(JOB / name)
            elif layout and name in ("far_background.png", "props/flag.png"):
                pinned = Image.open(SOURCE / approved["source"]).convert("RGBA")
                scale = layout["scene_scale"]
                resized = pinned.resize(
                    (round(pinned.width * scale), round(pinned.height * scale)),
                    Image.Resampling.NEAREST)
                if name == "far_background.png":
                    canvas = Image.new("RGBA", pinned.size)
                    grounding = layout.get("house_grounding")
                    drop = grounding["drop"] if grounding else 0
                    canvas.paste(resized, (round(1200 * (1 - scale)),
                                           layout["scene_y_offset"] + drop))
                    if grounding:
                        canvas = ground_house(canvas, grounding)
                    canvas.save(JOB / name)
                else:
                    resized.save(JOB / name)
            else:
                (JOB / name).write_bytes(data)
        else:
            image.save(JOB / name)

    write(JOB / "palette.json", {"colors": palette})
    sky = Image.open(SOURCE / "sky_repaint_generated_image.png").convert("RGB")
    # Reposition the model-generated distant silhouette above the roof and erase
    # its old footprint; it stays in the lightbox, never in moving geometry.
    sky_recipe = recipe["sky_recomposition"]
    if sky.size != tuple(sky_recipe["reference_size"]):
        raise ValueError("Sky edit dimensions changed; review and update the silhouette mask")
    rgb = np.asarray(sky).copy()
    monument_box = sky_recipe["monument_box"]
    crop = rgb[monument_box[1]:monument_box[3], monument_box[0]:monument_box[2]].copy()
    mask = crop.max(axis=2) < sky_recipe["dark_mask_max_channel"]
    if not mask.any():
        raise ValueError("The reviewed distant Monument silhouette is missing")
    for row in range(crop.shape[0]):
        rgb[monument_box[1] + row, monument_box[0]:monument_box[2]][mask[row]] = rgb[
            monument_box[1] + row, monument_box[0] - 8]
    monument = Image.fromarray(np.dstack([crop, mask.astype(np.uint8) * 255]))
    monument = monument.resize(tuple(sky_recipe["monument_size"]), Image.Resampling.NEAREST)
    sky = Image.fromarray(rgb)
    sky = sky.resize((960, 640), Image.Resampling.NEAREST)
    sky.paste(monument, tuple(sky_recipe["monument_position"]), monument)
    sky.save(SOURCE / "sky_composed.png")
    save_image("sky.png", quantize(sky).convert("RGB"))
    manifest = read(JOB / "level.json")
    if layout:
        manifest["play_area_fraction"] = (640 - lane_top) / 640
        manifest["foreground_layout"] = layout
    props_dir = JOB / "props"
    props_dir.mkdir(exist_ok=True)
    for layer in manifest["layers"]:
        image = Image.open(SOURCE / "renders" / f"{layer['id']}.png")
        image = quantize(image.resize((2400, 640), Image.Resampling.NEAREST))
        alpha = np.asarray(image.getchannel("A"))
        if layer["id"] == "ground":
            if not np.all(alpha[lane_top:] == 255) or np.any(alpha[:lane_top]):
                raise ValueError("Rendered street must exactly fill the protected flat lane")
        elif np.any(alpha[lane_top:]):
            raise ValueError(f"{layer['id']} intrudes into the protected lane")
        save_image(layer["image"], image)
    templates = {}
    template_positions = {}
    pivots = {}
    pixel_art = recipe.get("pixel_art")
    painted = {}
    if pixel_art:
        from stage_pixel_props import paint_fence, paint_tree

        painted["fence"] = (paint_fence(pixel_art["fence"], palette), None)
        for name, spec in pixel_art["trees"].items():
            painted[name] = paint_tree(spec, palette, pixel_art["light"])
    prop_names = [name for name in ("fence", "lamp", "fountain", "hedge", "flag")
                  if name not in painted]
    if "yard_revision" in recipe and layout and layout.get("street_lights"):
        prop_names.append("street_lamp")
    for name in prop_names:
        image = Image.open(SOURCE / "renders" / f"prop_{name}.png")
        image = quantize(image.resize((2400, 640), Image.Resampling.NEAREST))
        bounds = image.getchannel("A").getbbox()
        if not bounds:
            raise ValueError(f"Empty rendered prop: {name}")
        cropped = image.crop((bounds[0] - 2, bounds[1] - 2, bounds[2] + 2, bounds[3] + 2))
        save_image(f"props/{name}.png", cropped)
        templates[name] = Image.open(props_dir / f"{name}.png").size
        template_positions[name] = [bounds[0] - 2, bounds[1] - 2]
    for name, (image, pivot) in painted.items():
        save_image(f"props/{name}.png", quantize(image))
        templates[name] = image.size
        if pivot:
            pivots[name] = pivot
    placements = []

    def instance(name, x, base, index, layer="midground"):
        width, height = templates[name]
        placements.append({
            "id": f"{name}_{index}", "image": f"props/{name}.png", "layer": layer,
            "size": [width, height], "position": [x, base - height],
            "pivot": [width // 2, height - 2], "collision": False,
        })

    def pivot_instance(name, x, base, index):
        width, height = templates[name]
        pivot_x, pivot_y = pivots[name]
        placements.append({
            "id": f"{name}_{index}", "image": f"props/{name}.png", "layer": "midground",
            "size": [width, height], "position": [x - pivot_x, base - pivot_y],
            "pivot": [pivot_x, pivot_y], "collision": False,
        })

    if "yard_revision" in recipe:
        def scene_x(x):
            return round(1200 + (x - 1200) * layout["scene_scale"]) if layout else x

        def scene_y(y):
            return round(y * layout["scene_scale"] + layout["scene_y_offset"]) if layout else y

        for index, x in enumerate((640, 780, 920, 1060, 1200, 1340, 1480, 1620)):
            instance("hedge", scene_x(x), scene_y(390), index)
        # Painter order by ground contact: farther trees first, nearer ones over the fountain.
        x, y = template_positions["fountain"]
        scenery = [(y + templates["fountain"][1], "fountain", x)]
        scenery += [(base, name, x) for name, x, base in pixel_art["tree_placements"]]
        for base, name, x in sorted(scenery):
            if name == "fountain":
                instance(name, x, base, 0)
            else:
                pivot_instance(name, x, base, 0)
        fence = pixel_art["fence"]
        fence_width = templates["fence"][0]
        for index, x in enumerate(range(0, 2400, fence_width)):
            instance("fence", x, fence["base_y"], index)
        x, y = template_positions["lamp"]
        instance("lamp", x, y + templates["lamp"][1], 0)
        flag = dict(recipe["yard_revision"]["approved_flag"])
        if layout:
            flag["size"] = list(templates["flag"])
            flag["position"] = [scene_x(flag["position"][0]), scene_y(flag["position"][1])
                                + layout.get("house_grounding", {}).get("drop", 0)]
            flag["pivot"] = [round(value * layout["scene_scale"]) for value in flag["pivot"]]
        placements.append(flag)
        if layout and layout.get("street_lights"):
            # Sidewalk plane: drawn over the fence but still behind the fighters.
            lights = layout["street_lights"]
            for index, x in enumerate(lights["positions"]):
                instance("street_lamp", x, lights["base_y"], index)
    else:
        fence_width = templates["fence"][0]
        for index, x in enumerate(range(0, 2400 - fence_width + 1, fence_width - 4)):
            instance("fence", x, 543, index)
        instance("lamp", 1470, 543, 0)
        instance("fountain", 1200 - templates["fountain"][0] // 2, 452, 0)
        for index, x in enumerate((700, 845, 990, 1350, 1495, 1640)):
            instance("hedge", x, 380, index)
        instance("flag", 1200, 148, 0, "far_background")
    manifest["props"] = placements
    referenced = {Path(prop["image"]).name for prop in placements}
    for stale in props_dir.glob("*.png"):
        if stale.name not in referenced:
            stale.unlink()
            stale.with_name(stale.name + ".import").unlink(missing_ok=True)
    write(JOB / "level.json", manifest)
    stage_layers = [{"name": "sky", "ratio": 0.0, "image": "res://assets/levels/white_house/sky.png"}]
    for layer in manifest["layers"]:
        origin = round(-(2400 - 960) / 2 + 960 * layer["factor"] / 2)
        entry = {"name": layer["id"], "ratio": layer["factor"],
                 "image": f"res://assets/levels/white_house/{layer['image']}", "offset": [origin, 0]}
        if layer["id"] == "foreground":
            entry["front"] = True
        stage_layers.append(entry)
        for prop in placements:
            if prop["layer"] == layer["id"]:
                prop_entry = {
                    "name": prop["id"], "ratio": layer["factor"],
                    "image": f"res://assets/levels/white_house/{prop['image']}",
                    "offset": [origin + prop["position"][0], prop["position"][1]],
                }
                if layer["id"] == "foreground":
                    prop_entry["front"] = True
                stage_layers.append(prop_entry)
    stage_dir = ROOT / "stages" / "white_house"
    stage_dir.mkdir(exist_ok=True)
    write(stage_dir / "stage.json", {
        "id": "white_house", "name": "White House",
        "description": "Bright White House lawn and fountain. Production art awaiting artistic review.",
        "width": 1920, "floor_y": 576, "layers": stage_layers,
    })
    provenance = read(SOURCE / "provenance.json")
    tasks = read(SOURCE / "provider_tasks.json")
    uploads = read(SOURCE / "uploads.json")
    input_hashes = {value["file_token"]: digest for digest, value in uploads.items()}

    def public_record(value):
        if isinstance(value, dict):
            return {key: public_record(item) for key, item in value.items()}
        if isinstance(value, list):
            return [public_record(item) for item in value]
        if isinstance(value, str) and value in input_hashes:
            return {"uploaded_input_sha256": input_hashes[value]}
        return value

    provenance["generation"] = [{
        "method": "nano_banana_tripo_blender",
        "provider": "Tripo V3", "tasks": public_record(tasks),
        "assembly_tool": "scripts/white_house_stage.py",
        "assembly_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "recipe_sha256": hashlib.sha256((SOURCE / "assembly_recipe.json").read_bytes()).hexdigest(),
        "notes": "Sky and cleaned references are image-model outputs. The house is rendered "
                 "from segmented Tripo meshes. The revised yard uses independently masked "
                 "reference-textured 2.5D Blender cards to preserve the generated design, "
                 "not newly generated or fully reconstructed 3D yard meshes. Trees and the "
                 "iron fence are deterministic procedural pixel art (scripts/stage_pixel_props.py), "
                 "not Tripo, Blender or image-model output."
                 if "yard_revision" in recipe else
                 "Sky and cleaned references are image-model outputs. The inspected segmented "
                 "Tripo meshes were assembled, repaired and cel-shaded in Blender.",
    }]
    provenance["render_settings"] = read(SOURCE / "render_settings.json")
    if "yard_revision" in recipe:
        provenance["yard_revision"] = recipe["yard_revision"]
    if pixel_art:
        painter = Path(__file__).with_name("stage_pixel_props.py")
        provenance["pixel_art"] = dict(
            pixel_art, tool="scripts/stage_pixel_props.py",
            tool_sha256=hashlib.sha256(painter.read_bytes()).hexdigest(), remote_services=[])
    if layout:
        provenance["foreground_layout"] = layout
    provenance["production"]["status"] = "generated_pending_artistic_review"
    provenance["production"]["blockers"] = ["Style, sky cleanliness, composition and in-game human reviews remain pending."]
    provenance["production"]["remote_submissions"] = len(tasks)
    provenance["production"]["mesh_task_ids"] = [
        record["task_id"] for record in tasks.values()
        if record["endpoint"] in ("/mesh/smartsegment", "/models/texture")
    ]
    write(SOURCE / "provenance.json", provenance)
    print("Compiled White House layers, shared palette, reusable props and selectable stage.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare-yard", "render", "compile"])
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(arguments)
    if args.phase == "render":
        render()
    elif args.phase == "prepare-yard":
        prepare_yard()
    else:
        compile()
