#!/usr/bin/env bash
#
# run_andela_lookup.sh
# --------------------
# One-command runner for andela_profile_lookup.py on macOS.
#
# - Verifies python3 is available
# - Creates a local virtualenv (./.venv) on first run
# - Installs Playwright + Chromium if missing
# - Runs the lookup script
#
# Usage:
#   chmod +x run_andela_lookup.sh        # one time
#   ./run_andela_lookup.sh input.csv output.tsv
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/andela_profile_lookup.py"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <input.csv> <output.tsv>"
  exit 1
fi

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Error: andela_profile_lookup.py is missing next to this script."
  echo "Place both files in the same folder."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install with:  brew install python@3.11"
  exit 1
fi

# Create the venv on first run.
if [[ ! -d "$VENV_DIR" ]]; then
  echo "First-time setup: creating virtual environment ..."
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Install dependencies if missing.
if ! python -c "import playwright" 2>/dev/null; then
  echo "Installing Playwright (one time, ~30 sec) ..."
  pip install --quiet --upgrade pip
  pip install --quiet playwright
fi

# Make sure Chromium is downloaded for Playwright.
if ! python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch(channel='chrome').close()
" 2>/dev/null; then
  echo "Downloading Chromium for Playwright (one time, ~150 MB) ..."
  python -m playwright install chromium
fi

echo
echo "Running lookup. A browser window will open shortly."
echo "Sign in to Andela with your @andela.com account if prompted."
echo
exec python "$PYTHON_SCRIPT" "$1" "$2"
