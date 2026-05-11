#!/bin/bash
# Double-click this file to start the job finder server.
# It will open the dashboard in your default browser.
cd "$(dirname "$0")"
echo "Starting job finder server..."
echo "Press Ctrl+C in this window to stop the server."
echo ""
# Use the project's venv so rendercv and the tailor engine are importable.
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python server.py
else
  echo "Warning: .venv missing. Run: python3 -m venv .venv && .venv/bin/pip install python-docx pdfplumber rank-bm25 markdown-it-py 'rendercv[full]'" >&2
  exec python3 server.py
fi
