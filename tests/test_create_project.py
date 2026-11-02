"""Tests for project creation via `databricks bundle init`.

Verifies correct file generation, template substitution, and conditional file
inclusion across input combinations. Mirrors the databricks/mlops-stacks
tests/test_create_project.py pattern, adapted to the agentops-stacks schema.

Grounded against the real output of Databricks CLI v1.1.0.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
    ("tags=no", {"input_enable_cost_tags": "no"}),
    ("tags+policy", {"input_usage_policy_id": "1a2b3c4d-1234-5678-9abc-0123456789ab"}),
    ("tags+all_components", {
        "input_use_vector_search": "yes",
        "input_use_lakebase": "yes",
        "input_use_uc_functions": "yes",
        "input_usage_policy_id": "1a2b3c4d-1234-5678-9abc-0123456789ab",
    }),
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
    for f in ["experiment.yml", "schemas.yml", "volumes.yml"]:
        assert file_exists(p, f"resources/{f}"), f"Missing resources/{f}"


@pytest.mark.parametrize("uc", ["yes", "no"])
def test_uc_registration_job_only_with_uc_functions(tmp_path, uc):
    # The job runs src/components/tools/registry.py, which only exists with UC functions on.
    p = gen(tmp_path, input_use_uc_functions=uc)
    assert file_exists(p, "resources/uc_function_registration.yml") == (uc == "yes")
    assert file_exists(p, "src/components/tools/registry.py") == (uc == "yes")


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
        "pyproject.toml",
        ".env.example",
        "app/start_server.py",
        "app/utils.py",
    ]:
        assert file_exists(p, f"{agent}/{f}"), f"Missing {agent}/{f}"
    # The App's env lives in databricks.yml (resolved per target), not a source app.yaml.
    assert not file_exists(p, f"{agent}/app.yaml")


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
    # No sync.include: it overrides .gitignore and uploaded .venv/.env/mlflow.db (#61).
    assert "sync:" not in content
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
# CI Databricks CLI pin. CI must read bundle state written by any CLI that can
# scaffold this template, so its pin is never older than the schema minimum.
# ---------------------------------------------------------------------------

SETUP_CLI_SHA = re.compile(r"databricks/setup-cli[@/]([0-9a-f]{40})")
SETUP_CLI_TAG = re.compile(r"databricks/setup-cli@[0-9a-f]{40} # (v\d+\.\d+\.\d+)")


def _version(tag):
    return tuple(int(part) for part in tag.lstrip("v").split("."))


def _ci_text(project):
    ci_dirs = (".github/", ".gitlab/", ".azure/")
    return "\n".join(read_file(project, f) for f in sorted(paths(project)) if f.startswith(ci_dirs))


def test_ci_cli_pin_meets_template_minimum(tmp_path):
    minimum = json.loads(
        (Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "databricks_template_schema.json").read_text()
    )["min_databricks_cli_version"]
    tags = SETUP_CLI_TAG.findall(_ci_text(gen(tmp_path, input_cicd_platform="github_actions")))
    assert tags, "setup-cli steps must pin a commit SHA with a vX.Y.Z version comment"
    for tag in tags:
        assert _version(tag) >= _version(minimum), f"CI pins setup-cli {tag} < template minimum {minimum}"


@pytest.mark.parametrize("platform", list(CICD_MATRIX))
def test_ci_cli_pin_is_one_sha_across_platforms(tmp_path, platform):
    (tmp_path / "github").mkdir()
    (tmp_path / "other").mkdir()
    github = set(SETUP_CLI_SHA.findall(_ci_text(gen(tmp_path / "github", input_cicd_platform="github_actions"))))
    pinned = set(SETUP_CLI_SHA.findall(_ci_text(gen(tmp_path / "other", input_cicd_platform=platform))))
    assert pinned, f"no pinned setup-cli found for {platform}"
    assert pinned == github, f"{platform} pins {pinned}, GitHub pins {github}"


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
    assert not any(l.startswith(("existing_cluster_id:", "job_clusters:", "job_cluster_key:")) for l in live)
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
    app_env = read_file(p, "databricks.yml")
    assert "DATABRICKS_EMBEDDING_ENDPOINT" in app_env
    assert "databricks-gte-large-en" in app_env


def test_lakebase_short_term_omits_embedding_env(tmp_path):
    p = gen(tmp_path, input_use_lakebase="yes", input_memory_type="short_term")
    app_env = read_file(p, "databricks.yml")
    assert "DATABRICKS_EMBEDDING_ENDPOINT" not in app_env


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
    # databricks-agents makes eval_per_x_tokens a required keyword; without it the
    # default (synthetic) dataset build raises TypeError before saving anything.
    assert "estimate_synthetic_num_evals(docs, eval_per_x_tokens=" in content


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


@pytest.mark.parametrize("uc", ["yes", "no"])
def test_gate_floors_are_on_the_judge_scale(tmp_path, uc):
    # Built-in judges report a 0-1 pass rate; a floor above 1 can never pass.
    content = read_file(gen(tmp_path, input_use_uc_functions=uc), "src/agents/default/eval/gates.yml")
    floors = [float(v) for v in re.findall(r"floor:\s*([0-9.]+)", content)]
    assert floors and all(0 < f <= 1 for f in floors), floors


def test_eval_gate_never_scores_sample_data_silently(tmp_path):
    script = read_file(gen(tmp_path), "src/agents/default/eval/evaluate_agent.py")
    # mlflow.genai.evaluate passes inputs as kwargs, so the parameter is the inputs key.
    assert "def predict_fn(messages)" in script
    # The inline set is opt-in only, and tracking defaults to Databricks (hosted judges).
    assert "EVAL_ALLOW_INLINE_DATASET" in script
    assert 'os.environ.get("MLFLOW_TRACKING_URI", "databricks")' in script


def test_eval_gate_unit_tests_generated(tmp_path):
    assert file_exists(gen(tmp_path), "tests/test_eval_gates.py")


@pytest.mark.parametrize("workflow,target", [("ci", "staging"), ("cd-staging", "staging"), ("cd-prod", "prod")])
def test_github_eval_gate_reads_target_settings_from_bundle(tmp_path, workflow, target):
    content = read_file(gen(tmp_path), f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-{workflow}.yml")
    gate = content[content.index("  eval_gate:"):]
    assert f"databricks bundle summary -t {target} -o json" in gate
    for var in ("DATABRICKS_HOST", "CATALOG", "SCHEMA", "MLFLOW_TRACKING_URI", "MLFLOW_EXPERIMENT_ID"):
        assert var in gate, f"{var} not set for the {workflow} eval gate"
    assert "databricks/setup-cli@" in gate


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
# Usage tracking / cost-attribution tags
# ---------------------------------------------------------------------------

POLICY_ID = "1a2b3c4d-1234-5678-9abc-0123456789ab"
ALL_COMPONENTS = {
    "input_use_vector_search": "yes",
    "input_use_lakebase": "yes",
    "input_use_uc_functions": "yes",
}
LIVE_POLICY_LINE = "budget_policy_id: ${var.usage_policy_id}"
COMMENTED_POLICY_LINE = "# budget_policy_id: ${var.usage_policy_id}"
POLICY_RESOURCE_FILES = [
    "databricks.yml",
    "resources/lakebase.yml",
    "resources/vector_search.yml",
    "resources/data_pipeline.yml",
    "resources/uc_function_registration.yml",
]


def _live_policy_lines(content):
    return [l for l in content.splitlines() if l.strip() == LIVE_POLICY_LINE]


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
        assert not _live_policy_lines(content), f
    assert 'default: ""' in read_file(p, "databricks.yml")


def test_tags_with_policy_wires_policy_everywhere(tmp_path):
    p = gen(tmp_path, input_usage_policy_id=POLICY_ID, **ALL_COMPONENTS)
    for f in POLICY_RESOURCE_FILES:
        assert _live_policy_lines(read_file(p, f)), f"No live policy line in {f}"
    assert f'default: "{POLICY_ID}"' in read_file(p, "databricks.yml")


def test_usage_tracking_doc_and_script_reference_project(tmp_path):
    p = gen(tmp_path)
    assert DEFAULT_PROJECT_NAME in read_file(p, "docs/usage-tracking.md")
    script = read_file(p, "scripts/create_usage_policy.sh")
    assert f'PROJECT="{DEFAULT_PROJECT_NAME}"' in script
    assert "databricks account budget-policy create" in script
    assert "enable_usage_policy.py" in script


def _wire(tmp_path, *args):
    """Copy a tags-on, blank-policy project (generated projects are cached) and run the wiring script."""
    project = tmp_path / "wired"
    shutil.copytree(gen(tmp_path, **ALL_COMPONENTS), project)
    result = subprocess.run(
        [sys.executable, "scripts/enable_usage_policy.py", *args],
        cwd=project, capture_output=True, text=True,
    )
    return project, result


def test_enable_usage_policy_wires_every_target(tmp_path):
    other = "aaaaaaaa-1234-5678-9abc-0123456789ab"
    p, result = _wire(tmp_path, f"dev={POLICY_ID}", f"staging={other}", f"prod={other}")
    assert result.returncode == 0, result.stderr
    databricks_yml = read_file(p, "databricks.yml")
    assert f"      usage_policy_id: {POLICY_ID}" in databricks_yml
    assert databricks_yml.count(f"      usage_policy_id: {other}") == 2
    for f in POLICY_RESOURCE_FILES:
        content = read_file(p, f)
        assert _live_policy_lines(content), f"No live policy line in {f}"
        assert COMMENTED_POLICY_LINE not in content, f


def test_enable_usage_policy_shared_default(tmp_path):
    p, result = _wire(tmp_path, "--default", POLICY_ID)
    assert result.returncode == 0, result.stderr
    assert f'default: "{POLICY_ID}"' in read_file(p, "databricks.yml")
    for f in POLICY_RESOURCE_FILES:
        assert _live_policy_lines(read_file(p, f)), f


def test_enable_usage_policy_refuses_when_a_target_has_no_id(tmp_path):
    """A target without an ID would deploy an empty budget_policy_id, so nothing may change."""
    p, result = _wire(tmp_path, f"dev={POLICY_ID}", f"prod={POLICY_ID}")
    assert result.returncode != 0
    assert "staging" in result.stderr
    original = gen(tmp_path, **ALL_COMPONENTS)
    for f in POLICY_RESOURCE_FILES:
        assert read_file(p, f) == read_file(original, f), f


@pytest.mark.parametrize("args", [["dev=not-a-uuid"], [f"qa={POLICY_ID}"]], ids=["bad_id", "unknown_target"])
def test_enable_usage_policy_rejects_bad_input(tmp_path, args):
    _, result = _wire(tmp_path, *args)
    assert result.returncode != 0


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
    ("usage_policy_id_not_uuid", {"input_usage_policy_id": "not-a-policy-id"}),
]


@pytest.mark.parametrize("label,params", INVALID, ids=[c[0] for c in INVALID])
def test_invalid_params_rejected(tmp_path, label, params):
    with pytest.raises(RuntimeError):
        gen(tmp_path, **params)


# ---------------------------------------------------------------------------
# validate_inputs.py usage-tracking checks
# ---------------------------------------------------------------------------

_VALIDATOR = Path(__file__).resolve().parents[1] / "plugin/skills/agentops-stacks/scripts/validate_inputs.py"


def _validate(**overrides):
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_inputs", _VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    config = {"input_project_name": "my_project", "input_root_dir": "my_project", **overrides}
    return mod.validate(config)


def test_validator_defaults_cost_tags_to_yes():
    _, warnings = _validate()
    assert any("No usage policy ID" in w for w in warnings)


@pytest.mark.parametrize("policy_id", [12345, f"{POLICY_ID}\n"], ids=["not_str", "trailing_newline"])
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


# ---------------------------------------------------------------------------
# Deployed App: env resolved per target, UC grants, schema references, CD starts it
# ---------------------------------------------------------------------------

BUNDLE_SCHEMA = "${resources.schemas.project_schema.name}"


def _app_block(databricks_yml, app="default"):
    """The `resources.apps.<app>` block: from its key to the next 4-space key (or EOF)."""
    start = databricks_yml.index(f"\n    {app}:\n", databricks_yml.index("\n  apps:\n"))
    nxt = re.search(r"\n {0,4}\S", databricks_yml[start + 1:])
    return databricks_yml[start: start + 1 + nxt.start()] if nxt else databricks_yml[start:]


def test_app_env_is_resolved_per_target(tmp_path):
    app = _app_block(read_file(gen(tmp_path), "databricks.yml"))
    assert '["uv", "run", "--frozen", "--no-dev", "python", "app/start_server.py"]' in app
    assert "- name: CATALOG\n            value: ${var.catalog}" in app
    assert f"value: {BUNDLE_SCHEMA}" in app  # dev-prefixed schema, not the raw variable
    assert "- name: MLFLOW_TRACKING_URI\n            value: \"databricks\"" in app
    assert 'value_from: "experiment"' in app


def test_app_attaches_the_artifacts_volume(tmp_path):
    app = _app_block(read_file(gen(tmp_path), "databricks.yml"))
    assert f"securable_full_name: ${{var.catalog}}.{BUNDLE_SCHEMA}.${{resources.volumes.artifacts.name}}" in app
    assert 'securable_type: "VOLUME"' in app and 'permission: "WRITE_VOLUME"' in app


@pytest.mark.parametrize("chunked", ["no", "yes"])
def test_bundle_created_assets_reference_the_bundle_schema(tmp_path, chunked):
    p = gen(tmp_path, **ALL_COMPONENTS, input_has_chunked_table=chunked)
    files = ["resources/experiment.yml", "resources/volumes.yml", "resources/uc_function_registration.yml",
             "resources/vector_search.yml"] + (["resources/data_pipeline.yml"] if chunked == "no" else [])
    for f in files:
        for line in read_file(p, f).splitlines():
            if "${var.schema}" in line:
                # Only a pre-existing, user-owned chunked table stays in the raw schema.
                assert chunked == "yes" and "source_table:" in line, f"{f}: {line.strip()}"
    vs = read_file(p, "resources/vector_search.yml")
    expected = "${var.schema}" if chunked == "yes" else BUNDLE_SCHEMA
    assert f"source_table: ${{var.catalog}}.{expected}." in vs


@pytest.mark.parametrize("platform,files", [
    ("github_actions", [f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-cd-staging.yml",
                        f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-cd-prod.yml"]),
    ("gitlab", [f".gitlab/pipelines/{DEFAULT_PROJECT_NAME}-bundle-cd-staging.yml",
                f".gitlab/pipelines/{DEFAULT_PROJECT_NAME}-bundle-cd-prod.yml"]),
    ("azure_devops", [f".azure/devops-pipelines/{DEFAULT_PROJECT_NAME}-bundle-cicd.yml"]),
])
def test_cd_starts_every_app_after_deploy(tmp_path, platform, files):
    p = gen(tmp_path, input_cicd_platform=platform)
    for f in files:
        content = read_file(p, f)
        for target in ("staging", "prod"):
            deploy = f"databricks bundle deploy -t {target}"
            if deploy not in content:
                continue
            run = content.index(f'databricks bundle run "$app" -t {target}')
            assert content.index(deploy) < run, f"{f}: bundle run must follow deploy for {target}"


def test_add_agent_inherits_the_source_app_env(tmp_path):
    """/add-agent: the new App gets the source agent's env, the volume resource, and the bundle schema."""
    project = tmp_path / "copy"
    shutil.copytree(gen(tmp_path, input_use_lakebase="yes"), project)  # don't mutate the cached render
    script = Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "plugin/skills/agentops-stacks/scripts/add_agent.py"
    # "support" keeps the App name, my-agentops-project-support, within the 30-character cap.
    subprocess.run([sys.executable, str(script), "--name", "support", "--from", "default",
                    "--project-dir", str(project)], check=True, capture_output=True, text=True)
    yml = read_file(project, "databricks.yml")
    app = _app_block(yml, "support")
    assert "LAKEBASE_ENDPOINT" in app and 'value_from: "experiment"' in app
    assert 'permission: "WRITE_VOLUME"' in app and "--no-dev" in app
    assert f"artifact_location: dbfs:/Volumes/${{var.catalog}}/{BUNDLE_SCHEMA}/artifacts" in yml


# ---------------------------------------------------------------------------
# Deploy hygiene and CI auth
# ---------------------------------------------------------------------------


def test_gitignore_keeps_local_artifacts_out_of_deploys(tmp_path):
    gitignore = read_file(gen(tmp_path), ".gitignore")
    for pattern in (".venv/", ".env", "*.db", "mlruns", "__pycache__/"):
        assert pattern in gitignore, pattern


CI_FILES = {
    "github_actions": [f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-{w}.yml" for w in ("ci", "cd-staging", "cd-prod")],
    "gitlab": [f".gitlab/pipelines/{DEFAULT_PROJECT_NAME}-bundle-{w}.yml" for w in ("ci", "cd-staging", "cd-prod")],
    "azure_devops": [f".azure/devops-pipelines/{DEFAULT_PROJECT_NAME}-bundle-cicd.yml"],
}


@pytest.mark.parametrize("platform", list(CI_FILES))
@pytest.mark.parametrize("cloud", ["aws", "gcp", "azure"])
def test_ci_authenticates_with_sp_oauth_not_a_token(tmp_path, platform, cloud):
    p = gen(tmp_path, input_cicd_platform=platform, input_cloud=cloud)
    for f in CI_FILES[platform]:
        content = read_file(p, f)
        assert "DATABRICKS_TOKEN" not in content, f
        if cloud == "azure":
            assert "ARM_CLIENT_SECRET" in content, f
        else:
            assert "DATABRICKS_CLIENT_ID" in content and "DATABRICKS_CLIENT_SECRET" in content, f
            assert "_SP_CLIENT_SECRET" in content, f


@pytest.mark.parametrize("platform", list(CI_FILES))
def test_ci_runs_the_committed_lock(tmp_path, platform):
    p = gen(tmp_path, input_cicd_platform=platform)
    for f in CI_FILES[platform]:
        content = read_file(p, f)
        assert re.search(r'UV_FROZEN\b[":\s]+(value: )?"1"', content), f"{f}: UV_FROZEN not set"


# ---------------------------------------------------------------------------
# Every CI platform runs the same per-agent eval gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("platform", list(CI_FILES))
def test_every_platform_gates_on_the_per_agent_eval_layout(tmp_path, platform):
    p = gen(tmp_path, input_cicd_platform=platform)
    text = "\n".join(read_file(p, f) for f in CI_FILES[platform])
    assert "evaluation/" not in text  # the pre-migration layout the scaffold never generates
    assert "eval/gates.yml" in text and "eval/evaluate_agent.py" in text
    assert "databricks bundle summary -t staging -o json" in text
    for var in ("DATABRICKS_HOST", "CATALOG", "SCHEMA", "MLFLOW_TRACKING_URI", "MLFLOW_EXPERIMENT_ID"):
        assert var in text, f"{platform}: {var} not set for the eval gate"


@pytest.mark.parametrize("platform", ["gitlab", "azure_devops"])
def test_unit_tests_run_in_the_agent_folder(tmp_path, platform):
    # Each agent has its own pyproject.toml; there's none at the project root.
    ci = read_file(gen(tmp_path, input_cicd_platform=platform), CI_FILES[platform][0])
    assert "cd src/agents/default" in ci
    assert "pytest ../../../tests/" in ci


@pytest.mark.parametrize("platform", ["gitlab", "azure_devops"])
def test_agent_loops_fail_when_any_agent_fails(tmp_path, platform):
    # Without -e, a for-loop's status is its last iteration's: a failing agent could be masked.
    text = "\n".join(read_file(gen(tmp_path, input_cicd_platform=platform), f) for f in CI_FILES[platform])
    assert text.count("eval/evaluate_agent.py) || exit 1") == 3
    assert "bundle run \"$app\" -t staging || exit 1" in text


@pytest.mark.parametrize("cloud", ["aws", "azure"])
def test_azure_devops_eval_steps_have_credentials(tmp_path, cloud):
    ci = read_file(gen(tmp_path, input_cicd_platform="azure_devops", input_cloud=cloud), CI_FILES["azure_devops"][0])
    steps = ci.split("displayName: 'Run eval gate (conditional)'")[1:]
    assert len(steps) == 3
    for step in steps:
        env = step.split("- script:")[0]
        assert ("ARM_CLIENT_SECRET" if cloud == "azure" else "DATABRICKS_CLIENT_SECRET") in env


# ---------------------------------------------------------------------------
# Docs and the API-only App
# ---------------------------------------------------------------------------


def test_agent_server_validates_as_a_responses_agent(tmp_path):
    # AgentServer's first argument is the agent *type*; any other value skips request
    # validation (bad payloads get a 500, not a 400) and the OpenAI trace format.
    content = read_file(gen(tmp_path), "src/agents/default/app/start_server.py")
    assert 'AgentServer("ResponsesAgent")' in content
    # No chat UI is bundled, so the chat proxy would 503 every GET /.
    assert "enable_chat_proxy=True" not in content


def test_readme_local_eval_command_exists(tmp_path):
    readme = read_file(gen(tmp_path), "README.md")
    assert "agent-evaluate" not in readme  # there's no such console script
    assert "uv run --env-file .env python eval/evaluate_agent.py" in readme


@pytest.mark.parametrize("platform,has_check", [("github_actions", True), ("gitlab", False), ("azure_devops", False)])
def test_governance_check_is_only_described_where_it_exists(tmp_path, platform, has_check):
    # Only the GitHub prod CD workflow has a governance_check job.
    p = gen(tmp_path, input_cicd_platform=platform)
    for f in ("AGENTS.md", "README.md"):
        line = next(l for l in read_file(p, f).splitlines() if "**Governance posture**" in l)
        assert ("workflow" in line) == has_check, f"{f}: {line}"


# ---------------------------------------------------------------------------
# Plugin: installer, App-name cap
# ---------------------------------------------------------------------------


def test_generated_readme_points_at_the_plugin_repo(tmp_path):
    # plugin/ isn't part of a generated project, so a relative installer path can't work.
    readme = read_file(gen(tmp_path), "README.md")
    assert "`./plugin/skills/install_skills.sh`" not in readme
    assert "https://github.com/databricks-solutions/agentops-stacks" in readme


@pytest.mark.parametrize("project,ok", [("abcdefghijklmnopqrstuv", True), ("abcdefghijklmnopqrstuvw", False)],
                         ids=["30_chars", "31_chars"])
def test_app_name_cap_is_enforced_at_init(tmp_path, project, ok):
    # The App is <project>-<agent>; Databricks App names are limited to 30 characters.
    params = {"input_project_name": project, "input_root_dir": project}
    if ok:
        gen(tmp_path, **params)
    else:
        with pytest.raises(RuntimeError, match="limited to 30"):
            gen(tmp_path, **params)


def test_validator_rejects_an_app_name_over_30_chars():
    errors, _ = _validate(input_project_name="customer_support_assistant", input_root_dir="customer_support_assistant",
                          input_initial_agent_name="default")
    assert any("customer-support-assistant-default" in e and "30" in e for e in errors)


def test_add_agent_rejects_an_app_name_over_30_chars(tmp_path):
    project = tmp_path / "copy"
    shutil.copytree(gen(tmp_path), project)
    script = Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "plugin/skills/agentops-stacks/scripts/add_agent.py"
    r = subprocess.run([sys.executable, str(script), "--name", "support_bot", "--project-dir", str(project)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "my-agentops-project-support-bot" in r.stdout
    assert not (project / "src/agents/support_bot").exists()


def test_installer_copies_whole_skills_and_commands(tmp_path):
    installer = Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "plugin/skills/install_skills.sh"
    (tmp_path / "databricks.yml").write_text("")  # looks like a project root, so no prompt
    subprocess.run(["bash", str(installer)], cwd=tmp_path, check=True, capture_output=True, text=True,
                   env={**os.environ, "HOME": str(tmp_path)})
    plugin = Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "plugin"
    for skill in ("agentops-stacks", "agentops-bigbook"):
        expected = {f.relative_to(plugin / "skills" / skill) for f in (plugin / "skills" / skill).rglob("*")
                    if f.is_file() and "__pycache__" not in f.parts}
        installed = {f.relative_to(tmp_path / ".claude/skills" / skill)
                     for f in (tmp_path / ".claude/skills" / skill).rglob("*") if f.is_file()}
        assert installed == expected, skill
    commands = {f.name for f in (tmp_path / ".claude/commands").glob("*.md")}
    assert commands == {f.name for f in (plugin / "commands").glob("*.md")}
    assert "add-agent.md" in commands


def test_genie_notebook_installs_the_same_skills_as_the_installer():
    plugin = Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY) / "plugin/skills"
    shell = re.search(r"^SKILL_NAMES=\((.*)\)$", (plugin / "install_skills.sh").read_text(), re.M).group(1)
    notebook = re.search(r"^SKILLS = \[(.*)\]$", (plugin / "install_genie_code_skills.py").read_text(), re.M).group(1)
    names = lambda s: re.findall(r'"([a-z-]+)"', s)
    on_disk = {d.name for d in plugin.iterdir() if (d / "SKILL.md").exists()}
    assert set(names(shell)) == set(names(notebook)) == on_disk
