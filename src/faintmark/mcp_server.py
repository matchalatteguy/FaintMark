import json
from typing import Literal

from anyio import to_thread
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .core import CheckResult, FaintMark, ListResult, MarkResult

INSTRUCTIONS = (
    "Invisible per-recipient image watermarks. mark_image creates one marked copy per recipient "
    "and registers it locally; check_image identifies which registered copy an image is. "
    "Use absolute paths. 'matched' means the copy was issued to that recipient, not that they "
    "shared it."
)


def create_server(service: FaintMark | None = None) -> FastMCP:
    server = FastMCP("FaintMark", instructions=INSTRUCTIONS)

    def get_service():
        nonlocal service
        service = service or FaintMark()
        return service

    @server.tool(
        description=(
            "Create one invisibly watermarked copy of an image per recipient and register them "
            "locally. Use before sharing a picture with several people so a leaked copy can be "
            "traced to the recipient it was issued to. Keeps the source format (JPEG stays JPEG). "
            "Returns the output folder and each copy's path and id."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
        ),
    )
    async def mark_image(
        image_path: str,
        recipients: list[str],
        output_dir: str | None = None,
        format: Literal["png", "jpeg", "webp"] | None = None,
    ) -> MarkResult:
        return await to_thread.run_sync(
            get_service().mark, image_path, recipients, output_dir, format
        )

    @server.tool(
        description=(
            "Identify which registered copy an image is; designed to work after chat-app "
            "recompression or resizing. status is matched (returns recipient and id), "
            "unregistered (a watermark was found but it is not in this registry) or not_detected."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )
    async def check_image(image_path: str) -> CheckResult:
        result = await to_thread.run_sync(get_service().check, image_path)
        # FastMCP would fill the absent optional keys with nulls that its own outputSchema rejects
        text = TextContent(type="text", text=json.dumps(result, indent=2))
        return CallToolResult(content=[text], structuredContent=result)

    @server.tool(
        description="List registered copies, newest first.",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )
    async def list_copies(limit: int = 100) -> ListResult:
        return await to_thread.run_sync(get_service().list_copies, limit)

    return server


def run() -> None:
    create_server().run(transport="stdio")
