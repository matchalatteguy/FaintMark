import numpy as np
import pytest
from PIL import Image, ImageCms

from faintmark import bch


class Stub:
    """Stores the 96-bit codeword as a grid of 8x8 black/white blocks (12 rows by 8): it survives
    JPEG but not halving, and decodes through BCH like the real engine."""

    def encode(self, image, value):
        bits = np.array([int(c) for c in format(bch.encode(value), "096b")], dtype=np.uint8)
        pixels = np.array(image)
        pixels[:96, :64] = np.kron(bits.reshape(12, 8) * 255, np.ones((8, 8), np.uint8))[..., None]
        return Image.fromarray(pixels)

    def raw_bits(self, image):
        grey = np.asarray(image.convert("L"), dtype=float)
        if grey.shape[0] < 96 or grey.shape[1] < 64:
            return [False] * 100
        means = grey[:96, :64].reshape(12, 8, 8, 8).mean(axis=(1, 3))
        return [bool(m > 127) for m in means.ravel()] + [False] * 4

    def decode(self, image):
        bits = self.raw_bits(image)
        if not any(bits):
            return None
        data, ok = bch.decode(int("".join("1" if b else "0" for b in bits[:96]), 2))
        return data if ok else None


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
