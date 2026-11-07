from fastapi.testclient import TestClient

from picture_to_print.pipeline import PrintSettings
from picture_to_print.web import create_app
from picture_to_print.workflow import JobService


def test_dispatch_failure_is_terminal_and_keeps_error_internal(tmp_path):
    def reject(identifier):
        raise RuntimeError("private-cloud-error-detail")

    with JobService(tmp_path, dispatcher=reject) as service:
        job = service.submit("cube.stl", b"data", PrintSettings(size_mm=20, voxel_mm=0.5))
        persisted = service.get(job["id"])
        assert persisted["status"] == "failed"
        assert "private-cloud-error-detail" not in persisted["error"]


def test_declared_oversized_body_is_rejected_before_multipart_parsing(tmp_path):
    with JobService(tmp_path) as service:
        with TestClient(create_app(service)) as client:
            response = client.post(
                "/api/jobs", content=b"not-a-body", headers={"content-length": "90000000"}
            )
            assert response.status_code == 413


def test_corrupt_photo_never_enters_the_job_queue(tmp_path):
    with JobService(tmp_path, readiness=lambda: {"modal": True}) as service:
        with TestClient(create_app(service)) as client:
            response = client.post("/api/jobs", files={"file": ("dog.jpg", b"not-an-image")})
            assert response.status_code == 422
            assert service.list() == []
