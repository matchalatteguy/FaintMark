import hashlib
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from copymark.core import CopyMark


class Stub:
    def encode(self, image, value):
        data = value.to_bytes(5, "big")
        for x, byte in enumerate(data):
            image.putpixel((x, 0), (byte, 0, 0))
        return image

    def decode(self, image):
        return int.from_bytes(bytes(image.getpixel((x, 0))[0] for x in range(5)), "big")


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "original.png"
    Image.new("RGB", (64, 64), "white").save(source)
    return CopyMark(tmp_path / "private", engine=Stub()), source, tmp_path / "out"


def test_mark_isolation_original_backup(setup, tmp_path):
    app, source, output = setup
    original = source.read_bytes()
    result = app.mark(source, ["A / person", "A / person"], output, preflight=False)
    assert source.read_bytes() == original
    assert result["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert len({x["copy_id"] for x in result["copies"]}) == 2
    assert all(len(x["copy_id"]) == 10 for x in result["copies"])
    assert result["output_dir"] == str(output)
    assert "zip_path" not in result
    assert len(list(output.iterdir())) == 2
    assert all(path.suffix == ".png" for path in output.iterdir())
    copy = result["copies"][0]
    assert app.check(copy["path"])["recipient"] == "A / person"
    isolated = CopyMark(tmp_path / "other", engine=Stub())
    assert isolated.check(copy["path"])["status"] == "unknown"
    assert isolated.check(copy["path"])["recipient"] is None
    backup = app.backup(tmp_path / "backup.zip")
    with zipfile.ZipFile(backup) as z:
        assert "registry.sqlite3" in z.namelist()
        assert any(x.startswith("thumbnails/") for x in z.namelist())
        assert all("models" not in x and "original.png" not in x for x in z.namelist())
    with pytest.raises(FileExistsError):
        app.backup(backup)


def test_rollback(setup):
    app, source, output = setup
    app.engine.decode = lambda image: None
    with pytest.raises(RuntimeError):
        app.mark(source, ["Person"], output)
    assert app.list_copies() == []
    assert list(output.iterdir()) == []
    assert list((app.home / "thumbnails").iterdir()) == []
    assert app.check(source)["status"] == "inconclusive"


def test_reject_alpha(setup):
    app, source, output = setup
    Image.new("RGBA", (64, 64)).save(source)
    with pytest.raises(ValueError, match="Transparent"):
        app.mark(source, ["Person"], output)


def test_preflight_reports_real_failures(setup):
    app, source, output = setup
    result = app.mark(source, ["Person"], output)
    assert result["copies"][0]["warnings"]


def test_input_limits_before_inference(setup):
    app, source, output = setup
    with pytest.raises(ValueError, match="100 recipients"):
        app.mark(source, ["Person"] * 101, output)
    with pytest.raises(ValueError, match="200 characters"):
        app.mark(source, ["x" * 201], output)


def test_backup_thumbnail_paths_are_portable(setup, tmp_path):
    import sqlite3

    app, source, output = setup
    app.mark(source, ["Person"], output, preflight=False)
    with zipfile.ZipFile(app.backup(tmp_path / "snapshot.zip")) as z:
        database = tmp_path / "snapshot.sqlite3"
        database.write_bytes(z.read("registry.sqlite3"))
    with sqlite3.connect(database) as db:
        path = db.execute("SELECT thumbnail_path FROM batches").fetchone()[0]
        assert path.startswith("thumbnails/") and not Path(path).is_absolute()


def test_existing_copy_is_not_overwritten(setup, monkeypatch):
    app, source, output = setup
    output.mkdir()
    existing = output / "original-Person-0000000001.png"
    existing.write_bytes(b"preserve me")
    monkeypatch.setattr("copymark.core.secrets.randbits", lambda bits: 1)
    with pytest.raises(FileExistsError):
        app.mark(source, ["Person"], output, preflight=False)
    assert existing.read_bytes() == b"preserve me"
    assert app.list_copies() == []
    assert not list((app.home / "thumbnails").iterdir())


def test_identifier_collisions_retry(setup, monkeypatch):
    app, source, output = setup
    identifiers = iter([1, 1, 2])
    monkeypatch.setattr("copymark.core.secrets.randbits", lambda bits: next(identifiers))
    copies = app.mark(source, ["Person", "Person"], output, preflight=False)["copies"]
    assert [copy["copy_id"] for copy in copies] == ["0000000001", "0000000002"]


def test_manually_restored_backup_resolves_thumbnails(setup, tmp_path):
    app, source, output = setup
    copy = app.mark(source, ["Person"], output, preflight=False)["copies"][0]
    restore_home = tmp_path / "restored"
    with zipfile.ZipFile(app.backup(tmp_path / "restore.zip")) as z:
        z.extractall(restore_home)
    restored = CopyMark(restore_home, engine=Stub())
    thumbnail = Path(restored.check(copy["path"])["thumbnail_path"])
    assert thumbnail.is_relative_to(restore_home) and thumbnail.exists()
    assert restored.list_copies()[0]["thumbnail_path"] == str(thumbnail)
    restored._db.execute("UPDATE batches SET thumbnail_path='../outside.png'")
    restored._db.commit()
    with pytest.raises(ValueError, match="escapes"):
        restored.list_copies()
    with pytest.raises(ValueError, match="escapes"):
        restored.check(copy["path"])


def test_registry_version(setup, tmp_path):
    import sqlite3

    app, source, output = setup
    assert app._db.execute("PRAGMA user_version").fetchone()[0] == 1
    home = tmp_path / "future"
    home.mkdir()
    with sqlite3.connect(home / "registry.sqlite3") as db:
        db.execute("PRAGMA user_version=2")
    with pytest.raises(ValueError, match="Unsupported registry version 2"):
        CopyMark(home, engine=Stub())


def test_long_unicode_names_export_within_filesystem_limits(setup):
    app, source, output = setup
    renamed = source.with_name("界" * 70 + ".png")
    source.rename(renamed)
    copies = app.mark(renamed, ["人" * 100], output, preflight=False, create_archive=True)["copies"]
    exported = Path(copies[0]["path"])
    assert exported.exists()
    assert len(exported.name.encode("utf-8")) <= 240
    archive = next(output.glob("copymark-*.zip"))
    with zipfile.ZipFile(archive) as z:
        assert z.namelist() == [exported.name]
    assert not list(output.glob(".copymark-*"))


def test_streamed_archive_collision_rolls_back_without_overwrite(setup, monkeypatch):
    app, source, output = setup
    output.mkdir()
    archive = output / "copymark-fixed-batch.zip"
    archive.write_bytes(b"preserve archive")
    monkeypatch.setattr("copymark.core.secrets.token_hex", lambda count: "fixed-batch")
    with pytest.raises(FileExistsError):
        app.mark(source, ["Person"], output, preflight=False, create_archive=True)
    assert archive.read_bytes() == b"preserve archive"
    assert list(output.iterdir()) == [archive]
    assert app.list_copies() == []
    assert not list((app.home / "thumbnails").iterdir())
