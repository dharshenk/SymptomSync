#!/bin/bash
set -e

echo "▶️ Setting up Python virtual environment..."

echo "▶️ Installing Python dependencies..." uv pip install -r requirements.txt
curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync

echo "📦 Done setting up dev container!"
