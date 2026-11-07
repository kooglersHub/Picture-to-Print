"""Geometry-only use of the pinned TRELLIS.2 public sampling methods."""


def sample_geometry(pipeline, image, resolution, on_preprocessed=None):
    if resolution not in {512, 1024}:
        raise ValueError("Resolution must be 512 or 1024")
    image = pipeline.preprocess_image(image)
    if on_preprocessed:
        on_preprocessed(image)
    low_condition = pipeline.get_cond([image], 512)
    coordinates = pipeline.sample_sparse_structure(low_condition, 32, num_samples=1)
    low_model = pipeline.models["shape_slat_flow_model_512"]
    if resolution == 512:
        latent = pipeline.sample_shape_slat(low_condition, low_model, coordinates)
    else:
        high_condition = pipeline.get_cond([image], 1024)
        latent, resolution = pipeline.sample_shape_slat_cascade(
            low_condition,
            high_condition,
            low_model,
            pipeline.models["shape_slat_flow_model_1024"],
            512,
            1024,
            coordinates,
        )
    meshes, _ = pipeline.decode_shape_slat(latent, resolution)
    if not meshes:
        raise RuntimeError("TRELLIS returned no geometry")
    return meshes[0]
