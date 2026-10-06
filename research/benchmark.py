"""Local, reproducible image-watermark comparison; no platform uploads."""
from __future__ import annotations
import argparse
import binascii
import hashlib
import io
import json
import platform
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from skimage import data
from skimage.metrics import structural_similarity
import torch

ROOT = Path(__file__).resolve().parent


def fixtures():
    out = ROOT / "fixtures"
    out.mkdir(exist_ok=True)
    # Bundled scikit-image examples; source citations are in the recommendation.
    names = ["astronaut", "coffee", "chelsea", "rocket", "camera", "hubble_deep_field"]
    for name in names:
        path = out / f"{name}.png"
        if not path.exists():
            Image.fromarray(getattr(data, name)()).convert("RGB").save(path)
    im = Image.new("RGB", (1200, 800), "#f8f8f8")
    draw = ImageDraw.Draw(im)
    for y in range(60, 740, 50):
        draw.text((60, y), "CONFIDENTIAL SAMPLE — Recipient-specific image copy 0123456789", fill="#252525", font_size=24)
    im.save(out / "text_document.png")
    x = np.linspace(0, 255, 1200, dtype=np.uint8)
    arr = np.tile(x, (800, 1))
    Image.fromarray(np.stack([arr, arr, arr], axis=-1)).save(out / "smooth_gradient.png")
    # A larger export fixture, explicitly upscaled, not an independent photograph.
    Image.open(out / "astronaut.png").resize((2048, 2048), Image.Resampling.LANCZOS).save(out / "astronaut_upscaled_2048.png")
    return sorted(out.glob("*.png"))


def serialize(im, fmt="JPEG", quality=80):
    buf = io.BytesIO()
    kwargs = {"quality": quality}
    if fmt == "JPEG":
        kwargs["subsampling"] = 2
    im.save(buf, format=fmt, **kwargs)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def scale(im, factor):
    return im.resize(tuple(max(1, round(v * factor)) for v in im.size), Image.Resampling.LANCZOS)


def cap(im, edge):
    return scale(im, min(1, edge / max(im.size)))


def chain(im):
    for factor, quality in [(0.75, 80), (0.75, 70), (0.75, 60)]:
        im = serialize(scale(im, factor), quality=quality)
    return im


TRANSFORMS = {
    "png_unchanged": lambda im: serialize(im, "PNG"),
    "jpeg_95": lambda im: serialize(im, quality=95),
    "jpeg_85": lambda im: serialize(im, quality=85),
    "jpeg_70": lambda im: serialize(im, quality=70),
    "jpeg_50": lambda im: serialize(im, quality=50),
    "jpeg_30_stress": lambda im: serialize(im, quality=30),
    "webp_80": lambda im: serialize(im, "WEBP", 80),
    "webp_50": lambda im: serialize(im, "WEBP", 50),
    "half_jpeg_70": lambda im: serialize(scale(im, 0.5), quality=70),
    "quarter_jpeg_50_stress": lambda im: serialize(scale(im, 0.25), quality=50),
    "max1080_jpeg_80": lambda im: serialize(cap(im, 1080), quality=80),
    "three_generation_chain": chain,
    "max160_jpeg_50_stress": lambda im: serialize(cap(im, 160), quality=50),
}


class TrustmarkEngine:
    def __init__(self, device, variant="Q"):
        from trustmark import TrustMark
        self.model = TrustMark(verbose=False, model_type=variant, device=device,
                               encoding_type=TrustMark.Encoding.BCH_SUPER, loadRemover=False)
        if self.model.encoder is None or self.model.decoder is None:
            raise RuntimeError("TrustMark models failed to load")

    def encode(self, im, ident):
        return self.model.encode(im, f"{ident:040b}", MODE="binary")

    def decode(self, im):
        bits, valid, schema = self.model.decode(im, MODE="binary")
        return (int(bits, 2) if valid and len(bits) == 40 and schema == 0 else None), {"ecc_valid": bool(valid)}


class PixelSealEngine:
    def __init__(self, device, strength=1.0):
        import bchlib
        import videoseal
        self.device = device
        self.model = videoseal.load("pixelseal").to(device).eval()
        self.model.blender.scaling_w *= strength
        self.bch = bchlib.BCH(24, m=8)

    def packet(self, ident):
        ident_bytes = ident.to_bytes(5, "big")
        checksum = binascii.crc_hqx(ident_bytes, 0xffff).to_bytes(2, "big")
        body = ident_bytes + checksum
        encoded = body + self.bch.encode(body)
        bits = np.unpackbits(np.frombuffer(encoded, dtype=np.uint8))
        return np.pad(bits, (0, 256 - len(bits)))

    def tensor(self, im):
        return torch.from_numpy(np.array(im).copy()).permute(2, 0, 1).float().unsqueeze(0).to(self.device) / 255

    @torch.inference_mode()
    def encode(self, im, ident):
        msgs = torch.tensor(self.packet(ident), device=self.device).float().unsqueeze(0)
        arr = self.model.embed(self.tensor(im), msgs=msgs, is_video=False)["imgs_w"][0]
        arr = arr.detach().cpu().permute(1, 2, 0).numpy()
        return Image.fromarray(np.rint(np.clip(arr, 0, 1) * 255).astype(np.uint8))

    @torch.inference_mode()
    def decode(self, im):
        logits = self.model.detect(self.tensor(im), is_video=False)["preds"][0, 1:].flatten()
        bits = (logits > 0).detach().cpu().numpy().astype(np.uint8)
        if len(bits) != 256:
            raise RuntimeError(f"Unexpected PixelSeal output: {len(bits)} bits")
        packet = np.packbits(bits).tobytes()
        body = bytearray(packet[:7])
        ecc = bytearray(packet[7:7 + self.bch.ecc_bytes])
        errors = self.bch.decode(body, ecc)
        valid = errors >= 0
        if valid:
            self.bch.correct(body, ecc)
            valid = binascii.crc_hqx(body[:5], 0xffff) == int.from_bytes(body[5:7], "big")
        return (int.from_bytes(body[:5], "big") if valid else None), {"ecc_valid": bool(valid), "corrected_errors": int(errors), "raw_bits": bits.tolist()}


class ClassicEngine:
    def __init__(self, device):
        import cv2
        from imwatermark import WatermarkEncoder, WatermarkDecoder
        self.cv2 = cv2
        self.encoder = WatermarkEncoder()
        self.decoder = WatermarkDecoder("bits", 40)

    def encode(self, im, ident):
        self.encoder.set_watermark("bits", [int(x) for x in f"{ident:040b}"])
        bgr = self.cv2.cvtColor(np.array(im), self.cv2.COLOR_RGB2BGR)
        encoded = self.encoder.encode(bgr, "dwtDct")
        return Image.fromarray(self.cv2.cvtColor(encoded, self.cv2.COLOR_BGR2RGB))

    def decode(self, im):
        bgr = self.cv2.cvtColor(np.array(im), self.cv2.COLOR_RGB2BGR)
        if im.width * im.height < 256 * 256:
            # Upstream rejects small images. Do not invent a preprocessing rescue.
            return None, {"unsupported_size": True}
        bits = self.decoder.decode(bgr, "dwtDct")
        return int("".join(str(int(v)) for v in bits), 2), {}


ENGINES = {"trustmark_q": TrustmarkEngine, "pixelseal": PixelSealEngine,
           "pixelseal_1p4": lambda device: PixelSealEngine(device, strength=1.4),
           "classic_dwt_dct": ClassicEngine}


def synchronize(device):
    if device == "mps":
        torch.mps.synchronize()


def ident_for(name, recipient):
    return int.from_bytes(hashlib.sha256(f"watermarker-bench-v1/{name}/{recipient}".encode()).digest()[:5], "big")


def run(args):
    torch.set_num_threads(4)
    device = "mps" if torch.backends.mps.is_available() and not args.cpu else "cpu"
    paths = fixtures()
    if args.pilot:
        paths = [p for p in paths if p.stem == "astronaut"]
    transforms = TRANSFORMS if not args.pilot else {k: TRANSFORMS[k] for k in ["png_unchanged", "jpeg_70", "half_jpeg_70"]}
    recipients = 1 if args.pilot else 5
    registry = {ident_for(p.stem, r) for p in paths for r in range(recipients)}
    assert len(registry) == len(paths) * recipients
    output = ROOT / "results" / ("pilot" if args.pilot else "full")
    output.mkdir(parents=True, exist_ok=True)
    meta = {"device": device, "machine": platform.machine(), "platform": platform.platform(),
            "torch": torch.__version__, "cpu_threads": torch.get_num_threads(), "images": len(paths), "recipients_per_image": recipients,
            "transforms": list(transforms), "seed": "SHA256 watermarker-bench-v1", "platform_uploads": False,
            "fixture_sizes": {p.stem: Image.open(p).size for p in paths}}
    (output / "environment.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta), flush=True)
    for engine_name in args.engines:
        start = time.perf_counter()
        engine = ENGINES[engine_name](device)
        synchronize(device)
        cold_load = time.perf_counter() - start
        # Warm up; do not include model initialization or first inference in steady-state timings.
        warm = Image.open(paths[0]).convert("RGB")
        engine.decode(engine.encode(warm, ident_for(paths[0].stem, 0)))
        rows, controls, quality = [], [], []
        result_path = output / f"{engine_name}.json"
        for path in paths:
            im = Image.open(path).convert("RGB")
            for transform, fn in transforms.items():
                recovered, info = engine.decode(fn(im))
                controls.append({"image": path.stem, "transform": transform,
                                 "registered_match": recovered in registry, "decoded_id": recovered,
                                 "ecc_valid": info.get("ecc_valid")})
            for recipient in range(recipients):
                expected = ident_for(path.stem, recipient)
                synchronize(device)
                tick = time.perf_counter()
                marked = engine.encode(im, expected)
                synchronize(device)
                encode_s = time.perf_counter() - tick
                a, b = np.array(im), np.array(marked)
                mse = float(np.mean((a.astype(float) - b.astype(float)) ** 2))
                psnr = float(10 * np.log10(255 ** 2 / mse)) if mse else 99.0
                ssim = float(structural_similarity(a, b, data_range=255, channel_axis=-1))
                quality.append({"image": path.stem, "recipient": recipient, "psnr_db": psnr, "ssim": ssim, "encode_s": encode_s})
                if recipient == 0:
                    previews = output / "previews"
                    previews.mkdir(exist_ok=True)
                    marked.save(previews / f"{engine_name}_{path.stem}.png")
                for transform, fn in transforms.items():
                    attacked = fn(marked)
                    synchronize(device)
                    tick = time.perf_counter()
                    recovered, info = engine.decode(attacked)
                    synchronize(device)
                    decode_s = time.perf_counter() - tick
                    raw_accuracy = None
                    if "raw_bits" in info:
                        raw_accuracy = float(np.mean(np.array(info["raw_bits"]) == engine.packet(expected)))
                    rows.append({"image": path.stem, "recipient": recipient, "expected_id": expected,
                                 "transform": transform, "size": attacked.size, "correct": recovered == expected,
                                 "wrong_registered_id": recovered in registry and recovered != expected,
                                 "decoded_id": recovered, "decode_s": decode_s, "raw_bit_accuracy": raw_accuracy,
                                 "ecc_valid": info.get("ecc_valid"), "corrected_errors": info.get("corrected_errors")})
            result_path.write_text(json.dumps({"engine": engine_name, "cold_load_s": cold_load, "rows": rows, "controls": controls, "quality": quality}, indent=2))
            print(f"{engine_name}: {path.stem}: {sum(r['correct'] for r in rows)}/{len(rows)} cumulative exact recovery", flush=True)
        del engine
        if device == "mps":
            torch.mps.empty_cache()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engines", nargs="+", choices=list(ENGINES), default=list(ENGINES))
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--cpu", action="store_true")
    run(parser.parse_args())
