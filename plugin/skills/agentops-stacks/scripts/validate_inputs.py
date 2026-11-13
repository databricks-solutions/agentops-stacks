#!/usr/bin/env python3
"""Validate inputs for agentops-stacks scaffolding.

Usage:
    python validate_inputs.py --config <path-to-json>

The JSON file should contain all input_* keys from databricks_template_schema.json.
Exits 0 if all inputs are valid, non-zero with descriptive messages otherwise.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,}$")
VALID_CLOUDS = {"aws", "azure", "gcp"}
VALID_CICD = {
    "github_actions",
    "github_actions_for_github_enterprise_servers",
    "azure_devops",
    "gitlab",
}
VALID_MEMORY_TYPES = {"short_term", "long_term", "both"}
VALID_EVAL_SOURCES = {"synthetic", "manual", "production_traces", "existing"}
YES_NO = {"yes", "no"}
# Serverless usage policy ID: a UUID, or blank to skip (kept in sync with the schema pattern).
USAGE_POLICY_ID_PATTERN = re.compile(
    r"^$|^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def validate(config: dict) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings)."""
    errors = []
    warnings = []

    # --- Required infra inputs ---
    name = config.get("input_project_name", "")
    if not NAME_PATTERN.fullmatch(name):
        errors.append(
            f"Invalid project_name '{name}'. "
            "Must start with a lowercase letter, contain only lowercase letters/digits/underscores, "
            "and be at least 3 characters. Examples: my_agent, rag_bot_v2"
        )

    agent_name = config.get("input_initial_agent_name", "")
    if not NAME_PATTERN.fullmatch(agent_name):
        errors.append(
            f"Invalid initial_agent_name '{agent_name}'. "
            "Same rules as project_name: lowercase letters/digits/underscores, min 3 chars."
        )

    cloud = config.get("input_cloud", "")
    if cloud not in VALID_CLOUDS:
        errors.append(
            f"Invalid cloud '{cloud}'. Must be one of: {', '.join(sorted(VALID_CLOUDS))}"
        )

    cicd = config.get("input_cicd_platform", "")
    if cicd not in VALID_CICD:
        errors.append(
            f"Invalid cicd_platform '{cicd}'. Must be one of: {', '.join(sorted(VALID_CICD))}"
        )

    dest = config.get("destination", "")
    if dest:
        path = Path(dest)
        if not path.exists():
            errors.append(f"Destination '{dest}' does not exist.")
        elif not path.is_dir():
            errors.append(f"Destination '{dest}' is not a directory.")
        else:
            try:
                subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=str(path),
                    capture_output=True,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                warnings.append(
                    f"WARNING: '{dest}' is not inside a Git folder. "
                    "The Workspace UI Deployments panel won't appear. "
                    "Proceed with CLI-only deploy, or move into a Git folder first."
                )

    # --- Agent architecture inputs (yes/no enums) ---
    for key in [
        "input_use_vector_search",
        "input_has_chunked_table",
        "input_use_lakebase",
        "input_use_uc_functions",
        "input_uc_functions_exist",
    ]:
        val = config.get(key, "no")
        if val not in YES_NO:
            errors.append(f"Invalid {key} '{val}'. Must be 'yes' or 'no'.")

    # Schema default is "yes", unlike the inputs above.
    cost_tags = config.get("input_enable_cost_tags", "yes")
    if cost_tags not in YES_NO:
        errors.append(
            f"Invalid input_enable_cost_tags '{cost_tags}'. Must be 'yes' or 'no'."
        )

    # --- Conditional validations ---
    if (
        config.get("input_use_vector_search") == "no"
        and config.get("input_has_chunked_table") == "yes"
    ):
        warnings.append(
            "input_has_chunked_table is 'yes' but vector search is disabled. "
            "The chunked table setting will be ignored."
        )

    # Checked even when lakebase is off: bundle init rejects an invalid value
    # regardless of whether the prompt is skipped.
    mem = config.get("input_memory_type", "short_term")
    if mem not in VALID_MEMORY_TYPES:
        errors.append(
            f"Invalid memory_type '{mem}'. Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
        )

    if (
        config.get("input_use_uc_functions") == "no"
        and config.get("input_uc_functions_exist") == "yes"
    ):
        warnings.append(
            "input_uc_functions_exist is 'yes' but UC functions are disabled. "
            "The setting will be ignored."
        )

    # --- Usage tracking ---
    policy_id = config.get("input_usage_policy_id") or ""
    if not isinstance(policy_id, str) or not USAGE_POLICY_ID_PATTERN.fullmatch(
        policy_id
    ):
        errors.append(
            f"Invalid usage_policy_id {policy_id!r}. Must be a UUID or blank."
        )
        policy_id = ""
    if cost_tags == "no" and policy_id:
        warnings.append(
            "input_usage_policy_id is set but cost tags are disabled. "
            "The policy ID will be ignored."
        )
    elif cost_tags == "yes" and not policy_id:
        warnings.append(
            "No usage policy ID: resources are tagged, but serverless usage (Apps, "
            "Vector Search, Lakebase) stays untagged until one is set. "
            "See docs/usage-tracking.md in the generated project."
        )

    # --- Eval dataset source ---
    eval_source = config.get("input_eval_dataset_source", "synthetic")
    if eval_source not in VALID_EVAL_SOURCES:
        errors.append(
            f"Invalid eval_dataset_source '{eval_source}'. "
            f"Must be one of: {', '.join(sorted(VALID_EVAL_SOURCES))}"
        )

    return errors, warnings


def main() -> int:
    """CLI entry point: validate a config JSON file; return the exit code."""
    if len(sys.argv) != 3 or sys.argv[1] != "--config":
        print(f"Usage: {sys.argv[0]} --config <path-to-json>", file=sys.stderr)
        return 2

    config_path = Path(sys.argv[2])
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 2

    config = json.loads(config_path.read_text())
    errors, warnings = validate(config)

    for w in warnings:
        print(w, file=sys.stderr)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("All inputs valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
