#!/bin/bash
# Double-click this file in Finder to run the LinkedIn job scrape.
cd "$(dirname "$0")"
python3 scrape_jobs.py
echo ""
echo "------------------------------------------------------"
read -n 1 -s -r -p "Press any key to close this window..."
echo ""
