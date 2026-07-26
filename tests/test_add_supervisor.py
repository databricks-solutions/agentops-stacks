"""Tests for add_supervisor.py — the /add-supervisor engine.

These build a minimal fake project tree (no Databricks CLI needed) and run the
script's functions directly, asserting the three supervisor patterns wire into
databricks.yml, the manifest, and the agent/App or bootstrap-job layout as
designed. Complements test_create_project.py (which covers `bundle init`).
"""

import importlib.util
import sys
import textwrap
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
    assert "endpoint:" not in m  # only MAS gets an endpoint field


# --------------------------------------------------------------------------- #
# supervisor_api
# --------------------------------------------------------------------------- #

def test_supervisor_api_graph_and_dep(project):
    addsup.scaffold_supervisor_agent(project, "router", "supervisor_api", "rag", ["rag"])
    graph = read(project, "src/agents/router/graph.py")
    assert "DatabricksOpenAI" in graph
    assert "responses.create" in graph
    assert "databricks-openai" in read(project, "src/agents/router/pyproject.toml")


def test_manifest_records_supervisor_api(project):
    addsup.update_manifest(project, "router", "supervisor_api", ["rag"])
    m = read(project, ".agentops-stacks/manifest.yml")
    assert "type: supervisor_api" in m


# --------------------------------------------------------------------------- #
# agent_bricks_mas — NOT a DAB resource; bootstrap job + notebook only.
# --------------------------------------------------------------------------- #

def test_mas_scaffolds_bootstrap_job_and_notebook(project):
    addsup.scaffold_mas_bootstrap(project, "ops_mas", ["rag", "support"])
    assert exists(project, "notebooks/bootstrap_supervisor_ops_mas.py")
    assert exists(project, "resources/supervisor_ops_mas_bootstrap.yml")
    # Bootstrap job is included in databricks.yml.
    yml = read(project, "databricks.yml")
    assert "./resources/supervisor_ops_mas_bootstrap.yml" in yml
    # The job is a real DAB resource; the tile it creates is documented as not one.
    job = read(project, "resources/supervisor_ops_mas_bootstrap.yml")
    assert "jobs:" in job
    assert "notebook_task" in job
    nb = read(project, "notebooks/bootstrap_supervisor_ops_mas.py")
    assert "not a Declarative Automation Bundle resource" in nb.lower() or \
           "not a declarative automation bundle resource" in nb.lower()


def test_mas_does_not_create_agent_app(project):
    addsup.scaffold_mas_bootstrap(project, "ops_mas", ["rag"])
    # MAS must NOT create an src/agents App — it's a managed tile.
    assert not exists(project, "src/agents/ops_mas")


def test_manifest_records_mas_with_endpoint_field(project):
    addsup.update_manifest(project, "ops_mas", "agent_bricks_mas", ["rag"])
    m = read(project, ".agentops-stacks/manifest.yml")
    assert "type: agent_bricks_mas" in m
    assert "endpoint:" in m  # placeholder to fill after provisioning


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
