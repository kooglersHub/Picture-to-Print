from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from picture_to_print.pipeline import PrintSettings
from picture_to_print.workflow import JobService


def test_cloud_termination_is_detected_and_allows_repair_retry(tmp_path):
    with JobService(
        tmp_path,
        dispatcher=lambda _: SimpleNamespace(object_id="fc-failed"),
        call_status=lambda _: "failed",
        recover=False,
    ) as service:
        job = service.submit("cube.stl", b"data", PrintSettings(size_mm=20, voxel_mm=0.5))
        (service.folder(job["id"]) / "raw.ply").write_bytes(b"preserved raw mesh")
        recovered = service.get(job["id"])
        assert recovered["status"] == "interrupted"
        assert recovered["can_retry_repair"] is True


def test_completed_call_rereads_final_job_before_marking_interrupted(tmp_path):
    def call_status(identifier):
        job = service._read_job(job_id)
        job["status"] = "ready"
        service._save(job)
        return "completed"

    with JobService(
        tmp_path,
        dispatcher=lambda _: SimpleNamespace(object_id="fc-complete"),
        call_status=call_status,
        recover=False,
    ) as service:
        job = service.submit("cube.stl", b"data", PrintSettings(size_mm=20, voxel_mm=0.5))
        job_id = job["id"]
        assert service.get(job_id)["status"] == "ready"


def test_stale_queued_job_without_call_id_is_released_and_cannot_start(tmp_path):
    with JobService(
        tmp_path, dispatcher=lambda _: None, call_status=lambda _: "running", recover=False
    ) as service:
        job = service.submit("cube.stl", b"data", PrintSettings())
        job["created_at"] = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
        service._save(job)
        assert service.get(job["id"])["status"] == "interrupted"
        service.run_one(job["id"])
        assert service.get(job["id"])["status"] == "interrupted"
        assert not (service.folder(job["id"]) / "raw.ply").exists()


def test_no_call_id_does_not_interrupt_a_fresh_or_running_job(tmp_path):
    with JobService(
        tmp_path, dispatcher=lambda _: None, call_status=lambda _: "unknown", recover=False
    ) as service:
        job = service.submit("cube.stl", b"data", PrintSettings())
        assert service.get(job["id"])["status"] == "queued"
        job["created_at"] = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
        job["updated_at"] = datetime.now(UTC).isoformat()
        job["status"] = "generating"
        service._save(job)
        assert service.get(job["id"])["status"] == "generating"
