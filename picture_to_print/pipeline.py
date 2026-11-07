"""Synchronous worker contract usable from a CLI or a future shop queue."""

import hashlib
import json
import logging
import math
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import trimesh

from .geometry import describe, load_geometry, remove_enclosed_shells, surface_deviation, write_3mf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrintSettings:
    size_mm: float = 100.0
    voxel_mm: float = 0.4
    timeout_seconds: float = 300.0
    backend: str = "meshlib"
    strip_hidden_faces: bool = True

    def __post_init__(self):
        for name in ("size_mm", "voxel_mm", "timeout_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.backend not in {"meshlib", "blender"}:
            raise ValueError("backend must be meshlib or blender")


def save_manifest(output: Path, manifest: dict) -> None:
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output / "manifest.json")


def execute_worker(command, log_path, timeout):
    with log_path.open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        ) as process:
            try:
                returncode = process.wait(timeout=timeout)
            except BaseException:
                # Windows venv executables launch another interpreter. Killing
                # only the launcher leaves native repair running with a locked log.
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
                raise
            if returncode:
                raise subprocess.CalledProcessError(returncode, command)


def run_blender(mesh, settings, blender, workspace):
    source = workspace / "input.npz"
    result = workspace / "repaired.npz"
    metrics = workspace / "repair.json"
    np.savez(source, vertices=mesh.vertices, faces=mesh.faces)
    config = workspace / "job.json"
    config.write_text(
        json.dumps(
            {
                "input": str(source),
                "output": str(result),
                "metrics": str(metrics),
                "voxel_mm": settings.voxel_mm,
            }
        ),
        encoding="utf-8",
    )
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--threads",
        "4",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(__file__).with_name("blender_worker.py")),
        "--",
        str(config),
    ]
    log_path = workspace / "blender.log"
    try:
        execute_worker(command, log_path, settings.timeout_seconds)
    except (OSError, subprocess.SubprocessError) as error:
        tail = (
            log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            if log_path.exists()
            else ""
        )
        raise RuntimeError(f"Blender repair failed: {error}\n{tail}") from error
    with np.load(result) as data:
        repaired = trimesh.Trimesh(vertices=data["vertices"], faces=data["faces"], process=True)
    return repaired, json.loads(metrics.read_text(encoding="utf-8"))


def run_meshlib(mesh, settings, workspace):
    source = workspace / "input.ply"
    target = workspace / "repaired.stl"
    metrics = workspace / "repair.json"
    mesh.export(source)
    config = workspace / "job.json"
    config.write_text(
        json.dumps(
            {
                "input": str(source),
                "output": str(target),
                "metrics": str(metrics),
                "voxel_mm": settings.voxel_mm,
                "strip_hidden_faces": settings.strip_hidden_faces,
            }
        ),
        encoding="utf-8",
    )
    command = [sys.executable, str(Path(__file__).with_name("meshlib_worker.py")), str(config)]
    log_path = workspace / "meshlib.log"
    try:
        execute_worker(command, log_path, settings.timeout_seconds)
    except (OSError, subprocess.SubprocessError) as error:
        tail = (
            log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            if log_path.exists()
            else ""
        )
        raise RuntimeError(f"MeshLib repair failed: {error}\n{tail}") from error
    return trimesh.load_mesh(target, process=True), json.loads(metrics.read_text(encoding="utf-8"))


def prepare_model(source: Path, output: Path, settings: PrintSettings, blender="blender") -> dict:
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(f"Use a new job output directory: {output}")
    mesh = load_geometry(source)
    logger.info("Loaded %s: %d triangles", source.name, len(mesh.faces))
    # Native backends use float32. Normalize in float64 before scaling so a
    # distant scene origin cannot erase millimeter detail during conversion.
    mesh.apply_translation(-mesh.bounds.mean(axis=0))
    mesh.apply_scale(settings.size_mm / mesh.extents.max())
    grid_cells = math.prod(math.ceil(float(size) / settings.voxel_mm) + 6 for size in mesh.extents)
    if grid_cells > 150_000_000:
        raise ValueError(
            f"Estimated voxel grid {grid_cells:,} exceeds 150 million; increase --voxel-mm"
        )
    if settings.voxel_mm >= float(mesh.extents.max()) / 4:
        raise ValueError("voxel size must be smaller than one quarter of the model size")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "backend": settings.backend,
        "status": "rejected",
        "review_required": True,
        "review_reasons": ["visual_comparison", "wall_thickness_and_supports"],
        "created_at": datetime.now(UTC).isoformat(),
        "settings": asdict(settings),
        "input_geometry": describe(mesh),
        "artifacts": {},
    }
    with source.open("rb") as stream:
        manifest["source_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    try:
        with tempfile.TemporaryDirectory(prefix="print-", dir=output) as temporary:
            workspace = Path(temporary)
            removed_before = 0
            if settings.backend == "blender":
                mesh, removed_before = remove_enclosed_shells(mesh)
            logger.info(
                "Removed %d enclosed shells; reconstructing with %s",
                removed_before,
                settings.backend,
            )
            reference = mesh.copy()
            if settings.backend == "meshlib":
                mesh, repair = run_meshlib(mesh, settings, workspace)
            else:
                mesh, repair = run_blender(mesh, settings, blender, workspace)
            removed_after = 0
            if settings.backend == "blender":
                mesh, removed_after = remove_enclosed_shells(mesh)
            logger.info(
                "Removed %d enclosed shells in total; measuring surface change",
                removed_before + removed_after + repair.get("enclosed_shells_removed", 0),
            )
            repair["enclosed_shells_removed"] = (
                repair.get("enclosed_shells_removed", 0) + removed_before + removed_after
            )
            repair["boundary_edges_before"] = manifest["input_geometry"]["boundary_edges"]
            if not len(mesh.vertices):
                raise ValueError("Repair produced empty geometry; use a finer voxel size")
            deviation = surface_deviation(reference, mesh)
            manifest["surface_deviation"] = deviation
            if deviation["sampled_p95_mm"] > settings.voxel_mm * 2:
                manifest["review_reasons"].append("large_surface_change")
            # Put the model on z=0 without changing its chosen physical size.
            mesh.apply_translation(
                [-mesh.bounds.mean(axis=0)[0], -mesh.bounds.mean(axis=0)[1], -mesh.bounds[0, 2]]
            )
            stl = workspace / "model.stl"
            mesh.export(stl)
            exported = trimesh.load_mesh(stl, process=True)
            geometry = describe(exported)
            manifest.update(repair=repair, geometry=geometry)
            if not geometry["positive_volume"] or geometry["nonmanifold_edges"]:
                raise ValueError("Export does not represent closed, consistently oriented solids")
            if repair["self_intersections_after_remesh"]:
                raise ValueError("Voxel remesh still contains self-intersections")
            if geometry["components"] > 1:
                manifest["review_reasons"].append("separate_parts")
            write_3mf(exported, workspace / "model.3mf")
            for name in ("model.stl", "model.3mf"):
                (workspace / name).replace(output / name)
            manifest["status"] = "geometry_ready"
            manifest["artifacts"] = {"stl": "model.stl", "3mf": "model.3mf"}
    except Exception as error:
        for name in ("model.stl", "model.3mf"):
            (output / name).unlink(missing_ok=True)
        manifest["error"] = str(error)
        save_manifest(output, manifest)
        raise
    save_manifest(output, manifest)
    return manifest
