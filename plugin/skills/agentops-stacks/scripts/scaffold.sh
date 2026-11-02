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

# --- Warn if the project will land inside an existing git repo ---
# Git hosts only run CI/CD files from a repo's root, and <project_name>/ won't be one.
if command -v git &>/dev/null && REPO_ROOT=$(git -C "$DESTINATION" rev-parse --show-toplevel 2>/dev/null); then
  echo "WARNING: ${DESTINATION} is inside the git repo ${REPO_ROOT}, so the generated CI/CD files" >&2
  echo "  will land in ${PROJECT_NAME}/ and won't run. To use them, make ${PROJECT_NAME}/ the root of" >&2
  echo "  its own repo, or move its contents (including dot-directories) to the repo root." >&2
fi

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
