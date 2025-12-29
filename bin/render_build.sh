#!/usr/bin/env bash
set -euo pipefail

# Render build script - mirrors Render.com build process
# This script is used by GitHub Actions CI to verify Render parity

pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput

