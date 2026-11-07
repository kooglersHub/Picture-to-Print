import io
import json
import time
import zipfile

import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from picture_to_print.web import create_app
from picture_to_print.workflow import JobService


def wait_for_job(service, job_id):
    # Native mesh workers can start slowly on Windows during a cold full-suite run.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job["status"] in {"ready", "failed", "interrupted"}:
            return job
        time.sleep(0.05)
    pytest.fail("Workflow did not finish")


@pytest.fixture
def service(tmp_path):
    with JobService(tmp_path / "jobs") as value:
        yield value


def test_mesh_upload_runs_real_repair_and_downloads(service):
    source = trimesh.creation.box().export(file_type="stl")
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/api/jobs",
            files={"file": ("dog.stl", source)},
            data={"size_mm": "20", "voxel_mm": "0.5"},
        )
        assert response.status_code == 202
        job = wait_for_job(service, response.json()["id"])
        assert job["status"] == "ready", job
        assert job["review_required"]
        archive = client.get(f"/api/jobs/{job['id']}/files/result.zip")
        assert archive.status_code == 200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            assert {"model.stl", "model.3mf", "manifest.json", "preview.glb"} <= set(
                zipped.namelist()
            )
            assert not any("input" in name for name in zipped.namelist())
            assert json.loads(zipped.read("manifest.json"))["geometry"]["positive_volume"]
        assert client.get(f"/api/jobs/{job['id']}/files/../job.json").status_code != 200
        assert client.get(f"/api/jobs/{job['id']}/files/job.json").status_code == 404


def test_photo_job_preserves_raw_and_retry_does_not_regenerate(tmp_path):
    calls = []

    def generate(image, raw, resolution, seed, log):
        calls.append(image)
        trimesh.creation.box().export(raw)
        return {"model": "test-injected", "seed": seed, "resolution": resolution}

    image = io.BytesIO()
    Image.new("RGB", (512, 512), "white").save(image, "JPEG")
    with JobService(
        tmp_path / "jobs", generator=generate, readiness=lambda: {"modal": True, "hf": True}
    ) as service:
        with TestClient(create_app(service)) as client:
            response = client.post(
                "/api/jobs",
                files={"file": ("dog.jpg", image.getvalue())},
                data={"size_mm": "20", "voxel_mm": "0.5"},
            )
            job = wait_for_job(service, response.json()["id"])
            assert job["status"] == "ready", job
            assert (service.folder(job["id"]) / "raw.ply").exists()
            retry = client.post(
                f"/api/jobs/{job['id']}/retry", data={"size_mm": "25", "voxel_mm": "0.5"}
            )
            assert retry.status_code == 202
            redone = wait_for_job(service, retry.json()["id"])
            assert redone["status"] == "ready"
            assert len(calls) == 1


def test_missing_credentials_stops_photo_job_before_generation(service):
    image = io.BytesIO()
    Image.new("RGB", (512, 512)).save(image, "PNG")
    with TestClient(create_app(service)) as client:
        response = client.post("/api/jobs", files={"file": ("dog.png", image.getvalue())})
        assert response.status_code == 412
        assert not list(service.root.glob("*/job.json"))


def test_cross_origin_job_submission_is_rejected(service):
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/api/jobs",
            headers={"Origin": "https://evil.example"},
            files={"file": ("x.stl", b"not-a-mesh")},
        )
        assert response.status_code == 403


@pytest.mark.parametrize("data", [{"size_mm": "nan"}, {"voxel_mm": "-1"}, {"resolution": "2048"}])
def test_bad_parameters_do_not_create_jobs(service, data):
    with TestClient(create_app(service)) as client:
        response = client.post("/api/jobs", files={"file": ("x.stl", b"bad")}, data=data)
        assert response.status_code == 422
        assert not list(service.root.glob("*/job.json"))


def test_previous_unfinished_job_is_marked_interrupted(tmp_path):
    job_id = "a" * 32
    folder = tmp_path / job_id
    folder.mkdir()
    (folder / "job.json").write_text(json.dumps({"id": job_id, "status": "generating"}))
    with JobService(tmp_path) as service:
        assert service.get(job_id)["status"] == "interrupted"
