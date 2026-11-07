"""Small stdlib-only writer usable inside Blender's bundled interpreter."""

import re
from pathlib import Path


def write_native_snapshot(directory, stage_id, writer, suffix=".ply"):
    if not directory:
        return
    if not re.fullmatch(r"[a-z-]+", stage_id) or suffix not in {".ply", ".npz"}:
        raise ValueError("Invalid snapshot name")
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (stage_id + suffix)
    temporary = folder / (stage_id + ".tmp" + suffix)
    writer(temporary)
    temporary.replace(target)
