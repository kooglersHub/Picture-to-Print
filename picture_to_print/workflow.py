"""Persistent jobs shared by local execution and the Modal job dispatcher."""

import hashlib
import json
import re
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

import trimesh

from .pipeline import PrintSettings, prepare_model

ARTIFACTS = {"model.stl", "model.3mf", "manifest.json", "preview.glb", "result.zip"}
TERMINAL = {"ready", "failed", "interrupted"}


class JobService:
    def __init__(
        self,
        root,
        generator=None,
        readiness=None,
        dispatcher=None,
        refresh=None,
        commit=None,
        recover=True,
        call_status=None,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.generator = generator
        self.readiness = readiness or (lambda: {"modal": False, "hf": False})
        self.dispatcher = dispatcher
        self.refresh = refresh or (lambda: None)
        self.commit = commit or (lambda: None)
        self.call_status = call_status
        self.lock = RLock()
        self.executor = ThreadPoolExecutor(max_workers=1) if dispatcher is None else None
        if recover:
            for file in self.root.glob("*/job.json"):
                job = json.loads(file.read_text(encoding="utf-8"))
                if job.get("status") not in TERMINAL:
                    job.update(
                        status="interrupted",
                        error="Der Dienst wurde neu gestartet. Das Rohmodell kann erneut aufbereitet werden.",
                    )
                    self._save(job)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=True)

    def folder(self, job_id):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise KeyError("Unknown job")
        return self.root / job_id

    def _read_job(self, job_id):
        try:
            job = json.loads((self.folder(job_id) / "job.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError) as error:
            raise KeyError("Unknown job") from error
        return job

    def get(self, job_id, owner=None):
        job = self._read_job(job_id)
        if owner is not None and job.get("owner", "local") != owner:
            raise KeyError("Unknown job")
        dispatch = self.folder(job_id) / "dispatch.json"
        if self.call_status and job["status"] not in TERMINAL and dispatch.is_file():
            call_id = json.loads(dispatch.read_text(encoding="utf-8"))["call_id"]
            state = self.call_status(call_id)
            if state in {"completed", "failed"}:
                # A finished call may have committed its final JSON after the
                # HTTP request's initial volume snapshot. Re-read before repair.
                self.refresh()
                job = self._read_job(job_id)
                if job["status"] not in TERMINAL:
                    job.update(
                        status="interrupted",
                        can_retry_repair=(self.folder(job_id) / "raw.ply").is_file(),
                        error="Die Cloud-Verarbeitung wurde beendet. Ein vorhandenes Rohmodell kann erneut aufbereitet werden.",
                    )
                    self._save(job)
        return job

    def list(self, owner="local"):
        jobs = [self.get(file.parent.name) for file in self.root.glob("*/job.json")]
        return sorted(
            [job for job in jobs if job.get("owner", "local") == owner],
            key=lambda job: job.get("created_at", ""),
            reverse=True,
        )[:50]

    def _save(self, job):
        target = self.folder(job["id"]) / "job.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(target)
        self.commit()

    def _update(self, job_id, **values):
        with self.lock:
            job = self.get(job_id)
            job.update(values)
            job["updated_at"] = datetime.now(UTC).isoformat()
            self._save(job)
            return job

    def submit(self, name, data, settings, resolution=512, seed=42, owner="local", retry_from=None):
        with self.lock:
            if sum(job["status"] not in TERMINAL for job in self.list(owner)) >= 3:
                raise ValueError("Es sind bereits drei Aufträge aktiv. Bitte warten.")
            job_id = uuid4().hex
            folder = self.folder(job_id)
            folder.mkdir()
            suffix = Path(name).suffix.lower()
            source = folder / ("input" + suffix)
            source.write_bytes(data)
            if retry_from:
                shutil.copyfile(self.folder(retry_from) / "raw.ply", folder / "raw.ply")
            job = {
                "id": job_id,
                "owner": owner,
                "name": Path(name).name,
                "created_at": datetime.now(UTC).isoformat(),
                "status": "queued",
                "input_file": source.name,
                "input_sha256": hashlib.sha256(data).hexdigest(),
                "settings": asdict(settings),
                "resolution": resolution,
                "seed": seed,
                "review_required": True,
                "artifacts": {},
                "can_retry_repair": bool(retry_from),
            }
            self._save(job)
            if self.dispatcher:
                try:
                    call = self.dispatcher(job_id)
                    if call is not None and hasattr(call, "object_id"):
                        (folder / "dispatch.json").write_text(
                            json.dumps({"call_id": call.object_id}), encoding="utf-8"
                        )
                        self.commit()
                except Exception as error:
                    (folder / "error.log").write_text(
                        f"{type(error).__name__}: {error}", encoding="utf-8"
                    )
                    job = self._update(
                        job_id,
                        status="failed",
                        error="Der Cloud-Auftrag konnte nicht gestartet werden. Bitte später erneut versuchen.",
                    )
            else:
                self.executor.submit(self.run_one, job_id)
            return job

    def retry(self, job_id, settings, owner="local"):
        job = self.get(job_id, owner)
        raw = self.folder(job_id) / "raw.ply"
        if not raw.is_file() or job["status"] not in TERMINAL:
            raise ValueError("Für diesen Auftrag ist noch kein Rohmodell verfügbar.")
        return self.submit(
            "raw.ply",
            raw.read_bytes(),
            settings,
            job["resolution"],
            job["seed"],
            owner,
            retry_from=job_id,
        )

    def run_one(self, job_id):
        job = self.get(job_id)
        folder = self.folder(job_id)
        raw = folder / "raw.ply"
        try:
            if not raw.exists():
                source = folder / job["input_file"]
                if source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    self._update(job_id, status="generating")
                    if not self.generator:
                        raise RuntimeError("No image generator configured")
                    metadata = self.generator(
                        source, raw, job["resolution"], job["seed"], folder / "generation.log"
                    )
                    self._update(job_id, generation=metadata, can_retry_repair=True)
                else:
                    mesh = trimesh.load_scene(source, skip_materials=True).to_mesh()
                    mesh.export(raw)
                    self._update(job_id, can_retry_repair=True)
                self.commit()
            self._update(job_id, status="repairing")
            result = prepare_model(raw, folder / "print", PrintSettings(**job["settings"]))
            mesh = trimesh.load_mesh(folder / "print/model.stl")
            # Center the preview only; print units and placement stay unchanged.
            mesh.apply_translation(-mesh.bounds.mean(axis=0))
            mesh.export(folder / "print/preview.glb")
            instructions = (
                "Die Geometrieprüfungen wurden bestanden. Vor dem Druck Slicer-Schichten, "
                "Wandstärken, getrennte Teile und Stützen prüfen. 3MF verwendet Millimeter. "
                "Keine automatische Produktionsfreigabe.\n"
            )
            with zipfile.ZipFile(folder / "print/result.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(ARTIFACTS - {"result.zip"}):
                    archive.write(folder / "print" / name, name)
                archive.writestr("DRUCKHINWEISE.txt", instructions)
            self._update(
                job_id,
                status="ready",
                geometry=result["geometry"],
                review_reasons=result["review_reasons"],
                surface_deviation=result["surface_deviation"],
                artifacts={name: f"/api/jobs/{job_id}/files/{name}" for name in ARTIFACTS},
            )
        except Exception as error:
            with (folder / "error.log").open("a", encoding="utf-8") as log:
                log.write(f"{type(error).__name__}: {error}\n")
            self._update(
                job_id,
                status="failed",
                can_retry_repair=raw.is_file(),
                error=(
                    "Die Verarbeitung ist fehlgeschlagen. Falls ein Rohmodell vorhanden ist, "
                    "kannst du nur die Druckaufbereitung erneut starten. Details stehen im lokalen Auftragsprotokoll."
                ),
            )
