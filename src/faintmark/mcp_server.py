import json
from typing import Literal

from anyio import CapacityLimiter, to_thread
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .core import CheckResult, FaintMark, ListResult, MarkResult

INSTRUCTIONS = (
    "Invisible per-recipient image watermarks. mark_image creates one marked copy per recipient "
    "and registers it locally; check_image decodes an image's id and looks it up. Use absolute "
    "paths. 'matched' means the decoded id is registered to that recipient; it does not prove "
    "who shared the image, since copies can be forwarded and ids can be copied into other "
    "images. The mark can be removed by someone who knows it is there, so 'not_detected' says "
    "nothing about where an image came from."
)
_HEAVY = CapacityLimiter(1)  # one inference job at a time; a 25 MP copy peaks above 1 GB


def create_server(service: FaintMark | None = None) -> FastMCP:
    server = FastMCP("FaintMark", instructions=INSTRUCTIONS)

    def get_service():
        nonlocal service
        service = service or FaintMark()
        return service

    @server.tool(
        description=(
            "Create one invisibly watermarked copy of an image per recipient label and register "
            "them locally. Use before sharing a picture with several people so a copy that turns "
            "up later can be traced to the label it was issued under. Writes files only and sends "
            "nothing; keeps the source format (JPEG stays JPEG). Returns the output folder and "
            "each copy's path, id and warnings. A warning starting with 'may not survive' means "
            "the copy is fragile, so suggest sending it as a file rather than a photo."
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
            get_service().mark, image_path, recipients, output_dir, format, limiter=_HEAVY
        )

    @server.tool(
        description=(
            "Decode the id in an image and look it up in the local registry; designed to work "
            "after chat-app recompression or resizing. status is matched (the id is registered to "
            "the returned recipient), unregistered (an id was read but it is not in this "
            "registry) or not_detected (no readable mark, which says nothing about where the "
            "image came from)."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )
    async def check_image(image_path: str) -> CheckResult:
        result = await to_thread.run_sync(get_service().check, image_path, limiter=_HEAVY)
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
