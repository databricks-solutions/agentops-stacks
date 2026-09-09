#!/usr/bin/env python3
"""Add a supervisor agent to an existing AgentOps Stacks project.

A supervisor routes user queries across the project's existing agents (and
other managed sub-agents such as Genie spaces or Knowledge Assistants). This
script supports the two supervisor patterns AgentOps Stacks recognizes, which
differ in *who owns the routing loop*:

  custom          A hand-written LangGraph supervisor graph. It is just another
                  agent under src/agents/<name>/ — served as a Databricks App
                  via MLflow AgentServer, fully declared in databricks.yml, and
                  gated by the same CI eval loop as every other agent. GA.

  supervisor_api  The Databricks-managed supervisor loop (Responses API),
                  packaged as a thin wrapper App. Same declarable App shape as
                  `custom`; Databricks owns the routing loop. Beta — requires
                  AI Gateway + the UC OTel-traces preview enabled.

Both patterns create the supervisor by cloning the agent scaffold shape
(mirroring add_agent.py) and swapping in a supervisor graph, so it is a
first-class DAB citizen and CI's `detect_patterns -> eval_gate` picks it up with
zero workflow changes.

Usage:
    python add_supervisor.py --name router --type custom --routes rag,support
    python add_supervisor.py --name router --type supervisor_api --routes rag,support

Recommended: use the /add-supervisor skill, which runs the Selection Matrix
conversationally and then calls this script.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")
VALID_TYPES = {"custom", "supervisor_api"}

# Templates live next to this script so they ship with the plugin and don't
# collide with the DAB `template/` tree (which is Go-templated by bundle init).
TEMPLATE_DIR = Path(__file__).resolve().parent / "supervisor_templates"


# --------------------------------------------------------------------------- #
# Project discovery
# --------------------------------------------------------------------------- #

def find_project_root(start: Path) -> Path:
    """Walk up from start to find the project root (has databricks.yml)."""
    current = start.resolve()
    while current != current.parent:
        if (current / "databricks.yml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find databricks.yml in any parent directory")


def find_existing_agents(project_root: Path) -> list[str]:
    """Return list of existing agent names (dirs under src/agents with agent.py)."""
    agents_dir = project_root / "src" / "agents"
    if not agents_dir.exists():
        return []
    return sorted(
        d.name for d in agents_dir.iterdir()
        if d.is_dir() and (d / "agent.py").exists()
    )


def get_project_name(project_root: Path) -> str:
    """Extract the bundle name from databricks.yml."""
    content = (project_root / "databricks.yml").read_text()
    match = re.search(r"^\s*name:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def hyphenate(name: str) -> str:
    return name.replace("_", "-")


# --------------------------------------------------------------------------- #
# Template rendering — a tiny {{ placeholder }} substituter (NOT Go templates,
# to avoid any interaction with `databricks bundle init`).
# --------------------------------------------------------------------------- #

def render(template_name: str, subs: dict) -> str:
    raw = (TEMPLATE_DIR / template_name).read_text()
    for key, val in subs.items():
        raw = raw.replace("{{" + key + "}}", val)
    return raw


def _rename_identifier(text: str, source: str, target: str) -> str:
    """Rename agent identifier `source` -> `target`, matching it only as a whole
    token. Underscores and other separators count as boundaries, so source `rag`
    rewrites `rag`, `rag_eval`, and `proj_rag_eval` but never touches substrings
    like `storage` or `myrag`. A raw str.replace corrupts any identifier that
    merely contains the source name (e.g. `storage` -> `stoROUTERe`)."""
    return re.sub(rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])", target, text)


# --------------------------------------------------------------------------- #
# custom / supervisor_api — scaffold the supervisor as an agent App
# --------------------------------------------------------------------------- #

def scaffold_supervisor_agent(project_root: Path, name: str, sup_type: str,
                              source: str, routes: list[str]):
    """Copy an existing agent as the base, then overwrite graph/tools/deps with
    the supervisor variant. Keeps the eval harness, app server, and app.yaml so
    the CI eval gate and Databricks App serving work unchanged."""
    agents_dir = project_root / "src" / "agents"
    source_dir = agents_dir / source
    new_dir = agents_dir / name

    if new_dir.exists():
        sys.exit(f"ERROR: Agent directory already exists: {new_dir}")
    if not source_dir.exists():
        sys.exit(f"ERROR: Source agent not found: {source_dir}")

    shutil.copytree(source_dir, new_dir)

    # Rename all references to the source agent -> supervisor name (mirrors
    # add_agent.py so app/start_server.py, eval experiment names, etc. line up).
    for filepath in new_dir.rglob("*"):
        if not filepath.is_file():
            continue
        try:
            content = filepath.read_text()
        except UnicodeDecodeError:
            continue
        updated = _rename_identifier(content, source, name)
        if updated != content:
            filepath.write_text(updated)

    subs = {
        "SUPERVISOR_NAME": name,
        "PROJECT_NAME": get_project_name(project_root),
        "ROUTES_PY_LIST": repr(routes),
        "ROUTES_COMMENT": ", ".join(routes) if routes else "(none yet — edit graph.py)",
    }

    graph_tmpl = ("graph_custom.py.tmpl" if sup_type == "custom"
                  else "graph_supervisor_api.py.tmpl")
    (new_dir / "graph.py").write_text(render(graph_tmpl, subs))
    (new_dir / "tools.py").write_text(render("tools_supervisor.py.tmpl", subs))
    # Overwrite agent.py with the supervisor handler. The source agent's agent.py
    # may import graph symbols (e.g. get_async_checkpointer when the base agent
    # had Lakebase memory) that the supervisor graph.py doesn't define — which
    # would break server startup. The supervisor uses a stateless handler.
    (new_dir / "agent.py").write_text(render("agent_supervisor.py.tmpl", subs))

    # Merge extra deps into the supervisor's pyproject.toml.
    _add_supervisor_deps(new_dir / "pyproject.toml", sup_type)

    print(f"  Created: src/agents/{name}/ (supervisor, type={sup_type})")
    print(f"           graph.py routes to: {subs['ROUTES_COMMENT']}")


def _add_supervisor_deps(pyproject: Path, sup_type: str):
    """Add the supervisor's runtime dependency to pyproject.toml if missing.

    Pins are the versions this pattern is validated against:
      - langgraph-supervisor 0.0.31 (which transitively holds langgraph
        >=1.0.2,<2.0.0, keeping create_react_agent available).
      - databricks-openai 0.7.0+ — the floor where the DatabricksOpenAI client
        first ships; earlier releases only expose the tool helpers, so the
        supervisor_api graph would ImportError on `from databricks_openai
        import DatabricksOpenAI`.
    """
    if not pyproject.exists():
        print(f"  WARN: no pyproject.toml at {pyproject} — add the supervisor "
              f"dependency manually before `uv sync`.")
        return
    content = pyproject.read_text()
    dep = ('    "langgraph-supervisor>=0.0.31,<0.1",'
           if sup_type == "custom"
           else '    "databricks-openai>=0.7.0",')
    marker = dep.split('"')[1].split(">=")[0]
    if marker in content:
        return
    # Insert after the existing langgraph pin in any version form (>=, ==, ~=,
    # extras, or bare). The name is anchored so it never matches a sibling like
    # langgraph-supervisor or langgraph-checkpoint-postgres.
    new_content, n = re.subn(
        r'(\n[ \t]*"langgraph(?:\[[^\]]*\])?(?:[<>=!~][^"]*)?",)',
        r"\1\n" + dep,
        content,
        count=1,
    )
    if n == 0:
        # No langgraph pin in the expected shape — fall back to the head of the
        # dependencies array so the dep still lands.
        new_content, n = re.subn(
            r'(dependencies\s*=\s*\[)',
            r"\1\n" + dep,
            content,
            count=1,
        )
    if n == 0:
        print(f"  WARN: couldn't find a langgraph pin or a dependencies list in "
              f"{pyproject}. Add {dep.strip()} manually before `uv sync`.")
        return
    pyproject.write_text(new_content)


def append_agent_resources_to_databricks_yml(project_root: Path, name: str):
    """Append experiment + app resource for the supervisor agent (identical
    wiring to add_agent.py so the App deploys like any other agent)."""
    yml_path = project_root / "databricks.yml"
    content = yml_path.read_text()
    project_name = get_project_name(project_root)

    experiment_block = f"""
    {name}_experiment:
      name: /Shared/${{bundle.name}}_{name}_${{bundle.target}}
      artifact_location: dbfs:/Volumes/${{var.catalog}}/${{var.schema}}/artifacts"""

    app_block = f"""
    {name}:
      name: "{hyphenate(project_name)}-{hyphenate(name)}"
      description: "{name} supervisor — {project_name}"
      source_code_path: ./src/agents/{name}
      config:
        command: ["uv", "run", "python", "app/start_server.py"]
      resources:
        - name: "experiment"
          experiment:
            experiment_id: ${{resources.experiments.{name}_experiment.id}}
            permission: "CAN_MANAGE\""""

    if "experiments:" in content:
        content = content.replace("\n  apps:", f"{experiment_block}\n\n  apps:")
    else:
        content = content.replace(
            "resources:\n  apps:",
            f"resources:\n  experiments:{experiment_block}\n\n  apps:",
        )

    content = content.replace("\nsync:", f"{app_block}\n\nsync:")
    yml_path.write_text(content)
    print(f"  Updated: databricks.yml (added experiment + app for {name})")


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #

def update_manifest(project_root: Path, name: str, sup_type: str, routes: list[str]):
    """Record the supervisor in the scaffold contract. CI and tooling read this
    without needing to know how the supervisor was created."""
    manifest_path = project_root / ".agentops-stacks" / "manifest.yml"
    if not manifest_path.exists():
        print(f"  WARN: No manifest at {manifest_path} — skipping manifest update")
        return

    content = manifest_path.read_text().rstrip("\n")
    if "\nsupervisor:" in content or content.startswith("supervisor:"):
        print("  WARN: manifest already has a `supervisor:` block — leaving it "
              "in place. Edit .agentops-stacks/manifest.yml by hand if needed.")
        return

    routes_yaml = "".join(f"\n    - {r}" for r in routes) if routes else " []"
    block = f"""

# Supervisor agent (added via /add-supervisor)
# type: custom | supervisor_api
supervisor:
  type: {sup_type}
  name: {name}
  routes:{routes_yaml}"""

    manifest_path.write_text(content + block + "\n")
    print("  Updated: .agentops-stacks/manifest.yml (supervisor block)")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Add a supervisor agent to an AgentOps Stacks project"
    )
    parser.add_argument("--name", required=True,
                        help="Supervisor agent name (lowercase, underscores, min 3 chars)")
    parser.add_argument("--type", required=True, choices=sorted(VALID_TYPES),
                        help="Supervisor pattern (see the Selection Matrix in SKILL.md)")
    parser.add_argument("--routes", default="",
                        help="Comma-separated sub-agent names this supervisor routes to")
    parser.add_argument("--from", dest="source", default=None,
                        help="Existing agent to base the App shape on "
                             "(default: first found)")
    parser.add_argument("--project-dir", default=".", help="Project root (default: cwd)")
    args = parser.parse_args()

    if not NAME_RE.match(args.name):
        sys.exit("ERROR: Supervisor name must start with a lowercase letter and "
                 "contain only lowercase letters, digits, and underscores (min 3 chars).")

    routes = [r.strip() for r in args.routes.split(",") if r.strip()]
    if not routes:
        sys.exit("ERROR: --routes must name at least one sub-agent to route to "
                 "(comma-separated). A supervisor with no routes scaffolds an "
                 "empty create_supervisor([]) / managed tool list, which fails "
                 "to start. Example: --routes rag,support")

    project_root = find_project_root(Path(args.project_dir))
    print(f"Project root: {project_root}")

    existing = find_existing_agents(project_root)
    if args.name in existing:
        sys.exit(f"ERROR: An agent named '{args.name}' already exists.")

    # Validate that routes reference real agents (warn, don't hard-fail — a route
    # may point at a Genie space or managed endpoint rather than a local agent).
    unknown = [r for r in routes if r not in existing]
    if unknown:
        print(f"  NOTE: routes not matching a local agent (assumed managed "
              f"sub-agents — Genie/KA/endpoint): {unknown}")

    if not existing:
        sys.exit("ERROR: No existing agents to base the supervisor App on. "
                 "Scaffold at least one agent first.")
    source = args.source or existing[0]
    if source not in existing:
        sys.exit(f"ERROR: Source agent '{source}' not found. Available: {existing}")
    print(f"Adding {args.type} supervisor '{args.name}' (App shape from '{source}')\n")
    scaffold_supervisor_agent(project_root, args.name, args.type, source, routes)
    append_agent_resources_to_databricks_yml(project_root, args.name)

    update_manifest(project_root, args.name, args.type, routes)

    print(f"\nDone. Supervisor '{args.name}' ({args.type}) added.")
    _print_next_steps(args.name, args.type)


def _print_next_steps(name: str, sup_type: str):
    print("\nNext steps:")
    if sup_type == "custom":
        print(f"  1. cd src/agents/{name} && uv sync   # picks up langgraph-supervisor")
        print(f"  2. Edit graph.py — confirm each route's sub-agent endpoint/Genie id")
        print(f"  3. Edit eval/gates.yml — add a routing-accuracy scorer for the supervisor")
        print(f"  4. databricks bundle validate -t dev && databricks bundle deploy -t dev")
    else:  # supervisor_api
        print(f"  1. cd src/agents/{name} && uv sync   # picks up databricks-openai")
        print(f"  2. Ensure AI Gateway + the UC OTel-traces preview are enabled (Beta)")
        print(f"  3. Edit graph.py — set the sub-agent tool references (genie_space/serving_endpoint)")
        print(f"  4. databricks bundle validate -t dev && databricks bundle deploy -t dev")


if __name__ == "__main__":
    main()
