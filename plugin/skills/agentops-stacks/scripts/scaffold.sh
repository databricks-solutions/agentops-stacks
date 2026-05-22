#!/usr/bin/env bash
# scaffold.sh — Validate, write config, and run databricks bundle init.
#
# Usage:
#   scaffold.sh --config <path-to-json> --destination <path> [--template <source>]
#
# The JSON config must contain all input_* keys. The destination is where
# <project_name>/ will be created. Template source defaults to the GitHub repo.
#
# Exit codes:
#   0 — scaffold succeeded
#   1 — validation failed or missing arguments
#   2 — bundle init failed

set -euo pipefail

TEMPLATE_DEFAULT="https://github.com/databricks-solutions/agentops-stacks"

# --- Parse args ---
CONFIG_FILE=""
DESTINATION=""
TEMPLATE_SOURCE="$TEMPLATE_DEFAULT"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)     CONFIG_FILE="$2"; shift 2 ;;
    --destination) DESTINATION="$2"; shift 2 ;;
    --template)   TEMPLATE_SOURCE="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$CONFIG_FILE" || -z "$DESTINATION" ]]; then
  echo "Usage: scaffold.sh --config <json> --destination <path> [--template <source>]" >&2
  exit 1
fi

# --- Verify Databricks CLI ---
if ! command -v databricks &>/dev/null; then
  echo "ERROR: Databricks CLI not found. Install from https://docs.databricks.com/dev-tools/cli/install.html" >&2
  exit 1
fi

# --- Validate inputs ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! python3 "$SCRIPT_DIR/validate_inputs.py" --config "$CONFIG_FILE"; then
  echo "ERROR: Input validation failed. Fix the errors above and retry." >&2
  exit 1
fi

# --- Run bundle init ---
PROJECT_NAME=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['input_project_name'])" "$CONFIG_FILE")
echo "Scaffolding ${PROJECT_NAME} into ${DESTINATION}/ ..."

if ! databricks bundle init "$TEMPLATE_SOURCE" \
    --config-file "$CONFIG_FILE" \
    --output-dir "$DESTINATION"; then
  echo "ERROR: databricks bundle init failed. See output above." >&2
  exit 2
fi

# Leave the config file in place — OS cleans /tmp. Deleting programmatically
# triggers Genie Code's safety heuristic ("Code execution blocked").
echo ""
echo "Scaffold complete: ${DESTINATION}/${PROJECT_NAME}/"
