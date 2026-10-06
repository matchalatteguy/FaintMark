# CopyMark

Free, local invisible image watermarks. Create a separate copy for each recipient,
then identify that copy after it has been shared. CLI, MCP and a small web interface
use the same local registry.

## Start

Requires Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
After cloning this repository:

```sh
uv sync --locked
uv run copymark serve
```

On macOS, you can also double-click **Launch CopyMark.command** after setup.
First use downloads about 65 MB of verified, free TrustMark Q models.
After that, image processing works offline. No paid API or hosted service is used.
The Python runtime and dependencies take additional disk space.

1. Drop in a JPEG or opaque PNG.
2. Enter recipient names separated by commas or new lines and select **Create copies**.
3. Download the ZIP and send the appropriate copy.
4. Download a shared copy, select **Check image**, and drop it in.

Original files remain unchanged. Outputs are PNGs. JPEG, PNG and WebP recovered
images can be checked. Transparency, animations and non-sRGB inputs are rejected
for marking rather than silently changing their appearance.

## CLI

```sh
uv run copymark mark photo.jpg --recipient Alice --recipient Bob --output ./exports
uv run copymark check downloaded.jpg
uv run copymark list
uv run copymark backup registry-backup.zip
```

Use `--json` with `mark`, `check` or `list` for machine-readable results.
`check` exits with 0 for a match, 2 for unknown/inconclusive, and 1 for an error.
You can supply a text file with one recipient per line using `--recipients-file`.

```sh
uv run copymark --home ./my-private-registry mark photo.jpg --recipient Alice --output ./exports
uv run copymark --home ./my-private-registry check downloaded.jpg --json
```

The default registry is `~/.copymark`; `COPYMARK_HOME` or `--home` selects another.
Every installation has independent records and random copy IDs. Other users can
decode a copy's ID, but they cannot look up your recipient names without your
registry. Watermarks are not secret or impossible to remove.

## MCP

CopyMark uses the official MCP SDK over stdio. Add this configuration to your
MCP client's server settings, replacing the directory with your clone's absolute
path:

```json
{
  "mcpServers": {
    "copymark": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/copymark", "run", "copymark", "mcp"]
    }
  }
}
```

Tools: `mark_image`, `check_image`, `list_copies`, `backup_registry`.
Supply absolute image/output paths. CLI, web and MCP share the same registry by
default. MCP tool calls access local files and do not send images to platforms.

## QA

Follow the [QA matrix](docs/QA.md) for Discord, WhatsApp and Instagram.
Record the exact copy ID, client/settings and final downloaded file.

The [engine comparison](docs/RESEARCH.md) used nine fixtures
and five IDs per fixture. TrustMark Q recovered 435/450 IDs in the routine local
test group; shrinking and recompression still caused failures. These are sample
results, not certified platform compatibility. Actual platform round trips are
pending your QA. Raw local research outputs are excluded from Git.

Each saved export is decoded before success is reported. A compression/resize
preflight flags fragile copies. It cannot guarantee survival of later processing.
**Matched** identifies an assigned recipient copy; it does not prove that person
posted it. **Unknown** means a decoded ID is absent from this registry.
**Inconclusive** means no usable ID was recovered. No nearest-recipient guessing
is used, and a watermark alone does not establish legal ownership.

## Backup

Keep the private registry backup: it maps IDs to recipient names. A backup
contains that database and reference thumbnails, so treat it as private. It
contains no full-resolution originals or model files.

To restore, stop CopyMark, extract the backup into a **new, empty** private folder,
then select that folder with `--home` or `COPYMARK_HOME`. The archive contains
`registry.sqlite3`, `thumbnails/` and `format.json`. Do not overwrite an existing
registry. Model files are downloaded/reused again as needed; old export paths
refer to the original machine, while identification records remain usable.

## Development

```sh
uv sync --locked --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check src tests
```

The normal tests use a small injected engine and exercise registry isolation,
export verification/rollback, input limits, CLI, real MCP protocol, and web APIs.
Run the optional real-model smoke tests after downloading models:

```sh
COPYMARK_INTEGRATION=1 uv run --extra dev pytest -m integration
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding platforms or engines and
[THIRD_PARTY.md](THIRD_PARTY.md) for model provenance. No recipient databases,
original images, exports or checkpoints belong in commits.

MIT licensed. This repository remains private during initial QA.
