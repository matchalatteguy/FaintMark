#!/bin/zsh
set -eu
cd "${0:A:h}"
if command -v uv >/dev/null 2>&1; then
  exec uv run faintmark serve
elif [[ -x .venv/bin/faintmark ]]; then
  exec .venv/bin/faintmark serve
else
  print 'Install uv, then run: uv sync'
  read -r '?Press Enter to close.'
fi
