from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from threading import Event

from picture_to_print.pipeline import PrintSettings
from picture_to_print.workflow import JobService


def test_status_reader_cannot_block_atomic_status_replacement(tmp_path, monkeypatch):
    opened = Event()
    release = Event()
    writer_started = Event()
    original_read = Path.read_text
    with JobService(tmp_path, dispatcher=lambda _: None) as service:
        job = service.submit("cube.ply", b"source", PrintSettings())
        target = service.folder(job["id"]) / "job.json"

        def slow_read(path, *args, **kwargs):
            if path != target:
                return original_read(path, *args, **kwargs)
            # A Windows reader holds a non-delete-sharing handle until close.
            with path.open("r", encoding="utf-8") as stream:
                text = stream.read()
                opened.set()
                assert release.wait(10)
                return text

        def write_status():
            writer_started.set()
            service._save({**job, "status": "ready"})

        monkeypatch.setattr(Path, "read_text", slow_read)
        with ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(service.get, job["id"])
            assert opened.wait(10)
            writer = pool.submit(write_status)
            assert writer_started.wait(10)
            try:
                # The writer must wait for the read handle to close on Windows.
                wait([writer], timeout=0.1)
            finally:
                release.set()
            reader.result(timeout=10)
            writer.result(timeout=10)
        assert service.get(job["id"])["status"] == "ready"
