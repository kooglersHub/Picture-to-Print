"""Load scene geometry, remove cavities, and describe physical solids."""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import trimesh


def load_geometry(source: Path) -> trimesh.Trimesh:
    if source.suffix.lower() not in {".glb", ".stl", ".obj", ".ply"}:
        raise ValueError("Supported inputs: GLB, STL, OBJ, PLY")
    scene = trimesh.load_scene(source, process=False, skip_materials=True)
    mesh = scene.to_mesh()
    if not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise ValueError("Input has no usable finite triangle geometry")
    mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=True)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if not len(mesh.faces) or mesh.extents.max() <= 0:
        raise ValueError("Input geometry is empty or degenerate")
    return mesh


def remove_enclosed_shells(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, int]:
    parts = list(mesh.split(only_watertight=False, repair=False))
    bounds = np.array([part.bounds for part in parts])
    removed = set()
    for index, part in enumerate(parts):
        candidates = np.flatnonzero(
            (bounds[index, 0] > bounds[:, 0]).all(axis=1)
            & (bounds[index, 1] < bounds[:, 1]).all(axis=1)
        )
        for other_index in candidates:
            container = parts[other_index]
            if index == other_index or not container.is_watertight:
                continue
            # Vertex containment is insufficient for concave containers. This
            # Blender-only path conservatively retains any possible surface
            # contact. The MeshLib worker uses exact collision-aware isInside.
            disjoint = container.is_convex or not any(
                next(container.triangles_tree.intersection(triangle_bounds), None) is not None
                for triangle_bounds in np.hstack(
                    (part.triangles.min(axis=1), part.triangles.max(axis=1))
                )
            )
            if (
                disjoint
                and container.contains(
                    part.vertices if container.is_convex else part.vertices[:1]
                ).all()
            ):
                removed.add(index)
                break
    remaining = [part for index, part in enumerate(parts) if index not in removed]
    return trimesh.util.concatenate(remaining), len(removed)


def surface_deviation(reference: trimesh.Trimesh, repaired: trimesh.Trimesh) -> dict:
    distances = []
    for source, target in ((reference, repaired), (repaired, reference)):
        points, _ = trimesh.sample.sample_surface(source, 512, seed=42)
        _, distance, _ = trimesh.proximity.closest_point(target, points)
        distances.extend(distance)
    return {
        "samples_per_direction": 512,
        "sampled_max_mm": float(np.max(distances)),
        "sampled_p95_mm": float(np.percentile(distances, 95)),
        "note": "Sampled bidirectional surface distance, not a Hausdorff bound",
    }


def describe(mesh: trimesh.Trimesh) -> dict:
    edge_use = np.bincount(mesh.edges_unique_inverse)
    parts = mesh.split(only_watertight=False, repair=False)
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "boundary_edges": int(np.count_nonzero(edge_use == 1)),
        "nonmanifold_edges": int(np.count_nonzero(edge_use != 2)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "positive_volume": bool(parts) and all(part.is_volume for part in parts),
        "volume_mm3": float(mesh.volume),
        "dimensions_mm": mesh.extents.tolist(),
        "components": len(parts),
    }


def write_3mf(mesh: trimesh.Trimesh, target: Path) -> None:
    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", namespace)

    def element(parent, name, **attributes):
        return ET.SubElement(parent, f"{{{namespace}}}{name}", attributes)

    root = ET.Element(f"{{{namespace}}}model", {"unit": "millimeter"})
    resources = element(root, "resources")
    obj = element(resources, "object", id="1", type="model")
    geometry = element(obj, "mesh")
    vertices = element(geometry, "vertices")
    for x, y, z in mesh.vertices:
        element(vertices, "vertex", x=f"{x:.9g}", y=f"{y:.9g}", z=f"{z:.9g}")
    triangles = element(geometry, "triangles")
    for a, b, c in mesh.faces:
        element(triangles, "triangle", v1=str(a), v2=str(b), v3=str(c))
    build = element(root, "build")
    element(build, "item", objectid="1")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "3D/3dmodel.model", ET.tostring(root, encoding="utf-8", xml_declaration=True)
        )
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            "</Relationships>",
        )
