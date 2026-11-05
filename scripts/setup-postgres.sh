#!/usr/bin/env bash
# Configura PostgreSQL local para Sentinel RT&WS WITSML DataStore.
#
# - Crea (o actualiza) el rol de aplicación y la base de datos.
# - Genera una contraseña aleatoria para el rol de aplicación.
# - Escribe SENTINEL_DATABASE_URL en .env (sin imprimir la contraseña).
# - No abre PostgreSQL a la red: solo escucha en localhost.
#
# Uso en Windows (Git Bash, desde la carpeta del repo):
#   ./scripts/setup-postgres.sh
#
# Variables opcionales: SENTINEL_DB_NAME, SENTINEL_DB_USER, PGHOST, PGPORT,
#                       PGUSER (superusuario, por defecto postgres), ENV_FILE.

set -euo pipefail

DB_NAME="${SENTINEL_DB_NAME:-sentinel}"
DB_USER="${SENTINEL_DB_USER:-sentinel}"
PG_HOST="${PGHOST:-localhost}"
PG_PORT="${PGPORT:-5432}"
PG_SUPERUSER="${PGUSER:-postgres}"
ENV_FILE="${ENV_FILE:-.env}"

log()  { printf '[sentinel-db] %s\n' "$*"; }
fail() { printf '[sentinel-db] ERROR: %s\n' "$*" >&2; exit 1; }

# --- Localizar psql -----------------------------------------------------------
find_psql() {
  if command -v psql >/dev/null 2>&1; then
    command -v psql
    return
  fi
  local candidate
  for candidate in \
    "/c/Program Files/PostgreSQL/18/bin/psql.exe" \
    "/c/Program Files/PostgreSQL/17/bin/psql.exe" \
    "/c/Program Files/PostgreSQL/16/bin/psql.exe"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return
    fi
  done
  return 1
}

PSQL="$(find_psql)" || fail "No encuentro psql. Agrega la carpeta bin de PostgreSQL al PATH o instala PostgreSQL 18."
log "Usando psql: $PSQL"

# --- Contraseña del superusuario (no se guarda) -------------------------------
if [[ -z "${PGPASSWORD:-}" ]]; then
  read -rsp "Contraseña del superusuario '$PG_SUPERUSER': " PGPASSWORD
  echo
fi
export PGPASSWORD

psql_admin() {
  "$PSQL" -X -q -v ON_ERROR_STOP=1 -h "$PG_HOST" -p "$PG_PORT" -U "$PG_SUPERUSER" "$@"
}

# Comprobar conexión antes de tocar nada.
psql_admin -d postgres -tAc "SELECT 1" >/dev/null 2>&1 \
  || fail "No conecto a PostgreSQL en $PG_HOST:$PG_PORT como '$PG_SUPERUSER'. ¿Está el servicio arriba y la contraseña es correcta?"

# --- Contraseña aleatoria para el rol de aplicación ---------------------------
# Solo alfanumérica: no requiere codificación en la URL de conexión.
APP_PW="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)"
[[ ${#APP_PW} -eq 32 ]] || fail "No pude generar la contraseña aleatoria."

# --- Rol y base de datos (idempotente) ----------------------------------------
log "Creando o actualizando el rol '$DB_USER' y la base '$DB_NAME'..."
psql_admin -d postgres \
  -v app_user="$DB_USER" -v app_db="$DB_NAME" -v app_pw="$APP_PW" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')\gexec

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_pw')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db')\gexec
SQL

# --- Verificar que el rol de aplicación entra a su base -----------------------
PGPASSWORD="$APP_PW" "$PSQL" -X -q -v ON_ERROR_STOP=1 \
  -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT current_user || ' @ ' || current_database();" >/dev/null \
  || fail "El rol '$DB_USER' no pudo conectarse a '$DB_NAME'."
log "Conexión del rol '$DB_USER' verificada."

# --- Aviso si PostgreSQL escucha fuera de localhost --------------------------
LISTEN="$(psql_admin -d postgres -tAc "SHOW listen_addresses;")"
if [[ "$LISTEN" != "localhost" ]]; then
  log "AVISO: listen_addresses = '$LISTEN'. Para este despliegue debe ser 'localhost'."
fi

# --- Escribir SENTINEL_DATABASE_URL en .env ----------------------------------
DSN="postgresql+asyncpg://${DB_USER}:${APP_PW}@${PG_HOST}:${PG_PORT}/${DB_NAME}"
if [[ -f "$ENV_FILE" ]]; then
  TMP_FILE="${ENV_FILE}.tmp"
  { grep -v '^SENTINEL_DATABASE_URL=' "$ENV_FILE" || true; } > "$TMP_FILE"
  printf 'SENTINEL_DATABASE_URL=%s\n' "$DSN" >> "$TMP_FILE"
  mv "$TMP_FILE" "$ENV_FILE"
  log "SENTINEL_DATABASE_URL actualizado en $ENV_FILE (la contraseña no se imprime)."
else
  log "No existe $ENV_FILE. Copia .env.example a .env y agrega esta línea:"
  printf 'SENTINEL_DATABASE_URL=%s\n' "$DSN"
fi

unset PGPASSWORD APP_PW DSN
log "Listo. Siguiente paso: .\\.venv\\Scripts\\alembic.exe upgrade head"
