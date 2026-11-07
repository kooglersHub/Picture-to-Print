"""Standalone Blender worker. Arguments follow Blender's -- separator."""

import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from snapshots import write_native_snapshot


def save_snapshot(mesh, directory, stage_id):
    if not directory:
        return
    mesh.calc_loop_triangles()
    vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    faces = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
    mesh.vertices.foreach_get("co", vertices.ravel())
    mesh.loop_triangles.foreach_get("vertices", faces.ravel())
    write_native_snapshot(
        directory,
        stage_id,
        lambda file: np.savez(file, vertices=vertices, faces=faces),
        suffix=".npz",
    )


def run(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    data = np.load(config["input"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("print_geometry")
    mesh.from_pydata(data["vertices"].tolist(), [], data["faces"].tolist())
    mesh.update()
    obj = bpy.data.objects.new("print_geometry", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    stages = config.get("stages_directory")
    save_snapshot(mesh, stages, "native-import")

    editable = bmesh.new()
    editable.from_mesh(mesh)
    boundary = [edge for edge in editable.edges if edge.is_boundary]
    boundary_count = len(boundary)
    # Cap boundaries before volume reconstruction: an open surface otherwise
    # has no unambiguous inside and can collapse to a thin shell.
    if boundary:
        bmesh.ops.holes_fill(editable, edges=boundary, sides=0)
    bmesh.ops.recalc_face_normals(editable, faces=list(editable.faces))
    editable.to_mesh(mesh)
    editable.free()
    save_snapshot(mesh, stages, "pre-capped")

    modifier = obj.modifiers.new("solid_volume", "REMESH")
    modifier.mode = "VOXEL"
    modifier.voxel_size = config["voxel_mm"]
    modifier.adaptivity = 0
    modifier.use_remove_disconnected = False
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    save_snapshot(obj.data, stages, "remeshed")
    editable = bmesh.new()
    editable.from_mesh(obj.data)
    bmesh.ops.triangulate(editable, faces=list(editable.faces))
    bmesh.ops.recalc_face_normals(editable, faces=list(editable.faces))
    editable.faces.ensure_lookup_table()
    # BVH overlap checks omit adjacent triangles, which intentionally touch.
    tree = BVHTree.FromBMesh(editable, epsilon=0.0)
    faces = list(editable.faces)
    intersections = sum(
        1
        for a, b in tree.overlap(tree)
        if a < b and not set(faces[a].verts).intersection(faces[b].verts)
    )
    editable.to_mesh(obj.data)
    editable.free()
    obj.data.calc_loop_triangles()
    np.savez(
        config["output"],
        vertices=np.array([vertex.co[:] for vertex in obj.data.vertices]),
        faces=np.array([triangle.vertices[:] for triangle in obj.data.loop_triangles]),
    )
    Path(config["metrics"]).write_text(
        json.dumps(
            {
                "boundary_edges_before": boundary_count,
                "self_intersections_after_remesh": intersections,
                "blender_version": bpy.app.version_string,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--") + 1])
