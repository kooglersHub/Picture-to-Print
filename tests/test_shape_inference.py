from types import SimpleNamespace

import pytest

from picture_to_print.shape_inference import sample_geometry


class GeometryPipeline:
    models = {"shape_slat_flow_model_512": "shape512", "shape_slat_flow_model_1024": "shape1024"}

    def preprocess_image(self, image):
        return image

    def get_cond(self, images, resolution):
        return resolution

    def sample_sparse_structure(self, cond, resolution, **kwargs):
        return "coordinates"

    def sample_shape_slat(self, cond, model, coords):
        return ("shape", cond)

    def sample_shape_slat_cascade(
        self, low, high, low_model, high_model, low_res, high_res, coords
    ):
        return ("shape", high), high_res

    def decode_shape_slat(self, latent, resolution):
        return [SimpleNamespace(vertices=[resolution], faces=[1])], []

    def sample_tex_slat(self, *args, **kwargs):
        pytest.fail("Print generation must not sample textures")


@pytest.mark.parametrize("resolution", [512, 1024])
def test_shape_generation_outputs_geometry_without_texture_sampling(resolution):
    result = sample_geometry(GeometryPipeline(), "photo", resolution)
    assert result.vertices == [resolution]


def test_captures_the_actual_preprocessed_image_passed_to_conditioning():
    seen = []

    class Pipeline(GeometryPipeline):
        def preprocess_image(self, image):
            return "cropped image"

        def get_cond(self, images, resolution):
            assert images == ["cropped image"]
            return super().get_cond(images, resolution)

    sample_geometry(Pipeline(), "original", 512, on_preprocessed=seen.append)
    assert seen == ["cropped image"]
