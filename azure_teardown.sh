#!/usr/bin/env bash
#
# Tear down the PAAI deployment on Azure.
#
#   bash scripts/azure_teardown.sh          # container app + environment (keeps the database)
#   bash scripts/azure_teardown.sh --all    # everything, including the database
#
# Default keeps Postgres deliberately: it is the one piece already verified
# working (schema applied, pgvector allow-listed, firewall rules correct), and
# recreating it means redoing the region-policy hunt and the extension restart.
set -euo pipefail

RG="${RG:-RG}"
APP="${APP:-paai-api}"
ENV_NAME="${ENV_NAME:-paai-env}"
PG="${PG:-paai-pg}"

say() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }

FULL=false
[ "${1:-}" = "--all" ] && FULL=true

command -v az >/dev/null || { echo "Azure CLI not found." >&2; exit 1; }

say "Current resources in $RG"
az resource list -g "$RG" --query "[].{name:name, type:type}" -o table

if $FULL; then
  cat <<WARN

  This also deletes the DATABASE. You would need to redo:
    - region selection (your subscription is policy-restricted)
    - azure.extensions pgvector allow-list + server restart
    - database creation and alembic upgrade head

WARN
  read -rp "  Type DELETE-ALL to confirm: " confirm
  [ "$confirm" = "DELETE-ALL" ] || { echo "Aborted."; exit 1; }

  say "Deleting resource group $RG"
  az group delete --name "$RG" --yes --no-wait
  echo "    Running in the background. Check with: az group show -n $RG"
  exit 0
fi

# ── Container app ─────────────────────────────────────────────────────────────
say "Deleting container app: $APP"
if az containerapp show -g "$RG" -n "$APP" &>/dev/null; then
  az containerapp delete -g "$RG" -n "$APP" --yes -o none
  echo "    deleted"
else
  echo "    not found — skipping"
fi

# ── Environment ───────────────────────────────────────────────────────────────
# Worth deleting too, not just the app. The current one is an "express"
# environment, which is what rejected --revision-suffix and broke
# `az containerapp logs show`. A fresh one avoids both.
say "Deleting Container Apps environment: $ENV_NAME"
if az containerapp env show -g "$RG" -n "$ENV_NAME" &>/dev/null; then
  az containerapp env delete -g "$RG" -n "$ENV_NAME" --yes -o none
  echo "    deleted"
else
  echo "    not found — skipping"
fi

say "Remaining resources"
az resource list -g "$RG" --query "[].{name:name, type:type}" -o table

cat <<NOTE

  Database kept. Confirm it still answers:

    psql "host=${PG}.postgres.database.azure.com port=5432 dbname=paai \\
          user=paaiadmin sslmode=require" -c "\\dt"

  Then: bash scripts/azure_bootstrap.sh

NOTE
