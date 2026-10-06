"""Official Python SDK stdio server for FaintMark."""

from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable


def _service(home: str | Path | None) -> Any:
    # Keep optional model/package output away from stdout, which is reserved for
    # MCP protocol frames when this process is launched over stdio.
    with redirect_stdout(sys.stderr):
        from .core import FaintMark

        return FaintMark(home=home)


def create_server(
    home: str | Path | None = None,
    *,
    service: Any | None = None,
    service_factory: Callable[[str | Path | None], Any] | None = None,
) -> Any:
    """Build the SDK server; injectable service arguments support local tests."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - exercised in CLI dependency tests
        raise RuntimeError("MCP support requires the official 'mcp' Python SDK") from exc

    server = FastMCP("FaintMark")
    current_service = service

    def get_service() -> Any:
        nonlocal current_service
        if current_service is None:
            factory = service_factory or _service
            current_service = factory(home)
        return current_service

    @server.tool(
        description=(
            "Create a folder of recipient-specific PNG images and register them locally. "
            "Returns the output folder and each image path; no ZIP archive is created. "
            "A recipient label records the intended recipient; it does not prove who posted an image. "
            "Known registered copies are matched only when the detector is confident; nearest-match guessing is avoided."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            openWorldHint=False,
        ),
    )
    def mark_image(
        image_path: str,
        recipients: list[str],
        output_dir: str,
        preflight: bool = True,
    ) -> dict[str, Any]:
        """Create registered recipient copies from an image path."""
        with redirect_stdout(sys.stderr):
            return get_service().mark(
                image_path,
                recipients=recipients,
                output_dir=output_dir,
                preflight=preflight,
            )

    @server.tool(
        description=(
            "Check an image against the local FaintMark registry. Returns matched, unknown, or inconclusive; "
            "uncertain results are not assigned to the nearest known recipient."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
    )
    def check_image(image_path: str) -> dict[str, Any]:
        """Check an image against registered copies without guessing on uncertainty."""
        with redirect_stdout(sys.stderr):
            return get_service().check(image_path)

    @server.tool(
        description="List locally registered recipient copies, up to the requested limit.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
    )
    def list_copies(limit: int = 100) -> list[dict[str, Any]]:
        """List entries in the local FaintMark registry."""
        if limit < 0:
            raise ValueError("limit must be zero or greater")
        with redirect_stdout(sys.stderr):
            return get_service().list_copies(limit=limit)

    @server.tool(
        description=(
            "Export the local FaintMark registry to a ZIP file at the requested path. "
            "This writes an export file and does not delete registry data."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            openWorldHint=False,
        ),
    )
    def backup_registry(output_path: str) -> str:
        """Write a ZIP backup of the local registry and return its path."""
        with redirect_stdout(sys.stderr):
            return get_service().backup(output_path)

    return server


def run_server(home: str | Path | None = None) -> None:
    """Run the official MCP SDK server using only its stdio transport."""
    create_server(home=home).run(transport="stdio")


def main(argv: list[str] | None = None, *, home: str | Path | None = None) -> int:
    """Console entry point; CLI delegation can pass resolved configuration."""
    if home is None or argv is not None:
        parser = argparse.ArgumentParser(prog="faintmark-mcp")
        parser.add_argument("--home")
        home = parser.parse_args(argv).home
    run_server(home=home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
