#!/usr/bin/env bash
#
# Clean redeploy of the PAAI API to Azure Container Apps.
#
#   bash scripts/azure_bootstrap.sh
#
# Every step that failed during the first attempt now has a gate in front of it,
# because each of those cost a full container restart to discover:
#
#   * the DATABASE_URL is connected to from here before it is ever stored
#   * the built image is inspected for the old openAIkey.txt read before push
#   * the push is verified by pulling the tag back
#   * each secret's length is checked after being set
#   * the image tag is unique per run, never :latest (Azure will not re-pull a
#     moving tag reliably, so "nothing changed" looks like "the fix did nothing")
#
set -euo pipefail

RG="${RG:-RG}"
APP="${APP:-paai-api}"
ENV_NAME="${ENV_NAME:-paai-env}"
PG="${PG:-paai-pg}"
GH_USER="${GH_USER:-vyomya}"
TAG="${TAG:-$(date +%Y%m%d-%H%M%S)}"
IMAGE="ghcr.io/${GH_USER}/paai:${TAG}"

say()  { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[32m✓\033[0m %s\n" "$1"; }
die()  { printf "    \033[31m✗\033[0m %s\n" "$1" >&2; exit 1; }

# ── 0. Inputs ─────────────────────────────────────────────────────────────────
say "Loading .env"
[ -f .env ] || die ".env not found — run from the repo root"
set -a; source .env; set +a

for v in DATABASE_URL JWT_SECRET ENCRYPTION_KEY DASHSCOPE_API_KEY \
         GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
  val="${!v:-}"
  [ -n "$val" ] || die "$v is empty in .env"
  ok "$v set (${#val} chars)"
done

[ -n "${CR_PAT:-}" ] || die "CR_PAT not set — export your GitHub PAT (classic, write:packages + read:packages)"
ok "CR_PAT set (${#CR_PAT} chars)"

[ ${#JWT_SECRET} -ge 32 ] || die "JWT_SECRET must be at least 32 characters"

# ── 1. Prove the database URL works from here ─────────────────────────────────
# The last deploy failed with "password authentication failed". Finding that out
# from a crash-looping container costs ~4 minutes; finding it out here costs 2s.
say "Testing DATABASE_URL"
python3 - <<'PY' || die "DATABASE_URL does not work — fix it before deploying"
import os, sys
from sqlalchemy import create_engine, text
url = os.environ["DATABASE_URL"]
try:
    e = create_engine(url)
    with e.connect() as c:
        c.execute(text("select 1"))
        tables = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public'"))]
        ext = [r[0] for r in c.execute(text(
            "select extname from pg_extension where extname='vector'"))]
    host = url.split("@")[-1].split("/")[0]
    print(f"    connected: {host}")
    print(f"    tables: {len(tables)} -> {', '.join(sorted(tables))}")
    print(f"    pgvector: {'yes' if ext else 'NO — messages table will fail'}")
    if not ext:
        sys.exit(1)
    if "users" not in tables:
        print("    WARNING: schema looks empty; run alembic upgrade head first")
        sys.exit(1)
except Exception as exc:
    print(f"    {type(exc).__name__}: {exc}")
    sys.exit(1)
PY
ok "database reachable with a complete schema"

# ── 2. Build ──────────────────────────────────────────────────────────────────
say "Building $IMAGE"
# --platform is not optional: this Mac is arm64, Container Apps is amd64, and a
# mismatched image builds cleanly then crash-loops with "exec format error".
docker build --platform linux/amd64 -t "$IMAGE" . || die "build failed"
ok "built"

# ── 3. Inspect the image before pushing ───────────────────────────────────────
say "Verifying image contents"

docker run --rm --env-file .env "$IMAGE" python -c "import paai.api" \
  && ok "paai.api imports" \
  || die "paai.api does not import inside the image — check for missing files or deps"

if docker run --rm "$IMAGE" grep -q "openAIkey\|qwenkey" paai/llm.py 2>/dev/null; then
  die "llm.py still reads a key file — it must use settings.dashscope_api_key"
fi
ok "llm.py reads config, not a key file"

for f in .env token.json credentials.json gmail_token.json qwenkey.txt openAIkey.txt; do
  if docker run --rm "$IMAGE" test -e "$f" 2>/dev/null; then
    die "$f is inside the image — fix .dockerignore before pushing to a registry"
  fi
done
ok "no secret files baked into the image"

# ── 4. Push ───────────────────────────────────────────────────────────────────
say "Pushing to GHCR"
echo "$CR_PAT" | docker login ghcr.io -u "$GH_USER" --password-stdin >/dev/null \
  || die "docker login failed — token must be CLASSIC with write:packages"
ok "logged in"

docker push "$IMAGE" || die "push failed"

# Confirm it is actually retrievable, rather than trusting the push output.
docker manifest inspect "$IMAGE" >/dev/null 2>&1 \
  && ok "tag $TAG is on the registry" \
  || die "tag not found after push"

# ── 5. Environment ────────────────────────────────────────────────────────────
say "Container Apps environment"
LOCATION=$(az postgres flexible-server show -g "$RG" -n "$PG" --query location -o tsv)
ok "using region $LOCATION (same as the database)"

if az containerapp env show -g "$RG" -n "$ENV_NAME" &>/dev/null; then
  ok "environment exists"
else
  az containerapp env create --name "$ENV_NAME" -g "$RG" --location "$LOCATION" -o none \
    || die "environment create failed"
  ok "environment created"
fi

# ── 6. Create or update the app ───────────────────────────────────────────────
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

SECRETS=(
  "database-url=$DATABASE_URL"
  "jwt-secret=$JWT_SECRET"
  "encryption-key=$ENCRYPTION_KEY"
  "dashscope-key=$DASHSCOPE_API_KEY"
  "google-client-id=$GOOGLE_CLIENT_ID"
  "google-client-secret=$GOOGLE_CLIENT_SECRET"
  "ms-client-id=${MICROSOFT_CLIENT_ID:-unset}"
  "ms-client-secret=${MICROSOFT_CLIENT_SECRET:-unset}"
)

ENVVARS=(
  "DATABASE_URL=secretref:database-url"
  "JWT_SECRET=secretref:jwt-secret"
  "ENCRYPTION_KEY=secretref:encryption-key"
  "DASHSCOPE_API_KEY=secretref:dashscope-key"
  "GOOGLE_CLIENT_ID=secretref:google-client-id"
  "GOOGLE_CLIENT_SECRET=secretref:google-client-secret"
  "MICROSOFT_CLIENT_ID=secretref:ms-client-id"
  "MICROSOFT_CLIENT_SECRET=secretref:ms-client-secret"
  "FRONTEND_URL=$FRONTEND_URL"
  "BASE_URL=${FRONTEND_URL}/api"
  "DEV_MODE=false"
)

if az containerapp show -g "$RG" -n "$APP" &>/dev/null; then
  say "Updating $APP"
  az containerapp secret set -g "$RG" -n "$APP" --secrets "${SECRETS[@]}" -o none
  az containerapp registry set -g "$RG" -n "$APP" \
    --server ghcr.io --username "$GH_USER" --password "$CR_PAT" -o none
  az containerapp update -g "$RG" -n "$APP" \
    --image "$IMAGE" --set-env-vars "${ENVVARS[@]}" -o none
else
  say "Creating $APP"
  az containerapp create \
    --name "$APP" -g "$RG" --environment "$ENV_NAME" \
    --image "$IMAGE" \
    --registry-server ghcr.io \
    --registry-username "$GH_USER" \
    --registry-password "$CR_PAT" \
    --target-port 8000 --ingress external \
    --cpu 1.0 --memory 2.0Gi \
    --min-replicas 1 --max-replicas 3 \
    --secrets "${SECRETS[@]}" \
    --env-vars "${ENVVARS[@]}" \
    -o none
fi

# ── 7. Confirm the secrets landed with real values ────────────────────────────
# `secret list` only shows names. An empty value looks identical to a correct
# one there, and that is exactly how the database password went missing.
say "Verifying stored secrets"
for s in database-url jwt-secret encryption-key dashscope-key google-client-id; do
  n=$(az containerapp secret show -g "$RG" -n "$APP" --secret-name "$s" \
        --query value -o tsv 2>/dev/null | wc -c | tr -d ' ')
  [ "$n" -gt 5 ] || die "secret '$s' is empty or too short ($n chars)"
  ok "$s ($n chars)"
done

# ── 8. Health ─────────────────────────────────────────────────────────────────
FQDN=$(az containerapp show -g "$RG" -n "$APP" \
  --query properties.configuration.ingress.fqdn -o tsv)

say "Waiting for https://$FQDN to come up"
# Cold start loads the embedding model, so the first ~60s of failures are normal.
for i in $(seq 1 24); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://$FQDN/health/ready" || true)
  if [ "$code" = "200" ]; then
    ok "healthy after $((i*10))s"
    curl -s "https://$FQDN/health/ready"; echo
    cat <<NOTE

  API: https://$FQDN
  Tag: $TAG

  Next: deploy the frontend on Vercel with API_ORIGIN=https://$FQDN
        then rerun with FRONTEND_URL=https://<your-app>.vercel.app

NOTE
    exit 0
  fi
  printf "    %ss ... %s\n" "$((i*10))" "$code"
  sleep 10
done

say "Did not become healthy — recent logs"
WS=$(az containerapp env show -g "$RG" -n "$ENV_NAME" \
  --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv)
az monitor log-analytics query -w "$WS" --analytics-query \
  "ContainerAppConsoleLogs_CL | where ContainerAppName_s == '$APP' | where TimeGenerated > ago(10m) | where Log_s has_any ('Error','error','FATAL','Traceback','failed') | project TimeGenerated, Log_s | order by TimeGenerated desc | take 25" \
  -o table
exit 1
