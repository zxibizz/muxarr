#!/usr/bin/env bash
# Local development only. Runs the three processes the production image
# supervises under s6, minus the supervision: the first one to exit takes the
# container down, which is what you want when something crashes on reload.
set -euo pipefail

trap 'kill 0' EXIT INT TERM

cd /repo/services/backend

# Ahead of the worker, which would otherwise race an unmigrated database.
alembic upgrade head

uvicorn --factory src.api.app:build_app \
    --host 0.0.0.0 --port 8000 --reload --reload-dir src &

watchfiles --filter python "python -m src.worker" src &

cd /repo/services/frontend
# The image seeds node_modules; this only reconciles a changed lockfile.
npm install --no-audit --no-fund
npm run dev -- --host 0.0.0.0 &

wait -n
