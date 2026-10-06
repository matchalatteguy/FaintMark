---
name: faintmark
description: Create invisible per-recipient watermarked copies of an image and later identify which copy a shared or leaked image came from. Use when the user wants to share a picture with several people and trace who passed it on (WhatsApp, Discord, X, iMessage, WeChat, Signal, email), or asks which recipient a received image belongs to.
---

# FaintMark

Local CLI (`faintmark`, run with `uvx faintmark ...` if not installed). Every recipient gets a
copy with a unique invisible id, designed to survive chat-app recompression and moderate
resizing. Nothing is uploaded. The first run downloads 65 MB of models.

```sh
faintmark mark /abs/photo.jpg alice bob --json     # copies in /abs/marked/, one per recipient
faintmark check /abs/received.jpg --json           # status: matched | unregistered | not_detected
faintmark list --json
```

- Send each person only their own file (`copies[].path`). Keep the source format: JPEG stays JPEG.
- `check` exits 0 for `matched` (returns `recipient`, `id`, `original`, `marked_at`), 1 otherwise, 2 on error.
- `unregistered` means a watermark was found but it is not in this machine's registry (`~/.faintmark`);
  `not_detected` means no readable mark, for example after heavy downscaling or cropping.
- A copy with `warnings` is fragile; suggest sending it as a file rather than a photo.
- Say "this is the copy issued to X", never "X leaked it": copies can be forwarded.
- HEIC input needs the `heic` extra (`uvx --from 'faintmark[heic]' faintmark ...`). No transparency, up to 25 MP.
