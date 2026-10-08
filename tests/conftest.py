import numpy as np
import pytest
from PIL import Image, ImageCms


class Stub:
    """Stores the 40-bit id as an 8x8-pixel black/white block grid, so it survives JPEG."""

    def encode(self, image, value):
        bits = np.array([int(bit) for bit in f"{value:040b}"], dtype=np.uint8).reshape(5, 8)
        pixels = np.array(image)
        pixels[:40, :64] = np.kron(bits * 255, np.ones((8, 8), dtype=np.uint8))[..., None]
        return Image.fromarray(pixels)

    def decode(self, image):
        blocks = np.asarray(image.convert("L"), dtype=float)[:40, :64].reshape(5, 8, 8, 8)
        means = blocks.mean(axis=(1, 3))
        if not (
            (means < 60) | (means > 195)
        ).all():  # no clean grid: unmarked, like the real decoder
            return None
        return int("".join("1" if bit else "0" for bit in (means > 127).ravel()), 2)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FAINTMARK_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("faintmark.core.Engine", lambda models_dir: Stub())
    return tmp_path / "home"


@pytest.fixture
def icc():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


@pytest.fixture
def make_image(tmp_path):
    def make(name, size=(128, 96), **save):
        rng = np.random.default_rng(1)
        ramp = np.linspace(0, 200, size[0])[None, :, None]
        image = Image.fromarray((ramp + rng.integers(0, 50, (size[1], size[0], 3))).astype("uint8"))
        mpo = save.get("format") == "MPO"
        if mpo:
            save.update(save_all=True, append_images=[image.copy()])
        path = tmp_path / name
        image.save(path, **save)
        if mpo:
            with Image.open(path) as saved:
                assert saved.format == "MPO"
        return path

    return make
