# Contributing

```sh
uv sync
uv run ruff check src tests
uv run pytest
FAINTMARK_INTEGRATION=1 uv run pytest   # also runs the real-model tests (downloads 65 MB once)
```

Keep it small. FaintMark does one thing: one invisibly marked copy per recipient, and a check
that identifies a copy. New dependencies, flags or disclaimers need a strong reason.

Engine changes must keep `check` working on copies made by earlier versions: keep the old
decoding path next to the new one. Show recovery rates before and after on the same transforms
(JPEG quality 70, resizing to 1280 px). Never return a nearest-match guess.

Keep recipient registries, original photos and marked copies out of commits.
