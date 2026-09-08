#!/bin/sh
set -eu

: "${POSTGRES_SEEDS:?POSTGRES_SEEDS is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${SQL_PASSWORD:?SQL_PASSWORD is required}"

if ! temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" \
  -u "$POSTGRES_USER" -p "${DB_PORT:-5432}" \
  --db temporal setup-schema -v 0.0; then
  echo "Temporal primary schema already initialized; applying upgrades"
fi
temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" \
  -u "$POSTGRES_USER" -p "${DB_PORT:-5432}" \
  --db temporal update-schema \
  -d /etc/temporal/schema/postgresql/v12/temporal/versioned

if ! temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" \
  -u "$POSTGRES_USER" -p "${DB_PORT:-5432}" \
  --db temporal_visibility setup-schema -v 0.0; then
  echo "Temporal visibility schema already initialized; applying upgrades"
fi
temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" \
  -u "$POSTGRES_USER" -p "${DB_PORT:-5432}" \
  --db temporal_visibility update-schema \
  -d /etc/temporal/schema/postgresql/v12/visibility/versioned
