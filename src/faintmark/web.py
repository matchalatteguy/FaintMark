"""Small, loopback-only web interface for FaintMark."""

from __future__ import annotations

import json
import re
import secrets
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .paths import resolve_home

_MAX_UPLOAD = 30 * 1024 * 1024
_MAX_REQUEST_BODY = _MAX_UPLOAD + 500 * 1024
_CHUNK = 1024 * 1024
_STATIC = Path(__file__).with_name("static") / "index.html"


class _RequestTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Bound multipart bodies before Starlette parses their fields and files."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in {"/api/mark", "/api/check"}
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = 0
            if declared_length > self.max_bytes:
                await self._respond_too_large(scope, receive, send)
                return

        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await self._respond_too_large(scope, receive, send)

    @staticmethod
    async def _respond_too_large(scope, receive, send):
        await JSONResponse(
            {"detail": "Image is too large. Maximum size is 30 MB."}, status_code=413
        )(scope, receive, send)


def _home_path(home: str | Path | None) -> Path:
    return resolve_home(home)


def _display_filename(filename: str | None) -> str:
    # Treat both POSIX and Windows separators as separators; never use this value
    # as a path component outside the private per-request temporary directory.
    name = (filename or "image").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char >= " " and char != "\x7f").strip()
    name = name[:180]
    return name if name not in {"", ".", ".."} else "image"


def create_app(service=None, home=None, device="auto") -> FastAPI:
    """Create the local browser app. The default core is imported on first use."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.home = _home_path(home)
    app.state.service = service
    app.state.session_token = secrets.token_urlsafe(32)
    app.state.exports = {}
    service_lock = threading.Lock()
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=_MAX_REQUEST_BODY)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    def get_service():
        if app.state.service is None:
            with service_lock:
                if app.state.service is None:
                    from .core import FaintMark

                    app.state.service = FaintMark(home=app.state.home, device=device)
        return app.state.service

    def require_session(request: Request, supplied_token: str | None = None) -> None:
        cookie = request.cookies.get("faintmark_session", "")
        token = supplied_token or ""
        expected = app.state.session_token.encode("ascii")
        cookie_matches = secrets.compare_digest(cookie.encode("utf-8"), expected)
        token_matches = secrets.compare_digest(token.encode("utf-8"), expected)
        if not (cookie_matches and token_matches):
            raise HTTPException(status_code=403, detail="Session expired. Reload the page.")

    async def save_upload(upload: UploadFile, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = _display_filename(upload.filename)
        destination = directory / name
        total = 0
        try:
            with destination.open("xb") as output:
                while True:
                    chunk = await upload.read(_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_UPLOAD:
                        raise HTTPException(
                            status_code=413, detail="Image is too large. Maximum size is 30 MB."
                        )
                    output.write(chunk)
            if total == 0:
                raise HTTPException(status_code=400, detail="Choose an image first.")
            return destination
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        source = _STATIC.read_text(encoding="utf-8")
        page = source.replace("__FAINTMARK_SESSION_TOKEN__", json.dumps(app.state.session_token))
        response = HTMLResponse(page)
        response.set_cookie(
            "faintmark_session",
            app.state.session_token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response

    @app.post("/api/mark")
    async def mark(request: Request, image: UploadFile = File(...), recipients: str = Form(...)):
        require_session(request, request.headers.get("x-faintmark-token"))
        names = [name.strip() for name in re.split(r"[,\r\n]+", recipients) if name.strip()]
        if not names:
            raise HTTPException(status_code=400, detail="Enter at least one recipient.")
        if len(names) > 100:
            raise HTTPException(
                status_code=400,
                detail="Too many recipients. A batch can contain at most 100 names.",
            )
        if any(len(name) > 200 for name in names):
            raise HTTPException(
                status_code=400, detail="Recipient names must be 200 characters or fewer."
            )

        home = app.state.home
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_root = home / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        export_root = home / "exports"
        export_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="web-mark-", dir=temp_root) as temp_name:
            temp_dir = Path(temp_name)
            path = await save_upload(image, temp_dir)
            output_dir = export_root / secrets.token_hex(16)
            output_dir.mkdir(mode=0o700)
            try:
                result = await run_in_threadpool(
                    get_service().mark, path, names, output_dir, preflight=True, create_archive=True
                )
                zip_path = Path(result["zip_path"]).resolve(strict=True)
                if not zip_path.is_file() or not zip_path.is_relative_to(export_root.resolve()):
                    raise RuntimeError("The copy archive was not created in the exports folder.")
                token = secrets.token_urlsafe(24)
                batch_id = str(result.get("batch_id", "copies"))
                safe_batch = (
                    "".join(char for char in batch_id if char.isalnum() or char in "-_-")[:40]
                    or "copies"
                )
                export_name = f"FaintMark-{safe_batch}.zip"
                app.state.exports[token] = (zip_path, export_name)
                copies = result.get("copies", [])
                warnings = list(result.get("warnings", []))
                if not warnings:
                    warnings = [warning for copy in copies for warning in copy.get("warnings", [])]
                return {
                    "batch_id": result.get("batch_id"),
                    "original_sha256": result.get("original_sha256"),
                    "copies": [
                        {
                            "copy_id": copy.get("copy_id"),
                            "recipient": copy.get("recipient"),
                            "warnings": copy.get("warnings", []),
                        }
                        for copy in copies
                    ],
                    "warnings": warnings,
                    "download_url": f"/api/download/{token}",
                    "download_name": export_name,
                }
            except HTTPException:
                try:
                    output_dir.rmdir()
                except OSError:
                    pass
                raise
            except Exception as error:
                try:
                    output_dir.rmdir()
                except OSError:
                    pass
                raise HTTPException(
                    status_code=400, detail=str(error) or "Could not create copies."
                ) from error

    @app.post("/api/check")
    async def check(request: Request, image: UploadFile = File(...)):
        require_session(request, request.headers.get("x-faintmark-token"))
        home = app.state.home
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_root = home / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="web-check-", dir=temp_root) as temp_name:
            path = await save_upload(image, Path(temp_name))
            try:
                result = await run_in_threadpool(get_service().check, path)
                status = result.get("status")
                if status not in {"matched", "unknown", "inconclusive"}:
                    raise RuntimeError("The check returned an unsupported result.")
                response = {"status": status}
                if status == "matched":
                    response.update(
                        {
                            key: result.get(key)
                            for key in ("copy_id", "recipient", "created_at", "original_name")
                        }
                    )
                return response
            except HTTPException:
                raise
            except Exception as error:
                raise HTTPException(
                    status_code=400, detail=str(error) or "Could not check this image."
                ) from error

    @app.get("/api/download/{token}")
    async def download(request: Request, token: str):
        cookie = request.cookies.get("faintmark_session", "")
        if not secrets.compare_digest(
            cookie.encode("utf-8"), app.state.session_token.encode("ascii")
        ):
            raise HTTPException(status_code=403, detail="Session expired. Reload the page.")
        entry = app.state.exports.get(token)
        if not entry:
            raise HTTPException(status_code=404, detail="Download not found.")
        raw_path, filename = entry
        export_root = (app.state.home / "exports").resolve()
        try:
            path = raw_path.resolve(strict=True)
        except OSError:
            app.state.exports.pop(token, None)
            raise HTTPException(status_code=404, detail="Download not found.")
        if not path.is_file() or not path.is_relative_to(export_root):
            app.state.exports.pop(token, None)
            raise HTTPException(status_code=404, detail="Download not found.")
        return FileResponse(path, media_type="application/zip", filename=filename)

    return app


def serve(home=None, device="auto", port=8765, open_browser=True):
    """Run the web app on loopback only."""
    import uvicorn

    app = create_app(home=home, device=device)
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(0.7, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
