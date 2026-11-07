import json

import trimesh
from fastapi.testclient import TestClient

from picture_to_print.pipeline import PrintSettings
from picture_to_print.web import create_app
from picture_to_print.workflow import JobService


def test_upload_stores_selected_tool_and_health_reports_capabilities(tmp_path, monkeypatch):
    with JobService(tmp_path, dispatcher=lambda _: None) as service:
        monkeypatch.setattr(service, "repair_tools", lambda: {"meshlib": True, "blender": True})
        with TestClient(create_app(service)) as client:
            health = client.get("/api/health").json()
            assert health["repair_tools"]["blender"] is True
            response = client.post(
                "/api/jobs",
                files={"file": ("cube.stl", trimesh.creation.box().export(file_type="stl"))},
                data={"backend": "blender"},
            )
            assert response.status_code == 202
            assert response.json()["settings"]["backend"] == "blender"


def test_unavailable_or_unknown_tool_is_rejected_before_enqueue(tmp_path, monkeypatch):
    with JobService(tmp_path, dispatcher=lambda _: None) as service:
        monkeypatch.setattr(service, "repair_tools", lambda: {"meshlib": True, "blender": False})
        with TestClient(create_app(service)) as client:
            for backend, status in [("blender", 412), ("shell-command", 422)]:
                response = client.post(
                    "/api/jobs", files={"file": ("cube.stl", b"mesh")}, data={"backend": backend}
                )
                assert response.status_code == status
            assert service.list() == []


def test_compare_copies_same_raw_mesh_and_changes_only_repair_settings(tmp_path, monkeypatch):
    with JobService(tmp_path, dispatcher=lambda _: None) as service:
        monkeypatch.setattr(service, "repair_tools", lambda: {"meshlib": True, "blender": True})
        original = service.submit("dog.jpg", b"original photo", PrintSettings())
        raw = trimesh.creation.box().export(file_type="ply")
        (service.folder(original["id"]) / "raw.ply").write_bytes(raw)
        service._update(original["id"], status="ready", can_retry_repair=True)
        with TestClient(create_app(service)) as client:
            response = client.post(
                f"/api/jobs/{original['id']}/retry",
                data={"backend": "blender", "size_mm": 100, "voxel_mm": 0.4},
            )
        assert response.status_code == 202
        compared = response.json()
        assert compared["settings"]["backend"] == "blender"
        assert compared["source_job_id"] == original["id"]
        assert (service.folder(compared["id"]) / "raw.ply").read_bytes() == raw
        assert service.get(original["id"])["settings"]["backend"] == "meshlib"


def test_worker_passes_blender_path_and_records_elapsed_time(tmp_path, monkeypatch):
    from picture_to_print import workflow

    calls = []

    def prepare(source, target, settings, blender):
        calls.append((settings.backend, blender))
        target.mkdir()
        trimesh.creation.box(extents=[2, 4, 6]).export(target / "model.stl")
        (target / "model.3mf").write_bytes(b"export")
        (target / "manifest.json").write_text(json.dumps({"backend": settings.backend}))
        return {"geometry": {}, "review_reasons": [], "surface_deviation": {}}

    monkeypatch.setattr(workflow, "prepare_model", prepare)
    with JobService(tmp_path, dispatcher=lambda _: None, blender="/custom/blender") as service:
        job = service.submit(
            "cube.ply",
            trimesh.creation.box().export(file_type="ply"),
            PrintSettings(backend="blender"),
        )
        service.run_one(job["id"])
        result = service.get(job["id"])
        assert result["status"] == "ready"
        assert calls == [("blender", "/custom/blender")]
        assert result["repair_seconds"] >= 0
        assert len(result["raw_sha256"]) == 64
        print_mesh = trimesh.load_mesh(service.folder(job["id"]) / "print/model.stl")
        preview = trimesh.load_scene(service.folder(job["id"]) / "print/preview.glb").to_mesh()
        assert print_mesh.extents.tolist() == [2, 4, 6]
        assert preview.extents.tolist() == [2, 6, 4]
        assert preview.visual.vertex_colors[0, :3].max() < 200
