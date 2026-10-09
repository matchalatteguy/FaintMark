---
name: faintmark
license: MIT
description: Forensic (per-recipient) invisible image watermarking. Create one marked copy of an image per recipient, and later identify which registered copy a shared or leaked image is. Use when the user wants to share a picture with several people through chat apps (WhatsApp, Discord, Telegram, iMessage, Signal, WeChat, X) or email and trace a copy back to its recipient, or asks which recipient a received image was issued to. Not for visible logos or text watermarks.
---

# FaintMark

Local CLI (`faintmark`, run with `uvx faintmark ...` if not installed). Every recipient gets a
copy with a unique invisible id, designed to survive chat-app recompression and moderate
resizing. Nothing is uploaded. The first mark or check downloads 65 MB of models.

When the FaintMark MCP server is configured, prefer its tools `mark_image`, `check_image` and
`list_copies`; they cover the same operations and share the registry with the CLI.

```sh
faintmark mark /abs/photo.jpg alice bob --json   # MCP: mark_image {"image_path": "/abs/photo.jpg", "recipients": ["alice", "bob"]}
# {"original": "photo.jpg", "output_dir": "/abs/marked", "copies": [{"id": "991e318a21", "recipient": "alice", "path": "/abs/marked/photo-991e318a21.jpg", "warnings": []}, {"id": "746ac9fa88", "recipient": "bob", "path": "/abs/marked/photo-746ac9fa88.jpg", "warnings": []}]}
faintmark check /abs/received.jpg --json         # MCP: check_image {"image_path": "/abs/received.jpg"}
# {"status": "matched", "id": "991e318a21", "recipient": "alice", "marked_at": "2026-10-06T23:11:54Z", "same_image": true}
# {"status": "unregistered", "id": "3123f6f877"}  or  {"status": "not_detected"}
faintmark list -n 2 --json                       # MCP: list_copies {"limit": 2}
# {"copies": [{"id": "746ac9fa88", "recipient": "bob", "marked_at": "2026-10-06T23:11:54Z", "warnings": []}, {"id": "991e318a21", "recipient": "alice", "marked_at": "2026-10-06T23:11:54Z", "warnings": []}]}
```

- Writes files only, sends nothing. Send each person only their own file (`copies[].path`); file
  names carry the id, not the recipient. The source format is kept: JPEG stays JPEG.
- `check` exits 0 for `matched` (returns `recipient`, `id`, `marked_at`, `same_image`), 1 otherwise, 2 on
  error. `same_image`, present when the registry stored a hash for the copy, compares perceptual hashes
  with the issued copy: `false` means they differ beyond the threshold, which cropping or an id copied
  into another picture can cause. `true` is not authentication; a tuned forgery passed it in our
  measurements. `--files` adds file names and paths; omit it unless needed. HEIC input is written as JPEG.
- If a leaked copy returns `not_detected` and tampering is plausible, run `faintmark check IMAGE --deep --json`:
  it tries a flip and small rotations (`transform` names the one that worked), and otherwise lists `suspects` (`id`, `recipient`, `bit_errors`,
  `same_image`), up to three registered ids within 26 of 96 codeword bits of the raw decoder output, empty
  when none is that close, and `registry_size`. Suspects are uncalibrated candidates: they can be coincidental
  or forged. Say "the closest registered id is X, N bits away"; do not attribute the image to X.
- `unregistered` means a watermark was found but it is not in this machine's registry (`~/.faintmark`,
  or `FAINTMARK_HOME`); `not_detected` means no readable mark, for example after heavy downscaling or
  cropping, or a chat screenshot that still includes the app frame: crop it to the photo and check again.
- A warning starting with "may not survive" means the copy is fragile; suggest sending it as a file
  rather than a photo. Other warnings are informational (for example a JPEG saved at quality 95).
- Say "the id in this image is registered to X", never "X leaked it": copies can be forwarded and
  ids can be copied into other images. The mark can be removed by someone who knows it is there,
  so `not_detected` says nothing about where an image came from.
- HEIC input needs the `heic` extra (`uvx --from 'faintmark[heic]' faintmark ...`). `mark` takes JPEG, PNG,
  WebP or HEIC up to 25 MP with no animation, transparency, CMYK or 16-bit grayscale, and 1 to 100 labels of
  1 to 200 printable characters; `check` reads anything Pillow opens up to 100 MP.
