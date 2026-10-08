# Contributing

```sh
uv sync --locked --extra heic
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
FAINTMARK_INTEGRATION=1 uv run pytest   # also runs the real-model tests (downloads 65 MB once)
```

Open an issue before substantial features or new dependencies; small fixes can
go straight to a pull request. Keep each PR focused and describe its
validation. The maintainer decides scope.

Keep it small. FaintMark does one thing: one invisibly marked copy per
recipient, and a check that identifies a copy. New dependencies and CLI
options need a concrete use case.

Changes must continue to decode copies made by earlier releases. Add
regression fixtures before changing the encoder, decoder or payload format,
and show recovery rates before and after on the same images and transforms
(JPEG quality 70, resizing to 1280 px). Never return a nearest-match guess.

Keep personal photos, recipient registries and user-generated marked copies
out of commits. Small synthetic compatibility fixtures are welcome.

## Releasing

1. Start from a green `main`; note user-visible changes and anything that
   affects decoding or registry compatibility.
2. Bump the version in `pyproject.toml`, `server.json`,
   `gemini-extension.json`, `.claude-plugin/plugin.json` and the pinned
   launchers in `.mcp.json` and `gemini-extension.json`; run `uv lock`.
3. Run the commands above; `uv build` and check both distributions.
4. Write release notes by hand (what changed for users, compatibility).
5. Tag `vX.Y.Z` and push the tag; the release workflow publishes to PyPI,
   creates the GitHub release and publishes to the MCP registry.
6. Verify a fresh `uvx faintmark --version`, the PyPI page and the registry
   entry. If a step failed, rerun the workflow; it skips what already exists.
```
