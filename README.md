# FaintMark

Invisible per-recipient image watermarks. Mark one copy per recipient, then
identify a shared or leaked copy. Built for photos shared through chat apps
(WhatsApp, iMessage, Discord, Telegram, Signal, WeChat, X) and designed to
survive the recompression and resizing they apply. Local and free, no account,
no upload. CLI and MCP server.

```
$ faintmark mark photo.jpg alice bob
alice  991e318a21  /Users/me/Pictures/marked/photo-991e318a21.jpg
bob  746ac9fa88  /Users/me/Pictures/marked/photo-746ac9fa88.jpg
2 copies in /Users/me/Pictures/marked

$ faintmark check ~/Downloads/forwarded.jpg
matched: alice  991e318a21  photo.jpg  marked 2026-10-06T23:11:54Z
```

Send each person only their own file; file names carry the id, not the name.
Copies are indistinguishable by eye on photographs and keep the original's
format (HEIC becomes JPEG) and roughly its size. In the run above, a 935 KB
JPEG gave 873 KB copies, and a half-size, quality-60 re-save of one (40 KB)
still identified alice.

## Install

```sh
uvx faintmark mark photo.jpg alice bob   # no install, needs uv
uv tool install faintmark                # or: pipx install faintmark
```

Python 3.11 or newer on macOS, Linux or Windows; [uv](https://docs.astral.sh/uv/)
is the easiest way to get it. The first `mark` or `check` downloads Adobe's
TrustMark Q models (65 MB, SHA-256 verified) into `~/.faintmark`. iPhone HEIC
input needs the `heic` extra: `uv tool install 'faintmark[heic]'`, or
`uvx --from 'faintmark[heic]' faintmark mcp` for the server.
`uv tool uninstall faintmark` removes the command and leaves `~/.faintmark` in
place.

```
faintmark mark IMAGE RECIPIENT... [-o DIR] [--format png|jpeg|webp] [--json]
faintmark check IMAGE [--json]
faintmark list [-n N] [--json]
```

`--json` prints the same JSON the MCP tools return. `check` exits 0 for a
match, 1 for no match, 2 for an error. One run marks 1 to 100 recipients.
Marking accepts JPEG, PNG, WebP and HEIC up to 25 megapixels, not animated,
without transparency; `check` reads anything Pillow opens.

## Agents

```sh
claude mcp add --scope user faintmark -- uvx faintmark mcp
codex mcp add faintmark -- uvx faintmark mcp
gemini mcp add -s user faintmark uvx faintmark mcp
```

Any other client that reads an `mcpServers` config (Claude Desktop, Cursor, Windsurf):

```json
{ "mcpServers": { "faintmark": { "command": "uvx", "args": ["faintmark", "mcp"] } } }
```

[Add to Cursor](https://cursor.com/en/install-mcp?name=faintmark&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJmYWludG1hcmsiLCJtY3AiXX0=) ·
[Add to VS Code](https://vscode.dev/redirect/mcp/install?name=faintmark&config=%7B%22name%22%3A%22faintmark%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22faintmark%22%2C%22mcp%22%5D%7D) ·
Claude Code plugin: `claude plugin marketplace add matchalatteguy/FaintMark` then `claude plugin install faintmark@faintmark` ·
Codex plugin: `codex plugin marketplace add matchalatteguy/FaintMark` then `codex plugin add faintmark@faintmark` ·
Gemini extension: `gemini extensions install https://github.com/matchalatteguy/FaintMark` ·
Skill for any agent with a shell: `npx skills add matchalatteguy/FaintMark`

| Tool | Arguments | Returns |
| --- | --- | --- |
| `mark_image` | `image_path`, `recipients`, optional `output_dir`, `format` | output folder and each copy's `id`, `path`, `warnings` |
| `check_image` | `image_path` | `status` of `matched` (with `recipient`, `id`, `original`, `marked_at`), `unregistered` (with `id`) or `not_detected` |
| `list_copies` | optional `limit` | registered copies, newest first |

Give tools absolute paths. `unregistered` means an id was read but it is not
in this machine's registry; `not_detected` means no readable mark, which says
nothing about where the image came from.

## How it works

[TrustMark Q](https://github.com/adobe/trustmark) (Adobe, MIT) embeds a 40-bit
id as a faint, image-wide pattern (typically 41 to 50 dB PSNR) designed to
survive JPEG recompression, WebP conversion and moderate resizing. This is
forensic watermarking, not steganography: anyone with TrustMark can read the
id; only your registry maps it to a name. FaintMark draws a random id per
recipient, writes the copy in the source format (JPEG at the source's own
quantization tables, PNG, WebP; HEIC becomes JPEG), decodes the encoded copy to
prove the id is there, and records id, recipient and file in a local SQLite
registry. A JPEG whose source settings lose the mark is saved at quality 95
instead, and says so in its warnings. A preflight re-encodes each copy at JPEG
quality 70, at full size and resized to 1280 px (half size when the image is
smaller), and warns when the id does not survive; send those copies as a file
rather than a photo.

ICC profiles are kept so Display P3 photos stay the same colour. EXIF and other
metadata are not copied. Recovery depends on what is done to the copy; the
preflight warning is the per-copy evidence.

## Limits

- `matched` means the decoded id is registered to that recipient. It does not
  prove who shared the image: copies can be forwarded.
- `matched` is a registry lookup, not a signature. Anyone who knows an id can
  embed it in another image, and TrustMark publishes a watermark remover; an
  informed recipient can strip the mark.
- Two recipients comparing their copies can locate the mark.
- Images wider or taller than 2:1 carry the mark only in their centre square.
  Heavy downscaling (thumbnails, screenshots of previews) or cropping can
  destroy it.

## Registry

`~/.faintmark/registry.sqlite3` maps ids to recipient names. Keep it private
and back it up; without it a copy is `unregistered`. `FAINTMARK_HOME` selects
another location.

MIT licensed. TrustMark and its models are Adobe's, also MIT.

<!-- mcp-name: io.github.matchalatteguy/faintmark -->
