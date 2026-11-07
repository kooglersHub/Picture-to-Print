"""Local CLI; the same prepare_model function can run inside a job worker."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .pipeline import PrintSettings, prepare_model


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Reconstruct texture-free print geometry from a Trellis mesh"
    )
    parser.add_argument("source", type=Path, help="GLB, STL, OBJ or raw PLY")
    parser.add_argument("--output", required=True, type=Path, help="New per-job output directory")
    parser.add_argument(
        "--size-mm",
        type=float,
        default=100,
        help="Target longest dimension, not height (default 100)",
    )
    parser.add_argument(
        "--voxel-mm", type=float, default=0.4, help="Smaller retains detail, uses more RAM"
    )
    parser.add_argument("--timeout-seconds", type=float, default=300)
    parser.add_argument("--backend", choices=("meshlib", "blender"), default="meshlib")
    parser.add_argument("--blender", default=os.environ.get("BLENDER_BIN", "blender"))
    parser.add_argument(
        "--keep-hidden-faces",
        action="store_true",
        help="Disable sampled hidden-face stripping for MeshLib",
    )
    args = parser.parse_args()
    try:
        settings = PrintSettings(
            size_mm=args.size_mm,
            voxel_mm=args.voxel_mm,
            timeout_seconds=args.timeout_seconds,
            backend=args.backend,
            strip_hidden_faces=not args.keep_hidden_faces,
        )
        result = prepare_model(args.source, args.output, settings, args.blender)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Print preparation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
