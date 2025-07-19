#!/bin/bash
set -e

echo "▶️ Setting up Python virtual environment..."

# Optional: Use poetry or pip
python -m venv .venv
source .venv/bin/activate

echo "⬇ Installing development dependencies..."
pip install --upgrade pip
pip install \
    black \
    ruff \
    mypy \
    detect-secrets \
    pre-commit \
    codespell \

echo "✅ Installing pre-commit hooks..."
pre-commit install

echo "📦 Done setting up dev container!"
