---
name: faintmark
description: Forensic (per-recipient) invisible image watermarking. Create one marked copy of an image per recipient, and later identify which registered copy a shared or leaked image is. Use when the user wants to share a picture with several people through chat apps (WhatsApp, Discord, Telegram, iMessage, Signal, WeChat, X) or email and trace a copy back to its recipient, or asks which recipient a received image was issued to. Not for visible logos or text watermarks.
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

- Writes files only, sends nothing. Send each person only their own file (`copies[].path`); file
  names carry the id, not the recipient. The source format is kept: JPEG stays JPEG.
- `check` exits 0 for `matched` (returns `recipient`, `id`, `original`, `marked_at`), 1 otherwise, 2 on error.
- `unregistered` means a watermark was found but it is not in this machine's registry (`~/.faintmark`);
  `not_detected` means no readable mark, for example after heavy downscaling or cropping.
- A copy with `warnings` is fragile; suggest sending it as a file rather than a photo.
- Say "the id in this image is registered to X", never "X leaked it": copies can be forwarded and
  ids can be copied into other images. The mark can be removed by someone who knows it is there,
  so `not_detected` says nothing about where an image came from.
- HEIC input needs the `heic` extra (`uvx --from 'faintmark[heic]' faintmark ...`). No transparency, up to 25 MP.
