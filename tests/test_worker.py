import subprocess
import sys

import pytest

from picture_to_print.pipeline import execute_worker


def test_timeout_stops_descendants_and_releases_log(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(60)\n")
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable, sys.argv[1]])\n"
        "time.sleep(60)\n"
    )
    log = tmp_path / "worker.log"
    with pytest.raises(subprocess.TimeoutExpired):
        execute_worker([sys.executable, str(parent), str(child)], log, 1.0)
    # On Windows a surviving descendant keeps the inherited log locked.
    log.unlink()
