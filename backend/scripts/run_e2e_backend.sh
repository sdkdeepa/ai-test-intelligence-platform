#!/usr/bin/env bash
# Starts the backend against a disposable SQLite DB with the mock provider,
# for the frontend's Playwright e2e suite (frontend/playwright.config.ts).
# Never point this at a real DATABASE_URL — it drops and recreates the
# schema on every run.
set -euo pipefail
cd "$(dirname "$0")/.."

export DATABASE_URL="sqlite:///$(pwd)/.e2e.db"
export PROVIDER_DEFAULT_PROVIDER="mock"
export LOG_LEVEL="WARNING"

rm -f .e2e.db
.venv/bin/python scripts/create_e2e_db.py
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
