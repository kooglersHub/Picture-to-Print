"""Isolated native MeshLib process; a crash cannot publish an invalid export."""

import json
import sys
from pathlib import Path

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


def strip_hidden_faces(mesh):
    """Sample visibility, independent of face normals and mesh connectivity."""
    directions = [
        mm.Vector3f(x, y, z).normalized()
        for x in (-1, 0, 1)
        for y in (-1, 0, 1)
        for z in (-1, 0, 1)
        if (x, y, z) != (0, 0, 0)
    ]
    epsilon = mesh.computeBoundingBox().diagonal() * 1e-6
    hidden = mm.FaceBitSet()
    part = mm.MeshPart(mesh)
    for face in mesh.topology.getValidFaces():
        a, b, c = mesh.getTriPoints(face)
        center = (a + b + c) / 3
        visible = any(
            not mm.rayMeshIntersect(
                part, mm.Line3f(center, direction), rayStart=epsilon, closestIntersect=False
            )
            for direction in directions
        )
        if not visible:
            hidden.autoResizeSet(face)
    count = hidden.count()
    enclosed = sum(region.is_subset_of(hidden) for region in mm.getAllComponents(part))
    if count:
        mesh.deleteFaces(hidden)
    return count, enclosed


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
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run(sys.argv[1])
