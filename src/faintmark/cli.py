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
    mark.add_argument("image")
    mark.add_argument("recipients", nargs="+", metavar="RECIPIENT")
    mark.add_argument("-o", "--output", metavar="DIR", help="default: marked/ beside the image")
    mark.add_argument("--format", choices=["png", "jpeg", "webp"], help="default: the image's own")

    check = commands.add_parser("check", parents=[output], help="Identify which copy an image is.")
    check.add_argument("image")

    listing = commands.add_parser("list", parents=[output], help="List registered copies.")
    listing.add_argument("-n", "--limit", type=int, default=100, metavar="N")

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
            print(
                f"matched: {result['recipient']}  {result['id']}  {result['original']}  "
                f"marked {result['marked_at']}"
            )
        case "unregistered":
            print(f"unregistered: {result['id']} is not in this registry")
        case "not_detected":
            print("not detected")


def _print_list(result):
    for copy in result["copies"]:
        print(f"{copy['id']}  {copy['recipient']}  {copy['original']}  {copy['marked_at']}")
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
            result = service.check(args.image)
            code = 0 if result["status"] == "matched" else 1
        else:
            result = service.list_copies(args.limit)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            {"mark": _print_mark, "check": _print_check, "list": _print_list}[args.command](result)
        return code
    except FileNotFoundError as exc:
        print(f"faintmark: {Path(exc.filename).name}: no such file", file=sys.stderr)
    except Exception as exc:
        print(f"faintmark: {exc}", file=sys.stderr)
    return 2
