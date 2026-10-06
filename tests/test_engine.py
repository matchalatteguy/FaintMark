import json
import os
import shutil
import subprocess
import sys
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
MODELS = Path(os.environ.get("FAINTMARK_HOME", Path.home() / ".faintmark")) / "models"


@pytest.fixture(scope="module")
def engine():
    return Engine(MODELS)


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


def test_wide_image_marks_only_the_centre_square(engine):
    cover = noise(1200, 400)
    marked = engine.encode(cover, IDS[0])
    assert marked.size == (1200, 400)
    assert engine.decode(marked) == IDS[0]
    before, after = np.asarray(cover), np.asarray(marked)
    assert np.array_equal(before[:, :400], after[:, :400])
    assert np.array_equal(before[:, 800:], after[:, 800:])
    assert not np.array_equal(before[:, 400:800], after[:, 400:800])


def test_survives_jpeg_and_downscaling(engine):
    marked = engine.encode(noise(512, 512), IDS[0])
    assert engine.decode(jpeg70(marked)) == IDS[0]
    assert engine.decode(jpeg70(marked.resize((256, 256), Image.LANCZOS))) == IDS[0]


def test_unmarked_image_is_not_detected(engine):
    assert engine.decode(noise(512, 512)) is None


def test_cli_marks_and_traces_jpeg_copies(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    try:
        (home / "models").symlink_to(MODELS, target_is_directory=True)
    except OSError:
        shutil.copytree(MODELS, home / "models")

    def faintmark(*args):
        env = {**os.environ, "FAINTMARK_HOME": str(home)}
        run = subprocess.run(
            [sys.executable, "-m", "faintmark", *map(str, args), "--json"],
            capture_output=True,
            text=True,
            env=env,
        )
        return run.returncode, json.loads(run.stdout)

    source = tmp_path / "photo.jpg"
    noise(1200, 900).save(source, quality=85, subsampling=2)
    code, marked = faintmark("mark", source, "alice", "bob")
    assert code == 0
    copies = marked["copies"]
    assert [Path(copy["path"]).suffix for copy in copies] == [".jpg", ".jpg"]
    for copy in copies:
        assert 0.6 < Path(copy["path"]).stat().st_size / source.stat().st_size < 1.6

    code, found = faintmark("check", copies[0]["path"])
    assert (code, found["status"], found["recipient"]) == (0, "matched", "alice")
    resaved = tmp_path / "resaved.jpg"
    Image.open(copies[1]["path"]).save(resaved, quality=70)
    code, found = faintmark("check", resaved)
    assert (code, found["status"], found["recipient"]) == (0, "matched", "bob")
    code, found = faintmark("check", source)
    assert (code, found["status"]) == (1, "not_detected")
