"""Tests for project creation via `databricks bundle init`.

Verifies correct file generation, template substitution, and conditional file
inclusion across input combinations. Mirrors the databricks/mlops-stacks
tests/test_create_project.py pattern, adapted to the agentops-stacks schema.

Grounded against the real output of Databricks CLI v1.1.0.
"""

import pytest

from utils import (
    generate,
    paths,
    read_file,
    file_exists,
    has_template_file,
    assert_no_disallowed_strings_in_files,
    assert_no_go_templates,
    RESOURCE_TEMPLATE_ROOT_DIRECTORY,
    DEFAULT_PROJECT_NAME,
    DEFAULT_PROJECT_DIRECTORY,
)


def gen(tmp_path, **overrides):
    """Generate a project in a per-test tmp dir with the given overrides."""
    return generate(tmp_path, context=overrides)


# ---------------------------------------------------------------------------
# No residual Go template strings after substitution
# ---------------------------------------------------------------------------

GO_TEMPLATE_COMBOS = [
    ("defaults", {}),
    ("uc_functions=yes", {"input_use_uc_functions": "yes"}),
    ("uc_existing=yes", {"input_use_uc_functions": "yes", "input_uc_functions_exist": "yes"}),
    ("vs=yes", {"input_use_vector_search": "yes"}),
    ("vs+chunked", {"input_use_vector_search": "yes", "input_has_chunked_table": "yes"}),
    ("lakebase=yes", {"input_use_lakebase": "yes"}),
    ("lakebase+short", {"input_use_lakebase": "yes", "input_memory_type": "short_term"}),
    ("lakebase+long", {"input_use_lakebase": "yes", "input_memory_type": "long_term"}),
    ("lakebase+both", {"input_use_lakebase": "yes", "input_memory_type": "both"}),
    ("eval=existing", {"input_eval_dataset_source": "existing"}),
    ("eval=manual", {"input_eval_dataset_source": "manual"}),
    ("eval=production_traces", {"input_eval_dataset_source": "production_traces"}),
    ("cloud=azure", {"input_cloud": "azure"}),
    ("cloud=gcp", {"input_cloud": "gcp"}),
    ("cicd=azure_devops", {"input_cicd_platform": "azure_devops"}),
    ("cicd=gitlab", {"input_cicd_platform": "gitlab"}),
]


@pytest.mark.parametrize("label,params", GO_TEMPLATE_COMBOS, ids=[c[0] for c in GO_TEMPLATE_COMBOS])
def test_no_go_templates_after_substitution(tmp_path, label, params):
    assert_no_go_templates(gen(tmp_path, **params))


# ---------------------------------------------------------------------------
# No hardcoded workspace URLs in template sources
# ---------------------------------------------------------------------------


def test_no_hardcoded_workspace_urls():
    import os
    import pathlib

    template_dir = pathlib.Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "template"
    test_paths = [os.path.join(template_dir, p) for p in paths(template_dir)]
    assert_no_disallowed_strings_in_files(
        file_paths=test_paths,
        disallowed_strings=[
            "azuredatabricks.net",
            "cloud.databricks.com",
            "gcp.databricks.com",
        ],
        exclude_path_matches=[".yml", ".yaml", "docs/", "README"],
    )


# ---------------------------------------------------------------------------
# Default project generation
# ---------------------------------------------------------------------------


def test_default_project_core_files(tmp_path):
    p = gen(tmp_path)
    assert p.exists() and p.name == DEFAULT_PROJECT_DIRECTORY
    assert file_exists(p, "databricks.yml")
    assert file_exists(p, "AGENTS.md")
    assert file_exists(p, "docs/README.md")
    assert file_exists(p, "docs/setup.md")
    assert DEFAULT_PROJECT_NAME in read_file(p, "README.md")


def test_default_base_resources(tmp_path):
    p = gen(tmp_path)
    # These resources are always emitted regardless of component choices.
    for f in ["experiment.yml", "schemas.yml", "volumes.yml", "uc_function_registration.yml"]:
        assert file_exists(p, f"resources/{f}"), f"Missing resources/{f}"


def test_shared_eval_scorers_present(tmp_path):
    # scorers.py is a shared component, not agent-scoped.
    assert file_exists(gen(tmp_path), "src/components/eval/scorers.py")


# ---------------------------------------------------------------------------
# Agent scaffold
# ---------------------------------------------------------------------------


def test_default_agent_runtime_files(tmp_path):
    p = gen(tmp_path)
    agent = "src/agents/default"
    for f in [
        "agent.py",
        "graph.py",
        "tools.py",
        "app.yaml",
        "pyproject.toml",
        ".env.example",
        "app/start_server.py",
        "app/utils.py",
    ]:
        assert file_exists(p, f"{agent}/{f}"), f"Missing {agent}/{f}"


def test_custom_agent_name(tmp_path):
    p = gen(tmp_path, input_initial_agent_name="rag_bot")
    for f in ["agent.py", "graph.py", "tools.py"]:
        assert file_exists(p, f"src/agents/rag_bot/{f}"), f"Missing rag_bot/{f}"


def test_agent_eval_files_always_present(tmp_path):
    p = gen(tmp_path)
    for f in ["gates.yml", "evaluate_agent.py", "utils.py"]:
        assert file_exists(p, f"src/agents/default/eval/{f}"), f"Missing eval/{f}"


def test_agent_name_in_databricks_yml(tmp_path):
    content = read_file(gen(tmp_path, input_initial_agent_name="my_rag"), "databricks.yml")
    assert "my_rag" in content  # source_code_path
    assert "my-rag" in content  # hyphenated app name


def test_start_server_imports_are_local(tmp_path):
    content = read_file(gen(tmp_path), "src/agents/default/app/start_server.py")
    assert "sys.path" in content
    assert "from src." not in content


def test_graph_imports_are_local(tmp_path):
    content = read_file(gen(tmp_path), "src/agents/default/graph.py")
    assert "from src." not in content


# ---------------------------------------------------------------------------
# databricks.yml content
# ---------------------------------------------------------------------------


def test_databricks_yml_content(tmp_path):
    content = read_file(gen(tmp_path), "databricks.yml")
    assert f"name: {DEFAULT_PROJECT_NAME}" in content
    assert "source_code_path: ./src/agents/default" in content
    assert "app/start_server.py" in content
    assert "src/agents/**" in content
    for r in ["experiment.yml", "schemas.yml", "volumes.yml"]:
        assert f"./resources/{r}" in content


# ---------------------------------------------------------------------------
# CICD platform selection — the right directory, and only that one
# ---------------------------------------------------------------------------

CICD_MATRIX = {
    "github_actions": (".github", [".azure", ".gitlab"]),
    "github_actions_for_github_enterprise_servers": (".github", [".azure", ".gitlab"]),
    "azure_devops": (".azure", [".github", ".gitlab"]),
    "gitlab": (".gitlab", [".github", ".azure"]),
}


@pytest.mark.parametrize("platform,expected,excluded", [
    (k, v[0], v[1]) for k, v in CICD_MATRIX.items()
], ids=list(CICD_MATRIX.keys()))
def test_cicd_platform_selection(tmp_path, platform, expected, excluded):
    p = gen(tmp_path, input_cicd_platform=platform)
    assert file_exists(p, expected), f"{expected} should exist for {platform}"
    for d in excluded:
        assert not file_exists(p, d), f"{d} should not exist for {platform}"


def test_github_workflow_files_contain_project_name(tmp_path):
    p = gen(tmp_path, input_cicd_platform="github_actions")
    github_files = [f for f in paths(p) if ".github" in f]
    assert any(DEFAULT_PROJECT_NAME in f for f in github_files)


# ---------------------------------------------------------------------------
# UC Functions conditional output
# ---------------------------------------------------------------------------


def test_uc_functions_enabled_emits_components(tmp_path):
    p = gen(tmp_path, input_use_uc_functions="yes")
    assert file_exists(p, "src/components/tools/registry.py")
    assert file_exists(p, "src/components/tools/definitions/example_function.sql")


def test_uc_functions_enabled_adds_toolkit(tmp_path):
    content = read_file(gen(tmp_path, input_use_uc_functions="yes"), "src/agents/default/tools.py")
    assert "UCFunctionToolkit" in content


def test_uc_functions_disabled_omits_components(tmp_path):
    p = gen(tmp_path)
    assert not file_exists(p, "src/components/tools")
    assert "UCFunctionToolkit" not in read_file(p, "src/agents/default/tools.py")


def test_uc_functions_existing_skips_definitions(tmp_path):
    p = gen(tmp_path, input_use_uc_functions="yes", input_uc_functions_exist="yes")
    assert file_exists(p, "src/components/tools/registry.py")
    assert not file_exists(p, "src/components/tools/definitions")


# ---------------------------------------------------------------------------
# Vector Search conditional output
# ---------------------------------------------------------------------------


def test_vector_search_enabled_emits_resources(tmp_path):
    p = gen(tmp_path, input_use_vector_search="yes")
    assert file_exists(p, "resources/vector_search.yml")
    assert file_exists(p, "resources/data_pipeline.yml")
    assert file_exists(p, "src/components/retriever/data_pipeline.py")


def test_vector_search_disabled_omits_resources(tmp_path):
    p = gen(tmp_path)
    assert not file_exists(p, "resources/vector_search.yml")
    assert not file_exists(p, "src/components/retriever")


# ---------------------------------------------------------------------------
# Lakebase conditional output
# ---------------------------------------------------------------------------


def test_lakebase_enabled_emits_resource(tmp_path):
    assert file_exists(gen(tmp_path, input_use_lakebase="yes"), "resources/lakebase.yml")


def test_lakebase_disabled_omits_resource(tmp_path):
    assert not file_exists(gen(tmp_path), "resources/lakebase.yml")


def test_lakebase_resource_is_autoscaling(tmp_path):
    """The Lakebase resource uses Autoscaling (postgres_projects), not Provisioned."""
    content = read_file(gen(tmp_path, input_use_lakebase="yes"), "resources/lakebase.yml")
    assert "postgres_projects" in content
    assert "autoscaling_limit_max_cu" in content
    # No leftover Provisioned resource types / fields.
    assert "database_instances" not in content
    assert "database_catalogs" not in content
    assert "capacity: CU_" not in content


def test_lakebase_app_resource_uses_postgres_key(tmp_path):
    """The app binds the memory via the `postgres` resource key, not the Provisioned `database` key."""
    content = read_file(gen(tmp_path, input_use_lakebase="yes"), "databricks.yml")
    assert "postgres:" in content
    assert "branches/production" in content
    assert "instance_name:" not in content
    # The database *resource id* is hyphenated (databricks-postgres); using the
    # underscore Postgres db name here fails deploy with a 404. Guard against it.
    assert "databases/databricks-postgres" in content
    assert "databases/databricks_postgres" not in content


def test_lakebase_checkpointer_uses_databricks_langchain(tmp_path):
    """graph.py connects via databricks-langchain AsyncCheckpointSaver, not w.database."""
    content = read_file(
        gen(tmp_path, input_use_lakebase="yes"), "src/agents/default/graph.py"
    )
    assert "AsyncCheckpointSaver" in content
    assert "databricks_langchain" in content
    assert "LAKEBASE_ENDPOINT" in content
    # No leftover Provisioned SDK calls / env vars.
    assert "w.database.generate_database_credential" not in content
    assert "instance_names" not in content
    assert "LAKEBASE_INSTANCE" not in content


def test_lakebase_pyproject_adds_databricks_langchain_memory(tmp_path):
    content = read_file(
        gen(tmp_path, input_use_lakebase="yes"), "src/agents/default/pyproject.toml"
    )
    assert "databricks-langchain[memory]" in content


# ---------------------------------------------------------------------------
# Lakebase memory type — short-term (checkpointer) vs long-term (store + tools)
# ---------------------------------------------------------------------------


def test_lakebase_short_term_has_checkpointer_only(tmp_path):
    p = gen(tmp_path, input_use_lakebase="yes", input_memory_type="short_term")
    graph = read_file(p, "src/agents/default/graph.py")
    tools = read_file(p, "src/agents/default/tools.py")
    # Short-term checkpointer present, long-term store absent.
    assert "get_async_checkpointer" in graph
    assert "AsyncDatabricksStore" not in graph
    assert "get_async_store" not in graph
    assert "save_user_memory" not in tools
    assert "memory_tools" not in tools


def test_lakebase_long_term_has_store_and_tools(tmp_path):
    p = gen(tmp_path, input_use_lakebase="yes", input_memory_type="long_term")
    graph = read_file(p, "src/agents/default/graph.py")
    tools = read_file(p, "src/agents/default/tools.py")
    agent = read_file(p, "src/agents/default/agent.py")
    # Long-term store + tools present.
    assert "AsyncDatabricksStore" in graph
    assert "get_async_store" in graph
    assert "def memory_tools" in tools
    assert "save_user_memory" in tools
    assert "get_user_memory" in tools
    assert "delete_user_memory" in tools
    # user_id is wired into the request config.
    assert "get_user_id" in agent
    # long-term only → no short-term checkpointer.
    assert "get_async_checkpointer" not in graph


def test_lakebase_both_has_checkpointer_and_store(tmp_path):
    p = gen(tmp_path, input_use_lakebase="yes", input_memory_type="both")
    graph = read_file(p, "src/agents/default/graph.py")
    tools = read_file(p, "src/agents/default/tools.py")
    assert "get_async_checkpointer" in graph
    assert "AsyncCheckpointSaver" in graph
    assert "get_async_store" in graph
    assert "AsyncDatabricksStore" in graph
    assert "memory_tools" in tools


def test_lakebase_long_term_adds_embedding_env(tmp_path):
    p = gen(tmp_path, input_use_lakebase="yes", input_memory_type="long_term")
    app_yaml = read_file(p, "src/agents/default/app.yaml")
    assert "DATABRICKS_EMBEDDING_ENDPOINT" in app_yaml
    assert "databricks-gte-large-en" in app_yaml


def test_lakebase_short_term_omits_embedding_env(tmp_path):
    p = gen(tmp_path, input_use_lakebase="yes", input_memory_type="short_term")
    app_yaml = read_file(p, "src/agents/default/app.yaml")
    assert "DATABRICKS_EMBEDDING_ENDPOINT" not in app_yaml


def test_lakebase_disabled_omits_all_memory_wiring(tmp_path):
    """input_memory_type defaults exist, but no lakebase → no memory code at all."""
    p = gen(tmp_path)
    graph = read_file(p, "src/agents/default/graph.py")
    tools = read_file(p, "src/agents/default/tools.py")
    assert "AsyncCheckpointSaver" not in graph
    assert "AsyncDatabricksStore" not in graph
    assert "memory_tools" not in tools


# ---------------------------------------------------------------------------
# Eval dataset source conditional output
# ---------------------------------------------------------------------------


def test_eval_synthetic_uses_generate_evals_df(tmp_path):
    content = read_file(
        gen(tmp_path, input_eval_dataset_source="synthetic"),
        "src/agents/default/eval/create_dataset.py",
    )
    assert "generate_evals_df" in content


def test_eval_production_traces_uses_search_traces(tmp_path):
    content = read_file(
        gen(tmp_path, input_eval_dataset_source="production_traces"),
        "src/agents/default/eval/create_dataset.py",
    )
    assert "search_traces" in content


def test_eval_existing_skips_create_dataset(tmp_path):
    p = gen(tmp_path, input_eval_dataset_source="existing")
    assert not file_exists(p, "src/agents/default/eval/create_dataset.py")
    # But the rest of the eval scaffold remains.
    for f in ["gates.yml", "evaluate_agent.py", "utils.py"]:
        assert file_exists(p, f"src/agents/default/eval/{f}")


# ---------------------------------------------------------------------------
# gates.yml — scorers are conditional on enabled components
# ---------------------------------------------------------------------------


def test_gates_safety_and_fluency_always_present(tmp_path):
    content = read_file(gen(tmp_path), "src/agents/default/eval/gates.yml")
    assert "safety" in content
    assert "fluency" in content


def test_gates_vs_adds_relevance_groundedness(tmp_path):
    content = read_file(
        gen(tmp_path, input_use_vector_search="yes"), "src/agents/default/eval/gates.yml"
    )
    assert "relevance" in content
    assert "groundedness" in content


def test_gates_no_vs_omits_relevance_groundedness(tmp_path):
    content = read_file(gen(tmp_path), "src/agents/default/eval/gates.yml")
    assert "relevance" not in content
    assert "groundedness" not in content


def test_gates_uc_adds_tool_call_correctness(tmp_path):
    content = read_file(
        gen(tmp_path, input_use_uc_functions="yes"), "src/agents/default/eval/gates.yml"
    )
    assert "tool_call_correctness" in content


def test_gates_no_uc_omits_tool_call_correctness(tmp_path):
    content = read_file(gen(tmp_path), "src/agents/default/eval/gates.yml")
    assert "tool_call_correctness" not in content


# ---------------------------------------------------------------------------
# Manifest content
# ---------------------------------------------------------------------------


def test_manifest_records_choices(tmp_path):
    content = read_file(gen(tmp_path, input_cloud="gcp"), ".agentops-stacks/manifest.yml")
    assert f"project_name: {DEFAULT_PROJECT_NAME}" in content
    assert "cloud: gcp" in content
    assert "cicd_platform: github_actions" in content


def test_manifest_records_component_choices(tmp_path):
    content = read_file(
        gen(tmp_path, input_use_uc_functions="yes"), ".agentops-stacks/manifest.yml"
    )
    assert "uc_functions: yes" in content


# ---------------------------------------------------------------------------
# Cloud x CICD matrix — every combination generates cleanly
# ---------------------------------------------------------------------------

MATRIX = [
    (platform, cloud)
    for platform in ["github_actions", "azure_devops", "gitlab"]
    for cloud in ["aws", "azure", "gcp"]
]


@pytest.mark.large
@pytest.mark.parametrize("platform,cloud", MATRIX, ids=[f"{p}-{c}" for p, c in MATRIX])
def test_cloud_cicd_matrix(tmp_path, platform, cloud):
    p = gen(tmp_path, input_cicd_platform=platform, input_cloud=cloud)
    assert p.exists()
    assert file_exists(p, "databricks.yml")
    assert_no_go_templates(p)


# ---------------------------------------------------------------------------
# Invalid params are rejected
# ---------------------------------------------------------------------------

INVALID = [
    ("name_too_short", {"input_project_name": "ab", "input_root_dir": "ab"}),
    ("name_uppercase", {"input_project_name": "MyProject", "input_root_dir": "MyProject"}),
    ("name_starts_digit", {"input_project_name": "1bad", "input_root_dir": "1bad"}),
    ("agent_name_too_short", {"input_initial_agent_name": "ab"}),
]


@pytest.mark.parametrize("label,params", INVALID, ids=[c[0] for c in INVALID])
def test_invalid_params_rejected(tmp_path, label, params):
    with pytest.raises(RuntimeError):
        gen(tmp_path, **params)
