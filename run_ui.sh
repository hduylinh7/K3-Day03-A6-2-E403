#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python -m streamlit run streamlit_app.py
