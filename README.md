# FaintMark

[![CI](https://github.com/matchalatteguy/FaintMark/actions/workflows/ci.yml/badge.svg)](https://github.com/matchalatteguy/FaintMark/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/faintmark)](https://pypi.org/project/faintmark/)

Invisible per-recipient image watermarks. Create one marked copy per recipient,
then identify which copy a shared or leaked image is. Designed to tolerate the
recompression and resizing chat apps apply; see the app tests and limits
below. Runs locally, no account, no upload. Python CLI and MCP server.

```
$ faintmark mark photo.jpg alice bob
alice  991e318a21  /Users/me/Pictures/marked/photo-991e318a21.jpg
bob  746ac9fa88  /Users/me/Pictures/marked/photo-746ac9fa88.jpg
2 copies in /Users/me/Pictures/marked

$ faintmark check ~/Downloads/forwarded.jpg
matched: alice  991e318a21  marked 2026-10-06T23:11:54Z
```

![Original scene, a WhatsApp chat screenshot of the marked copy, and CLI checks: the received copy matches, the original has no mark, a transplanted id is flagged](https://raw.githubusercontent.com/matchalatteguy/FaintMark/main/docs/hero.jpg)

Send each person only their own file; file names carry the id, not the name.
A match identifies the label the copy was issued under, not who shared it.
The mark is intended to be visually unobtrusive on photographs. JPEG, PNG and
WebP keep their format; HEIC becomes JPEG.

## Install

```sh
uvx faintmark mark photo.jpg alice bob   # runs without installing; needs uv
uv tool install faintmark                # or: pipx install faintmark
```

Python 3.11 or newer on macOS, Linux or Windows (Intel Macs: 3.11 to 3.13).
[uv](https://docs.astral.sh/uv/) can install Python and run FaintMark. The
first `mark` or `check` downloads Adobe's TrustMark Q models (65 MB, SHA-256
verified) into `~/.faintmark`. For HEIC input install `faintmark[heic]`:
`uv tool install 'faintmark[heic]'`, or without a persistent install
`uvx --from 'faintmark[heic]' faintmark mark photo.heic alice`.
`uv tool uninstall faintmark` removes the command and leaves `~/.faintmark` in
place.

```
faintmark mark IMAGE RECIPIENT... [-o DIR] [--format png|jpeg|webp] [--json]
faintmark check IMAGE [--deep] [--files] [--json]
faintmark list [-n N] [--files] [--json]
```

Copies go into `marked/` beside the image unless `-o` says otherwise. Quote
labels with spaces: `faintmark mark photo.jpg 'Alice Smith'`. One run marks 1
to 100 recipients. `--json` prints the result the matching MCP tool returns;
`mark` includes the source file name and output paths, `check` and `list` omit
file names and paths unless `--files` is set. `check --deep` also tries a flip
and small rotations, and when nothing is detected lists up to three
registered ids within 26 of 96 codeword bits of the raw decoder output as
candidates, with their bit distance. Those are uncalibrated and can be
coincidental or forged; they are never a match. With `--json`, errors print
`{"error": "..."}`. `check` exits 0 for `matched`, 1 for `unregistered` or
`not_detected`, 2 for an error.

`mark` accepts non-animated JPEG, PNG, WebP and HEIC up to 25 megapixels
without transparency (16-bit RGB is read at 8 bits; 16-bit grayscale and CMYK
are rejected) and needs about 1.5 GB of memory at that size. `check` reads the
first frame of anything Pillow opens, up to 100 megapixels.

## Agents

```sh
claude mcp add --scope user faintmark -- uvx faintmark mcp
codex mcp add faintmark -- uvx faintmark mcp
gemini mcp add -s user faintmark uvx faintmark mcp
```

Any other client that reads an `mcpServers` config (Claude Desktop, Cursor,
Windsurf): add this entry to the client's MCP configuration. The client must
find `uvx` on its PATH; set `FAINTMARK_HOME` in the server's environment to
use another registry.

```json
{ "mcpServers": { "faintmark": { "type": "stdio", "command": "uvx", "args": ["faintmark", "mcp"] } } }
```

Choose one route per client; plugins and extensions bundle the skill too. For
HEIC input start the server as `uvx --from 'faintmark[heic]' faintmark mcp`;
the bundled launchers use the base package.

- [Add to Cursor](https://cursor.com/en/install-mcp?name=faintmark&config=eyJ0eXBlIjoic3RkaW8iLCJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJmYWludG1hcmsiLCJtY3AiXX0=)
- [Add to VS Code](https://vscode.dev/redirect/mcp/install?name=faintmark&config=%7B%22name%22%3A%22faintmark%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22faintmark%22%2C%22mcp%22%5D%7D)
- Claude Code plugin: `claude plugin marketplace add matchalatteguy/FaintMark` then `claude plugin install faintmark@faintmark`
- Codex plugin: `codex plugin marketplace add matchalatteguy/FaintMark` then `codex plugin add faintmark@faintmark`
- Gemini extension: `gemini extensions install https://github.com/matchalatteguy/FaintMark`
- Skill for any agent with a shell: `npx skills add matchalatteguy/FaintMark`

| Tool | Arguments | Returns |
| --- | --- | --- |
| `mark_image` | `image_path`, `recipients`, optional `output_dir`, `format` | output folder and each copy's `id`, `path`, `warnings` |
| `check_image` | `image_path`, optional `files`, `deep` | `status` of `matched` (with `recipient`, `id`, `marked_at`, and `same_image` when a stored hash exists), `unregistered` (with `id`) or `not_detected`; with `deep`, `transform` naming the flip or rotation that recovered the result, and `suspects` (`id`, `recipient`, `bit_errors`, `same_image`) plus `registry_size` when nothing was detected |
| `list_copies` | optional `limit`, `files` | registered copies, newest first |

Give tools absolute paths. `unregistered` means an id was decoded but it is
not in this machine's registry; `not_detected` means no readable mark, which
says nothing about where the image came from. `same_image` compares
perceptual hashes with the issued copy: `false` means they differ beyond the
threshold, which cropping or an id copied into another picture can cause; the
comparison can also miss differences.

`check_image` and `faintmark check --json` return one of these: the three
plain statuses (a match with `same_image: false` means the picture differs
from the issued copy); with `deep`, a result recovered by a transform, or a
miss with candidates (`suspects` is empty when no registered id is within the
cutoff). The CLI prints errors as the last line; MCP tools raise them as tool
errors (`isError`): messages from the service match, argument validation
messages differ.

```
{"status": "matched", "id": "991e318a21", "recipient": "alice", "marked_at": "2026-10-06T23:11:54Z", "same_image": true}
{"status": "matched", "id": "991e318a21", "recipient": "alice", "marked_at": "2026-10-06T23:11:54Z", "same_image": false}
{"status": "unregistered", "id": "3123f6f877"}
{"status": "not_detected"}
{"status": "matched", "id": "991e318a21", "recipient": "alice", "marked_at": "2026-10-06T23:11:54Z", "same_image": true, "transform": "rotated 4"}
{"status": "not_detected", "suspects": [{"id": "991e318a21", "recipient": "alice", "bit_errors": 21, "same_image": true}], "registry_size": 100}
{"error": "forwarded.jpg: no such file"}
```

`mark_image` and `faintmark mark --json` return the first line; `list_copies`
and `faintmark list --json` return the second, newest first:

```
{"original": "photo.jpg", "output_dir": "/Users/me/Pictures/marked", "copies": [{"id": "991e318a21", "recipient": "alice", "path": "/Users/me/Pictures/marked/photo-991e318a21.jpg", "warnings": []}]}
{"copies": [{"id": "991e318a21", "recipient": "alice", "marked_at": "2026-10-06T23:11:54Z", "warnings": []}]}
```

## Tested on real apps

7 October 2026, FaintMark 0.1.0, three source photos (an iPhone scene, a CC0
portrait, a CC0 sunset). Each row reports the samples actually sent on that
route at default photo quality. Screenshot rows are screenshots of the
receiving phone, cropped to the photo before checking. These are individual
round-trip observations, not recovery rates or guarantees for an app.

| Route | Received | Result |
| --- | --- | --- |
| WhatsApp photo, all three | long edge 1600 px, 155 to 317 KB | matched 3/3 |
| Discord attachment, scene | original size, 1.7 MB | matched 1/1 |
| Discord sticker made from the scene | 217x285 PNG | matched 1/1 |
| Telegram photo, scene | 960x1280, 102 KB | matched 1/1 |
| WeChat photo, portrait and sunset | long edge 1644 to 1920 px, 67 to 302 KB | matched 2/2 |
| Instagram DM, portrait | 1206x804, 176 KB | matched 1/1 |
| Chat screenshots on WhatsApp, Discord, Telegram, WeChat, Instagram | photo long edge 286 to 1022 px | matched 9/9 |
| Tinder profile card, portrait (screenshot) | heavy crop | not detected 0/1 |

Every match also reported `same_image: true`. The originals, every received
file, the screenshots, the crops and a manifest of expected ids and results
([docs/evidence-2026-10-07.json](https://github.com/matchalatteguy/FaintMark/blob/main/docs/evidence-2026-10-07.json)) are in the
[evidence release](https://github.com/matchalatteguy/FaintMark/releases/tag/evidence-2026-10-07).
On a machine without this registry, the received files return `unregistered`
with the id from the manifest; the originals and the Tinder crop return
`not_detected`. X, Signal, iMessage and Instagram stories were not tested.

## How it works

[TrustMark Q](https://github.com/adobe/trustmark) (Adobe, MIT) embeds a 40-bit
id as an image-wide pattern designed to tolerate JPEG recompression, WebP
conversion and moderate resizing. This is forensic watermarking, not
steganography: anyone with TrustMark can read the id; only your registry maps
it to a name. FaintMark draws a random id per recipient, writes the copy in
the source format (JPEG at the source's own quantization tables, PNG, WebP;
HEIC becomes JPEG), decodes the saved copy to verify its id is recoverable,
and records id, recipient, file and a perceptual hash of the copy in a local
SQLite registry. On a registered match, `check` compares perceptual hashes
and reports `same_image: false` when their distance exceeds the threshold. A
JPEG whose source settings lose the mark is saved at quality 95 instead, and
says so in its warnings. Marking an image that already carries a mark
replaces it and says so. A preflight re-encodes each copy at JPEG quality 70,
at full size (skipped with a warning when a side exceeds 65,500 px, JPEG's
limit) and resized to 1280 px (half size when the image is smaller), and
warns when the id does not survive; send those copies as a file rather than a
photo.

ICC profiles are kept so Display P3 photos stay the same colour. EXIF and other
metadata are not copied.

Compatibility with Adobe's implementation is checked in: `tests/fixtures`
holds BCH vectors and two images marked by upstream TrustMark 0.9.2; FaintMark
decodes their ids and reproduces their marked pixels within one value per RGB
channel. A chat-app style ladder in the real-model tests (resize to 1600, 1280
and 1024 px with JPEG 70 to 80, WebP 75, and a chained resize-plus-JPEG pass,
on delivered JPEG bytes) recovers the id on two 12-megapixel synthetic covers
and the 320 px fixture, except WebP 75 on the fixture.

## Attacks we measured

Someone who has this repository and a copy can do the following; measured on
three photos at 2000 px, two ids each, full tables in the attack report
attached to the evidence release.

- **Erase the mark invisibly.** Re-running the public encoder with a random
  payload removes it at 42 to 47 dB PSNR (6/6). `check` then says
  `not_detected`, exactly as for an unmarked photo.
- **Overwrite it.** Re-marking with another id wins every time (last writer
  wins, 41 to 44 dB). In these trials the decoder read the replacement and
  never the previous id.
- **Combine copies.** Averaging two or three recipients' copies defeats the
  plain decoder every time. Against a registry of 100 ids, the closest
  registered codeword belonged to a colluder in 264 of 264 trials (12 to 30
  bits away; the closest innocent was 28 to 41 away), and with the 26-bit
  cutoff `check --deep` lists at least one colluder in 253 of 264 and never
  an innocent. For random decoder output each registered id has about a
  4 in a million chance of falling within the cutoff, so coincidences grow
  with the registry.
- **Forge the picture check.** A plain transplant of an id into another photo
  fails `same_image` (28 to 32 bits away). A tuned forgery that also nudges
  the luminance to flip the cheapest hash bits passes both checks at 27 dB
  PSNR, with a visible but ordinary-looking tone shift.
- **Ordinary edits.** Blur, noise, JPEG down to quality 40, downscale to 100 px
  and back, flips, brightness and contrast changes, a print-and-photograph
  simulation: the mark survived all of them (6/6). Crops of 15% or more per
  side and rotations above 4 degrees destroy it for the plain decoder;
  `--deep` recovers rotations up to about 10 degrees.

## Limits

- `matched` means the decoded id is registered to that recipient. It does not
  prove who shared the image: copies can be forwarded.
- `matched` is a registry lookup, not a signature. Anyone who knows an id can
  embed it in another image. The perceptual-hash comparison may flag a
  different picture, but cannot authenticate a copy or detect re-marking of
  the same picture. TrustMark also publishes a watermark remover; an informed
  recipient can strip the mark, and so can heavy editing.
- Recipients who combine their copies defeat a plain `check`; `--deep`
  lists candidates by codeword distance, which can be coincidental or forged
  and is never proof.
- Images with an aspect ratio above 2:1 are marked only in their centre
  square; edits that move an image across that boundary can prevent decoding.
  Heavy downscaling and cropping destroy the mark.
- Results trust this machine's registry. Keep it private: anyone who can edit
  it can change attribution.

## Registry

`~/.faintmark/registry.sqlite3` maps ids to recipient names. Keep it private
and back it up; without it, a recoverable id is reported as `unregistered`.
`FAINTMARK_HOME` selects another directory.

MIT licensed. TrustMark and its models are Adobe's, also MIT. See
[CONTRIBUTING](https://github.com/matchalatteguy/FaintMark/blob/main/CONTRIBUTING.md),
[SECURITY](https://github.com/matchalatteguy/FaintMark/blob/main/SECURITY.md) and
[releases](https://github.com/matchalatteguy/FaintMark/releases).

<!-- mcp-name: io.github.matchalatteguy/faintmark -->
