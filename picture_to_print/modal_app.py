"""Deploy the private HTTP backend and durable print jobs with Modal."""

from pathlib import Path

import modal

PACKAGE = Path(__file__).parent
APP_NAME = "picture-to-print"
TRELLIS_REF = "75fbf0183001ed9876c8dbb35de6b68552ee08bd"
app = modal.App(APP_NAME)
weights = modal.Volume.from_name("darkfantasy-trellis2-weights", create_if_missing=True)
jobs = modal.Volume.from_name("picture-to-print-jobs", create_if_missing=True)
runtime_secret = modal.Secret.from_name("picture-to-print-runtime")

cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("blender")
    .pip_install(
        "numpy>=1.26,<3",
        "trimesh==5.2.0",
        "scipy>=1.11,<2",
        "rtree>=1.4,<2",
        "meshlib==3.1.4.297",
        "fastapi>=0.115,<1",
        "python-multipart>=0.0.20",
        "pillow>=11,<14",
    )
    .env({"PYTHONPATH": "/root", "OMP_NUM_THREADS": "4"})
    .add_local_dir(str(PACKAGE), "/root/picture_to_print", ignore=["__pycache__"])
)

gpu_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .entrypoint([])
    .apt_install(
        "build-essential", "git", "libgl1", "libglib2.0-0", "libjpeg-dev", "zlib1g-dev", "ffmpeg"
    )
    .pip_install(
        "torch==2.6.0", "torchvision==0.21.0", index_url="https://download.pytorch.org/whl/cu124"
    )
    .pip_install(
        "setuptools>=64",
        "wheel",
        "ninja",
        "cmake>=3.30",
        "imageio",
        "imageio-ffmpeg",
        "tqdm",
        "easydict",
        "opencv-python-headless",
        "trimesh==5.2.0",
        "scipy",
        "rtree",
        "transformers==4.57.5",
        "huggingface-hub>=0.34,<1",
        "kornia",
        "timm",
        "zstandard",
        "xformers==0.0.29.post3",
        "rembg[cpu]==2.0.69",
    )
    .run_commands(
        f"git clone --recursive https://github.com/microsoft/TRELLIS.2.git /opt/trellis && cd /opt/trellis && git checkout {TRELLIS_REF}",
        "python -m pip install git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8",
        "git clone --recursive https://github.com/JeffreyXiang/CuMesh.git /opt/cumesh && cd /opt/cumesh && git checkout 12289e1062f0603f2f0d0771b02e1395d247f26f && git submodule update --init --recursive",
        "git clone --recursive https://github.com/JeffreyXiang/FlexGEMM.git /opt/flexgemm && cd /opt/flexgemm && git checkout 6dd94a859c26ee8246888502eada3dd8ad85532e && git submodule update --init --recursive",
        "git clone -b v0.4.0 https://github.com/NVlabs/nvdiffrast.git /opt/nvdiffrast",
    )
    .apt_install("clang")
    .run_commands(
        "python -m pip install /opt/cumesh --no-build-isolation",
        "python -m pip install /opt/flexgemm --no-build-isolation",
        "python -m pip install /opt/trellis/o-voxel --no-build-isolation --no-deps",
        "python -m pip install /opt/nvdiffrast --no-build-isolation",
        gpu="A100-80GB",
        env={"TORCH_CUDA_ARCH_LIST": "8.0", "MAX_JOBS": "4", "CC": "gcc", "CXX": "g++"},
    )
    .run_commands(
        "python -c \"from huggingface_hub import snapshot_download; snapshot_download('camenduru/dinov3-vitl16-pretrain-lvd1689m', revision='3c276edd87d6f6e569ff0c4400e086807d0f3881', local_dir='/opt/dinov3')\"",
        'echo "dcb2e45127cccbf1601e5f42fef165eea275c8e5213197e8dcf3f48822718179  /opt/dinov3/model.safetensors" | sha256sum -c -',
    )
    .env(
        {
            "PYTHONPATH": "/root:/opt/trellis",
            "HF_HOME": "/cache",
            "U2NET_HOME": "/cache/u2net",
            "ATTN_BACKEND": "xformers",
            "SPCONV_ALGO": "native",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )
    .add_local_dir(str(PACKAGE), "/root/picture_to_print", ignore=["__pycache__"])
)


@app.function(
    image=gpu_image,
    gpu="A100-80GB",
    cpu=4,
    memory=32768,
    volumes={"/cache": weights},
    secrets=[runtime_secret],
    timeout=1200,
    scaledown_window=10,
    max_containers=1,
    retries=0,
)
def generate_geometry(photo: bytes, resolution: int, seed: int):
    import io
    import tempfile

    import torch
    from PIL import Image
    from rembg import new_session, remove
    from trellis2.modules import image_feature_extractor
    from trellis2.pipelines import Trellis2ImageTo3DPipeline, samplers
    from trellis2.pipelines.base import Pipeline

    from picture_to_print.shape_inference import sample_geometry
    from picture_to_print.trellis import export_raw_mesh

    class ShapeOnlyPipeline(Trellis2ImageTo3DPipeline):
        model_names_to_load = [
            "sparse_structure_decoder",
            "sparse_structure_flow_model",
            "shape_slat_decoder",
            "shape_slat_flow_model_512",
        ] + (["shape_slat_flow_model_1024"] if resolution == 1024 else [])

    try:
        image = Image.open(io.BytesIO(photo)).convert("RGBA")
        if image.getchannel("A").getextrema()[0] == 255:
            image = remove(image, session=new_session("u2net"))
        if not image.getchannel("A").getbbox():
            raise ValueError("Background removal found no foreground")
        pipeline = Pipeline.from_pretrained.__func__(ShapeOnlyPipeline, "microsoft/TRELLIS.2-4B")
        config = pipeline._pretrained_args
        for name in ("sparse_structure_sampler", "shape_slat_sampler"):
            spec = config[name]
            setattr(pipeline, name, getattr(samplers, spec["name"])(**spec["args"]))
            setattr(pipeline, name + "_params", spec["params"])
        pipeline.shape_slat_normalization = config["shape_slat_normalization"]
        encoder = config["image_cond_model"]
        # Match the user's prior deployment, with the encoder's exact digest
        # checked in the image build. Its upstream model license still applies.
        pipeline.image_cond_model = getattr(image_feature_extractor, encoder["name"])(
            model_name="/opt/dinov3"
        )
        pipeline.cuda()
        torch.manual_seed(seed)
        with torch.inference_mode():
            mesh = sample_geometry(pipeline, image, resolution)
        with tempfile.TemporaryDirectory() as directory:
            raw = export_raw_mesh(mesh, Path(directory) / "raw.ply")
            if raw.stat().st_size > 75_000_000:
                raise ValueError("Raw mesh exceeds transfer limit; use 512 resolution")
            return raw.read_bytes(), {
                "model": "microsoft/TRELLIS.2-4B",
                "trellis_commit": TRELLIS_REF,
                "resolution": resolution,
                "seed": seed,
                "textures_generated": False,
                "background_removal": "u2net",
            }
    finally:
        weights.commit()


@app.local_entrypoint()
def main(image_path: str, output: str, resolution: int = 512, seed: int = 42):
    data, metadata = generate_geometry.remote(Path(image_path).read_bytes(), resolution, seed)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    import json

    print(json.dumps(metadata))
