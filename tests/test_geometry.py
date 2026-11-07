import trimesh

from picture_to_print.geometry import describe, remove_enclosed_shells


def test_all_external_components_must_have_positive_volume():
    first = trimesh.creation.box(extents=[2, 2, 2])
    inverted = trimesh.creation.box()
    inverted.invert()
    inverted.apply_translation([5, 0, 0])
    mixed = trimesh.util.concatenate([first, inverted])
    assert mixed.volume > 0
    assert not describe(mixed)["positive_volume"]


def test_vertex_containment_does_not_discard_surface_crossing_a_ring():
    ring = trimesh.creation.torus(major_radius=10, minor_radius=2)
    bridge = trimesh.Trimesh(
        vertices=[[10, 0, 1], [-10, 0, 0], [0, 10, 0], [0, -10, 0]],
        faces=[[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]],
    )
    bridge.fix_normals()
    original = trimesh.util.concatenate([ring, bridge])
    result, removed = remove_enclosed_shells(original)
    assert removed == 0
    assert len(result.faces) == len(original.faces)
