"""Regenerate the upstream-compatibility fixtures.

The synthetic cover recipe lives here (imported by the tests). Running this file needs the
upstream PyTorch package (`pip install trustmark==0.9.2 torch torchvision`) and downloads its
official weights; it is a one-off, not part of the test suite:

    python tests/fixtures/make_fixtures.py
"""

import json
import random
from importlib.metadata import version
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
BCH_IDS = [0, 1, 2**40 - 1, 0x0123456789, 1 << 39]
COVER_ID, WIDE_ID = 0x0123456789, 0xFEDCBA9876


def synthetic_cover(width, height, seed=11, smooth=False):
    """Smooth gradients, hard-edged rectangles and mild noise (fewer shapes and no noise if smooth)."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)
    u, v = x / width, y / height
    img = np.stack(
        [
            60 + 150 * u + 20 * np.sin(6 * v),
            50 + 140 * v + 25 * np.cos(5 * u),
            200 - 90 * (u + v) / 2 + 15 * np.sin(4 * (u - v)),
        ],
        axis=-1,
    )
    for _ in range(3 if smooth else 6):
        x0, y0 = int(rng.uniform(0, 0.7) * width), int(rng.uniform(0, 0.7) * height)
        w, h = int(rng.uniform(0.1, 0.3) * width), int(rng.uniform(0.1, 0.3) * height)
        img[y0 : y0 + h, x0 : x0 + w] = rng.integers(20, 235, 3)
    if not smooth:
        img += rng.normal(0, 1.2, img.shape)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def main():
    from trustmark import TrustMark
    from trustmark.datalayer import DataLayer

    rng = random.Random(7)
    ids = BCH_IDS + [rng.randrange(2**40) for _ in range(7)]
    layer = DataLayer(100, verbose=False, encoding_mode=0)
    vectors = [
        {"id": i, "secret": "".join(str(int(b)) for b in layer.encode_binary([f"{i:040b}"])[0])}
        for i in ids
    ]
    (HERE / "bch_vectors.json").write_text(json.dumps(vectors, indent=1) + "\n")

    tm = TrustMark(
        use_ECC=True,
        verbose=False,
        model_type="Q",
        encoding_type=TrustMark.Encoding.BCH_SUPER,
        loadRemover=False,
        device="cpu",
    )
    record = {"trustmark": version("trustmark")}
    for name, size, copy_id in [
        ("upstream_marked", COVER_SIZE, COVER_ID),
        ("upstream_marked_wide", WIDE_SIZE, WIDE_ID),
    ]:
        cover_path = HERE / ("cover.png" if name == "upstream_marked" else "cover_wide.png")
        synthetic_cover(*size).save(cover_path, optimize=True)
        cover = Image.open(cover_path).convert("RGB")
        marked = tm.encode(cover, f"{copy_id:040b}", MODE="binary", WM_STRENGTH=1.0)
        marked.save(HERE / f"{name}.png", optimize=True)
        secret, detected, _ = tm.decode(
            Image.open(HERE / f"{name}.png").convert("RGB"), MODE="binary"
        )
        record[name] = {"id": copy_id, "upstream_decoded_id": int(secret, 2) if detected else None}
    (HERE / "upstream.json").write_text(json.dumps(record, indent=1) + "\n")


COVER_SIZE, WIDE_SIZE = (320, 240), (480, 160)

if __name__ == "__main__":
    main()
