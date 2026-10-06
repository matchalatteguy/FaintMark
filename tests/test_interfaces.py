from __future__ import annotations

import asyncio
import builtins
import io
import json
import os
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest


class FakeFaintMark:
    def __init__(self, home: str | None = None, device: str = "auto") -> None:
        self.home = home
        self.device = device
        self.calls: list[tuple[str, Any]] = []

    def mark(
        self, image: Any, recipients: list[str], output_dir: Any, preflight: bool = True
    ) -> dict[str, Any]:
        print("simulated model status")
        self.calls.append(("mark", (image, recipients, output_dir, preflight)))
        return {
            "batch_id": "batch-1",
            "original_sha256": "abc123",
            "copies": [
                {
                    "copy_id": "0123456789",
                    "recipient": recipient,
                    "path": f"{output_dir}/{recipient}.png",
                    "warnings": [],
                }
                for recipient in recipients
            ],
            "output_dir": str(output_dir),
        }

    def check(self, image: Any) -> dict[str, Any]:
        self.calls.append(("check", image))
        return {
            "status": "matched",
            "copy_id": "0123456789",
            "recipient": "recipient_1",
            "created_at": "2026-10-06T00:00:00Z",
            "original_name": "source.png",
            "thumbnail_path": "/tmp/thumbnail.png",
        }

    def list_copies(self, limit: int = 100) -> list[dict[str, Any]]:
        self.calls.append(("list_copies", limit))
        return [{"copy_id": "0123456789", "recipient": "recipient_1", "created_at": "now"}]

    def backup(self, destination: Any) -> str:
        self.calls.append(("backup", destination))
        return str(destination)


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[FakeFaintMark]]:
    from faintmark import cli as cli_module

    instances: list[FakeFaintMark] = []

    class FakeFactory(FakeFaintMark):
        def __init__(self, home: str | None = None, device: str = "auto") -> None:
            super().__init__(home, device)
            instances.append(self)

    core_module = types.ModuleType("faintmark.core")
    core_module.FaintMark = FakeFactory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faintmark.core", core_module)
    return cli_module, instances


def test_help_does_not_import_copy_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    from faintmark.cli import main

    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == ".core" or name.endswith("faintmark.core"):
            raise AssertionError("help must not import the engine")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0


def test_mark_combines_recipients_and_emits_clean_json(
    cli: tuple[Any, list[FakeFaintMark]], tmp_path: Path
) -> None:
    cli_module, instances = cli
    names_file = tmp_path / "recipients.txt"
    names_file.write_text("\nrecipient_3\n", encoding="utf-8")
    stdout, stderr = io.StringIO(), io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli_module.main(
            [
                "--home",
                str(tmp_path / "registry"),
                "--device",
                "cpu",
                "mark",
                str(tmp_path / "input.png"),
                "--recipients",
                "recipient_1,recipient_2",
                "--recipients-file",
                str(names_file),
                "--output",
                str(tmp_path / "out"),
                "--no-preflight",
                "--json",
            ]
        )

    assert code == 0
    output = json.loads(stdout.getvalue())
    assert [copy["recipient"] for copy in output["copies"]] == [
        "recipient_1",
        "recipient_2",
        "recipient_3",
    ]
    assert "simulated model status" in stderr.getvalue()
    instance = instances[0]
    assert (instance.home, instance.device) == (str(tmp_path / "registry"), "cpu")
    assert instance.calls[0][1][1:] == (
        ["recipient_1", "recipient_2", "recipient_3"],
        tmp_path / "out",
        False,
    )


@pytest.mark.parametrize("status,expected", [("matched", 0), ("unknown", 2), ("inconclusive", 2)])
def test_check_exit_codes(
    cli: tuple[Any, list[FakeFaintMark]],
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected: int,
) -> None:
    cli_module, instances = cli
    instance = FakeFaintMark()
    instance.check = lambda _image: {"status": status}  # type: ignore[method-assign]
    instances.append(instance)
    monkeypatch.setattr(cli_module, "_service", lambda _args: instance)
    stdout, stderr = io.StringIO(), io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli_module.main(["check", "source.png"])

    assert code == expected
    if status == "inconclusive":
        assert "inconclusive" in stdout.getvalue()


def test_list_and_backup_are_registry_operations(
    cli: tuple[Any, list[FakeFaintMark]], tmp_path: Path
) -> None:
    cli_module, instances = cli
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        assert cli_module.main(["list", "--json", "--limit", "7"]) == 0
    assert json.loads(stdout.getvalue())[0]["copy_id"] == "0123456789"
    assert instances[-1].calls == [("list_copies", 7)]

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        assert cli_module.main(["backup", str(tmp_path / "backup.zip")]) == 0
    assert stdout.getvalue().strip() == str(tmp_path / "backup.zip")
    assert instances[-1].calls == [("backup", tmp_path / "backup.zip")]


def test_mcp_tools_have_expected_schemas_and_annotations() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from faintmark.mcp_server import create_server

    server = create_server(service=FakeFaintMark())
    tools = server._tool_manager.list_tools()
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {"mark_image", "check_image", "list_copies", "backup_registry"}
    assert by_name["mark_image"].parameters["required"] == [
        "image_path",
        "recipients",
        "output_dir",
    ]
    assert by_name["mark_image"].parameters["properties"]["recipients"]["type"] == "array"
    assert by_name["list_copies"].parameters["properties"]["limit"]["default"] == 100
    mark_annotations = by_name["mark_image"].annotations.model_dump(by_alias=True)
    check_annotations = by_name["check_image"].annotations.model_dump(by_alias=True)
    backup_annotations = by_name["backup_registry"].annotations.model_dump(by_alias=True)
    assert mark_annotations["readOnlyHint"] is False
    assert mark_annotations["destructiveHint"] is False
    assert mark_annotations["openWorldHint"] is False
    assert check_annotations["readOnlyHint"] is True
    assert backup_annotations["destructiveHint"] is False
    assert not {"read_only_hint", "destructive_hint", "open_world_hint"}.intersection(
        mark_annotations
    )


def test_mcp_stdio_initializes_lists_and_calls_without_stdout_contamination(tmp_path: Path) -> None:
    pytest.importorskip("mcp.client.stdio")
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    source_root = str(Path(__file__).resolve().parents[1] / "src")
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(filter(None, [source_root, current_pythonpath]))
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "faintmark.mcp_server", "--home", str(tmp_path / "registry")],
        env=child_env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )

    async def exercise_server() -> None:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed_tools = await session.list_tools()
                names = {tool.name for tool in listed_tools.tools}
                assert "list_copies" in names
                list_tool = next(tool for tool in listed_tools.tools if tool.name == "list_copies")
                assert list_tool.annotations.model_dump(by_alias=True)["readOnlyHint"] is True

                result = await session.call_tool("list_copies", {"limit": 10})
                assert result.isError is not True
                assert result.structuredContent == {"result": []}

    asyncio.run(exercise_server())
