# Photo to print workflow

**Scope update:** The user subsequently requested a token-protected hosted website.
The local-only scope and missing-credential assumptions below describe the initial
design, not the current deployment. Modal login is complete; a verified pinned
DINOv3 mirror is baked into the GPU image. README.md and CHECKPOINT.md record
the implemented hosted design and the remaining real photo inference test.

Extend the existing CPU print processor into a local browser workflow. The
user selects a pet photo, chooses physical size, starts one job and downloads
STL/3MF plus a report and a texture-free GLB preview. Existing meshes remain a
first-class input and do not require Modal. Bind only to loopback; no hosted
shop, authentication service, checkout or public deployment is requested.

## Approach

The implementer chooses a small FastAPI app with packaged HTML/CSS/JS over a
CLI-only wrapper because the requested dog-photo workflow should not require
manual intermediate commands. Keep generation, job orchestration, geometry
repair and UI separate, so a future shop can reuse the same job function.
Use the user's existing Modal approach and weights volume
`darkfantasy-trellis2-weights`, discovered from their prior Trellis chat.

Modal runs pinned official TRELLIS.2 shape inference on one A100-80GB GPU.
Load shape models only and never invoke texture sampling, baking or GLB
postprocessing. Preserve raw PLY. Use U2Net via rembg for background removal
instead of the default BRIA background-removal model. The official DINOv3
encoder still requires the user's appropriate Hugging Face access.

No Modal configuration or HF credentials exist on this computer. Provide
in-app connection/setup, check prerequisites before accepting a billable photo
job, and report that real GPU validation requires these credentials. Do not
substitute a fake generator. Tests may inject a generator while exercising real
CPU repair, exports and HTTP downloads; label that evidence accurately.

## Job contract

Persistent UUID job directories, atomic job JSON, one worker, bounded queue.
Stages: queued, generating, repairing, ready, failed, interrupted. Uploads
limited to 25 MB and images to 20 million pixels; validate decoded images and
finite bounded numeric settings before generation. Reject duplicate submission
while busy in the UI; no automatic GPU retries. Store raw mesh and allow a
repair-only retry. Startup marks unfinished previous jobs interrupted.

Publish final files only after existing geometry validation. Always retain
review_required; separate parts and deformation must remain visible. ZIP has
print files, preview, manifest and concise slicer instructions, not the private
input photo. Downloads use an artifact allowlist and validated job IDs.
Show safe user errors; retain detailed logs locally. Local write routes reject
cross-origin requests; host is loopback and trusted-host validation is enabled.

A Windows launcher creates an isolated environment, installs the package,
starts the loopback app and opens it in a browser. Existing CLI remains
compatible. No credentials committed, returned by health endpoints or logged.
