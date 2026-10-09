from types import SimpleNamespace

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

from faintmark import __version__
from faintmark.mcp_server import _HEAVY, create_server


def converse(calls):
    async def session():
        async with create_connected_server_and_client_session(create_server()) as client:
            return await calls(client)

    return anyio.run(session)


def test_tools_are_declared_with_annotations_and_output_schemas():
    async def calls(client):
        return (await client.list_tools()).tools

    tools = {tool.name: tool for tool in converse(calls)}
    assert create_server()._mcp_server.version == __version__

    assert set(tools) == {"mark_image", "check_image", "list_copies"}
    assert tools["mark_image"].annotations.readOnlyHint is False
    assert tools["mark_image"].annotations.destructiveHint is False
    assert tools["check_image"].annotations.readOnlyHint is True
    assert tools["list_copies"].annotations.readOnlyHint is True
    assert tools["mark_image"].inputSchema["required"] == ["image_path", "recipients"]
    assert tools["check_image"].inputSchema["properties"]["files"]["default"] is False
    recipients = tools["mark_image"].inputSchema["properties"]["recipients"]
    assert (recipients["minItems"], recipients["maxItems"]) == (1, 100)
    assert (
        "absolute path"
        in tools["mark_image"].inputSchema["properties"]["image_path"]["description"]
    )
    assert "copies" in tools["mark_image"].outputSchema["properties"]
    assert tools["check_image"].outputSchema["required"] == ["status"]
    assert _HEAVY.total_tokens == 1  # one inference job at a time
    assert "copies" in tools["list_copies"].outputSchema["properties"]


def test_mark_then_check_roundtrip(home, make_image):
    source = make_image("photo.jpg", quality=85, subsampling=2)
    unmarked = make_image("small.png", size=(64, 48))  # too small for the stub to read at any angle

    async def calls(client):
        empty = await client.call_tool("list_copies", {})
        marked = await client.call_tool(
            "mark_image", {"image_path": str(source), "recipients": ["alice", "bob"]}
        )
        path = marked.structuredContent["copies"][1]["path"]
        checked = await client.call_tool("check_image", {"image_path": path})
        listed = await client.call_tool("list_copies", {"limit": 1})
        missing = await client.call_tool("check_image", {"image_path": str(source) + ".gone"})
        deep = await client.call_tool(
            "check_image", {"image_path": str(unmarked), "deep": True, "files": True}
        )
        return empty, marked, checked, listed, missing, deep

    empty, marked, checked, listed, missing, deep = converse(calls)

    assert empty.structuredContent == {"copies": []}
    copies = marked.structuredContent["copies"]
    assert [copy["path"].endswith(".jpg") for copy in copies] == [True, True]
    assert checked.structuredContent["status"] == "matched"
    assert checked.structuredContent["recipient"] == "bob"
    assert checked.structuredContent["same_image"] is True
    assert "path" not in checked.structuredContent
    assert [copy["id"] for copy in listed.structuredContent["copies"]] == [copies[1]["id"]]
    assert missing.isError
    assert deep.structuredContent == {
        "status": "not_detected",
        "suspects": [],
        "registry_size": 2,
    }


def test_unmatched_checks_return_only_their_own_keys(home, make_image, monkeypatch, tmp_path):
    from faintmark.core import FaintMark

    copy = FaintMark().mark(make_image("photo.jpg"), ["alice"])["copies"][0]
    monkeypatch.setenv("FAINTMARK_HOME", str(tmp_path / "other"))

    async def calls(client):
        return await client.call_tool("check_image", {"image_path": copy["path"]})

    unregistered = converse(calls)
    assert not unregistered.isError
    assert list(unregistered.structuredContent) == ["status", "id"]
    assert unregistered.structuredContent["status"] == "unregistered"

    monkeypatch.setattr(
        "faintmark.core.Engine", lambda models_dir: SimpleNamespace(decode=lambda image: None)
    )
    assert converse(calls).structuredContent == {"status": "not_detected"}
