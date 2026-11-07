"""Immutable diagnostic snapshots, separate from validated print artifacts."""

import json
import math
from pathlib import Path
from threading import RLock

import numpy as np
import trimesh

from .snapshots import write_native_snapshot

STEPS = {
    "input": ("Originalfoto", "Das hochgeladene Foto ohne Bildbearbeitung."),
    "foreground": ("Freistellung", "Tatsächliche U2Net-Ausgabe mit transparentem Hintergrund."),
    "generation-input": (
        "TRELLIS-Eingabebild",
        "Tatsächlicher Zuschnitt nach TRELLIS-Vorverarbeitung.",
    ),
    "raw": (
        "TRELLIS-Rohmesh",
        "Geometrie vor jeder Reparatur; nur Größe und Lage für den Vergleich vereinheitlicht.",
    ),
    "prepared": (
        "Vorbereitung",
        "Doppelte und degenerierte Flächen bereinigt, Punkte zusammengeführt und auf Zielgröße skaliert.",
    ),
    "pre-shells": (
        "Innenhüllen vorab entfernt",
        "Blender-Pfad: eingeschlossene Teilhüllen vor dem Remeshing entfernt.",
    ),
    "native-import": (
        "Werkzeug-Import",
        "Mesh direkt nach dem Einlesen im gewählten Reparaturwerkzeug.",
    ),
    "visible": (
        "Sichtbarkeitsfilter",
        "MeshLib: aus 26 Richtungen verdeckte Flächen entfernt. Hier können Details verloren gehen.",
    ),
    "pre-capped": (
        "Randlöcher gefüllt",
        "Blender: offene Ränder vor der Volumenrekonstruktion geschlossen.",
    ),
    "remeshed": (
        "Voxel-Rekonstruktion",
        "Oberfläche aus dem Volumenraster neu erzeugt, noch vor nachträglichen Korrekturen.",
    ),
    "capped": (
        "Restöffnungen geschlossen",
        "MeshLib: verbleibende Randöffnungen nach dem Remeshing geschlossen.",
    ),
    "no-cavities": ("Innenhüllen entfernt", "Eingeschlossene Hüllen nach dem Remeshing entfernt."),
    "oriented": (
        "Orientierung korrigiert",
        "Flächenorientierung für die einzelnen Teilkörper vereinheitlicht.",
    ),
    "exported": (
        "STL-Export",
        "Exportierte und erneut eingelesene Geometrie. Druckfreigabe hängt vom Auftragsstatus ab.",
    ),
}
IMAGE_IDS = {"input", "foreground", "generation-input"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def read_stages(directory):
    file = Path(directory) / "index.json"
    return json.loads(file.read_text(encoding="utf-8")) if file.is_file() else []


def mesh_metrics(mesh):
    edge_use = np.bincount(mesh.edges_unique_inverse)
    labels = trimesh.graph.connected_component_labels(
        mesh.face_adjacency, node_count=len(mesh.faces)
    )
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.faces),
        "boundary_edges": int(np.count_nonzero(edge_use == 1)),
        "nonmanifold_edges": int(np.count_nonzero(edge_use != 2)),
        "components": int(labels.max() + 1) if len(labels) else 0,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_mm3": float(mesh.volume),
        "dimensions_mm": mesh.extents.tolist(),
    }


def preview_mesh(mesh):
    preview = mesh.copy()
    preview.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    # A constant material gives every phase identical lighting without adding
    # texture images or duplicating every vertex to attach per-face colors.
    preview.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=[104, 122, 111, 255], metallicFactor=0, roughnessFactor=0.85
        )
    )
    return preview


class StageRecorder:
    def __init__(self, directory, size_mm, lock=None, commit=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.size_mm = size_mm
        self.lock = lock or RLock()
        self.commit = commit or (lambda: None)

    def _register(self, entry):
        with self.lock:
            rows = [row for row in read_stages(self.directory) if row["id"] != entry["id"]]
            rows.append(entry)
            order = list(STEPS)
            rows.sort(key=lambda row: order.index(row["id"]))
            target = self.directory / "index.json"
            temporary = self.directory / "index.tmp"
            temporary.write_text(json.dumps(rows, allow_nan=False), encoding="utf-8")
            temporary.replace(target)
            self.commit()

    def _entry(self, stage_id, kind, filename, metrics=None):
        label, description = STEPS[stage_id]
        return {
            "id": stage_id,
            "label": label,
            "description": description,
            "kind": kind,
            "status": "available",
            "preview_file": filename,
            "download_file": filename,
            "metrics": metrics,
            "bytes": (self.directory / filename).stat().st_size,
        }

    def image(self, stage_id, data, suffix=".png"):
        if stage_id not in IMAGE_IDS or suffix not in IMAGE_SUFFIXES:
            raise ValueError("Unknown image stage")
        filename = stage_id + suffix
        temporary = self.directory / (filename + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(self.directory / filename)
        self._register(self._entry(stage_id, "image", filename))

    def mesh(self, stage_id, mesh):
        if stage_id not in STEPS or stage_id in IMAGE_IDS:
            raise ValueError("Unknown mesh stage")
        write_native_snapshot(
            self.directory, stage_id, lambda file: mesh.export(file, file_type="ply")
        )
        metrics = mesh_metrics(mesh)
        filename = stage_id + ".glb"
        temporary = self.directory / (filename + ".tmp")
        temporary.write_bytes(preview_mesh(mesh).export(file_type="glb"))
        temporary.replace(self.directory / filename)
        entry = self._entry(stage_id, "mesh", filename, metrics)
        entry["download_file"] = stage_id + ".ply"
        self._register(entry)

    def import_snapshots(self):
        captured = {row["id"] for row in read_stages(self.directory)}
        for stage_id in STEPS:
            file = self.directory / (stage_id + ".ply")
            arrays = self.directory / (stage_id + ".npz")
            if stage_id in captured:
                continue
            if file.is_file():
                mesh = trimesh.load_mesh(file, process=False, skip_materials=True)
            elif arrays.is_file():
                with np.load(arrays) as data:
                    mesh = trimesh.Trimesh(
                        vertices=data["vertices"], faces=data["faces"], process=False
                    )
            else:
                continue
            self.mesh(stage_id, mesh)
