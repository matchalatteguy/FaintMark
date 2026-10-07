"""TrustMark Q encoder and decoder on ONNX Runtime, with a pinned model download.

The pre- and post-processing ports Adobe's TrustMark (https://github.com/adobe/trustmark,
MIT, Copyright 2023 Adobe).
"""

import hashlib
import os
import shutil
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from .bch import N
from .bch import decode as bch_decode
from .bch import encode as bch_encode

MODEL_URL = "https://cai-watermark.adobe.net/watermarking/trustmark-models/"
# Published by Adobe on 2026-09-28; fetched and hashed on 2026-10-06.
MODEL_HASHES = {
    "encoder_Q.onnx": "19b3d1b25836130ffd78775a8f61539f993375d1823ef0e59ba5b8dffb4f892d",
    "decoder_Q.onnx": "ee3268f057c9dabef680e169302f5973d0589feea86189ed229a896cc3aa88df",
}
ENC_RES, DEC_RES, ASPECT_LIMIT, FEATHER = 256, 256, 2.0, 0.01


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def ensure_models(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    announced = False
    for name, digest in MODEL_HASHES.items():
        target = directory / name
        if target.is_file() and _sha256(target) == digest:
            continue
        if not announced:
            print("downloading TrustMark Q models (65 MB, once)...", file=sys.stderr)
            announced = True
        temp = tempfile.NamedTemporaryFile(dir=directory, delete=False)
        try:
            with temp, urllib.request.urlopen(MODEL_URL + name, timeout=60) as response:
                shutil.copyfileobj(response, temp)
            if _sha256(temp.name) != digest:
                raise RuntimeError(f"model checksum mismatch: {name}")
            os.replace(temp.name, target)
        except BaseException:
            Path(temp.name).unlink(missing_ok=True)
            raise
    return directory


def _region(w, h):
    """Left, top, right, bottom to process: the whole image, or its centre square if aspect > 2."""
    if max(w, h) / min(w, h) > ASPECT_LIMIT:
        s = min(w, h)
        left, top = (w - s) // 2, (h - s) // 2
        return left, top, left + s, top + s
    return 0, 0, w, h


def _tensor(im):
    """RGB PIL -> (1,3,H,W) float32 in [-1,1]; identical to torchvision ToTensor()*2-1."""
    a = np.asarray(im, dtype=np.uint8).astype(np.float32).transpose(2, 0, 1)[None]
    return a / np.float32(255) * np.float32(2) - np.float32(1)


def _axis(out, n):
    half = np.float32(0.5)
    src = np.maximum((np.arange(out, dtype=np.float32) + half) * np.float32(n / out) - half, 0)
    i0 = np.minimum(src.astype(np.int64), n - 1)
    return i0, np.minimum(i0 + 1, n - 1), (src - i0).astype(np.float32)


def _resize(x, h, w):
    """torch.nn.functional.interpolate(mode='bilinear', align_corners=False, antialias=False)."""
    y0, y1, ly = _axis(h, x.shape[2])
    x0, x1, lx = _axis(w, x.shape[3])
    rows = x[:, :, y0] * (1 - ly)[:, None] + x[:, :, y1] * ly[:, None]
    return rows[..., x0] * (1 - lx) + rows[..., x1] * lx


def _paste(out, cover, wm, top, bottom, left, right):
    """TrustMark.feather_paste: write wm into out[top:bottom, left:right] with a feathered edge."""
    fs = min(max(1, int(min(right - left, bottom - top) * FEATHER)), 50)
    out[top:bottom, left:right] = wm
    for i in range(fs):
        a = (i + 1) / fs
        for row, k in ((top + i, i), (bottom - 1 - i, bottom - top - 1 - i)):
            out[row, left:right] = a * wm[k] + (1 - a) * cover[row, left:right]
    for i in range(fs):
        a = (i + 1) / fs
        for col, k in ((left + i, i), (right - 1 - i, right - left - 1 - i)):
            out[top:bottom, col] = a * wm[:, k] + (1 - a) * cover[top:bottom, col]


def _load(path):
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")  # official builds phone home by default
    import onnxruntime as ort

    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.log_severity_level = 3
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


class Engine:
    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self._sessions = {}
        self._load_lock = threading.Lock()

    def _session(self, name):
        with self._load_lock:
            if name not in self._sessions:
                self._sessions[name] = _load(ensure_models(self.models_dir) / name)
        return self._sessions[name]

    def encode(self, image: Image.Image, copy_id: int) -> Image.Image:
        if not isinstance(copy_id, int) or not 0 <= copy_id < 2**40:
            raise ValueError("copy_id must be an int in [0, 2**40)")
        encoder = self._session("encoder_Q.onnx")
        # 96 codeword bits + 4 schema bits (BCH_SUPER = 0)
        bits = [int(c) for c in format(bch_encode(copy_id), f"0{N}b")] + [0, 0, 0, 0]
        secret = np.array([bits], dtype=np.float32)
        box = _region(*image.size)
        crop = image.crop(box)
        w, h = crop.size
        cover = _tensor(crop.resize((ENC_RES, ENC_RES), Image.BILINEAR))
        inputs = dict(zip((i.name for i in encoder.get_inputs()), (cover, secret)))
        stego = encoder.run(None, inputs)[0]
        residual = np.clip(stego, -1, 1) - cover
        # remove per-channel colour shift
        residual = residual - residual.mean(axis=(2, 3), keepdims=True)
        # float32 and in place: the float64 expression upstream uses peaks at 2.4 GB for 25 MP
        marked = np.ascontiguousarray(_resize(residual, h, w)[0].transpose(1, 2, 0))
        marked += np.asarray(crop, dtype=np.float32) / np.float32(127.5)
        marked -= 1
        np.clip(marked, -1, 1, out=marked)
        marked *= 127.5
        marked += 127.5
        base = np.asarray(image, dtype=np.uint8)
        out = base.copy()
        left, top, right, bottom = box
        _paste(out, base, marked, top, bottom, left, right)  # assignment into uint8 truncates
        return Image.fromarray(out)

    def decode(self, image: Image.Image) -> int | None:
        decoder = self._session("decoder_Q.onnx")
        crop = image.crop(_region(*image.size)).resize((DEC_RES, DEC_RES), Image.BILINEAR)
        bits = decoder.run(None, {decoder.get_inputs()[0].name: _tensor(crop)})[0][0] > 0
        if bits[98] or bits[99]:  # schema bits must be 00
            return None
        data, ok = bch_decode(int("".join("1" if b else "0" for b in bits[:N]), 2))
        return data if ok else None
