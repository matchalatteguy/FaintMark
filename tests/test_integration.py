"""Opt-in checks against the real vetted model and public interfaces."""

import asyncio
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from copymark.core import CopyMark
from copymark.web import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("COPYMARK_INTEGRATION") != "1", reason="real models opt-in"),
]


@pytest.fixture(scope="module")
def real_image(tmp_path_factory):
    folder = tmp_path_factory.mktemp("real-images")
    image = folder / "sample.png"
    rng = np.random.default_rng(42)
    # Generated texture; no private image or download is needed for this fixture.
    texture = rng.integers(40, 220, (512, 512, 3), dtype=np.uint8)
    Image.fromarray(texture).save(image)
    return image


def test_real_cli_saved_exports_and_jpeg(real_image, tmp_path):
    source = tmp_path / "source.jpg"
    with Image.open(real_image) as image:
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "test fixture"
        image.crop((0, 0, 384, 512)).save(source, quality=90, exif=exif)
    original = source.read_bytes()
    home = tmp_path / "home"
    output = tmp_path / "copies"
    prefix = [sys.executable, "-m", "copymark", "--home", str(home), "--device", "cpu"]
    result = subprocess.run(
        prefix
        + [
            "mark",
            str(source),
            "--recipients",
            "recipient_1,recipient_2,recipient_3",
            "--output",
            str(output),
            "--json",
        ],
        text=True,
        capture_output=True,
        timeout=120,
        check=True,
    )
    batch = json.loads(result.stdout)
    assert len(batch["copies"]) == 3
    assert source.read_bytes() == original
    assert batch["output_dir"] == str(output)
    assert "zip_path" not in batch and not list(output.glob("*.zip"))
    for copy in batch["copies"]:
        with Image.open(copy["path"]) as marked:
            assert marked.size == (512, 384)
            assert len(marked.getexif()) == 0 and not marked.info
        checked = subprocess.run(
            prefix + ["check", copy["path"], "--json"],
            text=True,
            capture_output=True,
            timeout=120,
            check=True,
        )
        assert json.loads(checked.stdout)["copy_id"] == copy["copy_id"]
    jpeg = tmp_path / "recompressed.jpg"
    with Image.open(batch["copies"][0]["path"]) as image:
        image.save(jpeg, quality=70, subsampling=2)
    checked = subprocess.run(
        prefix + ["check", str(jpeg), "--json"],
        text=True,
        capture_output=True,
        timeout=120,
        check=True,
    )
    assert json.loads(checked.stdout)["recipient"] == "recipient_1"
    unmarked = subprocess.run(
        prefix + ["check", str(real_image), "--json"], text=True, capture_output=True, timeout=120
    )
    assert unmarked.returncode == 2
    assert json.loads(unmarked.stdout)["status"] != "matched"


def test_real_web_saved_files_and_registry_interop(real_image, tmp_path):
    service = CopyMark(tmp_path / "home", device="cpu")
    app = create_app(service=service, home=service.home)
    client = TestClient(app, base_url="http://127.0.0.1")
    client.get("/")
    headers = {"x-copymark-token": app.state.session_token}
    response = client.post(
        "/api/mark",
        headers=headers,
        files={"image": ("sample.png", real_image.read_bytes(), "image/png")},
        data={"recipients": "recipient_1, recipient_2, recipient_3"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert [copy["recipient"] for copy in result["copies"]] == [
        "recipient_1",
        "recipient_2",
        "recipient_3",
    ]
    assert len({copy["copy_id"] for copy in result["copies"]}) == 3
    archive = client.get(result["download_url"])
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert len(z.namelist()) == 3
        for copy in result["copies"]:
            filename = next(name for name in z.namelist() if copy["copy_id"] in name)
            returned = client.post(
                "/api/check",
                headers=headers,
                files={"image": ("returned.png", z.read(filename), "image/png")},
            )
            assert returned.json()["recipient"] == copy["recipient"]
            assert returned.json()["copy_id"] == copy["copy_id"]
    row = service.list_copies()[0]
    assert Path(row["path"]).is_file()
    assert row["original_name"] == "sample.png"
    # A second process/service using the same registry also finds the copy.
    other = CopyMark(service.home, device="cpu")
    assert other.check(row["path"])["copy_id"] == row["copy_id"]


def test_real_mcp_mark_and_check(real_image, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "copymark", "--home", str(tmp_path / "home"), "--device", "cpu", "mcp"],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                created = await session.call_tool(
                    "mark_image",
                    {
                        "image_path": str(real_image),
                        "recipients": ["Recipient 4"],
                        "output_dir": str(tmp_path / "copies"),
                        "preflight": False,
                    },
                )
                assert not created.isError, created
                batch = created.structuredContent
                assert "zip_path" not in batch
                assert batch["output_dir"] == str(tmp_path / "copies")
                assert not list((tmp_path / "copies").glob("*.zip"))
                copy = batch["copies"][0]
                checked = await session.call_tool("check_image", {"image_path": copy["path"]})
                assert not checked.isError
                assert checked.structuredContent["recipient"] == "Recipient 4"
                assert checked.structuredContent["copy_id"] == copy["copy_id"]

    asyncio.run(exercise())
