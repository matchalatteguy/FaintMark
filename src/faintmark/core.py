"""Private local recipient-copy registry and lossless verified exports."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from .engine import Engine


class FaintMark:
    def __init__(self, home=None, engine=None):
        self.home = Path(home or os.environ.get("FAINTMARK_HOME") or Path.home() / ".faintmark").expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.home / "thumbnails").mkdir(exist_ok=True, mode=0o700)
        self.engine = engine if engine is not None else Engine(self.home / "models")
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.home / "registry.sqlite3", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self._db.close()
            raise ValueError(f"Unsupported registry version {version}; update FaintMark first.")
        self._db.execute("PRAGMA user_version=1")
        self._db.executescript("""CREATE TABLE IF NOT EXISTS batches (batch_id TEXT PRIMARY KEY, original_sha256 TEXT NOT NULL, original_name TEXT NOT NULL, thumbnail_path TEXT NOT NULL, created_at TEXT NOT NULL, variant TEXT NOT NULL, schema INTEGER NOT NULL, strength REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS copies (copy_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(batch_id), recipient TEXT NOT NULL, path TEXT NOT NULL, warnings TEXT NOT NULL);""")
        self._db.commit()
        os.chmod(self.home / "registry.sqlite3", 0o600)

    @staticmethod
    def _image(path, marking=False):
        with Image.open(path) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError("Images must contain at most 25 million pixels.")
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Choose a JPEG, PNG, or WebP image.")
            if getattr(image, "is_animated", False):
                raise ValueError("Animated images are not supported.")
            if marking:
                if "A" in image.getbands() or "transparency" in image.info:
                    raise ValueError(
                        "Transparent images are not supported; supply an opaque RGB image."
                    )
                if image.mode not in ("RGB", "L"):
                    raise ValueError("Supply an RGB or grayscale image.")
                icc = image.info.get("icc_profile")
                if icc:
                    try:
                        description = ImageCms.getProfileDescription(
                            ImageCms.ImageCmsProfile(BytesIO(icc))
                        )
                    except Exception as error:
                        raise ValueError(
                            "Unrecognized color profile; supply an sRGB image."
                        ) from error
                    if "srgb" not in description.lower():
                        raise ValueError(
                            "Non-sRGB color profiles are not supported; convert to sRGB first."
                        )
            return ImageOps.exif_transpose(image).convert("RGB")

    @staticmethod
    def _save_exclusive(path, image):
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        FaintMark._write_exclusive(path, buffer.getvalue())

    @staticmethod
    def _write_exclusive(path, data):
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".faintmark-")
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.link(temp, path)  # Atomic creation; never replace a preexisting file.
        finally:
            Path(temp).unlink(missing_ok=True)

    @staticmethod
    def _safe_component(value):
        value = re.sub(r"[^\w.-]+", "-", value.strip()).strip(".-")
        return value.encode("utf-8")[:80].decode("utf-8", errors="ignore") or "image"

    @staticmethod
    def _publish_archive(path, populate):
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".faintmark-zip-")
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                populate(archive)
            with open(temporary, "rb") as source:
                os.fsync(source.fileno())
            os.link(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def mark(self, image, recipients, output_dir, preflight=True, create_archive=False):
        if len(recipients) > 100:
            raise ValueError("A batch supports at most 100 recipients.")
        if any(isinstance(r, str) and len(r) > 200 for r in recipients):
            raise ValueError("Recipient names must contain at most 200 characters.")
        if not recipients or any(not isinstance(r, str) or not r.strip() for r in recipients):
            raise ValueError("Provide at least one nonempty recipient name.")
        source = Path(image).expanduser().resolve()
        cover = self._image(source, marking=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        batch = secrets.token_hex(12)
        created = datetime.now(timezone.utc).isoformat()
        thumb_path = self.home / "thumbnails" / (batch + ".png")
        zip_path = output / ("faintmark-" + batch + ".zip")
        made = []
        copies = []
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                thumbnail = cover.copy()
                thumbnail.thumbnail((320, 320))
                self._save_exclusive(thumb_path, thumbnail)
                made.append(thumb_path)
                self._db.execute(
                    "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?)",
                    (batch, digest, source.name, str(thumb_path), created, "Q", 0, 1.0),
                )
                for recipient in recipients:
                    while True:
                        value = secrets.randbits(40)
                        copy_id = f"{value:010x}"
                        if not self._db.execute(
                            "SELECT 1 FROM copies WHERE copy_id=?", (copy_id,)
                        ).fetchone():
                            break
                    safe = self._safe_component(recipient)
                    stem = self._safe_component(source.stem)
                    path = output / f"{stem}-{safe}-{copy_id}.png"
                    marked = self.engine.encode(cover.copy(), value)
                    self._save_exclusive(path, marked)
                    made.append(path)
                    saved = self._image(path)
                    if self.engine.decode(saved) != value:
                        raise RuntimeError(
                            "The saved watermark could not be verified; no copies were registered."
                        )
                    warnings = []
                    if preflight:
                        for label, size in [
                            ("JPEG quality 70", saved.size),
                            (
                                "half-size JPEG quality 70",
                                (max(1, saved.width // 2), max(1, saved.height // 2)),
                            ),
                        ]:
                            buffer = BytesIO()
                            saved.resize(size, Image.Resampling.LANCZOS).save(
                                buffer, format="JPEG", quality=70
                            )
                            buffer.seek(0)
                            with Image.open(buffer) as transformed:
                                if self.engine.decode(transformed.convert("RGB")) != value:
                                    warnings.append(f"Watermark did not survive {label}.")
                    item = dict(
                        copy_id=copy_id,
                        recipient=recipient.strip(),
                        path=str(path),
                        warnings=warnings,
                    )
                    copies.append(item)
                    self._db.execute(
                        "INSERT INTO copies VALUES (?,?,?,?,?)",
                        (copy_id, batch, item["recipient"], str(path), json.dumps(warnings)),
                    )

                if create_archive:

                    def populate_archive(archive):
                        for item in copies:
                            archive.write(item["path"], Path(item["path"]).name)

                    self._publish_archive(zip_path, populate_archive)
                    made.append(zip_path)
                self._db.commit()
            except BaseException:
                self._db.rollback()
                for path in reversed(made):
                    path.unlink(missing_ok=True)
                raise
        result = dict(batch_id=batch, original_sha256=digest, copies=copies, output_dir=str(output))
        if create_archive:
            result["zip_path"] = str(zip_path)
        return result

    def _thumbnail_path(self, value):
        path = Path(value)
        if not path.is_absolute():
            path = (self.home / path).resolve()
            if not path.is_relative_to(self.home):
                raise ValueError("Registry thumbnail path escapes the private home.")
        return str(path)

    def check(self, image):
        value = self.engine.decode(self._image(image))
        result = dict(
            status="inconclusive",
            copy_id=None,
            recipient=None,
            created_at=None,
            original_name=None,
            thumbnail_path=None,
        )
        if value is None:
            return result
        if not isinstance(value, int) or not 0 <= value < 2**40:
            return result
        copy_id = f"{value:010x}"
        with self._lock:
            row = self._db.execute(
                "SELECT c.*, b.created_at,b.original_name,b.thumbnail_path FROM copies c JOIN batches b USING(batch_id) WHERE copy_id=?",
                (copy_id,),
            ).fetchone()
        result.update(status="unknown", copy_id=copy_id)
        if row:
            result.update(
                status="matched",
                **{
                    key: row[key]
                    for key in ("recipient", "created_at", "original_name", "thumbnail_path")
                },
            )
        if result["thumbnail_path"] is not None:
            result["thumbnail_path"] = self._thumbnail_path(result["thumbnail_path"])
        return result

    def list_copies(self, limit=100):
        with self._lock:
            rows = self._db.execute(
                "SELECT c.*,b.created_at,b.original_name,b.original_sha256,b.thumbnail_path FROM copies c JOIN batches b USING(batch_id) ORDER BY b.created_at DESC,c.rowid DESC LIMIT ?",
                (max(0, int(limit)),),
            ).fetchall()
        return [
            dict(
                row,
                warnings=json.loads(row["warnings"]),
                thumbnail_path=self._thumbnail_path(row["thumbnail_path"]),
            )
            for row in rows
        ]

    def backup(self, destination):
        path = Path(destination).expanduser().resolve()
        if path.is_dir():
            path = path / f"faintmark-backup-{secrets.token_hex(8)}.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "registry.sqlite3"
            db = sqlite3.connect(snapshot)
            try:
                self._db.backup(db)
                thumbnail_paths = [
                    row[0] for row in db.execute("SELECT thumbnail_path FROM batches")
                ]
                for original_path in thumbnail_paths:
                    db.execute(
                        "UPDATE batches SET thumbnail_path=? WHERE thumbnail_path=?",
                        ("thumbnails/" + Path(original_path).name, original_path),
                    )
                db.commit()
            finally:
                db.close()

            def populate_archive(archive):
                archive.write(snapshot, "registry.sqlite3")
                archive.writestr(
                    "format.json",
                    json.dumps(
                        {
                            "format": "faintmark-backup",
                            "version": 1,
                            "thumbnail_paths": "thumbnails/<batch_id>.png",
                        }
                    ),
                )
                for thumbnail_path in thumbnail_paths:
                    thumbnail = Path(self._thumbnail_path(thumbnail_path))
                    archive.write(thumbnail, "thumbnails/" + thumbnail.name)

            self._publish_archive(path, populate_archive)
        return str(path)
