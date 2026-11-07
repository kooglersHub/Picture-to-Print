import trimesh

from picture_to_print.geometry import describe, orient_closed_components, remove_enclosed_shells


def test_all_external_components_must_have_positive_volume():
    first = trimesh.creation.box(extents=[2, 2, 2])
    inverted = trimesh.creation.box()
    inverted.invert()
    inverted.apply_translation([5, 0, 0])
    mixed = trimesh.util.concatenate([first, inverted])
    assert mixed.volume > 0
    assert not describe(mixed)["positive_volume"]
    fixed_faces = orient_closed_components(mixed)
    assert fixed_faces == len(inverted.faces)
    assert describe(mixed)["positive_volume"]


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


def test_many_open_patches_do_not_hide_a_nested_closed_shell():
    # A TRELLIS mesh can have thousands of open disconnected surface patches.
    # Query spatial candidates instead of allocating an all-pairs scan per part.
    parts = []
    for index in range(100):
        patch = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2]])
        patch.apply_translation([index * 3, 0, 0])
        parts.append(patch)
    outer = trimesh.creation.box(extents=[4, 4, 4])
    inner = trimesh.creation.box()
    outer.apply_translation([-10, 0, 0])
    inner.apply_translation([-10, 0, 0])
    source = trimesh.util.concatenate([*parts, outer, inner])
    result, removed = remove_enclosed_shells(source)
    assert removed == 1
    assert len(result.faces) == len(source.faces) - len(inner.faces)
