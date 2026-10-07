"""Marked copies per recipient, the sqlite registry that tracks them, and image I/O."""

import json
import os
import re
import secrets
import sqlite3
from contextlib import closing, suppress
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageOps, JpegImagePlugin, UnidentifiedImageError
from typing_extensions import Required, TypedDict  # pydantic needs these before Python 3.12

from .engine import Engine

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

MAX_PIXELS = 25_000_000
MAX_CHECK_PIXELS = 100_000_000
MAX_RECIPIENTS = 100
MAX_NAME = 200

DEFAULT_TARGET = {"JPEG": "jpeg", "PNG": "png", "WEBP": "webp", "HEIF": "jpeg"}
EXTENSIONS = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
JPEG_Q92 = {"quality": 92, "subsampling": 2, "optimize": True}
JPEG_Q95 = {"quality": 95, "subsampling": 2, "optimize": True}
SAME_IMAGE = 12  # max perceptual-hash distance (bits) for the picture as issued
INSERT = "INSERT INTO copies VALUES (:id, :recipient, :original, :path, :at, :warnings, :phash)"
SCHEMA = """CREATE TABLE IF NOT EXISTS copies (
    id TEXT PRIMARY KEY, recipient TEXT NOT NULL, original TEXT NOT NULL,
    path TEXT NOT NULL, marked_at TEXT NOT NULL, warnings TEXT NOT NULL, phash TEXT)"""


class Copy(TypedDict):
    id: str
    recipient: str
    path: str
    warnings: list[str]


class ListedCopy(TypedDict, total=False):
    id: Required[str]
    recipient: Required[str]
    marked_at: Required[str]
    warnings: Required[list[str]]
    original: str
    path: str


class MarkResult(TypedDict):
    original: str
    output_dir: str
    copies: list[Copy]


class CheckResult(TypedDict, total=False):
    status: Required[Literal["matched", "unregistered", "not_detected"]]
    id: str
    recipient: str
    marked_at: str
    same_image: bool
    original: str
    path: str


class ListResult(TypedDict):
    copies: list[ListedCopy]


def _open(path):
    try:
        return Image.open(path)
    except UnidentifiedImageError:
        if path.suffix.lower() in (".heic", ".heif") and "HEIF" not in Image.OPEN:
            raise ValueError(
                f"{path.name}: HEIC needs the heic extra (uv tool install 'faintmark[heic]')"
            ) from None
        raise ValueError(f"{path.name}: not an image") from None


def _rgb(image):
    return ImageOps.exif_transpose(image).convert("RGB")


def _decoded(data):
    with Image.open(BytesIO(data)) as image:
        return _rgb(image)


def _read(path):
    """The RGB cover, its source format, JPEG save parameters and the ICC profile to carry."""
    with _open(path) as image:
        fmt = "JPEG" if image.format == "MPO" else image.format
        if fmt not in DEFAULT_TARGET:
            raise ValueError(f"{path.name}: unsupported format {fmt}; use JPEG, PNG, WebP or HEIC")
        if image.format != "MPO" and getattr(image, "is_animated", False):
            raise ValueError(f"{path.name}: animated images are not supported")
        if image.width * image.height > MAX_PIXELS:
            raise ValueError(f"{path.name}: larger than 25 megapixels")
        if image.mode in ("I", "F") or image.mode.startswith("I;16"):
            raise ValueError(f"{path.name}: 16-bit images are not supported; convert to 8-bit")
        if (
            image.has_transparency_data
            and image.convert("RGBA").getchannel("A").getextrema()[0] < 255
        ):
            raise ValueError(f"{path.name}: has transparency; flatten it first")
        icc = image.info.get("icc_profile")
        icc = icc if icc and icc[16:20] == b"RGB " else None  # outputs are always RGB
        jpeg = JPEG_Q92
        if fmt == "JPEG" and len(image.quantization) >= 2:
            # qtables and quality are exclusive: quality would rescale the tables
            jpeg = {"qtables": image.quantization, "optimize": True}
            sampling = JpegImagePlugin.get_sampling(image)
            if sampling in (0, 1, 2):
                jpeg["subsampling"] = sampling
        return _rgb(image), fmt, jpeg, icc


def _phash(image):
    """64-bit perceptual hash: sign of the low DCT coefficients of a 32x32 grey thumbnail."""
    grey = np.asarray(image.convert("L").resize((32, 32), Image.BILINEAR), dtype=np.float64)
    n = np.arange(32)
    basis = np.cos(np.pi * (2 * n[None, :] + 1) * n[:, None] / 64)
    low = (basis @ grey @ basis.T)[:8, :8].ravel()[1:]
    return sum(1 << i for i, above in enumerate(low > np.median(low)) if above)


def _save(image, target, params):
    buffer = BytesIO()
    image.save(buffer, format=target.upper(), **params)
    return buffer.getvalue()


def _safe(text):
    text = re.sub(r"[^\w.-]+", "-", text.strip()).strip(".-")
    return text.encode()[:80].decode(errors="ignore") or "image"


def _unused_id(db, taken):
    while True:
        value = secrets.randbits(40)
        copy_id = f"{value:010x}"
        if (
            copy_id not in taken
            and not db.execute("SELECT 1 FROM copies WHERE id = ?", (copy_id,)).fetchone()
        ):
            return value


def _verified(engine, marked, value, target, attempts, name):
    """Saved bytes, their decoded image and the attempt index of the first copy that decodes."""
    for attempt, params in enumerate(attempts):
        data = _save(marked, target, params)
        saved = _decoded(data)
        if engine.decode(saved) == value:
            return data, saved, attempt
    hint = "the image may be too small" if target == "png" else "try --format png"
    raise RuntimeError(f"{name}: watermark could not be verified in the saved copy; {hint}")


def _jpeg70(image):
    return _decoded(_save(image, "jpeg", {"quality": 70}))


def _preflight(engine, saved, value):
    long = max(saved.size)
    edge = 1280 if long > 1280 else max(1, long // 2)
    size = tuple(max(1, round(side * edge / long)) for side in saved.size)
    warnings = []
    if engine.decode(_jpeg70(saved)) != value:
        warnings.append("may not survive JPEG recompression")
    if engine.decode(_jpeg70(saved.resize(size, Image.LANCZOS))) != value:
        warnings.append(f"may not survive resizing to {edge}px")
    return warnings


class FaintMark:
    def __init__(self, home: str | Path | None = None, engine: Engine | None = None):
        home = home or os.environ.get("FAINTMARK_HOME") or Path.home() / ".faintmark"
        self.home = Path(home).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine = engine or Engine(self.home / "models")
        self._registry = self.home / "registry.sqlite3"
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 2, 3):
                raise ValueError(f"registry version {version} is not supported by this FaintMark")
            db.execute(SCHEMA)
            if version == 2:
                db.execute("ALTER TABLE copies ADD COLUMN phash TEXT")
            db.execute("PRAGMA user_version = 3")
        with suppress(OSError):
            os.chmod(self._registry, 0o600)

    def _connect(self):
        # One connection per call: sqlite3 connections are bound to their creating thread
        return closing(sqlite3.connect(self._registry))

    def mark(
        self,
        image: str | Path,
        recipients: list[str],
        output_dir: str | Path | None = None,
        format: Literal["png", "jpeg", "webp"] | None = None,
    ) -> MarkResult:
        names = [name.strip() for name in recipients]
        if not 1 <= len(names) <= MAX_RECIPIENTS:
            raise ValueError(f"give 1 to {MAX_RECIPIENTS} recipients")
        if not all(1 <= len(name) <= MAX_NAME and name.isprintable() for name in names):
            raise ValueError(f"recipient names must be 1 to {MAX_NAME} printable characters")
        source = Path(image).expanduser()
        cover, fmt, jpeg, icc = _read(source)
        target = format or DEFAULT_TARGET[fmt]
        attempts = {"jpeg": [jpeg, JPEG_Q95], "png": [{}], "webp": [{"quality": 90}]}[target]
        attempts = [{**params, "icc_profile": icc} if icc else params for params in attempts]
        out = Path(output_dir).expanduser() if output_dir else source.resolve().parent / "marked"
        out = out.resolve()
        out.mkdir(parents=True, exist_ok=True)
        marked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        stem = _safe(source.stem)
        created = []
        copies = []
        hashes = []
        with self._connect() as db:
            try:
                for recipient in names:
                    value = _unused_id(db, {c["id"] for c in copies})
                    copy_id = f"{value:010x}"
                    marked = self.engine.encode(cover.copy(), value)
                    data, saved, attempt = _verified(
                        self.engine, marked, value, target, attempts, source.name
                    )
                    path = out / f"{stem}-{copy_id}{EXTENSIONS[target]}"
                    with open(path, "xb") as file:
                        created.append(path)
                        file.write(data)
                    warnings = _preflight(self.engine, saved, value)
                    if attempt:
                        warnings.append(
                            "saved at JPEG quality 95; the source settings lost the mark"
                        )
                    copies.append(
                        dict(id=copy_id, recipient=recipient, path=str(path), warnings=warnings)
                    )
                    hashes.append(f"{_phash(saved):016x}")
                rows = [
                    dict(
                        c,
                        original=source.name,
                        at=marked_at,
                        warnings=json.dumps(c["warnings"]),
                        phash=phash,
                    )
                    for c, phash in zip(copies, hashes)
                ]
                with db:
                    db.executemany(INSERT, rows)
            except BaseException:
                for path in created:
                    with suppress(OSError):
                        path.unlink()
                raise
        return {"original": source.name, "output_dir": str(out), "copies": copies}

    def check(self, image: str | Path, files: bool = False) -> CheckResult:
        path = Path(image).expanduser()
        with _open(path) as opened:
            if opened.width * opened.height > MAX_CHECK_PIXELS:
                raise ValueError(f"{path.name}: larger than 100 megapixels")
            rgb = _rgb(opened)
        value = self.engine.decode(rgb)
        if value is None:
            return {"status": "not_detected"}
        copy_id = f"{value:010x}"
        with self._connect() as db:
            row = db.execute(
                "SELECT recipient, original, path, marked_at, phash FROM copies WHERE id = ?",
                (copy_id,),
            ).fetchone()
        if row is None:
            return {"status": "unregistered", "id": copy_id}
        recipient, original, issued, marked_at, phash = row
        result: CheckResult = {
            "status": "matched",
            "id": copy_id,
            "recipient": recipient,
            "marked_at": marked_at,
        }
        if phash:  # registries from before version 3 have no hash
            distance = bin(_phash(rgb) ^ int(phash, 16)).count("1")
            result["same_image"] = distance <= SAME_IMAGE
        if files:
            result.update(original=original, path=issued)
        return result

    def list_copies(self, limit: int = 100, files: bool = False) -> ListResult:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, recipient, marked_at, warnings, original, path FROM copies "
                "ORDER BY rowid DESC LIMIT ?",
                (max(limit, 0),),
            ).fetchall()
        copies = []
        for copy_id, recipient, marked_at, warnings, original, path in rows:
            copy: ListedCopy = {
                "id": copy_id,
                "recipient": recipient,
                "marked_at": marked_at,
                "warnings": json.loads(warnings),
            }
            if files:
                copy.update(original=original, path=path)
            copies.append(copy)
        return {"copies": copies}
