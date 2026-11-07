"""Isolated native MeshLib process; a crash cannot publish an invalid export."""

import json
import sys
from pathlib import Path

import numpy as np
from meshlib import mrmeshnumpy as mn
from meshlib import mrmeshpy as mm


def remove_enclosed_shells(mesh, known_disjoint=False):
    regions = list(mm.getAllComponents(mm.MeshPart(mesh)))
    if len(regions) <= 1:
        return 0
    boxes = [mesh.computeBoundingBox(region) for region in regions]
    closed = [mesh.topology.isClosed(region) for region in regions]
    remove = []
    for index, region in enumerate(regions):
        for other_index, other in enumerate(regions):
            if index == other_index or not closed[other_index]:
                continue
            small, large = boxes[index], boxes[other_index]
            if not all(
                getattr(small.min, axis) > getattr(large.min, axis)
                and getattr(small.max, axis) < getattr(large.max, axis)
                for axis in ("x", "y", "z")
            ):
                continue
            inside = mm.isNonIntersectingInside if known_disjoint else mm.isInside
            if inside(mm.MeshPart(mesh, region), mm.MeshPart(mesh, other)):
                remove.append(index)
                break
    hidden = mm.FaceBitSet()
    for index in remove:
        for face in regions[index]:
            hidden.autoResizeSet(face)
    if remove:
        mesh.deleteFaces(hidden)
    return len(remove)


def strip_hidden_faces(mesh, batch_size=65536):
    """Sample visibility, independent of face normals and mesh connectivity."""
    directions = [
        mm.Vector3f(x, y, z).normalized()
        for x in (-1, 0, 1)
        for y in (-1, 0, 1)
        for z in (-1, 0, 1)
        if (x, y, z) != (0, 0, 0)
    ]
    epsilon = mesh.computeBoundingBox().diagonal() * 1e-6
    # Pack first so the compact numpy triangle indices match FaceIds even if
    # the input topology contains deleted faces. No geometry is simplified.
    mesh.packOptimally()
    faces = mn.getNumpyFaces(mesh.topology)
    vertices = mn.getNumpyVerts(mesh)
    centers = vertices[faces].mean(axis=1).astype(np.float32)
    hidden_mask = np.ones(len(faces), dtype=bool)
    part = mm.MeshPart(mesh)
    for start in range(0, len(faces), batch_size):
        pending = np.arange(start, min(start + batch_size, len(faces)))
        for direction in directions:
            if not len(pending):
                break
            origins = mn.fromNumpyArray(centers[pending])
            vectors = mn.fromNumpyArray(
                np.tile([direction.x, direction.y, direction.z], (len(pending), 1)).astype(
                    np.float32
                )
            )
            result = mm.MultiRayMeshIntersectResult()
            result.intersectingRays = mm.BitSet()
            mm.multiRayMeshIntersect(
                part, origins, vectors, result, rayStart=epsilon, closestIntersect=False
            )
            blocked = mn.getNumpyBitSet(result.intersectingRays)
            hidden_mask[pending[~blocked]] = False
            pending = pending[blocked]
    hidden = mn.faceBitSetFromBools(hidden_mask)
    count = hidden.count()
    enclosed = sum(region.is_subset_of(hidden) for region in mm.getAllComponents(part))
    if count:
        mesh.deleteFaces(hidden)
    return count, enclosed


def close_remesh_boundaries(mesh):
    # Hole-aware sign assignment can still leave open boundary loops in a
    # pathological reconstruction. These are surface defects, not valid tunnels.
    holes = mesh.topology.findHoleRepresentiveEdges()
    count = len(holes)
    if count:
        mm.fillHoles(mesh, holes)
    return count


def run(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    mesh = mm.loadMesh(config["input"])
    print("MeshLib: testing face visibility", flush=True)
    hidden, removed_before = strip_hidden_faces(mesh) if config["strip_hidden_faces"] else (0, 0)
    print(f"MeshLib: removed {hidden} hidden faces; reconstructing volume", flush=True)
    params = mm.GeneralOffsetParameters()
    params.voxelSize = config["voxel_mm"]
    params.signDetectionMode = mm.SignDetectionMode.HoleWindingRule
    params.closeHolesInHoleWindingNumber = True
    solid = mm.generalOffsetMesh(mm.MeshPart(mesh), 0.0, params)
    holes_filled = close_remesh_boundaries(solid)
    collisions = mm.findSelfCollidingTriangles(mm.MeshPart(solid))
    print(f"MeshLib: checking interior shells ({len(collisions)} intersections)", flush=True)
    # A single global collision check proves the precondition for the much
    # cheaper non-intersecting containment query across all voxel components.
    removed_after = remove_enclosed_shells(solid, known_disjoint=True) if not len(collisions) else 0
    mm.saveMesh(solid, config["output"])
    Path(config["metrics"]).write_text(
        json.dumps(
            {
                "hidden_faces_removed": hidden,
                "self_intersections_after_remesh": len(collisions),
                "method": "HoleWindingRule",
                "enclosed_shells_removed": removed_before + removed_after,
                "post_remesh_holes_filled": holes_filled,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run(sys.argv[1])
