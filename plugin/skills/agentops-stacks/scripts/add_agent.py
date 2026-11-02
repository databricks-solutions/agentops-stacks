#!/usr/bin/env python3
"""Add a new agent to an existing AgentOps Stacks project.

Copies an existing agent as a template, renames references, appends the
app + experiment resources to databricks.yml, and registers in the manifest.

Usage:
    python add_agent.py --name support_bot [--from rag] [--project-dir .]

Recommended: use the /add-agent Claude skill which calls this script
with interactive guidance.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

def find_project_root(start: Path) -> Path:
    """Walk up from start to find the project root (has databricks.yml)."""
    current = start.resolve()
    while current != current.parent:
        if (current / "databricks.yml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find databricks.yml in any parent directory")


def find_existing_agents(project_root: Path) -> list[str]:
    """Return list of existing agent names."""
    agents_dir = project_root / "src" / "agents"
    if not agents_dir.exists():
        return []
    return [d.name for d in agents_dir.iterdir() if d.is_dir() and (d / "agent.py").exists()]


def _rename_identifier(text: str, source: str, target: str) -> str:
    """Rename agent identifier `source` -> `target`, matching it only as a whole
    token. Underscores and other separators count as boundaries, so source `rag`
    rewrites `rag`, `rag_eval`, and `proj_rag_eval` but never touches substrings
    like `storage` or `myrag`. A raw str.replace corrupts any identifier that
    merely contains the source name (e.g. `storage` -> `stoROUTERe`)."""
    return re.sub(rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])", target, text)


def copy_agent(project_root: Path, source_name: str, new_name: str):
    """Copy an agent folder, replacing the source name with new name in all files."""
    agents_dir = project_root / "src" / "agents"
    source_dir = agents_dir / source_name
    new_dir = agents_dir / new_name

    if new_dir.exists():
        print(f"ERROR: Agent directory already exists: {new_dir}")
        sys.exit(1)

    if not source_dir.exists():
        print(f"ERROR: Source agent not found: {source_dir}")
        sys.exit(1)

    # Copy the directory tree
    shutil.copytree(source_dir, new_dir)

    # Replace source agent name with new name in all text files
    for filepath in new_dir.rglob("*"):
        if not filepath.is_file():
            continue
        try:
            content = filepath.read_text()
        except UnicodeDecodeError:
            continue

        updated = _rename_identifier(content, source_name, new_name)
        if updated != content:
            filepath.write_text(updated)

    print(f"  Created: src/agents/{new_name}/")


def get_project_name(project_root: Path) -> str:
    """Extract the bundle name from databricks.yml."""
    content = (project_root / "databricks.yml").read_text()
    match = re.search(r'^\s*name:\s*(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "unknown"


def usage_tracking_snippets(content: str, project_name: str, agent_name: str) -> tuple[str, str]:
    """Return (experiment_tags, app_policy_line) matching the project's usage
    tracking setup, or ("", "") when the project was scaffolded without tags.

    The app policy line is live only if databricks.yml already has a live
    `budget_policy_id: ${var.usage_policy_id}`; otherwise it stays commented
    so an empty policy ID never reaches the API.
    """
    if not re.search(r"^  usage_policy_id:", content, re.MULTILINE):
        return "", ""
    experiment_tags = f"""
      tags:
        - key: project
          value: {project_name}
        - key: environment
          value: ${{bundle.target}}
        - key: agent
          value: {agent_name}"""
    policy = "budget_policy_id: ${var.usage_policy_id}"
    if not re.search(r"^\s*budget_policy_id: \$\{var\.usage_policy_id\}", content, re.MULTILINE):
        policy = f"# {policy}  # TODO: wire with scripts/enable_usage_policy.py — see docs/usage-tracking.md"
    return experiment_tags, f"\n      {policy}"


def source_app_env(content: str, source_name: str) -> str:
    """Return the source agent's `config.env` block from databricks.yml, verbatim.

    The App's env lives in the bundle (resolved per target), so a new agent
    inherits the source agent's env the way it inherits its code. Projects
    scaffolded before that keep env in the copied app.yaml; then this is "".
    """
    match = re.search(
        rf"\n    {re.escape(source_name)}:\n(?:      .*\n)*?        env:\n((?:          .*\n)+)",
        content,
    )
    return "\n        env:\n" + match.group(1).rstrip("\n") if match else ""


def append_to_databricks_yml(project_root: Path, new_name: str, source_name: str | None = None):
    """Append experiment + app resource for the new agent to databricks.yml."""
    yml_path = project_root / "databricks.yml"
    content = yml_path.read_text()
    project_name = get_project_name(project_root)
    hyphenated_name = new_name.replace("_", "-")
    hyphenated_project = project_name.replace("_", "-")
    experiment_tags, app_policy_line = usage_tracking_snippets(content, project_name, new_name)
    app_env = source_app_env(content, source_name) if source_name else ""

    # Build the new experiment block
    experiment_block = f"""
    {new_name}_experiment:
      name: /Shared/${{bundle.name}}_{new_name}_${{bundle.target}}
      artifact_location: dbfs:/Volumes/${{var.catalog}}/${{resources.schemas.project_schema.name}}/artifacts{experiment_tags}"""

    # Build the new app block
    app_block = f"""
    {new_name}:
      name: "{hyphenated_project}-{hyphenated_name}"
      description: "{new_name} agent — {project_name}"
      source_code_path: ./src/agents/{new_name}
      config:
        command: ["uv", "run", "--frozen", "--no-dev", "python", "app/start_server.py"]{app_env}{app_policy_line}
      resources:
        - name: "experiment"
          experiment:
            experiment_id: ${{resources.experiments.{new_name}_experiment.id}}
            permission: "CAN_MANAGE"
        - name: "artifacts"
          uc_securable:
            securable_full_name: ${{var.catalog}}.${{resources.schemas.project_schema.name}}.${{resources.volumes.artifacts.name}}
            securable_type: "VOLUME"
            permission: "WRITE_VOLUME\""""

    # Insert experiment: find the experiments block or create one
    if "experiments:" in content:
        # Append after the last experiment entry (before the apps: line)
        content = content.replace(
            "\n  apps:",
            f"{experiment_block}\n\n  apps:",
        )
    else:
        # No experiments block — add one before apps
        content = content.replace(
            "resources:\n  apps:",
            f"resources:\n  experiments:{experiment_block}\n\n  apps:",
        )

    # Append the app after the last app entry: `targets:` is the top-level key
    # that follows `resources:` in the scaffold's databricks.yml.
    if "\ntargets:" not in content:
        sys.exit("ERROR: databricks.yml has no top-level `targets:` key to insert the new app before.")
    content = content.replace(
        "\ntargets:",
        f"{app_block}\n\ntargets:",
        1,
    )

    yml_path.write_text(content)
    print(f"  Updated: databricks.yml (added experiment + app for {new_name})")


def update_manifest(project_root: Path, new_name: str):
    """Add the new agent to the manifest agents list."""
    manifest_path = project_root / ".agentops-stacks" / "manifest.yml"
    if not manifest_path.exists():
        print(f"  WARN: No manifest found at {manifest_path}")
        return

    content = manifest_path.read_text()
    # Append to agents list
    content = content.rstrip() + f"\n  - name: {new_name}\n"
    manifest_path.write_text(content)
    print(f"  Updated: .agentops-stacks/manifest.yml")


def main():
    parser = argparse.ArgumentParser(description="Add a new agent to an AgentOps Stacks project")
    parser.add_argument("--name", required=True, help="Name for the new agent (lowercase, underscores)")
    parser.add_argument("--from", dest="source", default=None, help="Existing agent to copy from (default: first found)")
    parser.add_argument("--project-dir", default=".", help="Project root directory (default: current)")
    args = parser.parse_args()

    # Validate name
    if not re.match(r'^[a-z][a-z0-9_]{2,}$', args.name):
        print("ERROR: Agent name must start with a lowercase letter and contain only lowercase letters, digits, and underscores (min 3 chars).")
        sys.exit(1)

    project_root = find_project_root(Path(args.project_dir))
    print(f"Project root: {project_root}")

    # The App is named <project>-<agent>; Databricks App names are limited to 30 characters.
    app_name = f"{get_project_name(project_root)}-{args.name}".replace("_", "-")
    if len(app_name) > 30:
        print(f"ERROR: The agent App would be named '{app_name}' ({len(app_name)} characters), "
              "but Databricks App names are limited to 30. Choose a shorter agent name.")
        sys.exit(1)

    # Find source agent
    existing = find_existing_agents(project_root)
    if not existing:
        print("ERROR: No existing agents found to copy from.")
        sys.exit(1)

    if args.name in existing:
        print(f"ERROR: Agent '{args.name}' already exists.")
        sys.exit(1)

    source = args.source or existing[0]
    if source not in existing:
        print(f"ERROR: Source agent '{source}' not found. Available: {existing}")
        sys.exit(1)

    print(f"Adding agent '{args.name}' (based on '{source}')\n")

    copy_agent(project_root, source, args.name)
    append_to_databricks_yml(project_root, args.name, source)
    update_manifest(project_root, args.name)

    print(f"\nDone. New agent at: src/agents/{args.name}/")
    print(f"\nNext steps:")
    print(f"  1. cd src/agents/{args.name}")
    print(f"  2. Edit graph.py and tools.py for this agent's behavior")
    print(f"  3. Edit eval/gates.yml for this agent's quality bar")
    print(f"  4. databricks bundle deploy -t dev")


if __name__ == "__main__":
    main()
