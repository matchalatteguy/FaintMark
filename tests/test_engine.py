import os
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from faintmark.engine import Engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("FAINTMARK_INTEGRATION") != "1", reason="needs the TrustMark models"
    ),
]
IDS = [0x0123456789, 0xFEDCBA9876]


@pytest.fixture(scope="module")
def engine():
    return Engine(Path(os.environ.get("FAINTMARK_HOME", Path.home() / ".faintmark")) / "models")


def noise(width, height):
    rng = np.random.default_rng(42)
    return Image.fromarray(rng.integers(40, 220, (height, width, 3), dtype=np.uint8))


def jpeg70(image):
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=70)
    return Image.open(buffer).convert("RGB")


def test_roundtrip_is_nearly_invisible(engine):
    cover = noise(512, 512)
    for copy_id in IDS:
        marked = engine.encode(cover, copy_id)
        assert engine.decode(marked) == copy_id
        diff = np.abs(np.asarray(marked, dtype=int) - np.asarray(cover, dtype=int))
        assert 0 < diff.mean() < 6


def test_wide_image_uses_the_centre_square(engine):
    marked = engine.encode(noise(1200, 400), IDS[0])
    assert marked.size == (1200, 400)
    assert engine.decode(marked) == IDS[0]


def test_survives_jpeg_and_downscaling(engine):
    marked = engine.encode(noise(512, 512), IDS[0])
    assert engine.decode(jpeg70(marked)) == IDS[0]
    assert engine.decode(jpeg70(marked.resize((256, 256), Image.LANCZOS))) == IDS[0]


def test_unmarked_image_is_not_detected(engine):
    assert engine.decode(noise(512, 512)) is None
