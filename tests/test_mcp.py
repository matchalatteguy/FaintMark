import threading
from types import SimpleNamespace

import anyio
import pytest
from anyio import to_thread
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CancelledNotification, CancelledNotificationParams, ClientNotification

from faintmark import __version__
from faintmark.core import FaintMark
from faintmark.mcp_server import _serialized, create_server


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
    assert "copies" in tools["list_copies"].outputSchema["properties"]


def test_mark_then_check_roundtrip(home, make_image, monkeypatch):
    source = make_image("photo.jpg", quality=85, subsampling=2)
    unmarked = make_image("small.png", size=(64, 48))  # too small for the stub to read at any angle
    draws = iter([1, 2])  # codewords 31 and 36 bits from the all-zero read, so never candidates
    monkeypatch.setattr("faintmark.core.secrets.randbits", lambda bits: next(draws))

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
    assert missing.isError and missing.content[0].text.endswith("photo.jpg.gone: no such file")
    assert deep.structuredContent == {
        "status": "not_detected",
        "suspects": [],
        "registry_size": 2,
    }


def test_unmatched_checks_return_only_their_own_keys(home, make_image, monkeypatch, tmp_path):
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


@pytest.mark.parametrize(
    "tool, recipients, paused",
    [
        ("mark_image", ["alice"], "encode"),  # cancelled before the registry commit
        ("mark_image", ["alice", "bob"], "encode"),  # cancelled before the second copy
        ("check_image", None, "decode"),
        ("list_copies", None, None),
    ],
)
def test_a_cancelled_call_leaves_no_trace_and_the_server_survives(
    home, make_image, monkeypatch, tool, recipients, paused
):
    service = FaintMark()
    source, other = make_image("photo.png"), make_image("other.png")
    started, release, finished, waiting = (threading.Event() for _ in range(4))
    order = []
    method = {"mark_image": "mark", "check_image": "check", "list_copies": "list_copies"}[tool]
    original, check = getattr(service, method), service.check

    def pause():
        started.set()
        release.wait(5)

    def finishing(*args):
        if paused is None:
            pause()
        try:
            return original(*args)
        finally:
            order.append(method)
            finished.set()

    def checking(*args):
        order.append("check")
        return check(*args)

    def observed(func, *args):  # the competing check has reached the lock
        if func is checking:
            waiting.set()
        return _serialized(func, *args)

    monkeypatch.setattr(service, method, finishing)
    monkeypatch.setattr("faintmark.mcp_server._serialized", observed)
    if paused:
        inner = getattr(service.engine, paused)
        monkeypatch.setattr(service.engine, paused, lambda *args: (pause(), inner(*args))[1])
    if tool == "mark_image":
        monkeypatch.setattr(service, "check", checking)
    arguments = {"image_path": str(source)} if tool != "list_copies" else {}
    if recipients:
        arguments["recipients"] = recipients

    async def session():
        async with create_connected_server_and_client_session(create_server(service)) as client:
            with anyio.fail_after(20):
                request_id = client._request_id  # the id the next request will carry
                outcome, answered = [], anyio.Event()

                async def call():
                    try:
                        await client.call_tool(tool, arguments)
                    except McpError as error:
                        outcome.append(error.error.message)
                    answered.set()

                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(call)
                    await to_thread.run_sync(started.wait, 5)
                    cancel = CancelledNotification(
                        method="notifications/cancelled",
                        params=CancelledNotificationParams(requestId=request_id),
                    )
                    await client.send_notification(ClientNotification(cancel))
                    await answered.wait()
                    if tool == "mark_image":  # another inference must wait for the abandoned one
                        tasks.start_soon(
                            client.call_tool, "check_image", {"image_path": str(other)}
                        )
                        await to_thread.run_sync(waiting.wait, 5)
                        await anyio.sleep(0.2)
                        assert order == []
                    release.set()
                await to_thread.run_sync(finished.wait, 5)
                return outcome, await client.call_tool("list_copies", {})

    outcome, listed = anyio.run(session)
    assert outcome == ["Request cancelled"]
    assert listed.structuredContent == {"copies": []}
    assert not (source.parent / "marked").exists() or not list((source.parent / "marked").iterdir())
    if tool == "mark_image":
        assert order == ["mark", "check"]
