"""Proof against Adobe's own implementation (trustmark 0.9.2, PyTorch): golden vectors and images
produced by the upstream package are checked in under tests/fixtures (see make_fixtures.py)."""

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from faintmark import bch
from faintmark.engine import Engine

FIXTURES = Path(__file__).parent / "fixtures"
MODELS = Path(os.environ.get("FAINTMARK_HOME", Path.home() / ".faintmark")) / "models"
needs_models = pytest.mark.skipif(
    os.environ.get("FAINTMARK_INTEGRATION") != "1", reason="needs the TrustMark models"
)
UPSTREAM = json.loads((FIXTURES / "upstream.json").read_text())
# (cover, upstream's marked version); the second is wider than 2:1, so only its centre square is marked
PAIRS = [("cover", "upstream_marked"), ("cover_wide", "upstream_marked_wide")]


def load(name):
    return Image.open(FIXTURES / f"{name}.png").convert("RGB")


def test_bch_matches_upstream_vectors():
    vectors = json.loads((FIXTURES / "bch_vectors.json").read_text())
    assert len(vectors) == 12
    for vector in vectors:
        copy_id, secret = vector["id"], vector["secret"]
        assert len(secret) == 100
        assert format(bch.encode(copy_id), "096b") + "0000" == secret
        assert bch.decode(int(secret[:96], 2)) == (copy_id, True)


@pytest.fixture(scope="module")
def engine():
    return Engine(MODELS)


@pytest.mark.parametrize("name", ["upstream_marked", "upstream_marked_wide"])
@pytest.mark.integration
@needs_models
def test_decodes_images_marked_by_upstream_trustmark(engine, name):
    assert UPSTREAM["trustmark"] == "0.9.2"
    assert UPSTREAM[name]["upstream_decoded_id"] == UPSTREAM[name]["id"]
    assert engine.decode(load(name)) == UPSTREAM[name]["id"]


@pytest.mark.parametrize(("cover", "name"), PAIRS)
@pytest.mark.integration
@needs_models
def test_encoder_matches_upstream_within_one_level(engine, cover, name):
    upstream = np.asarray(load(name), dtype=int)
    ours = engine.encode(load(cover), UPSTREAM[name]["id"])
    assert ours.size == (upstream.shape[1], upstream.shape[0])
    diff = np.abs(np.asarray(ours, dtype=int) - upstream)
    differing = (diff.max(axis=2) > 0).mean()
    # measured: max 1 level; 1.81% (cover) and 0.54% (cover_wide) of pixels differ, from float rounding
    # differences between ONNX Runtime and PyTorch at the final uint8 truncation
    assert diff.max() <= 1
    assert differing <= 0.025, f"{differing:.3%} of pixels differ"
