#!/bin/bash
# One-shot setup for a fresh clone of this project.
# Double-click in Finder, or run from a terminal:
#   ./setup.command
#
# Creates ./.venv if it does not exist and installs every dependency the
# scraper, scorer, tailor engine and PDF renderer need. Safe to re-run —
# pip will only download what is missing or outdated.
set -e
cd "$(dirname "$0")"

GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
NC='\033[0m'

echo -e "${GREEN}>>> job-finder setup${NC}"
echo "    working dir: $(pwd)"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo -e "${RED}ERROR: python3 not found on PATH.${NC}"
  echo "Install Python 3.11 or newer (e.g. 'brew install python@3.13') and re-run."
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
echo "    python3: $(command -v python3)  (Python ${PY_VERSION})"

if [ ! -x ".venv/bin/python" ]; then
  echo -e "${YELLOW}>>> creating .venv${NC}"
  python3 -m venv .venv
else
  echo "    .venv already present, reusing"
fi

echo -e "${YELLOW}>>> upgrading pip${NC}"
.venv/bin/pip install --upgrade pip --quiet

echo -e "${YELLOW}>>> installing project dependencies${NC}"
.venv/bin/pip install --upgrade \
  python-jobspy \
  openpyxl \
  python-docx \
  pdfplumber \
  rank-bm25 \
  markdown-it-py \
  'rendercv[full]'

echo ""
echo -e "${GREEN}>>> done${NC}"
echo ""
echo "Next:"
echo "  1. (Optional) Edit .env  ← copy from .env.example, add APIFY_TOKEN etc."
echo "  2. Build the bullet corpus from your master sentences markdown:"
echo "       .venv/bin/python tailor/extract_corpus.py"
echo "  3. Start the server (any of these — they all auto-use .venv):"
echo "       python3 server.py"
echo "       .venv/bin/python server.py"
echo "       open start_server.command"
echo ""
echo "Then visit http://localhost:8765"
