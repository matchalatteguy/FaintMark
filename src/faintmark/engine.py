"""Lazy, integrity-checked TrustMark Q inference."""

import hashlib
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

MODEL_HOST = "https://cai-watermark.adobe.net/watermarking/trustmark-models/"
MODEL_HASHES = {
    "trustmark_Q.yaml": "43f37103f92efa8bd6b1c5902bb537cc12a981dc699fca19d9bb7de8c62d03d9",
    "decoder_Q.ckpt": "e3d9cea5406a26590735719f8f15cb10802b11852ae69047eaf4cf17214df781",
    "encoder_Q.ckpt": "dc382c3f6b4fd568b27d6fbb763d6ffc2d2587126d84afe9d5ee95b4c5d99826",
}
_LOCK = threading.RLock()
_MODELS = {}


def _valid(path, digest):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest


def ensure_models(directory):
    """Reuse verified installed weights, otherwise download atomically."""
    import trustmark

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundled = Path(trustmark.__file__).parent / "models"
    for name, digest in MODEL_HASHES.items():
        target = directory / name
        if _valid(target, digest):
            continue
        last = None
        for attempt in range(3):
            fd, temporary = tempfile.mkstemp(dir=directory, prefix=".download-")
            try:
                with os.fdopen(fd, "wb") as output:
                    if _valid(bundled / name, digest):
                        with (bundled / name).open("rb") as source:
                            shutil.copyfileobj(source, output)
                    else:
                        with urllib.request.urlopen(MODEL_HOST + name, timeout=60) as source:
                            shutil.copyfileobj(source, output)
                if not _valid(Path(temporary), digest):
                    raise RuntimeError(f"Model checksum mismatch: {name}")
                os.replace(temporary, target)
                break
            except Exception as error:
                last = error
                if attempt == 2:
                    raise RuntimeError(f"Could not obtain verified model {name}: {last}") from error
                time.sleep(attempt + 1)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return directory


class TrustMarkEngine:
    def __init__(self, home, device="auto"):
        self.home = Path(home)
        self.device = device

    def _model(self):
        import torch
        from trustmark import TrustMark
        from trustmark.trustmark import OmegaConf, instantiate_from_config

        device = self.device
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS is unavailable on this computer; choose auto or cpu.")
        if device not in ("cpu", "mps"):
            raise ValueError("Choose auto, cpu, or mps for the device.")
        key = (str(self.home.resolve()), device)
        if key in _MODELS:
            return _MODELS[key]
        models = ensure_models(self.home / "models")

        class VettedTrustMark(TrustMark):
            def load_model(self, config_path, weight_path, device, secret_len, part="all"):
                config = OmegaConf.load(models / Path(config_path).name).model
                replaced = (
                    ("secret_encoder", "discriminator", "loss", "noise")
                    if part == "decoder"
                    else ("secret_decoder", "discriminator", "loss", "noise")
                )
                for component in replaced:
                    config.params[component + "_config"].target = "trustmark.model.Identity"
                model = instantiate_from_config(config)
                checkpoint = torch.load(
                    models / Path(weight_path).name, map_location="cpu", weights_only=True
                )
                model.load_state_dict(checkpoint.get("state_dict", checkpoint), strict=False)
                return model.to(device).eval()

        with redirect_stdout(sys.stderr):
            model = VettedTrustMark(
                use_ECC=True,
                verbose=False,
                model_type="Q",
                encoding_type=TrustMark.Encoding.BCH_SUPER,
                loadRemover=False,
                device=device,
            )
        _MODELS[key] = model
        return model

    def _invoke(self, operation, image, **kwargs):
        try:
            return getattr(self._model(), operation)(image, **kwargs)
        except RuntimeError:
            import torch

            if self.device == "auto" and torch.backends.mps.is_available():
                self.device = "cpu"
                return getattr(self._model(), operation)(image, **kwargs)
            raise

    def encode(self, image, copy_id):
        if not isinstance(copy_id, int) or not 0 <= copy_id < 2**40:
            raise ValueError("Copy IDs must contain exactly 40 bits.")
        with _LOCK:
            return self._invoke(
                "encode", image, string_secret=f"{copy_id:040b}", MODE="binary", WM_STRENGTH=1.0
            )

    def decode(self, image):
        with _LOCK:
            bits, detected, schema = self._invoke("decode", image, MODE="binary")
            if (
                not detected
                or schema != 0
                or not isinstance(bits, str)
                or len(bits) != 40
                or set(bits) - {"0", "1"}
            ):
                return None
            return int(bits, 2)
