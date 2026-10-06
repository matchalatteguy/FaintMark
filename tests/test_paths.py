from pathlib import Path

from faintmark.paths import resolve_home


def test_legacy_registry_is_reused_without_moving_it(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("FAINTMARK_HOME", raising=False)
    monkeypatch.delenv("COPYMARK_HOME", raising=False)
    legacy = tmp_path / ".copymark"
    legacy.mkdir()
    database = legacy / "registry.sqlite3"
    database.write_bytes(b"existing records")
    assert resolve_home() == legacy
    assert database.read_bytes() == b"existing records"
    current = tmp_path / ".faintmark"
    current.mkdir()
    (current / "registry.sqlite3").touch()
    assert resolve_home() == current


def test_explicit_home_and_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("COPYMARK_HOME", str(tmp_path / "old-config"))
    monkeypatch.delenv("FAINTMARK_HOME", raising=False)
    assert resolve_home() == tmp_path / "old-config"
    monkeypatch.setenv("FAINTMARK_HOME", str(tmp_path / "new-config"))
    assert resolve_home() == tmp_path / "new-config"
    assert resolve_home(tmp_path / "explicit") == tmp_path / "explicit"
