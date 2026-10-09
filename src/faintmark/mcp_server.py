import json
from typing import Annotated, Literal

from anyio import CapacityLimiter, to_thread
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from . import __version__
from .core import CheckResult, FaintMark, ListResult, MarkResult

INSTRUCTIONS = (
    "Invisible per-recipient image watermarks. mark_image creates one marked copy per recipient "
    "and registers it locally; check_image decodes an image's id and looks it up. Use absolute "
    "paths. 'matched' means the decoded id is registered to that recipient; it does not prove "
    "who shared the image, since copies can be forwarded and ids can be copied into other "
    "images. The mark can be removed by someone who knows it is there, so 'not_detected' says "
    "nothing about where an image came from. The first mark or check downloads 65 MB of models "
    "from Adobe."
)
_HEAVY = CapacityLimiter(1)  # one inference job at a time; a 25 MP copy peaks above 1 GB


def create_server(service: FaintMark | None = None) -> FastMCP:
    server = FastMCP("FaintMark", instructions=INSTRUCTIONS)
    server._mcp_server.version = __version__  # the SDK would report its own version

    def get_service():
        nonlocal service
        service = service or FaintMark()
        return service

    @server.tool(
        description=(
            "Create one invisibly watermarked copy of an image per recipient label and register "
            "them locally. Use before sharing a picture with several people so a copy that turns "
            "up later can be traced to the label it was issued under. Writes files only and sends "
            "nothing; keeps the source format (JPEG stays JPEG). Accepts 8-bit JPEG, PNG, WebP or "
            "HEIC (HEIC only when the server runs with the heic extra) up to 25 megapixels without "
            "transparency, and 1 to 100 recipient labels. Returns the output folder and "
            "each copy's path, id and warnings. A warning starting with 'may not survive' means "
            "the copy is fragile, so suggest sending it as a file rather than a photo."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
        ),
    )
    async def mark_image(
        image_path: Annotated[str, Field(description="absolute path of the image to mark")],
        recipients: Annotated[
            list[Annotated[str, Field(min_length=1, max_length=200)]],
            Field(description="1 to 100 labels, one copy each", min_length=1, max_length=100),
        ],
        output_dir: Annotated[
            str | None, Field(description="default: a marked/ folder beside the image")
        ] = None,
        format: Annotated[
            Literal["png", "jpeg", "webp"] | None, Field(description="default: the source format")
        ] = None,
    ) -> MarkResult:
        return await to_thread.run_sync(
            get_service().mark, image_path, recipients, output_dir, format, limiter=_HEAVY
        )

    @server.tool(
        description=(
            "Decode the id in an image (any format Pillow opens, up to 100 megapixels) and look it "
            "up in the local registry; designed to work after chat-app recompression or resizing. "
            "status is matched (the id is registered to the returned recipient), unregistered (an "
            "id was read but it is not in this registry) or not_detected (no readable mark, which "
            "says nothing about where the image came from). A match also reports same_image when a "
            "stored hash exists, a perceptual-hash comparison with the issued copy: false means "
            "they differ beyond the "
            "threshold, which cropping or an id copied into another picture can cause. same_image "
            "true is not authentication: a tuned forgery passed it in our measurements. deep=true "
            "also tries a flip and small rotations, and when nothing is detected lists the "
            "registered ids within 26 of 96 codeword bits of the raw decoder output as suspects "
            "(up to three, each with id, recipient and bit_errors, plus same_image when a stored "
            "hash exists; empty when none is that close) and registry_size. Suspects are "
            "uncalibrated candidates "
            "by codeword distance: they can be coincidental (more likely with a large registry) "
            "or forged, and they never mean a match. files=true adds the original file name and "
            "the issued copy's path."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )
    async def check_image(
        image_path: Annotated[str, Field(description="absolute path of the image to check")],
        files: Annotated[bool, Field(description="include file names and paths")] = False,
        deep: Annotated[
            bool, Field(description="try flips and rotations, then list suspects")
        ] = False,
    ) -> CheckResult:
        result = await to_thread.run_sync(
            get_service().check, image_path, files, deep, limiter=_HEAVY
        )
        # FastMCP would fill the absent optional keys with nulls that its own outputSchema rejects
        text = TextContent(type="text", text=json.dumps(result, indent=2))
        return CallToolResult(content=[text], structuredContent=result)

    @server.tool(
        description=("List registered copies, newest first. files=true adds file names and paths."),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )
    async def list_copies(
        limit: Annotated[int, Field(description="newest N copies", ge=0)] = 100,
        files: Annotated[bool, Field(description="include file names and paths")] = False,
    ) -> ListResult:
        return await to_thread.run_sync(get_service().list_copies, limit, files)

    return server


def run() -> None:
    create_server().run(transport="stdio")
