# Contributing

FaintMark is a local, free tool. Keep the CLI and MCP tools on the same
core operations. Keep originals unchanged and recipient data out of Git.

```sh
uv sync
uv run pytest
uv run ruff check src tests
```

For an engine change, add a small, reproducible comparison of complete ID
recovery, false matches and visual quality. Do not accept a nearest ID when
decoding fails. A copied identifier must never be described as proof that a
person leaked an image. Tests should exercise saved output files and include
unmarked images.

Use the engine interface in `src/faintmark/engine.py` for future algorithms.
Introduce new variants/schemas explicitly, retain old decoding compatibility,
and preserve the registry's migration path. Keep model provenance and hashes
reviewable; do not commit model files or add paid services to the default path.
