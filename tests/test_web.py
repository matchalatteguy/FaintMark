from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from copymark.web import create_app


class FakeCore:
    def __init__(self, check_result=None, fail=False):
        self.check_result = check_result or {"status": "unknown"}
        self.fail = fail
        self.mark_calls = []
        self.check_calls = []
        self.output_dirs = []

    def mark(self, image, recipients, output_dir, preflight=True, create_archive=False):
        assert create_archive, "Only the web download requests an archive"
        self.mark_calls.append((Path(image), recipients, Path(output_dir), preflight))
        self.output_dirs.append(Path(output_dir))
        if self.fail:
            raise ValueError("Unable to mark image")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        copies = []
        archive = Path(output_dir) / "result.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for name in recipients:
                copy_path = Path(output_dir) / f"{name}-0123456789.png"
                Image.new("RGB", (8, 8), (20, 40, 60)).save(copy_path)
                output.write(copy_path, copy_path.name)
                copies.append(
                    {
                        "copy_id": "0123456789",
                        "recipient": name,
                        "path": str(copy_path),
                        "warnings": [],
                    }
                )
        return {
            "batch_id": "batch-1",
            "original_sha256": "abc123",
            "copies": copies,
            "zip_path": str(archive),
        }

    def check(self, image):
        self.check_calls.append(Path(image))
        if self.fail:
            raise ValueError("Cannot decode image")
        return dict(self.check_result)


def client_for(tmp_path, core):
    client = TestClient(
        create_app(service=core, home=tmp_path / "service"), base_url="http://127.0.0.1"
    )
    page = client.get("/")
    assert page.status_code == 200
    token = page.text.split("const sessionToken = ", 1)[1].split(";", 1)[0].strip('"')
    return client, token


def test_page_has_session_and_is_the_simple_copy_mark_interface(tmp_path):
    client, _ = client_for(tmp_path, FakeCore())
    page = client.get("/")
    assert "<h1>CopyMark</h1>" in page.text
    assert "Create copies" in page.text
    assert "Check image" in page.text
    assert "__COPYMARK_SESSION_TOKEN__" not in page.text
    cookie = client.cookies.get("copymark_session")
    assert cookie and client.cookies.get("copymark_session") == cookie


def test_mark_requires_session_token(tmp_path):
    core = FakeCore()
    client = TestClient(
        create_app(service=core, home=tmp_path / "service"), base_url="http://127.0.0.1"
    )
    response = client.post(
        "/api/mark",
        data={"recipients": "recipient_1"},
        files={"image": ("source.png", b"image", "image/png")},
    )
    assert response.status_code == 403
    assert core.mark_calls == []


@pytest.mark.parametrize(
    "names",
    [
        "recipient_1, recipient_2, recipient_3",
        "recipient_1\nrecipient_2\nrecipient_3",
        "recipient_1,recipient_2\nrecipient_3",
        "recipient_1,\n recipient_2,\r\n recipient_3,,",
    ],
)
def test_each_comma_or_line_separated_recipient_gets_its_own_image(tmp_path, names):
    core = FakeCore()
    client, token = client_for(tmp_path, core)
    response = client.post(
        "/api/mark",
        data={"recipients": names},
        files={"image": ("source.png", b"image", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert response.status_code == 200
    result = response.json()
    assert core.mark_calls[0][1] == ["recipient_1", "recipient_2", "recipient_3"]
    assert [copy["recipient"] for copy in result["copies"]] == [
        "recipient_1",
        "recipient_2",
        "recipient_3",
    ]
    archive = client.get(result["download_url"])
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert set(z.namelist()) == {
            "recipient_1-0123456789.png",
            "recipient_2-0123456789.png",
            "recipient_3-0123456789.png",
        }


def test_mark_creates_archive_and_download_is_session_bound(tmp_path):
    core = FakeCore()
    client, token = client_for(tmp_path, core)
    response = client.post(
        "/api/mark",
        data={"recipients": "recipient_1\n\nrecipient_2"},
        files={"image": ("../../source.png", b"image bytes", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert [copy["recipient"] for copy in body["copies"]] == ["recipient_1", "recipient_2"]
    assert "path" not in body
    assert core.mark_calls[0][1] == ["recipient_1", "recipient_2"]
    assert core.mark_calls[0][0].name == "source.png"
    assert core.mark_calls[0][0].parent != core.mark_calls[0][2]
    assert not core.mark_calls[0][0].exists()
    assert core.mark_calls[0][2] == core.output_dirs[0]
    assert core.mark_calls[0][2].parent == tmp_path / "service" / "exports"
    assert all(
        Path(copy["path"]).is_file()
        for copy in [
            {"path": next(core.output_dirs[0].glob("recipient_1-*.png"))},
            {"path": next(core.output_dirs[0].glob("recipient_2-*.png"))},
        ]
    )

    download = client.get(body["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert set(zipfile.ZipFile(io.BytesIO(download.content)).namelist()) == {
        "recipient_1-0123456789.png",
        "recipient_2-0123456789.png",
    }

    stranger = TestClient(
        create_app(service=core, home=tmp_path / "other"), base_url="http://127.0.0.1"
    )
    assert stranger.get(body["download_url"]).status_code == 403
    assert client.get("/api/download/../../etc/passwd").status_code in {404, 422}


def test_check_returns_only_a_match_or_simple_status(tmp_path):
    core = FakeCore(
        {
            "status": "matched",
            "copy_id": "a1b2c3d4e5",
            "recipient": "recipient_1",
            "created_at": "2026-10-06T12:00:00Z",
            "original_name": "source.png",
            "thumbnail_path": "/private/service/thumb.png",
        }
    )
    client, token = client_for(tmp_path, core)
    response = client.post(
        "/api/check",
        files={"image": ("../../returned.png", b"returned image", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "matched",
        "copy_id": "a1b2c3d4e5",
        "recipient": "recipient_1",
        "created_at": "2026-10-06T12:00:00Z",
        "original_name": "source.png",
    }
    assert core.check_calls[0].name == "returned.png"
    assert not core.check_calls[0].exists()


def test_unknown_and_inconclusive_are_returned_as_statuses(tmp_path):
    for status in ("unknown", "inconclusive"):
        core = FakeCore({"status": status, "copy_id": "must-not-escape"})
        client, token = client_for(tmp_path / status, core)
        response = client.post(
            "/api/check",
            files={"image": ("returned.jpg", b"image", "image/jpeg")},
            headers={"X-CopyMark-Token": token},
        )
        assert response.status_code == 200
        assert response.json() == {"status": status}


def test_failed_mark_and_check_clean_temporary_uploads(tmp_path):
    core = FakeCore(fail=True)
    client, token = client_for(tmp_path, core)
    mark_response = client.post(
        "/api/mark",
        data={"recipients": "recipient_1"},
        files={"image": ("source.png", b"image", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    check_response = client.post(
        "/api/check",
        files={"image": ("returned.png", b"image", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert mark_response.status_code == 400
    assert mark_response.json()["detail"] == "Unable to mark image"
    assert check_response.status_code == 400
    assert check_response.json()["detail"] == "Cannot decode image"
    assert list((tmp_path / "service" / "tmp").iterdir()) == []
    assert list((tmp_path / "service" / "exports").iterdir()) == []


def test_mark_rejects_empty_recipients(tmp_path):
    client, token = client_for(tmp_path, FakeCore())
    response = client.post(
        "/api/mark",
        data={"recipients": " \n"},
        files={"image": ("source.png", b"image", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Enter at least one recipient."


def test_mark_enforces_core_recipient_limit(tmp_path):
    client, token = client_for(tmp_path, FakeCore())
    response = client.post(
        "/api/mark",
        data={"recipients": "\n".join(f"Name {index}" for index in range(101))},
        files={"image": ("source.png", b"image", "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Too many recipients")
    assert not (tmp_path / "service" / "exports").exists()


def test_upload_over_limit_is_rejected_and_removed(tmp_path):
    client, token = client_for(tmp_path, FakeCore())
    response = client.post(
        "/api/check",
        files={"image": ("large.png", b"x" * (31 * 1024 * 1024 + 1), "image/png")},
        headers={"X-CopyMark-Token": token},
    )
    assert response.status_code == 413
    assert response.json()["detail"].startswith("Image is too large")
    assert not (tmp_path / "service" / "tmp").exists()


def test_rejects_untrusted_host(tmp_path):
    client = TestClient(
        create_app(service=FakeCore(), home=tmp_path / "service"),
        base_url="http://attacker.example",
    )
    assert client.get("/").status_code == 400
