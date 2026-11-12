"""Integration tests for the generated scripts/enable_usage_policy.py.

These run the generated script, so they are excluded from the default pytest
run (see `norecursedirs` in pytest.ini). They need the Databricks CLI on PATH
to generate the project. Run them explicitly:

    pytest tests/integration
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import generate, read_file  # noqa: E402

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


@pytest.fixture(autouse=True, scope="module")
def require_databricks_cli():
    if shutil.which("databricks") is None:
        pytest.fail("Databricks CLI not found on PATH; these tests generate a project.")


def gen(tmp_path, **overrides):
    """Generate a project in a per-test tmp dir with the given overrides."""
    return generate(tmp_path, context=overrides)


def _live_policy_lines(content):
    return [l for l in content.splitlines() if l.strip() == LIVE_POLICY_LINE]


def _wire(tmp_path, *args):
    """Copy a tags-on, blank-policy project (generated projects are cached) and run the wiring script."""
    project = tmp_path / "wired"
    shutil.copytree(gen(tmp_path, **ALL_COMPONENTS), project)
    result = subprocess.run(
        [sys.executable, "scripts/enable_usage_policy.py", *args],
        cwd=project,
        capture_output=True,
        text=True,
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


@pytest.mark.parametrize(
    "args", [["dev=not-a-uuid"], [f"qa={POLICY_ID}"]], ids=["bad_id", "unknown_target"]
)
def test_enable_usage_policy_rejects_bad_input(tmp_path, args):
    _, result = _wire(tmp_path, *args)
    assert result.returncode != 0
