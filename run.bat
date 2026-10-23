@echo off
cd /d "%~dp0"

if not exist ".venv" (
    echo 🔧 Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo 📦 Installing dependencies...
pip install -q -e ".[dev]"

echo 🎬 Starting CNV (Chi Ni Vidimu) on http://127.0.0.1:8000
python -m app\main

