"""Command-line interface for CopyMark."""

from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Sequence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copymark",
        description="Create recipient-specific marked image copies and check them later.",
    )
    parser.add_argument(
        "--home", help="Registry and model directory (default: $COPYMARK_HOME or ~/.copymark)."
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps"), default="auto", help="Inference device."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    mark = commands.add_parser("mark", help="Create marked copies for recipients.")
    mark.add_argument("image", type=Path)
    mark.add_argument(
        "--recipient",
        action="append",
        default=[],
        metavar="NAME",
        help="Recipient name; repeat to add more.",
    )
    mark.add_argument(
        "--recipients-file", type=Path, help="Text file with one recipient name per line."
    )
    mark.add_argument("--recipients", help="Comma-separated recipient names.")
    mark.add_argument(
        "--output",
        type=Path,
        default=Path("./marked"),
        help="Output directory (default: ./marked).",
    )
    mark.add_argument("--no-preflight", action="store_true", help="Skip preflight checks.")
    mark.add_argument("--json", action="store_true", help="Write machine-readable JSON to stdout.")

    check = commands.add_parser("check", help="Check whether an image matches a registered copy.")
    check.add_argument("image", type=Path)
    check.add_argument("--json", action="store_true", help="Write machine-readable JSON to stdout.")

    listing = commands.add_parser("list", help="List registered copies.")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument(
        "--json", action="store_true", help="Write machine-readable JSON to stdout."
    )

    backup = commands.add_parser("backup", help="Export the local registry to a ZIP archive.")
    backup.add_argument("output", type=Path)

    serve = commands.add_parser("serve", help="Start the local web interface.")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-open", action="store_true", help="Do not open a browser window.")

    commands.add_parser("mcp", help="Run the local MCP stdio server.")
    return parser


def _service(args: argparse.Namespace) -> Any:
    # Importing the package facade does not load the image model; the core owns
    # lazy model construction. Keep any incidental import chatter off stdout.
    with redirect_stdout(sys.stderr):
        from .core import CopyMark

        return CopyMark(home=args.home, device=args.device)


def _recipients(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    names = list(args.recipient)
    if args.recipients:
        names.extend(
            name.strip() for name in re.split(r"[,\r\n]+", args.recipients) if name.strip()
        )
    if args.recipients_file:
        try:
            names.extend(
                line.strip()
                for line in args.recipients_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        except OSError as exc:
            parser.error(f"cannot read recipients file {args.recipients_file}: {exc}")
    names = [name.strip() for name in names if name.strip()]
    if not names:
        parser.error("mark requires --recipients, --recipient, or a non-empty --recipients-file")
    return names


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _mark_human(result: dict[str, Any]) -> None:
    print(
        f"Marked {len(result.get('copies', []))} copies (batch {result.get('batch_id', 'unknown')})."
    )
    print(f"Original SHA-256: {result.get('original_sha256', 'unknown')}")
    for copy in result.get("copies", []):
        print(
            f"{copy.get('recipient', 'Recipient')}: {copy.get('copy_id', 'unknown')}  {copy.get('path', '')}"
        )
        for warning in copy.get("warnings", []):
            print(f"  Warning: {warning}", file=sys.stderr)
    if result.get("output_dir"):
        print(f"Folder: {result['output_dir']}")


def _check_human(result: dict[str, Any]) -> int:
    status = result.get("status", "inconclusive")
    if status == "matched":
        print(
            f"Matched copy {result.get('copy_id', 'unknown')} for {result.get('recipient', 'unknown recipient')}."
        )
        if result.get("created_at"):
            print(f"Created: {result['created_at']}")
        if result.get("original_name"):
            print(f"Original: {result['original_name']}")
        if result.get("thumbnail_path"):
            print(f"Thumbnail: {result['thumbnail_path']}")
        return 0
    if status == "unknown":
        print("No registered copy matched this image.")
        return 2
    print("The result is inconclusive; CopyMark could not determine a match.")
    return 2


def _list_human(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No registered copies.")
        return
    for row in rows:
        print(
            f"{row.get('copy_id', 'unknown')}  {row.get('recipient', 'unknown recipient')}  "
            f"{row.get('path', row.get('created_at', ''))}"
        )


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "mcp":
        from .mcp_server import run_server

        run_server(home=args.home, device=args.device)
        return 0
    if args.command == "serve":
        from .web import serve

        serve(home=args.home, device=args.device, port=args.port, open_browser=not args.no_open)
        return 0

    service = _service(args)
    if args.command == "mark":
        recipients = _recipients(args, parser)
        with redirect_stdout(sys.stderr):
            result = service.mark(
                args.image,
                recipients=recipients,
                output_dir=args.output,
                preflight=not args.no_preflight,
            )
        if args.json:
            _json(result)
        else:
            _mark_human(result)
        return 0
    if args.command == "check":
        with redirect_stdout(sys.stderr):
            result = service.check(args.image)
        if args.json:
            _json(result)
            return 0 if result.get("status") == "matched" else 2
        return _check_human(result)
    if args.command == "list":
        if args.limit < 0:
            parser.error("--limit must be zero or greater")
        with redirect_stdout(sys.stderr):
            rows = service.list_copies(limit=args.limit)
        _json(rows) if args.json else _list_human(rows)
        return 0
    if args.command == "backup":
        with redirect_stdout(sys.stderr):
            result = service.backup(args.output)
        print(result)
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _run(args, parser)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"copymark: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
