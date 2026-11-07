"""HTTP adapter. Hosted requests require the private edge-to-worker bearer."""

import hmac
import io
import math
import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, UnidentifiedImageError

from .pipeline import PrintSettings
from .workflow import ARTIFACTS

MAX_UPLOAD = 25_000_000
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
MESHES = {".glb", ".stl", ".obj", ".ply"}


class UploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = MAX_UPLOAD + 100001
        if declared > MAX_UPLOAD + 100000:
            return await JSONResponse({"detail": "Datei ist zu groß"}, 413)(scope, receive, send)
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > MAX_UPLOAD + 100000:
                raise HTTPException(413, "Datei ist zu groß")
            return message

        return await self.app(scope, limited_receive, send)


def create_app(service, backend_token=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(UploadLimit)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if backend_token:
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, "Bearer " + backend_token):
                return JSONResponse({"detail": "Zugriff verweigert"}, 401)
            owner = request.headers.get("x-p2p-owner", "")
            if not re.fullmatch(r"[0-9a-f]{64}", owner):
                return JSONResponse({"detail": "Ungültige Sitzung"}, 401)
            request.state.owner = owner
        else:
            if request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}:
                return JSONResponse({"detail": "Nur lokaler Zugriff erlaubt"}, 403)
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Fremder Ursprung nicht erlaubt"}, 403)
            request.state.owner = "local"
        try:
            with service.lock:
                service.refresh()
            return await call_next(request)
        except KeyError:
            return JSONResponse({"detail": "Auftrag nicht gefunden"}, 404)

    @app.get("/api/health")
    def health():
        return {
            "ready": True,
            "generation": service.readiness(),
            "repair_tools": service.repair_tools(),
            "review_required": True,
        }

    @app.get("/api/jobs")
    def jobs(request: Request):
        with service.lock:
            return service.list(request.state.owner)

    def settings(size_mm, voxel_mm, backend):
        try:
            value = PrintSettings(
                size_mm=size_mm, voxel_mm=voxel_mm, timeout_seconds=600, backend=backend
            )
            if not 10 <= size_mm <= 500 or not 0.05 <= voxel_mm <= 2:
                raise ValueError("Größe oder Auflösung außerhalb des erlaubten Bereichs")
            if (math.ceil(size_mm / voxel_mm) + 6) ** 3 > 150_000_000:
                raise ValueError(
                    "Diese Kombination braucht zu viel Speicher. Gröbere Auflösung wählen."
                )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

        if not service.repair_tools().get(backend):
            raise HTTPException(412, "Das gewählte Reparaturwerkzeug ist nicht verfügbar")
        return value

    @app.post("/api/jobs", status_code=202)
    async def submit(
        request: Request,
        file: UploadFile = File(...),
        size_mm: float = Form(100),
        voxel_mm: float = Form(0.4),
        resolution: int = Form(512),
        seed: int = Form(42),
        backend: str = Form("meshlib"),
    ):
        options = settings(size_mm, voxel_mm, backend)
        if resolution not in {512, 1024} or not 0 <= seed < 2**31:
            raise HTTPException(422, "Ungültige Generierungseinstellungen")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in IMAGES | MESHES:
            raise HTTPException(422, "Bitte ein Foto oder GLB/STL/OBJ/PLY auswählen")
        data = await file.read(MAX_UPLOAD + 1)
        await file.close()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Die Datei darf höchstens 25 MB groß sein")
        if not data:
            raise HTTPException(422, "Die Datei ist leer")
        if suffix in IMAGES:
            try:
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 20_000_000 or min(image.size) < 128:
                        raise ValueError(
                            "Bildauflösung muss zwischen 128 Pixeln und 20 Megapixeln liegen"
                        )
                    image.verify()
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                Image.DecompressionBombError,
            ) as error:
                raise HTTPException(422, "Das Foto ist ungültig oder zu groß") from error
            ready = service.readiness()
            if not ready.get("modal"):
                raise HTTPException(412, "Die GPU-Verbindung ist noch nicht eingerichtet")
        with service.lock:
            try:
                return service.submit(
                    file.filename, data, options, resolution, seed, request.state.owner
                )
            except ValueError as error:
                raise HTTPException(429, str(error)) from error

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, request: Request):
        with service.lock:
            return service.get(job_id, request.state.owner)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry(
        job_id: str,
        request: Request,
        size_mm: float = Form(100),
        voxel_mm: float = Form(0.4),
        backend: str = Form("meshlib"),
    ):
        options = settings(size_mm, voxel_mm, backend)
        with service.lock:
            try:
                return service.retry(job_id, options, request.state.owner)
            except ValueError as error:
                raise HTTPException(409, str(error)) from error

    @app.get("/api/jobs/{job_id}/files/{name}")
    def download(job_id: str, name: str, request: Request):
        with service.lock:
            job = service.get(job_id, request.state.owner)
            if name not in ARTIFACTS or job["status"] != "ready":
                raise HTTPException(404, "Datei nicht verfügbar")
            file = service.folder(job_id) / "print" / name
            if not file.is_file():
                raise HTTPException(404, "Datei nicht verfügbar")
            # Volume.reload cannot run while a streamed file remains open.
            data = file.read_bytes()
        mime = {
            "preview.glb": "model/gltf-binary",
            "manifest.json": "application/json",
            "result.zip": "application/zip",
        }.get(name, "application/octet-stream")
        return Response(
            data,
            media_type=mime,
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="{name}"',
            },
        )

    return app
