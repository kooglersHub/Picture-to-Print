import io

import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from picture_to_print.pipeline import PrintSettings, prepare_model
from picture_to_print.stages import StageRecorder, read_stages
from picture_to_print.web import create_app
from picture_to_print.workflow import JobService


def test_stage_meshes_keep_a_shared_frame_and_exact_topology(tmp_path):
    recorder = StageRecorder(tmp_path, size_mm=100)
    first = trimesh.creation.box(extents=[20, 10, 40])
    second = first.copy()
    second.apply_translation([10, 0, 0])
    recorder.mesh("raw", first)
    recorder.mesh("prepared", second)
    stages = read_stages(tmp_path)
    assert [stage["id"] for stage in stages] == ["raw", "prepared"]
    a = trimesh.load_scene(tmp_path / "raw.glb").to_mesh()
    b = trimesh.load_scene(tmp_path / "prepared.glb").to_mesh()
    assert b.bounds.mean(axis=0)[0] - a.bounds.mean(axis=0)[0] == pytest.approx(10)
    assert a.extents == pytest.approx([20, 40, 10])
    assert stages[0]["metrics"]["triangles"] == len(first.faces)
    assert stages[0]["metrics"]["components"] == 1


def test_real_meshlib_repair_records_every_completed_repair_phase(tmp_path):
    source = tmp_path / "raw.ply"
    mesh = trimesh.creation.box()
    mesh.update_faces(list(range(1, len(mesh.faces))))
    mesh.export(source)
    stages = tmp_path / "stages"
    prepare_model(
        source, tmp_path / "print", PrintSettings(size_mm=20, voxel_mm=0.5), stage_directory=stages
    )
    recorded = {stage["id"]: stage for stage in read_stages(stages)}
    assert {
        "prepared",
        "native-import",
        "visible",
        "remeshed",
        "capped",
        "no-cavities",
        "oriented",
        "exported",
    } <= recorded.keys()
    assert recorded["prepared"]["metrics"]["boundary_edges"] > 0
    assert recorded["exported"]["metrics"]["boundary_edges"] == 0
    assert all(stage["status"] == "available" for stage in recorded.values())


def test_stage_assets_are_private_and_diagnostics_work_after_failure(tmp_path):
    owner = "a" * 64
    with JobService(tmp_path, dispatcher=lambda _: None) as service:
        job = service.submit("cube.ply", b"source", PrintSettings(), owner=owner)
        recorder = StageRecorder(service.folder(job["id"]) / "stages", size_mm=100)
        recorder.mesh("prepared", trimesh.creation.box())
        service._update(job["id"], status="failed")
        with TestClient(create_app(service, backend_token="private")) as client:
            url = f"/api/jobs/{job['id']}/stages"
            assert client.get(url).status_code == 401
            headers = {"Authorization": "Bearer private", "X-P2P-Owner": owner}
            response = client.get(url, headers=headers)
            assert response.status_code == 200
            stage = next(stage for stage in response.json()["stages"] if stage["id"] == "prepared")
            assert client.get(stage["preview_url"], headers=headers).status_code == 200
            assert (
                client.get(
                    stage["preview_url"], headers={**headers, "X-P2P-Owner": "b" * 64}
                ).status_code
                == 404
            )
            assert (
                client.get(
                    f"/api/jobs/{job['id']}/stage-files/job.json", headers=headers
                ).status_code
                == 404
            )
            assert (
                client.get(f"/api/jobs/{job['id']}/files/model.stl", headers=headers).status_code
                == 404
            )


def test_legacy_jobs_show_saved_input_but_do_not_invent_foreground(tmp_path):
    image = io.BytesIO()
    Image.new("RGB", (128, 128)).save(image, "PNG")
    with JobService(tmp_path, dispatcher=lambda _: None) as service:
        job = service.submit("dog.png", image.getvalue(), PrintSettings())
        with TestClient(create_app(service)) as client:
            stages = client.get(f"/api/jobs/{job['id']}/stages").json()["stages"]
            assert (
                next(stage for stage in stages if stage["id"] == "input")["status"] == "available"
            )
            assert (
                next(stage for stage in stages if stage["id"] == "foreground")["status"]
                == "missing"
            )


def test_gpu_image_artifacts_are_saved_by_the_workflow(tmp_path):
    source = io.BytesIO()
    Image.new("RGBA", (128, 128), (100, 100, 100, 255)).save(source, "PNG")

    def generator(photo, raw, resolution, seed, log):
        trimesh.creation.box().export(raw)
        return {
            "model": "injected",
            "images": {"foreground": source.getvalue(), "generation-input": source.getvalue()},
        }

    with JobService(tmp_path, generator=generator, dispatcher=lambda _: None) as service:
        job = service.submit("dog.png", source.getvalue(), PrintSettings(size_mm=20, voxel_mm=0.5))
        service.run_one(job["id"])
        assert service.get(job["id"])["status"] == "ready"
        saved = {stage["id"]: stage for stage in service.stage_catalog(job["id"])["stages"]}
        assert saved["foreground"]["status"] == "available"
        assert saved["generation-input"]["status"] == "available"
        assert "images" not in service.get(job["id"])["generation"]


def test_generation_failure_preserves_already_committed_image_stages(tmp_path):
    source = io.BytesIO()
    Image.new("RGBA", (128, 128), (100, 100, 100, 255)).save(source, "PNG")

    def generator(photo, raw, resolution, seed, log):
        recorder = StageRecorder(photo.parent / "stages", size_mm=100)
        recorder.image("foreground", source.getvalue())
        raise RuntimeError("Sampling failed after preprocessing")

    with JobService(tmp_path, generator=generator, dispatcher=lambda _: None) as service:
        job = service.submit("dog.png", source.getvalue(), PrintSettings())
        service.run_one(job["id"])
        assert service.get(job["id"])["status"] == "failed"
        rows = service.stage_catalog(job["id"])["stages"]
        assert next(row for row in rows if row["id"] == "foreground")["status"] == "available"
