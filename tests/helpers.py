"""Shared test helpers for agentops-stacks template tests.

Provides generate(), file inspection, and assertion utilities.
No external dependencies — stdlib only.
"""

import json
import os
import pathlib
import re
import subprocess
import tempfile

TEMPLATE_ROOT = str(pathlib.Path(__file__).parent.parent)

# Default params that satisfy all required inputs
BASE_PARAMS = {
    "input_project_name": "test_project",
    "input_root_dir": "test_project",
    "input_initial_agent_name": "test_agent",
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

# Cache to avoid re-generating for same params
_cache = {}


def generate(**overrides):
    """Run databricks bundle init with given overrides. Cached per param set."""
    key = tuple(sorted(overrides.items()))
    if key in _cache:
        return _cache[key]

    params = {**BASE_PARAMS, **overrides}
    tmpdir = tempfile.mkdtemp()
    config_file = os.path.join(tmpdir, "config.json")
    with open(config_file, "w") as f:
        json.dump(params, f)

    result = subprocess.run(
        ["databricks", "bundle", "init", TEMPLATE_ROOT,
         "--config-file", config_file, "--output-dir", tmpdir],
        capture_output=True, text=True,
        env={**os.environ, "DATABRICKS_HOST": "https://stub", "DATABRICKS_TOKEN": "stub"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"bundle init failed:\n{result.stderr}")

    project = pathlib.Path(tmpdir) / params["input_root_dir"]
    _cache[key] = project
    return project


def exists(project, path):
    """Check if a path exists in the generated project."""
    return (pathlib.Path(project) / path).exists()


def read(project, path):
    """Read a file from the generated project."""
    return (pathlib.Path(project) / path).read_text()


def all_files(project):
    """Return set of all file paths relative to project root."""
    return {str(p.relative_to(project)) for p in pathlib.Path(project).rglob("*") if p.is_file()}


def assert_no_go_templates(project):
    """Assert no Go template directives remain in generated files.

    Uses regex to find '{{ .', '{{ if', '{{ end', '{{ skip', etc.
    Ignores CICD YAML files (${{ }} is GitHub Actions / GitLab syntax).
    """
    go_tmpl_re = re.compile(r'\{\{\s*[\.\$a-z]', re.IGNORECASE)
    skip_ext = [".png", ".parquet", ".lock", ".yml", ".yaml"]

    for filepath in all_files(project):
        if any(pat in filepath for pat in skip_ext):
            continue
        content = (pathlib.Path(project) / filepath).read_text(errors="ignore")
        match = go_tmpl_re.search(content)
        assert match is None, (
            f"Go template in {filepath}: "
            f"...{content[max(0, match.start()-20):match.end()+30]}..."
        )


def has_template_file(*path_parts):
    """Check if a template file exists in the repo (for conditional test skipping)."""
    return pathlib.Path(TEMPLATE_ROOT, "template", *path_parts).exists()
