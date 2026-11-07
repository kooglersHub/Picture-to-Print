import numpy as np
import trimesh
from meshlib import mrmeshnumpy as mn
from meshlib import mrmeshpy as mm

from picture_to_print.meshlib_worker import close_remesh_boundaries, strip_hidden_faces


def scalar_hidden_count(mesh):
    directions = [
        mm.Vector3f(x, y, z).normalized()
        for x in (-1, 0, 1)
        for y in (-1, 0, 1)
        for z in (-1, 0, 1)
        if (x, y, z) != (0, 0, 0)
    ]
    epsilon = mesh.computeBoundingBox().diagonal() * 1e-6
    part = mm.MeshPart(mesh)
    hidden = 0
    for face in mesh.topology.getValidFaces():
        a, b, c = mesh.getTriPoints(face)
        center = (a + b + c) / 3
        visible = any(
            not mm.rayMeshIntersect(
                part, mm.Line3f(center, direction), rayStart=epsilon, closestIntersect=False
            )
            for direction in directions
        )
        hidden += not visible
    return hidden


def test_batch_visibility_matches_scalar_rays_and_preserves_exterior(monkeypatch):
    outer = trimesh.creation.box(extents=[4, 4, 4])
    inner = trimesh.creation.box()
    inner.invert()
    source = trimesh.util.concatenate([outer, inner])
    mesh = mn.meshFromFacesVerts(source.faces.astype(np.int32), source.vertices.astype(np.float32))
    expected = scalar_hidden_count(mesh)
    assert expected == len(inner.faces)

    def forbidden_scalar(*args, **kwargs):
        raise AssertionError("Per-face Python ray calls must not be used")

    monkeypatch.setattr(mm, "rayMeshIntersect", forbidden_scalar)
    removed, enclosed = strip_hidden_faces(mesh, batch_size=3)
    assert removed == expected
    assert enclosed == 1
    assert mesh.topology.numValidFaces() == len(outer.faces)


def test_batch_visibility_handles_holes_and_invalid_face_ids():
    sphere = trimesh.creation.icosphere(subdivisions=1)
    mesh = mn.meshFromFacesVerts(sphere.faces.astype(np.int32), sphere.vertices.astype(np.float32))
    faces = mm.FaceBitSet()
    faces.autoResizeSet(mm.FaceId(4))
    mesh.deleteFaces(faces)
    expected = scalar_hidden_count(mesh)
    before = mesh.topology.numValidFaces()
    removed, _ = strip_hidden_faces(mesh, batch_size=7)
    assert removed == expected
    assert mesh.topology.numValidFaces() == before - expected


def test_closes_residual_remesh_boundaries_without_filling_a_torus_tunnel():
    box = trimesh.creation.box()
    box.update_faces(np.arange(len(box.faces)) != 0)
    mesh = mn.meshFromFacesVerts(box.faces.astype(np.int32), box.vertices.astype(np.float32))
    assert close_remesh_boundaries(mesh) == 1
    assert mesh.topology.isClosed()
    assert len(mm.findSelfCollidingTriangles(mm.MeshPart(mesh))) == 0
    torus = trimesh.creation.torus(major_radius=10, minor_radius=2)
    mesh = mn.meshFromFacesVerts(torus.faces.astype(np.int32), torus.vertices.astype(np.float32))
    before = mesh.topology.numValidFaces()
    assert close_remesh_boundaries(mesh) == 0
    assert mesh.topology.numValidFaces() == before
