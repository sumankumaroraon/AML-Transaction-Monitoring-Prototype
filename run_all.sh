#!/usr/bin/env bash
# Rebuild everything from scratch: data -> SQLite -> alerts -> evaluation.
set -euo pipefail
cd "$(dirname "$0")/src"
python3 01_generate_data.py
python3 02_load_sqlite.py
python3 03_run_rules.py
python3 04_evaluate.py
echo "Done. Start the dashboard with: streamlit run app/streamlit_app.py"
