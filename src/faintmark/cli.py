import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _parser():
    parser = argparse.ArgumentParser(
        prog="faintmark", description="Invisible per-recipient image watermarks."
    )
    parser.add_argument("--version", action="version", version=f"faintmark {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true", help="print the result as JSON")

    mark = commands.add_parser(
        "mark", parents=[output], help="Create one invisibly marked copy per recipient."
    )
    mark.add_argument("image", help="JPEG, PNG, WebP or HEIC, up to 25 megapixels")
    mark.add_argument(
        "recipients", nargs="+", metavar="RECIPIENT", help="one label per copy (1 to 100)"
    )
    mark.add_argument("-o", "--output", metavar="DIR", help="default: marked/ beside the image")
    mark.add_argument("--format", choices=["png", "jpeg", "webp"], help="default: the image's own")

    files = argparse.ArgumentParser(add_help=False)
    files.add_argument("--files", action="store_true", help="include file names and paths")

    check = commands.add_parser(
        "check", parents=[output, files], help="Identify which copy an image is."
    )
    check.add_argument("image", help="any image Pillow can open")

    listing = commands.add_parser("list", parents=[output, files], help="List registered copies.")
    listing.add_argument(
        "-n", "--limit", type=int, default=100, metavar="N", help="newest N copies (default 100)"
    )

    commands.add_parser("mcp", help="Run the MCP server over stdio.")
    return parser


def _print_mark(result):
    for copy in result["copies"]:
        print(f"{copy['recipient']}  {copy['id']}  {copy['path']}")
        for warning in copy["warnings"]:
            print(f"  warning: {warning}", file=sys.stderr)
    count = len(result["copies"])
    print(f"{count} {'copy' if count == 1 else 'copies'} in {result['output_dir']}")


def _print_check(result):
    match result["status"]:
        case "matched":
            original = f"  {result['original']}" if "original" in result else ""
            print(
                f"matched: {result['recipient']}  {result['id']}{original}  "
                f"marked {result['marked_at']}"
            )
            if result.get("same_image") is False:
                print(
                    "  warning: the picture differs from the issued copy; cropping or a "
                    "copied id may explain this",
                    file=sys.stderr,
                )
        case "unregistered":
            print(f"unregistered: {result['id']} is not in this registry")
        case "not_detected":
            print("not detected")


def _print_list(result):
    for copy in result["copies"]:
        original = f"  {copy['original']}" if "original" in copy else ""
        print(f"{copy['id']}  {copy['recipient']}{original}  {copy['marked_at']}")
    if not result["copies"]:
        print("no copies")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "mcp":
            from .mcp_server import run

            run()
            return 0
        from .core import FaintMark

        service = FaintMark()
        code = 0
        if args.command == "mark":
            result = service.mark(args.image, args.recipients, args.output, args.format)
        elif args.command == "check":
            result = service.check(args.image, args.files)
            code = 0 if result["status"] == "matched" else 1
        else:
            result = service.list_copies(args.limit, args.files)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            {"mark": _print_mark, "check": _print_check, "list": _print_list}[args.command](result)
        return code
    except FileNotFoundError as exc:
        message = f"{Path(exc.filename).name}: no such file"
    except Exception as exc:
        message = str(exc)
    if args.json:
        print(json.dumps({"error": message}))
    else:
        print(f"faintmark: {message}", file=sys.stderr)
    return 2
