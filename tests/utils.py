"""Shared test utilities for agentops-stacks template tests.

Mirrors the structure of databricks/mlops-stacks/tests/utils.py.
No external dependencies beyond stdlib + the Databricks CLI on PATH.
"""

import ast
import itertools
import json
import os
import pathlib
import re
import subprocess

from pyflakes import checker as pyflakes_checker

RESOURCE_TEMPLATE_ROOT_DIRECTORY = str(pathlib.Path(__file__).parent.parent)

DEFAULT_PROJECT_NAME = "my_agentops_project"
DEFAULT_PROJECT_DIRECTORY = "my_agentops_project"

# Default params satisfying every required template input in
# databricks_template_schema.json. Keep in sync with that schema.
DEFAULT_PARAMS = {
    "input_project_name": DEFAULT_PROJECT_NAME,
    "input_root_dir": DEFAULT_PROJECT_DIRECTORY,
    "input_initial_agent_name": "default",
    "input_cloud": "aws",
    "input_cicd_platform": "github_actions",
    "input_use_vector_search": "no",
    "input_has_chunked_table": "no",
    "input_use_lakebase": "no",
    "input_memory_type": "short_term",
    "input_use_uc_functions": "no",
    "input_uc_functions_exist": "no",
    "input_enable_cost_tags": "yes",
    "input_usage_policy_id": "",
    "input_eval_dataset_source": "synthetic",
}

# Cache generated projects so identical param sets aren't regenerated.
_cache = {}


def generate(directory, context=None):
    """Run `databricks bundle init` with the given context.

    Returns the pathlib.Path of the generated project directory. Raises
    RuntimeError if bundle init fails (used to assert invalid inputs are
    rejected).
    """
    params = {**DEFAULT_PARAMS, **(context or {})}

    key = tuple(sorted(params.items()))
    if key in _cache:
        return _cache[key]

    os.makedirs(str(directory), exist_ok=True)
    config_file = os.path.join(str(directory), "config.json")
    with open(config_file, "w") as f:
        json.dump(params, f)

    result = subprocess.run(
        [
            "databricks",
            "bundle",
            "init",
            RESOURCE_TEMPLATE_ROOT_DIRECTORY,
            "--config-file",
            config_file,
            "--output-dir",
            str(directory),
        ],
        capture_output=True,
        text=True,
        # Stub auth so the CLI never contacts a real workspace during tests.
        env={
            **os.environ,
            "DATABRICKS_HOST": "https://stub",
            "DATABRICKS_TOKEN": "stub",
        },
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"databricks bundle init failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    project = pathlib.Path(str(directory)) / params["input_root_dir"]
    _cache[key] = project
    return project


def paths(directory):
    """Return every file path under directory, relative, as a set of strings."""
    all_paths = list(pathlib.Path(directory).rglob("*"))
    return {str(f.relative_to(directory)) for f in all_paths if f.is_file()}


def read_file(project_dir, path):
    return (pathlib.Path(project_dir) / path).read_text()


def file_exists(project_dir, path):
    return (pathlib.Path(project_dir) / path).exists()


def has_template_file(*path_parts):
    """True if a template source file exists in the repo (for conditional skips)."""
    return pathlib.Path(
        RESOURCE_TEMPLATE_ROOT_DIRECTORY, "template", *path_parts
    ).exists()


def assert_no_disallowed_strings_in_files(
    file_paths, disallowed_strings, exclude_path_matches=None
):
    """Assert none of the files contain any of the disallowed strings."""
    if exclude_path_matches is None:
        exclude_path_matches = []
    exclude_path_matches = exclude_path_matches + [
        ".png",
        ".parquet",
        ".tar.gz",
        ".lock",
    ]

    def should_check(filepath):
        return not any(
            sub in filepath for sub in exclude_path_matches
        ) and os.path.isfile(filepath)

    for path in filter(should_check, file_paths):
        with open(path, "r", errors="ignore") as f:
            data = f.read()
        for s in disallowed_strings:
            assert s not in data, f"Disallowed string '{s}' found in {path}"


def assert_no_go_templates(project_dir):
    """Assert no Go template directives remain in generated files.

    Matches `{{ .` / `{{ if` / `{{ end` etc. (a `{{` immediately followed by a
    dot, dollar, or letter) — not bare `{{ }}` which legitimately appears in
    JSON and Python dicts, and not `${{ }}` CI expressions. YAML is checked too.
    """
    # `${{ ... }}` (GitHub Actions / Azure DevOps expressions) is legitimate in
    # generated CI files, so a `{{` preceded by `$` is not a Go directive.
    go_tmpl_re = re.compile(r"(?<!\$)\{\{\s*[\.\$a-z]", re.IGNORECASE)
    skip_ext = [".png", ".parquet", ".lock"]

    for filepath in paths(project_dir):
        if any(pat in filepath for pat in skip_ext):
            continue
        content = (pathlib.Path(project_dir) / filepath).read_text(errors="ignore")
        match = go_tmpl_re.search(content)
        assert match is None, (
            f"Go template string in {filepath}: "
            f"...{content[max(0, match.start() - 20):match.end() + 30]}..."
        )


def read_workflow(project_dir, workflow_name=None):
    """Read generated GitHub Actions workflow(s)."""
    workflow_dir = pathlib.Path(project_dir) / ".github" / "workflows"
    if not workflow_dir.exists():
        return "" if workflow_name else {}
    if workflow_name:
        matches = list(workflow_dir.glob(f"*{workflow_name}*"))
        assert matches, f"No workflow matching '{workflow_name}' in {workflow_dir}"
        return matches[0].read_text()
    return {f.name: f.read_text() for f in workflow_dir.glob("*.yml")}


# ---------------------------------------------------------------------------
# Generation matrix (mirrors mlops-stacks' parametrize_by_project_generation_params)
# ---------------------------------------------------------------------------

# Inputs that change generated code. Each level is the set of params it sets.
VECTOR_SEARCH_LEVELS = [
    {"input_use_vector_search": "no"},
    {"input_use_vector_search": "yes", "input_has_chunked_table": "no"},
    {"input_use_vector_search": "yes", "input_has_chunked_table": "yes"},
]
LAKEBASE_LEVELS = [
    {"input_use_lakebase": "no"},
    {"input_use_lakebase": "yes", "input_memory_type": "short_term"},
    {"input_use_lakebase": "yes", "input_memory_type": "long_term"},
    {"input_use_lakebase": "yes", "input_memory_type": "both"},
]
UC_FUNCTION_LEVELS = [
    {"input_use_uc_functions": "no"},
    {"input_use_uc_functions": "yes", "input_uc_functions_exist": "no"},
    {"input_use_uc_functions": "yes", "input_uc_functions_exist": "yes"},
]
EVAL_SOURCE_LEVELS = [
    {"input_eval_dataset_source": v}
    for v in ["synthetic", "manual", "production_traces", "existing"]
]
EXAMPLE_USAGE_POLICY_ID = "1a2b3c4d-1234-5678-9abc-0123456789ab"
COST_TAG_LEVELS = [
    {"input_enable_cost_tags": "no"},
    {"input_enable_cost_tags": "yes", "input_usage_policy_id": ""},
    {"input_enable_cost_tags": "yes", "input_usage_policy_id": EXAMPLE_USAGE_POLICY_ID},
]
CODE_FACTORS = [
    VECTOR_SEARCH_LEVELS,
    LAKEBASE_LEVELS,
    UC_FUNCTION_LEVELS,
    COST_TAG_LEVELS,
    EVAL_SOURCE_LEVELS,
]

CLOUDS = ["aws", "azure", "gcp"]
CICD_PLATFORMS = [
    "github_actions",
    "github_actions_for_github_enterprise_servers",
    "azure_devops",
    "gitlab",
]


def _label(params):
    return "-".join(f"{k.removeprefix('input_')}={v}" for k, v in params.items())


def _pairs(levels):
    """Every (factor, level) pair a row of level indexes covers."""
    return {
        ((i, a), (j, b))
        for i, a in enumerate(levels)
        for j, b in enumerate(levels)
        if i < j
    }


def _pairwise_rows():
    """Deterministic greedy pairwise cover over CODE_FACTORS.

    Repeatedly takes the first row of the full product that covers the most
    still-uncovered level pairs, until every pair of levels across any two
    factors appears in at least one row.
    """
    product = list(itertools.product(*(range(len(f)) for f in CODE_FACTORS)))
    uncovered = set().union(*(_pairs(row) for row in product))
    rows = []
    while uncovered:
        best = max(product, key=lambda row: len(_pairs(row) & uncovered))
        rows.append(best)
        uncovered -= _pairs(best)
    return rows


def code_combinations(full=False):
    """Combinations of the code-affecting inputs as (id, params) pairs.

    full=False returns a pairwise covering set (see _pairwise_rows). Odd rows
    use a non-default agent name to catch a hardcoded "default".
    full=True returns the full product of CODE_FACTORS.
    """
    if full:
        indexes = list(itertools.product(*(range(len(f)) for f in CODE_FACTORS)))
    else:
        indexes = _pairwise_rows()
    rows = []
    for n, idx in enumerate(indexes):
        row = {}
        for factor, i in zip(CODE_FACTORS, idx):
            row.update(factor[i])
        if not full and n % 2:
            row["input_initial_agent_name"] = "support_bot"
        rows.append(row)
    return [(_label(r), r) for r in rows]


def cicd_combinations():
    """Every cloud x CI/CD platform pair, at default component settings."""
    return [
        (f"{p}-{c}", {"input_cicd_platform": p, "input_cloud": c})
        for p in CICD_PLATFORMS
        for c in CLOUDS
    ]


def assert_no_missing_template_values(project_dir):
    """Go's text/template renders a missing key as `<no value>`."""
    for filepath in paths(project_dir):
        content = (pathlib.Path(project_dir) / filepath).read_text(errors="ignore")
        assert "<no value>" not in content, f"'<no value>' rendered in {filepath}"


# ---------------------------------------------------------------------------
# Static Python checks (shared by generated-code and plugin tests)
# ---------------------------------------------------------------------------

NOTEBOOK_HEADER = "# Databricks notebook source"
NOTEBOOK_GLOBALS = {"spark", "dbutils", "display", "displayHTML"}
AGENT_DIR_RE = re.compile(r"^src/agents/[^/]+/")


def normalize(relpath):
    return AGENT_DIR_RE.sub("src/agents/<agent>/", relpath)


def is_notebook(source):
    return source.startswith(NOTEBOOK_HEADER)


def pyflakes_messages(relpath, source):
    """pyflakes findings, honoring `# noqa` on the reported line like flake8 does."""
    tree = ast.parse(source, filename=relpath)
    w = pyflakes_checker.Checker(tree, filename=relpath, builtins=NOTEBOOK_GLOBALS)
    lines = source.splitlines()
    return {
        f"{normalize(relpath)}: {m.message % m.message_args}"
        for m in w.messages
        if "# noqa" not in lines[m.lineno - 1]
    }


def docstring_violations(relpath, source):
    """Missing docstrings: module (non-notebooks), public classes, functions, methods."""
    tree = ast.parse(source, filename=relpath)
    name = normalize(relpath)
    found = set()
    if not is_notebook(source) and not ast.get_docstring(tree):
        found.add(f"{name}: module")

    def visit(nodes, prefix=""):
        for node in nodes:
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if node.name.startswith("_"):
                continue
            qual = f"{prefix}{node.name}"
            if not ast.get_docstring(node):
                found.add(f"{name}: {qual}")
            if isinstance(node, ast.ClassDef):
                visit(node.body, prefix=f"{qual}.")

    visit(tree.body)
    return found
