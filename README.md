# FaintMark

Free, local invisible image watermarks. Create a separate copy for each recipient,
then identify that copy after it has been shared. CLI, MCP and a small web interface
use the same local registry.

## Start

Requires Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Clone and install:

```sh
git clone https://github.com/matchalatteguy/FaintMark.git
cd FaintMark
uv sync --locked
```

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
Existing CopyMark installations automatically reuse `~/.copymark` if it contains
a registry and no FaintMark registry exists. `COPYMARK_HOME` remains a supported
fallback, and the old `copymark` / `copymark-mcp` commands remain aliases. Your
existing marked images and recipient records keep working.
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
It returns the folder and individual PNG paths. ZIPs are used only for browser
downloads and registry backups.
Supply absolute image/output paths. CLI, web and MCP share the same registry by
default. MCP tool calls access local files and do not send images to platforms.

## Local interface

```sh
uv run faintmark serve
```

On macOS, you can also double-click **Launch FaintMark.command** after setup.
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

Exports retain the displayed pixel dimensions, with EXIF orientation normalized
(a rotated source may swap width and height). FaintMark adds no EXIF, recipient
names or tracking tags to the images; existing metadata is not copied to exports.
The watermark itself changes pixel values slightly. PNG output can be substantially
larger than a JPEG source, so original file sizes are not preserved.

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

To restore, stop FaintMark, extract the backup into a **new, empty** private folder,
then select that folder with `--home` or `FAINTMARK_HOME`. The archive contains
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
FAINTMARK_INTEGRATION=1 uv run --extra dev pytest -m integration
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding platforms or engines and
[THIRD_PARTY.md](THIRD_PARTY.md) for model provenance. No recipient databases,
original images, exports or checkpoints belong in commits.

MIT licensed. This repository remains private during initial QA.
