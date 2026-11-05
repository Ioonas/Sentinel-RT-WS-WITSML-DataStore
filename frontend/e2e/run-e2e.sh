#!/usr/bin/env bash
# Ejecuta la suite E2E: base limpia, backend de pruebas, interfaz en producción y node --test.
# FRONTEND_DIR: carpeta con dependencias instaladas (por defecto, frontend/ del repositorio).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT/frontend}"
PY="${SENTINEL_PYTHON:-/home/claude/venv314/bin/python}"
export SENTINEL_E2E_DSN="${SENTINEL_E2E_DSN:-postgresql+asyncpg://sentinel_test:sentinel_test@localhost:5432/sentinel_e2e}"

cleanup() {
  [[ -n "${BACKEND_PID:-}" ]] && kill -- -"$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONT_PID:-}" ]] && kill -- -"$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT

(cd "$ROOT" && SENTINEL_ENV=test "$PY" -m tests.e2e.reset)

cd "$ROOT"
setsid env SENTINEL_E2E_DSN="$SENTINEL_E2E_DSN" "$PY" -m uvicorn tests.e2e.server:app --port 8100 \
  > /tmp/e2e-backend.log 2>&1 &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
SENTINEL_API_URL=http://127.0.0.1:8100 npx next build > /tmp/e2e-build.log 2>&1
SENTINEL_API_URL=http://127.0.0.1:8100 setsid npx next start -p 3100 > /tmp/e2e-front.log 2>&1 &
FRONT_PID=$!
for _ in $(seq 1 60); do curl -sf localhost:3100/admin/login >/dev/null && break; sleep 1; done

cd "$ROOT/frontend"
node --test e2e/admin.e2e.mjs
