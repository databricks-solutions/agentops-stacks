"""Tests for add_supervisor.py — the /add-supervisor engine.

These build a minimal fake project tree (no Databricks CLI needed) and run the
script's functions directly, asserting the supervisor wires into databricks.yml,
the manifest, and the agent/App layout as designed. Complements
test_create_project.py (which covers `bundle init`).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "plugin" / "skills" / "agentops-stacks" / "scripts" / "add_supervisor.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("add_supervisor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


addsup = _load_module()


# --------------------------------------------------------------------------- #
# Fixtures — a minimal AgentOps Stacks project with one agent.
# --------------------------------------------------------------------------- #

DATABRICKS_YML = """\
bundle:
  name: my_proj
  engine: direct

include:
  - ./resources/experiment.yml

resources:
  apps:
    rag:
      name: "my-proj-rag"
      source_code_path: ./src/agents/rag

sync:
  include:
    - src/agents/**

targets:
  dev:
    default: true
"""

MANIFEST_YML = """\
contract_version: 5
project_name: my_proj
agents:
  - name: rag
"""

PYPROJECT = """\
[project]
name = "my_proj"
dependencies = [
    "mlflow>=3.10.0",
    "langgraph>=1.1.0",
    "python-dotenv>=1.2.1",
]
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "my_proj"
    agent = root / "src" / "agents" / "rag"
    (agent / "app").mkdir(parents=True)
    (agent / "eval").mkdir(parents=True)
    (root / ".agentops-stacks").mkdir(parents=True)
    (root / "resources").mkdir(parents=True)

    (root / "databricks.yml").write_text(DATABRICKS_YML)
    (root / ".agentops-stacks" / "manifest.yml").write_text(MANIFEST_YML)

    # Minimal source agent files that add_supervisor copies/overwrites.
    (agent / "agent.py").write_text("# rag agent\nfrom graph import graph\n")
    (agent / "graph.py").write_text("# rag graph\n")
    (agent / "tools.py").write_text("def get_tools():\n    return []\n")
    (agent / "pyproject.toml").write_text(PYPROJECT)
    (agent / "app.yaml").write_text("command: []\n")
    (agent / "app" / "start_server.py").write_text('AgentServer("rag")\n')
    (agent / "eval" / "gates.yml").write_text("block:\n  - safety:\n      floor: 4.0\n")
    return root


def read(root, rel):
    return (Path(root) / rel).read_text()


def exists(root, rel):
    return (Path(root) / rel).exists()


# --------------------------------------------------------------------------- #
# Discovery helpers
# --------------------------------------------------------------------------- #

def test_find_project_root(project):
    nested = project / "src" / "agents" / "rag"
    assert addsup.find_project_root(nested) == project.resolve()


def test_find_existing_agents(project):
    assert addsup.find_existing_agents(project) == ["rag"]


def test_get_project_name(project):
    assert addsup.get_project_name(project) == "my_proj"


# --------------------------------------------------------------------------- #
# custom supervisor
# --------------------------------------------------------------------------- #

def test_custom_scaffolds_agent_app(project):
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag", "support"])
    # New agent dir with the supervisor graph + tools.
    assert exists(project, "src/agents/router/graph.py")
    assert exists(project, "src/agents/router/eval/gates.yml")  # inherited → CI gates it
    graph = read(project, "src/agents/router/graph.py")
    assert "create_supervisor" in graph
    assert "'rag'" in graph and "'support'" in graph
    # Dependency added.
    assert "langgraph-supervisor" in read(project, "src/agents/router/pyproject.toml")


def test_custom_overwrites_agent_py(project):
    # Base agent.py imports `graph` symbols; the supervisor must overwrite it
    # with its own handler so startup imports resolve against the new graph.py.
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    agent_py = read(project, "src/agents/router/agent.py")
    assert "AgentServer handlers (supervisor)" in agent_py
    assert "get_async_checkpointer" not in agent_py  # not carried over from a lakebase base
    assert "from graph import graph" in agent_py


def test_custom_overwrites_agent_py_even_with_lakebase_base(project):
    # Simulate a base agent that had Lakebase memory: its agent.py imports
    # get_async_checkpointer. The supervisor overwrite must drop that import.
    base = project / "src" / "agents" / "rag" / "agent.py"
    base.write_text("from graph import graph_builder, get_async_checkpointer\n")
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    assert "get_async_checkpointer" not in read(project, "src/agents/router/agent.py")


def test_custom_appends_databricks_yml(project):
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    addsup.append_agent_resources_to_databricks_yml(project, "router")
    yml = read(project, "databricks.yml")
    assert "router_experiment:" in yml
    assert "source_code_path: ./src/agents/router" in yml
    assert "my-proj-router" in yml
    # App block inserted before sync:, experiment created a new experiments block.
    assert yml.index("router:") < yml.index("sync:")


def test_manifest_records_custom_supervisor(project):
    addsup.update_manifest(project, "router", "custom", ["rag", "support"])
    m = read(project, ".agentops-stacks/manifest.yml")
    assert "supervisor:" in m
    assert "type: custom" in m
    assert "name: router" in m
    assert "- rag" in m and "- support" in m


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #

def test_manifest_not_double_written(project):
    addsup.update_manifest(project, "router", "custom", ["rag"])
    addsup.update_manifest(project, "router2", "custom", ["rag"])
    m = read(project, ".agentops-stacks/manifest.yml")
    assert m.count("supervisor:") == 1  # second call is a no-op


def test_dep_not_duplicated(project):
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    py = read(project, "src/agents/router/pyproject.toml")
    assert py.count("langgraph-supervisor") == 1


# --------------------------------------------------------------------------- #
# Review fixes (PR #33) — runtime/startup blockers, caught structurally here
# and validated at import out-of-band (see the PR's testing notes).
# --------------------------------------------------------------------------- #

def test_custom_graph_drops_messages_state_schema(project):
    # Blocker 1: create_supervisor(state_schema=MessagesState) raises
    # "Missing required key(s) {'remaining_steps'}" at import under langgraph 1.x.
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    graph = read(project, "src/agents/router/graph.py")
    assert "state_schema=MessagesState" not in graph
    assert "from langgraph.graph import MessagesState" not in graph
    assert "create_supervisor(" in graph


def test_template_uses_supported_model_endpoint(project):
    # Blocker 2: databricks-claude-sonnet-4 is deprecated and 400s on every call.
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    graph = read(project, "src/agents/router/graph.py")
    assert "databricks-claude-sonnet-4-5" in graph
    assert '"databricks-claude-sonnet-4"' not in graph  # bare deprecated id gone


def test_empty_routes_rejected(project, monkeypatch):
    # Empty --routes scaffolds create_supervisor([]) / an empty managed tool
    # list, which can't start. Reject at the CLI instead of scaffolding it.
    monkeypatch.setattr(
        sys, "argv",
        ["add_supervisor", "--name", "router", "--type", "custom",
         "--routes", "", "--project-dir", str(project)],
    )
    with pytest.raises(SystemExit):
        addsup.main()
    assert not exists(project, "src/agents/router")  # nothing scaffolded


def test_rename_is_token_aware():
    # Raw str.replace corrupts identifiers that merely contain the source name
    # (storage -> stoROUTERe); underscored compounds (proj_rag_eval) must rename.
    out = addsup._rename_identifier(
        "storage myrag rag rag_eval proj_rag_eval", "rag", "router")
    assert out == "storage myrag router router_eval proj_router_eval"


def test_rename_does_not_corrupt_copied_files(project):
    # Integration: a copied file whose text contains the source name as a
    # substring survives the scaffold rename intact.
    (project / "src" / "agents" / "rag" / "notes.py").write_text(
        "storage_path = '/tmp'  # rag notes\n")
    addsup.scaffold_supervisor_agent(project, "router", "custom", "rag", ["rag"])
    notes = read(project, "src/agents/router/notes.py")
    assert "storage_path" in notes       # not corrupted to stoROUTERe_path
    assert "# router notes" in notes     # standalone token still renamed


def test_deps_added_for_alternate_langgraph_pin(tmp_path):
    # The dep insert must not silently no-op on a non->= langgraph pin shape.
    for i, pin in enumerate(('"langgraph==1.1.0",', '"langgraph~=1.1",', '"langgraph",')):
        py = tmp_path / f"pp_{i}.toml"
        py.write_text(f"[project]\ndependencies = [\n    {pin}\n]\n")
        addsup._add_supervisor_deps(py)
        assert "langgraph-supervisor>=0.0.31" in py.read_text()


def test_deps_warn_when_no_anchor(tmp_path, capsys):
    # No langgraph pin and no dependencies list — warn, don't silently drop it.
    py = tmp_path / "pp.toml"
    py.write_text("[project]\nname = 'x'\n")
    addsup._add_supervisor_deps(py)
    assert "WARN" in capsys.readouterr().out
    assert "langgraph-supervisor" not in py.read_text()


def test_invalid_type_rejected(project, monkeypatch):
    # Only `custom` remains valid; the removed supervisor_api must be rejected by
    # argparse rather than scaffolding anything.
    monkeypatch.setattr(
        sys, "argv",
        ["add_supervisor", "--name", "router", "--type", "supervisor_api",
         "--routes", "rag", "--project-dir", str(project)],
    )
    with pytest.raises(SystemExit):
        addsup.main()
    assert not exists(project, "src/agents/router")
