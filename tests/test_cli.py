import json
import re
from importlib.metadata import version
from types import SimpleNamespace

import pytest

from faintmark.cli import main


def run(capsys, *argv):
    code = main([str(arg) for arg in argv])
    out, err = capsys.readouterr()
    return code, out, err


def test_mark_json_shape_and_positional_recipients(home, make_image, capsys):
    source = make_image("photo.png")
    code, out, err = run(capsys, "mark", source, "alice", "bob", "--json")

    assert (code, err) == (0, "")
    result = json.loads(out)
    assert list(result) == ["original", "output_dir", "copies"]
    assert [copy["recipient"] for copy in result["copies"]] == ["alice", "bob"]
    assert all(list(copy) == ["id", "recipient", "path", "warnings"] for copy in result["copies"])


def test_mark_check_and_list_human_output(home, make_image, capsys, tmp_path):
    assert run(capsys, "list") == (0, "no copies\n", "")
    assert run(capsys, "list", "--json") == (0, '{\n  "copies": []\n}\n', "")

    source = make_image("photo.png")
    out_dir = tmp_path / "out"
    code, out, err = run(capsys, "mark", source, "alice", "bob", "-o", out_dir)

    first, second, summary = out.splitlines()
    assert (code, summary) == (0, f"2 copies in {out_dir.resolve()}")
    alice = re.fullmatch(r"alice  ([0-9a-f]{10})  (.+)", first)
    assert alice and second.startswith("bob  ")
    assert err == "  warning: may not survive resizing to 64px\n" * 2

    code, out, _ = run(capsys, "check", alice[2])
    pattern = rf"matched: alice  {alice[1]}  marked \d{{4}}-\d\d-\d\dT[\d:]{{8}}Z\n"
    assert code == 0 and re.fullmatch(pattern, out)
    code, out, _ = run(capsys, "check", alice[2], "--files")
    assert code == 0 and f"  {alice[1]}  photo.png  marked " in out

    code, out, _ = run(capsys, "list", "-n", 1)
    assert (code, len(out.splitlines())) == (0, 1)
    assert out.startswith(f"{second.split()[1]}  bob  2")
    assert run(capsys, "list", "-n", 1, "--files")[1].startswith(
        f"{second.split()[1]}  bob  photo.png  "
    )


def test_check_exits_1_without_a_match(home, make_image, capsys, tmp_path, monkeypatch):
    marked = json.loads(run(capsys, "mark", make_image("photo.png"), "alice", "--json")[1])
    path = marked["copies"][0]["path"]
    assert run(capsys, "check", path)[0] == 0

    monkeypatch.setenv("FAINTMARK_HOME", str(tmp_path / "other"))
    code, out, _ = run(capsys, "check", path)
    assert code == 1 and re.fullmatch(r"unregistered: [0-9a-f]{10} is not in this registry\n", out)

    monkeypatch.setattr(
        "faintmark.core.Engine", lambda models_dir: SimpleNamespace(decode=lambda image: None)
    )
    assert run(capsys, "check", path) == (1, "not detected\n", "")
    assert run(capsys, "check", path, "--json") == (1, '{\n  "status": "not_detected"\n}\n', "")


def test_errors_exit_with_2(home, tmp_path, capsys):
    assert run(capsys, "mark", "missing.jpg", "alice") == (
        2,
        "",
        "faintmark: missing.jpg: no such file\n",
    )
    (tmp_path / "notes.txt").write_text("hello")
    assert run(capsys, "check", tmp_path / "notes.txt") == (
        2,
        "",
        "faintmark: notes.txt: not an image\n",
    )
    assert run(capsys, "mark", "missing.jpg", "alice", "--json") == (
        2,
        '{"error": "missing.jpg: no such file"}\n',
        "",
    )
    with pytest.raises(SystemExit) as usage:
        main(["mark", "photo.jpg"])
    assert usage.value.code == 2
    with pytest.raises(SystemExit):
        main(["mark", "photo.jpg", "--json"])
    assert json.loads(capsys.readouterr().out)["error"].startswith("the following arguments")


def test_version(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out == f"faintmark {version('faintmark')}\n"
