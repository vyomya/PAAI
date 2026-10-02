#!/usr/bin/env bash
#
# Read container logs.
#
#   bash scripts/azure_logs.sh            # last 10 minutes, everything
#   bash scripts/azure_logs.sh errors     # last 10 minutes, errors only
#   bash scripts/azure_logs.sh system     # platform events (pulls, restarts, OOM)
#
# `az containerapp logs show` crashes with KeyError: 'eventStreamEndpoint' on
# express environments, so this queries Log Analytics directly instead.
set -euo pipefail

RG="${RG:-RG}"
APP="${APP:-paai-api}"
ENV_NAME="${ENV_NAME:-paai-env}"
MODE="${1:-all}"
WINDOW="${WINDOW:-10m}"

WS=$(az containerapp env show -g "$RG" -n "$ENV_NAME" \
  --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv)

case "$MODE" in
  errors)
    Q="ContainerAppConsoleLogs_CL
        | where ContainerAppName_s == '$APP'
        | where TimeGenerated > ago($WINDOW)
        | where Log_s has_any ('Error','ERROR','FATAL','Traceback','failed','Exception')
        | project TimeGenerated, Log_s
        | order by TimeGenerated desc
        | take 30" ;;
  system)
    Q="ContainerAppSystemLogs_CL
        | where ContainerAppName_s == '$APP'
        | where TimeGenerated > ago($WINDOW)
        | project TimeGenerated, Log_s
        | order by TimeGenerated desc
        | take 30" ;;
  *)
    Q="ContainerAppConsoleLogs_CL
        | where ContainerAppName_s == '$APP'
        | where TimeGenerated > ago($WINDOW)
        | project TimeGenerated, Log_s
        | order by TimeGenerated desc
        | take 60" ;;
esac

# The ago() filter matters. Without it you read old crash-loop output and debug
# a problem that was already fixed — which happened repeatedly last time.
az monitor log-analytics query -w "$WS" --analytics-query "$Q" -o table