import re
import sqlite3
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, JpegImagePlugin, UnidentifiedImageError

from faintmark import engine
from faintmark.core import FaintMark


@pytest.fixture
def app(home):
    return FaintMark()


@pytest.mark.parametrize(
    "name, save, fmt, suffix",
    [
        ("photo.jpg", {"quality": 85, "subsampling": 0}, None, ".jpg"),
        ("photo.png", {}, None, ".png"),
        ("photo.webp", {"quality": 80}, None, ".webp"),
        ("photo.jpg", {"format": "MPO", "quality": 85}, None, ".jpg"),
        ("photo.jpg", {"quality": 85}, "png", ".png"),
    ],
)
def test_output_keeps_the_source_format(app, make_image, icc, name, save, fmt, suffix):
    source = make_image(name, icc_profile=icc, **save)
    result = app.mark(source, ["alice", "bob"], format=fmt)

    assert result["original"] == name
    assert result["output_dir"] == str(source.parent.resolve() / "marked")
    copy = result["copies"][0]
    path = Path(copy["path"])
    assert re.fullmatch(r"[0-9a-f]{10}", copy["id"])
    assert path.name == f"photo-{copy['id']}{suffix}"
    with Image.open(path) as saved:
        assert saved.format == {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[suffix]
        assert saved.info["icc_profile"] == icc
        if suffix == ".jpg":
            with Image.open(source) as original:
                assert saved.quantization == original.quantization
                assert JpegImagePlugin.get_sampling(saved) == JpegImagePlugin.get_sampling(original)
            if "format" not in save:  # an MPO source file holds two frames
                assert 0.5 < path.stat().st_size / source.stat().st_size < 1.3
    assert copy["warnings"] == ["may not survive resizing to 64px"]
    checked = app.check(path)
    assert (checked["status"], checked["recipient"], checked["id"]) == (
        "matched",
        "alice",
        copy["id"],
    )


def test_heic_becomes_jpeg(app, make_image):
    pytest.importorskip("pillow_heif")
    copy = app.mark(make_image("photo.heic", quality=80), ["alice"])["copies"][0]
    path = Path(copy["path"])
    assert (path.parent.name, path.name) == ("marked", f"photo-{copy['id']}.jpg")
    with Image.open(path) as saved:
        assert saved.format == "JPEG"
    assert app.check(path)["recipient"] == "alice"


@pytest.mark.parametrize("slot", [0, 1, 3])
def test_grayscale_jpeg_keeps_its_single_table(app, tmp_path, slot):
    source = tmp_path / "scan.jpg"
    Image.fromarray(np.tile(np.linspace(0, 200, 128).astype(np.uint8), (96, 1))).save(
        source, quality=80
    )
    data = bytearray(source.read_bytes())  # move the table: its id in DQT and in the SOF component
    data[data.index(b"\xff\xdb") + 4] = data[data.index(b"\xff\xc0") + 12] = slot
    source.write_bytes(data)
    with Image.open(source) as original:
        [table] = original.quantization.values()
        assert list(original.quantization) == [slot]
    copy = app.mark(source, ["alice"])["copies"][0]
    with Image.open(copy["path"]) as saved:
        assert (saved.mode, saved.quantization) == ("RGB", {0: table})
    assert app.check(copy["path"])["recipient"] == "alice"


def test_transparency_is_rejected_and_opaque_alpha_is_dropped(app, tmp_path):
    seethrough = Image.new("RGBA", (128, 96), (10, 20, 30, 255))
    seethrough.putpixel((5, 5), (10, 20, 30, 254))
    seethrough.save(tmp_path / "clear.png")
    with pytest.raises(ValueError, match="^clear.png: has transparency; flatten it first$"):
        app.mark(tmp_path / "clear.png", ["alice"])

    Image.new("RGBA", (128, 96), (10, 20, 30, 255)).save(tmp_path / "opaque.png")
    copy = app.mark(tmp_path / "opaque.png", ["alice"])["copies"][0]
    with Image.open(copy["path"]) as saved:
        assert saved.mode == "RGB"


def test_check_reports_each_status(app, make_image, tmp_path, monkeypatch):
    copy = app.mark(make_image("photo.png"), ["alice"])["copies"][0]

    matched = app.check(copy["path"])
    assert matched.pop("marked_at").endswith("Z")
    assert matched == {
        "status": "matched",
        "id": copy["id"],
        "recipient": "alice",
        "same_image": True,
    }
    with_files = app.check(copy["path"], files=True)
    assert (with_files["original"], with_files["path"]) == ("photo.png", copy["path"])
    assert "original" not in app.list_copies()["copies"][0]
    assert app.list_copies(files=True)["copies"][0]["path"] == copy["path"]
    other = FaintMark(tmp_path / "other")
    assert other.check(copy["path"]) == {"status": "unregistered", "id": copy["id"]}
    monkeypatch.setattr(app.engine, "decode", lambda image: None)
    assert app.check(copy["path"]) == {"status": "not_detected"}


def test_existing_files_are_never_overwritten(app, make_image, monkeypatch):
    source = make_image("photo.png")
    monkeypatch.setattr("faintmark.core.secrets.randbits", lambda bits: 0x0123456789)
    taken = source.parent / "marked" / "photo-0123456789.png"
    taken.parent.mkdir()
    taken.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        app.mark(source, ["alice"])
    assert taken.read_bytes() == b"keep"
    assert app.list_copies() == {"copies": []}


def test_failed_verification_registers_nothing_and_removes_files(app, make_image, monkeypatch):
    source = make_image("photo.png")
    marked = source.parent / "marked"
    encode = app.engine.encode

    def encode_second_copy_unmarked(image, value):
        written = list(marked.iterdir())
        if written:
            assert len(written) == 1  # alice's copy was written before bob's fails
            return image
        return encode(image, value)

    monkeypatch.setattr(app.engine, "encode", encode_second_copy_unmarked)
    with pytest.raises(RuntimeError, match="^photo.png: watermark could not be verified"):
        app.mark(source, ["alice", "bob"])

    assert list(marked.iterdir()) == []
    assert app.list_copies() == {"copies": []}


def test_ids_drawn_twice_in_one_batch_are_redrawn(app, make_image, monkeypatch):
    draws = iter([7, 7, 8])
    monkeypatch.setattr("faintmark.core.secrets.randbits", lambda bits: next(draws))
    copies = app.mark(make_image("photo.png"), ["alice", "bob"])["copies"]
    assert [copy["id"] for copy in copies] == ["0000000007", "0000000008"]


def test_jpeg_is_resaved_at_quality_95_when_verification_fails(app, make_image, monkeypatch):
    source = make_image("photo.jpg", quality=60, subsampling=2)
    decode = app.engine.decode
    calls = []

    def fail_first(image):
        calls.append(image)
        return None if len(calls) == 2 else decode(image)  # call 1 inspects the cover

    monkeypatch.setattr(app.engine, "decode", fail_first)
    copy = app.mark(source, ["alice"])["copies"][0]

    assert copy["warnings"][-1].startswith("saved at JPEG quality 95")
    reference = BytesIO()
    Image.new("RGB", (8, 8)).save(reference, format="JPEG", quality=95)
    with Image.open(copy["path"]) as saved, Image.open(reference) as q95:
        assert saved.quantization == q95.quantization


def test_input_limits(app, make_image, tmp_path, monkeypatch):
    source = make_image("photo.png")
    copy = app.mark(source, ["alice"])["copies"][0]

    for recipients in ([], ["x"] * 101):
        with pytest.raises(ValueError, match="^give 1 to 100 recipients$"):
            app.mark(source, recipients)
    for recipients in (["x" * 201], ["  "], ["a\nb"]):
        with pytest.raises(ValueError, match="^recipient names must be 1 to 200 printable char"):
            app.mark(source, recipients)
    Image.new("I;16", (128, 96), 40000).save(tmp_path / "scan.png")
    with pytest.raises(ValueError, match="^scan.png: 16-bit images are not supported"):
        app.mark(tmp_path / "scan.png", ["alice"])
    Image.new("CMYK", (128, 96)).save(tmp_path / "print.jpg")
    with pytest.raises(
        ValueError, match="^print.jpg: CMYK images are not supported; convert to RGB$"
    ):
        app.mark(tmp_path / "print.jpg", ["alice"])
    Image.new("P", (8, 8)).save(tmp_path / "icon.gif")
    with pytest.raises(ValueError, match=r"^icon.gif: unsupported format GIF; use JPEG, PNG"):
        app.mark(tmp_path / "icon.gif", ["alice"])

    with pytest.raises(ValueError, match="^limit must be 0 or more$"):
        app.list_copies(-1)

    monkeypatch.setattr("faintmark.core.MAX_PIXELS", 100)
    with pytest.raises(ValueError, match="^photo.png: larger than 25 megapixels$"):
        app.mark(source, ["alice"])
    assert app.check(copy["path"])["status"] == "matched"


def test_exif_orientation_is_applied_and_not_copied(app, make_image):
    exif = Image.Exif()
    exif[274] = 6  # rotate 90 degrees clockwise on display
    source = make_image("photo.jpg", size=(192, 128), quality=90, exif=exif.tobytes())
    copy = app.mark(source, ["alice"])["copies"][0]
    with Image.open(copy["path"]) as saved:
        assert saved.size == (128, 192)
        assert not saved.getexif()
    assert app.check(copy["path"])["recipient"] == "alice"


def test_registry_failure_removes_the_written_files(app, make_image, monkeypatch):
    source = make_image("photo.png")
    monkeypatch.setattr("faintmark.core.INSERT", "INSERT INTO nowhere VALUES (:id)")
    with pytest.raises(sqlite3.OperationalError):
        app.mark(source, ["alice", "bob"])
    assert list((source.parent / "marked").iterdir()) == []


def test_tampered_model_download_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "cdn"
    source.mkdir()
    for name in engine.MODEL_HASHES:
        (source / name).write_bytes(b"not the model")
    monkeypatch.setattr(engine, "MODEL_URL", source.as_uri() + "/")
    with pytest.raises(RuntimeError, match="^model checksum mismatch: encoder_Q.onnx$"):
        engine.ensure_models(tmp_path / "models")
    assert list((tmp_path / "models").iterdir()) == []
    monkeypatch.setattr(engine, "MAX_MODEL_BYTES", 8)
    with pytest.raises(RuntimeError, match="^model download larger than expected: encoder_Q.onnx$"):
        engine.ensure_models(tmp_path / "models")
    assert list((tmp_path / "models").iterdir()) == []


def test_an_id_copied_into_another_picture_is_flagged(app, make_image, tmp_path):
    source = make_image("photo.png", size=(512, 384))  # the stub's grid is a small part of it
    copy = app.mark(source, ["alice"])["copies"][0]
    with Image.open(source) as image:  # a different picture: the negative of the source
        other = Image.fromarray(255 - np.asarray(image.convert("RGB")))
    forged = app.engine.encode(other, int(copy["id"], 16))
    forged.save(tmp_path / "forged.png")
    assert app.check(copy["path"])["same_image"] is True
    assert app.check(tmp_path / "forged.png") == {
        "status": "matched",
        "id": copy["id"],
        "recipient": "alice",
        "marked_at": app.check(copy["path"])["marked_at"],
        "same_image": False,
    }


@pytest.mark.parametrize("version", [0, 2, 7])
def test_unsupported_registries_are_refused(home, version):
    home.mkdir()
    with sqlite3.connect(home / "registry.sqlite3") as db:
        db.execute("CREATE TABLE copies (id TEXT)")  # version 0 with a table was not made by us
        db.execute(f"PRAGMA user_version = {version}")
    with pytest.raises(ValueError, match=f"^registry version {version} is not supported"):
        FaintMark()


def test_heic_without_the_extra_is_explained(app, tmp_path, monkeypatch):
    def unreadable(path):
        raise UnidentifiedImageError

    monkeypatch.setattr("faintmark.core.Image.open", unreadable)
    monkeypatch.delitem(Image.OPEN, "HEIF", raising=False)
    with pytest.raises(ValueError, match=r"^photo.heic: HEIC needs the heic extra \(install"):
        app.check(tmp_path / "photo.heic")


def test_marking_a_marked_image_replaces_the_mark_and_says_so(app, make_image):
    first = app.mark(make_image("photo.png"), ["alice"])["copies"][0]
    second = app.mark(first["path"], ["bob"])["copies"][0]
    assert second["warnings"][0] == f"replaced an existing mark, id {first['id']}"
    assert app.check(second["path"])["recipient"] == "bob"


def test_deep_check_undoes_a_flip_and_names_suspects(app, make_image, tmp_path):
    copy = app.mark(make_image("photo.png"), ["alice"])["copies"][0]
    with Image.open(copy["path"]) as image:
        image.transpose(Image.FLIP_LEFT_RIGHT).save(tmp_path / "flipped.png")
        damaged = np.array(image.convert("RGB"))
    assert app.check(tmp_path / "flipped.png") == {"status": "not_detected"}
    recovered = app.check(tmp_path / "flipped.png", deep=True)
    assert (recovered["status"], recovered["recipient"], recovered["transform"]) == (
        "matched",
        "alice",
        "flipped",
    )

    damaged[:16, :40] = 255 - damaged[:16, :40]  # ten grid blocks inverted: beyond BCH's eight
    Image.fromarray(damaged).save(tmp_path / "damaged.png")
    assert app.check(tmp_path / "damaged.png") == {"status": "not_detected"}
    deep = app.check(tmp_path / "damaged.png", deep=True)
    assert isinstance(deep["suspects"][0].pop("same_image"), bool)  # the stub's grid is visible
    assert deep == {
        "status": "not_detected",
        "suspects": [{"id": copy["id"], "recipient": "alice", "bit_errors": 10}],
        "registry_size": 1,
    }
    assert FaintMark(tmp_path / "other").check(tmp_path / "damaged.png", deep=True) == {
        "status": "not_detected",
        "suspects": [],
        "registry_size": 0,
    }


def test_deep_check_keeps_an_unregistered_id_found_after_a_flip(app, make_image, tmp_path):
    copy = app.mark(make_image("photo.png"), ["alice"])["copies"][0]
    with Image.open(copy["path"]) as image:
        image.transpose(Image.FLIP_LEFT_RIGHT).save(tmp_path / "flipped.png")
    other = FaintMark(tmp_path / "other")
    assert other.check(tmp_path / "flipped.png", deep=True) == {
        "status": "unregistered",
        "id": copy["id"],
        "transform": "flipped",
    }
