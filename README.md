# FaintMark

Free, local invisible image watermarks. Create a separate copy for each recipient,
then identify that copy after it has been shared. CLI and MCP share the same local
registry.

## Start

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Clone and install:

```sh
git clone https://github.com/matchalatteguy/FaintMark.git
cd FaintMark
uv sync --locked
```

The models are about 65 MB of ONNX files downloaded from Adobe on first use and
verified by SHA-256. HEIC input needs the extra: `uv sync --extra heic`.

## CLI

```sh
uv run faintmark mark photo.jpg recipient_1 recipient_2 recipient_3
uv run faintmark check downloaded.jpg
uv run faintmark list
```

Copies go to `marked/` beside the image; `-o DIR` picks another folder and
`--format png|jpeg|webp` overrides the format. Use `--json` with `mark`, `check`
or `list` for machine-readable results. Outputs keep the source format (JPEG stays
JPEG, PNG stays PNG, WebP stays WebP, HEIC becomes JPEG) and any ICC profile; EXIF
and other metadata are not copied. `check` reports `matched`, `unregistered` (a
watermark was found but it is not in this registry) or `not_detected`, and exits
with 0 for a match, 1 for no match and 2 for an error.

```sh
FAINTMARK_HOME=./my-private-registry uv run faintmark mark photo.jpg recipient_1 -o ./exports
FAINTMARK_HOME=./my-private-registry uv run faintmark check downloaded.jpg --json
```

The default registry is `~/.faintmark`; `FAINTMARK_HOME` selects another.
Every installation has independent records and random copy IDs. Other users can
decode a copy's ID, but they cannot look up your recipient names without your
registry. Watermarks are not secret or impossible to remove.

## MCP

FaintMark uses the official MCP SDK over stdio. Add this configuration to your
MCP client's server settings, replacing the directory with your clone's absolute
path:

```json
{
  "mcpServers": {
    "faintmark": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/faintmark", "run", "faintmark", "mcp"]
    }
  }
}
```

Tools: `mark_image`, `check_image`, `list_copies`.
`mark_image` takes an image path, a recipient-name list and optional `output_dir`
and `format`. It returns the output folder and each copy's path and id.
Supply absolute image/output paths. CLI and MCP share the same registry by
default. MCP tool calls access local files and do not send images to platforms.

## Development

```sh
uv sync --locked
uv run pytest
uv run ruff check src tests
```

The normal tests use a small injected engine and exercise registry isolation,
export verification/rollback, input limits, CLI, and real MCP protocol.
Run the optional real-model tests (they download the models on first use):

```sh
FAINTMARK_INTEGRATION=1 uv run pytest -m integration
```

No recipient databases, original images, exports or model files belong in commits.

MIT licensed.
