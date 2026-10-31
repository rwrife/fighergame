"""Verify the polygon budget of a newly generated FBX before caching it."""

import argparse
from pathlib import Path
import sys

import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--max-faces", type=int, default=20000)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.max_faces <= 0:
        raise ValueError("The face limit must be positive.")
    if bpy.app.version[:2] != (4, 5):
        raise RuntimeError("Model verification requires Blender 4.5 LTS.")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(args.model.resolve()))
    count = sum(len(obj.data.polygons) for obj in bpy.context.scene.objects
                if obj.type == "MESH")
    if not 0 < count <= args.max_faces:
        raise ValueError(f"Generated mesh has {count:,} polygons; limit is {args.max_faces:,}.")
    print(f"Verified generated mesh: {count:,} / {args.max_faces:,} polygons")


if __name__ == "__main__":
    main()
