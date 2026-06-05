"""Shared test utilities for agentops-stacks template tests.

Mirrors the structure of databricks/mlops-stacks/tests/utils.py.
No external dependencies beyond stdlib.
"""

import json
import os
import pathlib
import re
import subprocess
import tempfile

RESOURCE_TEMPLATE_ROOT_DIRECTORY = str(pathlib.Path(__file__).parent.parent)

DEFAULT_PROJECT_NAME = "my_agentops_project"
DEFAULT_PROJECT_DIRECTORY = "my_agentops_project"

# Default params that satisfy all required template inputs
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
    "input_use_genie": "no",
    "input_genie_space_id": "",
    "input_use_local_tools": "no",
    "input_use_uc_functions": "no",
    "input_uc_functions_exist": "no",
    "input_has_eval_dataset": "no",
    "input_eval_scorers": "relevance,groundedness,safety",
}

# Cache to avoid regenerating for same param set
_cache = {}


def generate(directory, context=None):
    """Run databricks bundle init with the given context.

    Returns the path to the generated project directory.
    """
    params = {**DEFAULT_PARAMS, **(context or {})}

    key = tuple(sorted(params.items()))
    if key in _cache:
        return _cache[key]

    config_file = os.path.join(str(directory), "config.json")
    with open(config_file, "w") as f:
        json.dump(params, f)

    result = subprocess.run(
        [
            "databricks", "bundle", "init",
            RESOURCE_TEMPLATE_ROOT_DIRECTORY,
            "--config-file", config_file,
            "--output-dir", str(directory),
        ],
        capture_output=True, text=True,
        env={**os.environ, "DATABRICKS_HOST": "https://stub", "DATABRICKS_TOKEN": "stub"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"databricks bundle init failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    project = pathlib.Path(str(directory)) / params["input_root_dir"]
    _cache[key] = project
    return project


def paths(directory):
    """Return all file paths relative to directory as a set of strings."""
    all_paths = list(pathlib.Path(directory).rglob("*"))
    return {str(f.relative_to(directory)) for f in all_paths if f.is_file()}


def read_file(project_dir, path):
    """Read a file from the generated project."""
    return (pathlib.Path(project_dir) / path).read_text()


def file_exists(project_dir, path):
    """Check if a path exists in the generated project."""
    return (pathlib.Path(project_dir) / path).exists()


def has_template_file(*path_parts):
    """Check if a template file exists in the repo (for conditional test skipping)."""
    return pathlib.Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY, "template", *path_parts).exists()


def assert_no_disallowed_strings_in_files(
    file_paths, disallowed_strings, exclude_path_matches=None
):
    """Assert that files do not contain any of the specified disallowed strings.

    :param file_paths: List of absolute file paths to check
    :param disallowed_strings: List of strings that should not appear
    :param exclude_path_matches: List of substrings — files with paths containing
        one of these are skipped
    """
    if exclude_path_matches is None:
        exclude_path_matches = []
    exclude_path_matches = exclude_path_matches + [".png", ".parquet", ".tar.gz", ".lock"]

    for path in file_paths:
        assert os.path.exists(path), f"Provided nonexistent path to test: {path}"

    def should_check(filepath):
        return (
            not any(sub in filepath for sub in exclude_path_matches)
            and os.path.isfile(filepath)
        )

    for path in filter(should_check, file_paths):
        with open(path, "r", errors="ignore") as f:
            data = f.read()
        for s in disallowed_strings:
            assert s not in data, f"Disallowed string '{s}' found in {path}"


def assert_no_go_templates(project_dir):
    """Assert no Go template directives remain in generated files.

    Looks for '{{ .' / '{{ if' / '{{ end' patterns — not bare {{ }}
    which appear in Python dicts, JSON, and GitHub Actions ${{ }}.
    """
    go_tmpl_re = re.compile(r'\{\{\s*[\.\$a-z]', re.IGNORECASE)
    skip_ext = [".png", ".parquet", ".lock", ".yml", ".yaml"]

    for filepath in paths(project_dir):
        if any(pat in filepath for pat in skip_ext):
            continue
        full_path = pathlib.Path(project_dir) / filepath
        content = full_path.read_text(errors="ignore")
        match = go_tmpl_re.search(content)
        assert match is None, (
            f"Go template string in {filepath}: "
            f"...{content[max(0, match.start()-20):match.end()+30]}..."
        )


def read_workflow(project_dir, workflow_name=None):
    """Read a GitHub Actions workflow file. If workflow_name is None, returns all."""
    workflow_dir = pathlib.Path(project_dir) / ".github" / "workflows"
    if not workflow_dir.exists():
        return ""
    if workflow_name:
        matches = list(workflow_dir.glob(f"*{workflow_name}*"))
        assert len(matches) > 0, f"No workflow matching '{workflow_name}' in {workflow_dir}"
        return matches[0].read_text()
    return {f.name: f.read_text() for f in workflow_dir.glob("*.yml")}
