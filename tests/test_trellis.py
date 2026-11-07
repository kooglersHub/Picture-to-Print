from types import SimpleNamespace

import numpy as np
import pytest
import trimesh

from picture_to_print.trellis import export_raw_mesh


def test_raw_export_preserves_geometry_without_texture_or_remesh(tmp_path):
    cube = trimesh.creation.box()
    source = SimpleNamespace(vertices=cube.vertices, faces=cube.faces)
    path = export_raw_mesh(source, tmp_path / "raw.ply")
    reloaded = trimesh.load_mesh(path, process=False)
    np.testing.assert_allclose(reloaded.vertices, cube.vertices)
    np.testing.assert_array_equal(reloaded.faces, cube.faces)
    with pytest.raises(FileExistsError):
        export_raw_mesh(source, path)
