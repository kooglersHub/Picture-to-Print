import json
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest
import trimesh

from picture_to_print.pipeline import PrintSettings, prepare_model


@pytest.fixture(scope="session")
def blender():
    executable = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if not executable:
        pytest.skip("Set BLENDER_BIN to run Blender integration tests")
    return executable


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size_mm": 0},
        {"size_mm": float("nan")},
        {"voxel_mm": -1},
        {"voxel_mm": float("inf")},
        {"timeout_seconds": 0},
    ],
)
def test_rejects_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        PrintSettings(**kwargs)


def test_repairs_open_cube_and_exports_explicit_mm(tmp_path):
    cube = trimesh.creation.box()
    cube.update_faces(np.arange(len(cube.faces)) != 0)
    source = tmp_path / "open.stl"
    cube.export(source)
    result = prepare_model(source, tmp_path / "job", PrintSettings(size_mm=20, voxel_mm=0.5))
    assert result["status"] == "geometry_ready"
    assert result["review_required"] is True
    repaired = trimesh.load_mesh(tmp_path / "job/model.stl")
    assert repaired.is_volume
    assert repaired.extents.max() == pytest.approx(20, abs=1.0)
    assert result["repair"]["boundary_edges_before"] > 0
    assert result["geometry"]["components"] == 1
    with zipfile.ZipFile(tmp_path / "job/model.3mf") as archive:
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        assert root.attrib["unit"] == "millimeter"
        assert b"texture" not in archive.read("3D/3dmodel.model").lower()
    assert json.loads((tmp_path / "job/manifest.json").read_text())["source_sha256"]


def test_removes_nested_shells_instead_of_exporting_cavities(tmp_path):
    outer = trimesh.creation.icosphere(subdivisions=2, radius=1)
    inner = trimesh.creation.icosphere(subdivisions=2, radius=0.6)
    inner.invert()
    source = tmp_path / "hollow.glb"
    trimesh.Scene([outer, inner]).export(source)
    result = prepare_model(source, tmp_path / "solid", PrintSettings(size_mm=20, voxel_mm=0.5))
    assert result["status"] == "geometry_ready"
    assert result["geometry"]["components"] == 1
    assert result["geometry"]["volume_mm3"] > 3500
    assert result["repair"]["enclosed_shells_removed"] >= 1


def test_preserves_scene_transforms_and_external_parts(tmp_path):
    scene = trimesh.Scene()
    for x in (0, 3):
        transform = trimesh.transformations.translation_matrix([x, 0, 0])
        scene.add_geometry(trimesh.creation.box(), transform=transform)
    source = tmp_path / "parts.glb"
    scene.export(source)
    result = prepare_model(source, tmp_path / "parts", PrintSettings(size_mm=40, voxel_mm=0.5))
    assert result["geometry"]["components"] == 2
    assert result["geometry"]["dimensions_mm"][0] == pytest.approx(40, abs=1)
    assert "separate_parts" in result["review_reasons"]


def test_refuses_existing_job_directory(tmp_path):
    source = tmp_path / "cube.stl"
    trimesh.creation.box().export(source)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        prepare_model(source, output, PrintSettings(), "unused")
    assert sentinel.read_text() == "keep"


def test_rejects_excessive_voxel_grid_before_launching_blender(tmp_path):
    source = tmp_path / "cube.stl"
    trimesh.creation.box().export(source)
    with pytest.raises(ValueError, match="voxel"):
        prepare_model(source, tmp_path / "large", PrintSettings(voxel_mm=0.001), "unused")
    assert not (tmp_path / "large/model.stl").exists()


def test_failed_worker_produces_rejection_without_print_artifacts(tmp_path):
    source = tmp_path / "cube.stl"
    trimesh.creation.box().export(source)
    with pytest.raises(RuntimeError, match="Blender"):
        prepare_model(
            source,
            tmp_path / "failed",
            PrintSettings(backend="blender"),
            "missing-blender-executable",
        )
    manifest = json.loads((tmp_path / "failed/manifest.json").read_text())
    assert manifest["status"] == "rejected"
    assert not (tmp_path / "failed/model.stl").exists()


def test_meshlib_preserves_ring_bore(tmp_path):
    ring = trimesh.creation.torus(
        major_radius=10, minor_radius=2, major_sections=48, minor_sections=16
    )
    source = tmp_path / "ring.stl"
    ring.export(source)
    result = prepare_model(source, tmp_path / "ring", PrintSettings(size_mm=24, voxel_mm=0.4))
    assert result["backend"] == "meshlib"
    repaired = trimesh.load_mesh(tmp_path / "ring/model.stl")
    assert repaired.is_volume
    assert not repaired.contains([[0, 0, 0.0], [0, 0, 2.0]]).any()
    assert repaired.euler_number == 0


def test_blender_backend_repairs_open_cube(tmp_path, blender):
    mesh = trimesh.creation.box()
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    source = tmp_path / "open.stl"
    mesh.export(source)
    result = prepare_model(
        source,
        tmp_path / "blender",
        PrintSettings(size_mm=20, voxel_mm=0.5, backend="blender"),
        blender,
    )
    assert result["status"] == "geometry_ready"
    assert result["geometry"]["positive_volume"]


def test_removes_connected_inner_walls(tmp_path):
    # A double wall connected through one small opening, as in Trellis exports.
    outer = trimesh.creation.icosphere(subdivisions=2, radius=10)
    inner = outer.copy()
    inner.apply_scale(0.9)
    inner.invert()
    hole = outer.triangles_center[:, 2].argmax()
    opening = outer.faces[hole].copy()
    keep = np.arange(len(outer.faces)) != hole
    outer.update_faces(keep)
    inner.update_faces(keep)
    offset = len(outer.vertices)
    rim_faces = []
    for index, a in enumerate(opening):
        b = opening[(index + 1) % 3]
        rim_faces.extend([[a, b, a + offset], [b, b + offset, a + offset]])
    shell = trimesh.Trimesh(
        vertices=np.vstack([outer.vertices, inner.vertices]),
        faces=np.vstack([outer.faces, inner.faces + offset, rim_faces]),
    )
    shell.fix_normals()
    assert len(shell.split(only_watertight=False, repair=False)) == 1
    source = tmp_path / "double-wall.stl"
    shell.export(source)
    result = prepare_model(source, tmp_path / "walls", PrintSettings(size_mm=20, voxel_mm=0.5))
    assert result["status"] == "geometry_ready"
    assert result["geometry"]["volume_mm3"] > 3500
    assert result["geometry"]["components"] == 1
    assert result["repair"]["hidden_faces_removed"] > 0


def test_native_reconstruction_centers_large_scene_coordinates(tmp_path):
    cube = trimesh.creation.box(extents=[20, 20, 20])
    cube.apply_translation([1e8, 0, 0])
    source = tmp_path / "far.obj"
    cube.export(source)
    result = prepare_model(source, tmp_path / "centered", PrintSettings(size_mm=20, voxel_mm=0.5))
    assert result["geometry"]["dimensions_mm"] == pytest.approx([20, 20, 20], abs=1)
