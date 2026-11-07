import trimesh
from fastapi.testclient import TestClient

from picture_to_print.web import create_app
from picture_to_print.workflow import JobService


def test_hosted_backend_rejects_missing_bearer_and_cross_owner_download(tmp_path):
    with JobService(tmp_path) as service:
        with TestClient(create_app(service, backend_token="server-secret")) as client:
            assert client.get("/api/jobs").status_code == 401
            alice = {"Authorization": "Bearer server-secret", "X-P2P-Owner": "a" * 64}
            bob = {"Authorization": "Bearer server-secret", "X-P2P-Owner": "b" * 64}
            data = trimesh.creation.box().export(file_type="stl")
            response = client.post(
                "/api/jobs",
                headers=alice,
                files={"file": ("dog.stl", data)},
                data={"size_mm": 20, "voxel_mm": 0.5},
            )
            assert response.status_code == 202
            identifier = response.json()["id"]
            assert client.get(f"/api/jobs/{identifier}", headers=bob).status_code == 404
            assert (
                client.get(f"/api/jobs/{identifier}/files/model.stl", headers=bob).status_code
                == 404
            )
            assert client.get("/api/jobs", headers=bob).json() == []
