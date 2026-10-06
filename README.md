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
verified by SHA-256.

## CLI

```sh
uv run faintmark mark photo.jpg --output ./exports --recipients "recipient_1,recipient_2,recipient_3"
uv run faintmark check downloaded.jpg
uv run faintmark list
uv run faintmark backup registry-backup.zip
```

Use `--json` with `mark`, `check` or `list` for machine-readable results.
Marking creates the output folder and saves one verified PNG per recipient;
CLI and MCP do not create a ZIP. Their results include the folder and image paths.
`check` exits with 0 for a match, 2 for unknown/inconclusive, and 1 for an error.
You can supply a text file with one recipient per line using `--recipients-file`.
Use repeated `--recipient` flags when a recipient label itself contains a comma.

```sh
uv run faintmark --home ./my-private-registry mark photo.jpg --recipient recipient_1 --output ./exports
uv run faintmark --home ./my-private-registry check downloaded.jpg --json
```

The default registry is `~/.faintmark`; `FAINTMARK_HOME` or `--home` selects another.
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

Tools: `mark_image`, `check_image`, `list_copies`, `backup_registry`.
`mark_image` takes an image path, recipient-name list and output-folder path.
It returns the folder and individual PNG paths. ZIPs are used only for registry
backups.
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
