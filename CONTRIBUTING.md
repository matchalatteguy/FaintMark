# Contributing

FaintMark is a local, free tool. Keep the CLI, MCP tools and web interface on the
same core operations. Keep originals unchanged and recipient data out of Git.

```sh
uv sync --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check src tests
```

For a new platform, use the workflow in [the QA matrix](docs/QA.md). Record the
platform, client, date, send/download settings, final dimensions and exact copy
ID result. Use images you can share, and obtain approval before publishing any
image, recipient label or private registry. Submit anonymized results and a
reproducible transformation profile; a platform name alone is not a robustness
guarantee.

For an engine change, add a small, reproducible comparison of complete ID
recovery, false matches and visual quality. Do not accept a nearest ID when
decoding fails. A copied identifier must never be described as proof that a
person leaked an image. Tests should exercise saved output files and include
unmarked images.

Use the engine interface in `src/faintmark/engine.py` for future algorithms.
Introduce new variants/schemas explicitly, retain old decoding compatibility,
and preserve the registry's migration path. Keep model provenance and hashes
reviewable; do not commit checkpoints or add paid services to the default path.
