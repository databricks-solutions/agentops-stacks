"""Tests for project creation via `databricks bundle init`.

Verifies correct file generation, template substitution, and conditional file
inclusion across input combinations. Mirrors the databricks/mlops-stacks
tests/test_create_project.py pattern, adapted to the agentops-stacks schema.

Grounded against the real output of Databricks CLI v1.1.0.
"""

from pathlib import Path

import pytest

from utils import (
    ALL_COMPONENTS,
    COMMENTED_POLICY_LINE,
    EXAMPLE_USAGE_POLICY_ID as POLICY_ID,
    POLICY_RESOURCE_FILES,
    live_policy_lines,
    generate,
    paths,
    read_file,
    file_exists,
    assert_no_disallowed_strings_in_files,
    RESOURCE_TEMPLATE_ROOT_DIRECTORY,
    DEFAULT_PROJECT_NAME,
    DEFAULT_PROJECT_DIRECTORY,
)


def gen(tmp_path, **overrides):
    """Generate a project in a per-test tmp dir with the given overrides."""
    return generate(tmp_path, context=overrides)


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
    for f in [
        "experiment.yml",
        "schemas.yml",
        "volumes.yml",
        "uc_function_registration.yml",
    ]:
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
    content = read_file(
        gen(tmp_path, input_initial_agent_name="my_rag"), "databricks.yml"
    )
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


@pytest.mark.parametrize(
    "platform,expected,excluded",
    [(k, v[0], v[1]) for k, v in CICD_MATRIX.items()],
    ids=list(CICD_MATRIX.keys()),
)
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
    content = read_file(
        gen(tmp_path, input_use_uc_functions="yes"), "src/agents/default/tools.py"
    )
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


@pytest.mark.parametrize("cost_tags", ["yes", "no"])
def test_data_pipeline_is_serverless(tmp_path, cost_tags):
    """Serverless-only workspaces reject classic pipelines; dev mode comes from the target."""
    p = gen(tmp_path, input_use_vector_search="yes", input_enable_cost_tags=cost_tags)
    pipeline = read_file(p, "resources/data_pipeline.yml")
    assert "serverless: true" in pipeline
    assert "development:" not in pipeline


@pytest.mark.parametrize("cost_tags", ["yes", "no"])
def test_uc_registration_job_defaults_to_serverless(tmp_path, cost_tags):
    """No live cluster setting: the task runs on serverless (tagged via the usage policy)."""
    p = gen(tmp_path, input_use_uc_functions="yes", input_enable_cost_tags=cost_tags)
    job = read_file(p, "resources/uc_function_registration.yml")
    live = [l.strip() for l in job.splitlines() if not l.strip().startswith("#")]
    assert not any(
        l.startswith(("existing_cluster_id:", "job_clusters:", "job_cluster_key:"))
        for l in live
    )
    assert "# job_clusters:" in job


def test_uc_registration_job_classic_example_tags_cluster(tmp_path):
    """Classic compute bills under cluster custom_tags, so the job_clusters example carries them."""
    p = gen(tmp_path, input_use_uc_functions="yes")
    job = read_file(p, "resources/uc_function_registration.yml")
    assert "#       custom_tags:" in job
    assert f"#         project: {DEFAULT_PROJECT_NAME}" in job
    assert "#         environment: ${bundle.target}" in job


def test_vector_search_disabled_omits_resources(tmp_path):
    p = gen(tmp_path)
    assert not file_exists(p, "resources/vector_search.yml")
    assert not file_exists(p, "src/components/retriever")


# ---------------------------------------------------------------------------
# Lakebase conditional output
# ---------------------------------------------------------------------------


def test_lakebase_enabled_emits_resource(tmp_path):
    assert file_exists(
        gen(tmp_path, input_use_lakebase="yes"), "resources/lakebase.yml"
    )


def test_lakebase_disabled_omits_resource(tmp_path):
    assert not file_exists(gen(tmp_path), "resources/lakebase.yml")


def test_lakebase_resource_is_autoscaling(tmp_path):
    """The Lakebase resource uses Autoscaling (postgres_projects), not Provisioned."""
    content = read_file(
        gen(tmp_path, input_use_lakebase="yes"), "resources/lakebase.yml"
    )
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
        gen(tmp_path, input_use_vector_search="yes"),
        "src/agents/default/eval/gates.yml",
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
    content = read_file(
        gen(tmp_path, input_cloud="gcp"), ".agentops-stacks/manifest.yml"
    )
    assert f"project_name: {DEFAULT_PROJECT_NAME}" in content
    assert "cloud: gcp" in content
    assert "cicd_platform: github_actions" in content


def test_manifest_records_component_choices(tmp_path):
    content = read_file(
        gen(tmp_path, input_use_uc_functions="yes"), ".agentops-stacks/manifest.yml"
    )
    assert "uc_functions: yes" in content


# ---------------------------------------------------------------------------
# Usage tracking / cost-attribution tags
# ---------------------------------------------------------------------------


def test_tags_disabled_renders_no_tagging(tmp_path):
    """Opting out renders nothing tag-related: no tags, policy, docs, or script."""
    p = gen(tmp_path, input_enable_cost_tags="no", **ALL_COMPONENTS)
    for f in [
        "databricks.yml",
        "resources/experiment.yml",
        "resources/lakebase.yml",
        "resources/vector_search.yml",
        "resources/data_pipeline.yml",
        "resources/uc_function_registration.yml",
    ]:
        content = read_file(p, f)
        for s in ["tags:", "custom_tags:", "budget_policy_id", "usage_policy_id"]:
            assert s not in content, f"{s!r} unexpectedly in {f}"
    assert not file_exists(p, "docs/usage-tracking.md")
    assert not file_exists(p, "scripts/create_usage_policy.sh")


def test_tags_enabled_tags_every_taggable_resource(tmp_path):
    p = gen(tmp_path, **ALL_COMPONENTS)
    lakebase = read_file(p, "resources/lakebase.yml")
    assert "custom_tags:" not in lakebase  # tags come from the usage policy
    assert "budget_policy_id" in lakebase
    for f in ["resources/uc_function_registration.yml", "resources/data_pipeline.yml"]:
        content = read_file(p, f)
        assert f"project: {DEFAULT_PROJECT_NAME}" in content, f
        assert "environment: ${bundle.target}" in content, f
    experiment = read_file(p, "resources/experiment.yml")
    assert "key: agent" in experiment
    assert "value: default" in experiment
    assert file_exists(p, "docs/usage-tracking.md")
    assert file_exists(p, "scripts/create_usage_policy.sh")


def test_tags_without_policy_comments_out_policy_lines(tmp_path):
    """A blank policy ID must never render a live budget_policy_id (empty ID breaks deploy)."""
    p = gen(tmp_path, **ALL_COMPONENTS)
    for f in POLICY_RESOURCE_FILES:
        content = read_file(p, f)
        assert COMMENTED_POLICY_LINE in content, f
        assert not live_policy_lines(content), f
    assert 'default: ""' in read_file(p, "databricks.yml")


def test_tags_with_policy_wires_policy_everywhere(tmp_path):
    p = gen(tmp_path, input_usage_policy_id=POLICY_ID, **ALL_COMPONENTS)
    for f in POLICY_RESOURCE_FILES:
        assert live_policy_lines(read_file(p, f)), f"No live policy line in {f}"
    assert f'default: "{POLICY_ID}"' in read_file(p, "databricks.yml")


def test_usage_tracking_doc_and_script_reference_project(tmp_path):
    p = gen(tmp_path)
    assert DEFAULT_PROJECT_NAME in read_file(p, "docs/usage-tracking.md")
    script = read_file(p, "scripts/create_usage_policy.sh")
    assert f'PROJECT="{DEFAULT_PROJECT_NAME}"' in script
    assert "databricks account budget-policy create" in script
    assert "enable_usage_policy.py" in script


# ---------------------------------------------------------------------------
# validate_inputs.py usage-tracking checks
# ---------------------------------------------------------------------------

_VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "plugin/skills/agentops-stacks/scripts/validate_inputs.py"
)


def _validate(**overrides):
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_inputs", _VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    config = {
        "input_project_name": "my_project",
        "input_root_dir": "my_project",
        **overrides,
    }
    return mod.validate(config)


def test_validator_defaults_cost_tags_to_yes():
    _, warnings = _validate()
    assert any("No usage policy ID" in w for w in warnings)


@pytest.mark.parametrize(
    "policy_id", [12345, f"{POLICY_ID}\n"], ids=["not_str", "trailing_newline"]
)
def test_validator_rejects_malformed_policy_id(policy_id):
    errors, _ = _validate(input_usage_policy_id=policy_id)
    assert any("usage_policy_id" in e for e in errors)


def test_validator_accepts_null_policy_id():
    errors, _ = _validate(input_usage_policy_id=None)
    assert not any("usage_policy_id" in e for e in errors)


def test_databricks_yml_has_single_blank_line_before_include(tmp_path):
    for tags in ["yes", "no"]:
        p = gen(tmp_path / tags, input_enable_cost_tags=tags)
        assert "\n\n\ninclude:" not in read_file(p, "databricks.yml")
        assert "\n\ninclude:" in read_file(p, "databricks.yml")
