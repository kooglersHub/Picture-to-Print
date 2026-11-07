"""Hook immediately after pipeline.run(image)[0], before to_glb()."""

from pathlib import Path

import numpy as np
import trimesh


def as_numpy(value):
    # Duck typing keeps PyTorch and GPU dependencies out of CPU print workers.
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def export_raw_mesh(mesh, target: Path) -> Path:
    target = Path(target)
    if target.suffix.lower() != ".ply":
        raise ValueError("Raw geometry must be saved as PLY")
    geometry = trimesh.Trimesh(
        vertices=as_numpy(mesh.vertices), faces=as_numpy(mesh.faces), process=False
    )
    data = geometry.export(file_type="ply")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    return target
