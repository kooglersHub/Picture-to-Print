"""Deployable CPU website backend, independent of GPU image builds."""

import os

import modal

from picture_to_print.modal_app import cpu_image, jobs, runtime_secret

app = modal.App("picture-to-print-web")


def call_status(identifier):
    try:
        modal.FunctionCall.from_id(identifier).get(timeout=0)
        return "completed"
    except (
        modal.exception.FunctionTimeoutError,
        modal.exception.ExecutionError,
        modal.exception.RemoteError,
        modal.exception.NotFoundError,
        modal.exception.OutputExpiredError,
    ):
        return "failed"
    except modal.exception.TimeoutError:
        return "running"
    except Exception:
        # A transient control-plane outage does not establish worker failure.
        return "unknown"


@app.function(
    image=cpu_image,
    volumes={"/data": jobs},
    timeout=3600,
    cpu=4,
    memory=16384,
    max_containers=1,
    retries=0,
)
def process_job(job_id: str):
    from picture_to_print.workflow import JobService

    jobs.reload()

    def generator(source, raw, resolution, seed, log):
        function = modal.Function.from_name("picture-to-print", "generate_geometry")
        data, metadata = function.remote(source.read_bytes(), resolution, seed)
        raw.write_bytes(data)
        return metadata

    service = JobService(
        "/data/jobs",
        generator=generator,
        dispatcher=lambda _: None,
        commit=jobs.commit,
        recover=False,
    )
    service.run_one(job_id)


@app.function(
    image=cpu_image,
    volumes={"/data": jobs},
    secrets=[runtime_secret],
    cpu=1,
    memory=2048,
    timeout=300,
    max_containers=1,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def web():
    from picture_to_print.web import create_app
    from picture_to_print.workflow import JobService

    service = JobService(
        "/data/jobs",
        dispatcher=lambda identifier: process_job.spawn(identifier),
        readiness=lambda: {"modal": True, "hf": False},
        refresh=jobs.reload,
        commit=jobs.commit,
        recover=False,
        call_status=call_status,
    )
    return create_app(service, backend_token=os.environ["P2P_BACKEND_TOKEN"])
