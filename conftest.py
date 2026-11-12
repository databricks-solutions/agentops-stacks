"""Pytest configuration for agentops-stacks template tests.

The default suite is static: it shells out to the Databricks CLI
(`databricks bundle init`, `databricks bundle schema`) to materialize the
template, then parses, lints, and schema-checks the generated files. Nothing
generated is executed and no real workspace is contacted (auth is stubbed in
utils.generate). It requires the Databricks CLI (>= the schema's
min_databricks_cli_version) on PATH.

tests/integration is excluded from default collection (pytest.ini) and does not
need the CLI.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

INTEGRATION_DIR = Path(__file__).parent / "tests" / "integration"


def pytest_configure(config):
    config.addinivalue_line("markers", "large: slow tests that generate many projects")


def _needs_cli(session):
    """True if any collected test lives outside tests/integration."""
    return any(INTEGRATION_DIR not in Path(item.path).parents for item in session.items)


@pytest.fixture(scope="session", autouse=True)
def require_databricks_cli(request):
    """Fail fast with a clear message if the Databricks CLI is missing."""
    if not _needs_cli(request.session):
        return
    if shutil.which("databricks") is None:
        pytest.exit(
            "Databricks CLI not found on PATH. Install it (see README) before "
            "running the template tests.",
            returncode=1,
        )
    version = subprocess.run(
        ["databricks", "--version"], capture_output=True, text=True
    ).stdout.strip()
    print(f"Using: {version}")


def pytest_addoption(parser):
    parser.addoption(
        "--large",
        action="store_true",
        default=False,
        help="Also run tests marked large (full input matrix).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--large"):
        return
    skip = pytest.mark.skip(reason="large test: pass --large to run")
    for item in items:
        if "large" in item.keywords:
            item.add_marker(skip)
