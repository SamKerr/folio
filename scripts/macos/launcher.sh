#!/bin/bash
# Folio.app launcher — opens the GUI without a Terminal window (uses pythonw).

set -euo pipefail

FOLIO_PROJECT_DIR="@FOLIO_PROJECT_DIR@"
cd "$FOLIO_PROJECT_DIR"

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [[ -x ".venv/bin/pythonw" ]]; then
	exec ".venv/bin/pythonw" -m folio gui
fi

if [[ -x ".venv/bin/python" ]]; then
	exec ".venv/bin/python" -m folio gui
fi

if command -v uv >/dev/null 2>&1; then
	exec uv run folio gui
fi

osascript -e 'display alert "Folio setup required" message "Run uv sync in the Folio project folder first, then rebuild the app." as critical'
exit 1
