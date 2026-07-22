"""Pytest configuration for agentops-stacks template tests.

The suite shells out to the Databricks CLI (`databricks bundle init`) to
materialize the template, then asserts on the generated file tree and content.
It requires the Databricks CLI (>= the schema's min_databricks_cli_version) on
PATH and does not contact any real workspace (auth is stubbed in utils.generate).
"""

import shutil
import subprocess

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "large: slow tests that generate many projects")


@pytest.fixture(scope="session", autouse=True)
def require_databricks_cli():
    """Fail fast with a clear message if the Databricks CLI is missing."""
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
