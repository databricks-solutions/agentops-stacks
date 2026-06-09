"""Tests for generated GitHub Actions workflows.

Validates that workflow YAML files are generated correctly for each
cloud provider and contain the expected structure, triggers, and auth blocks.

Run with: python3 tests/test_github_actions.py
Requires: databricks CLI v1.1.0+ on PATH
"""

import subprocess
import sys
import tempfile
import traceback

from utils import (
    generate,
    read_file,
    read_workflow,
    file_exists,
    paths,
    DEFAULT_PROJECT_NAME,
)

PASSED = 0
FAILED = 0
ERRORS = []


def test(name):
    def decorator(fn):
        global PASSED, FAILED
        try:
            fn()
            PASSED += 1
            print(f"  PASS  {name}")
        except AssertionError as e:
            FAILED += 1
            ERRORS.append((name, str(e)))
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            FAILED += 1
            ERRORS.append((name, traceback.format_exc()))
            print(f"  ERROR {name}: {e}")
        return fn
    return decorator


def gen(**overrides):
    tmpdir = tempfile.mkdtemp()
    return generate(tmpdir, context={"input_cicd_platform": "github_actions", **overrides})


# ============================================================
# Workflow file generation
# ============================================================

def test_workflow_files_generated():
    print("\n=== Workflow files generated ===\n")

    @test("CI workflow exists")
    def _():
        p = gen()
        assert file_exists(p, f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-ci.yml")

    @test("CD staging workflow exists")
    def _():
        p = gen()
        assert file_exists(p, f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-cd-staging.yml")

    @test("CD prod workflow exists")
    def _():
        p = gen()
        assert file_exists(p, f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-cd-prod.yml")

    @test("workflow README exists")
    def _(): assert file_exists(gen(), ".github/workflows/README.md")

    @test("custom project name in workflow filenames")
    def _():
        p = gen(input_project_name="cool_app", input_root_dir="cool_app")
        files = paths(p)
        wf_files = [f for f in files if ".github/workflows" in f and f.endswith(".yml")]
        assert any("cool_app" in f for f in wf_files), f"No cool_app in: {wf_files}"


# ============================================================
# CI workflow content
# ============================================================

def test_ci_workflow_content():
    print("\n=== CI workflow content ===\n")

    @test("CI triggered on pull_request")
    def _():
        content = read_workflow(gen(), "bundle-ci")
        assert "pull_request" in content

    @test("CI has unit_tests job")
    def _():
        content = read_workflow(gen(), "bundle-ci")
        assert "unit_tests" in content

    @test("CI uses uv for dependency management")
    def _():
        content = read_workflow(gen(), "bundle-ci")
        assert "uv" in content

    @test("CI uses actions/checkout")
    def _():
        content = read_workflow(gen(), "bundle-ci")
        assert "actions/checkout" in content


# ============================================================
# CD workflows content
# ============================================================

def test_cd_workflow_content():
    print("\n=== CD workflow content ===\n")

    @test("CD staging deploys on merge to main")
    def _():
        content = read_workflow(gen(), "cd-staging")
        assert "main" in content

    @test("CD prod workflow exists and has deploy step")
    def _():
        content = read_workflow(gen(), "cd-prod")
        assert "deploy" in content.lower() or "bundle" in content.lower()


# ============================================================
# Cloud-specific auth blocks
# ============================================================

def test_cloud_auth_blocks():
    print("\n=== Cloud-specific auth ===\n")

    @test("AWS — uses DATABRICKS_TOKEN")
    def _():
        content = read_workflow(gen(input_cloud="aws"), "bundle-ci")
        assert "DATABRICKS_TOKEN" in content

    @test("Azure — uses ARM_TENANT_ID / ARM_CLIENT_ID")
    def _():
        content = read_workflow(gen(input_cloud="azure"), "bundle-ci")
        assert "ARM_TENANT_ID" in content
        assert "ARM_CLIENT_ID" in content
        assert "ARM_CLIENT_SECRET" in content

    @test("GCP — uses DATABRICKS_TOKEN (same as AWS)")
    def _():
        content = read_workflow(gen(input_cloud="gcp"), "bundle-ci")
        assert "DATABRICKS_TOKEN" in content

    @test("AWS — no Azure ARM vars")
    def _():
        content = read_workflow(gen(input_cloud="aws"), "bundle-ci")
        assert "ARM_TENANT_ID" not in content

    @test("Azure — no DATABRICKS_TOKEN")
    def _():
        content = read_workflow(gen(input_cloud="azure"), "bundle-ci")
        assert "DATABRICKS_TOKEN" not in content


# ============================================================
# Cloud × GHES matrix
# ============================================================

def test_ghes_workflows():
    print("\n=== GitHub Enterprise Server ===\n")

    @test("GHES — generates .github directory")
    def _():
        p = gen(input_cicd_platform="github_actions_for_github_enterprise_servers")
        assert file_exists(p, ".github")

    @test("GHES + AWS — workflow exists")
    def _():
        p = gen(input_cicd_platform="github_actions_for_github_enterprise_servers", input_cloud="aws")
        assert file_exists(p, f".github/workflows/{DEFAULT_PROJECT_NAME}-bundle-ci.yml")

    @test("GHES + Azure — Azure auth block")
    def _():
        p = gen(input_cicd_platform="github_actions_for_github_enterprise_servers", input_cloud="azure")
        content = read_workflow(p, "bundle-ci")
        assert "ARM_TENANT_ID" in content


# ============================================================
# Workflow YAML validity (actionlint if available)
# ============================================================

def test_workflow_yaml_lint():
    print("\n=== Workflow YAML lint ===\n")

    # Check if actionlint is available
    result = subprocess.run(["which", "actionlint"], capture_output=True)
    if result.returncode != 0:
        print("  SKIP  actionlint not installed — skipping YAML lint")
        return

    for cloud in ["aws", "azure", "gcp"]:
        @test(f"actionlint passes — {cloud}")
        def _(c=cloud):
            p = gen(input_cloud=c)
            # actionlint requires a git repo
            subprocess.run(["git", "init"], cwd=str(p), capture_output=True)
            result = subprocess.run(
                ["actionlint"],
                cwd=str(p),
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"actionlint errors:\n{result.stdout}\n{result.stderr}"


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    try:
        result = subprocess.run(["databricks", "--version"], capture_output=True, text=True)
        print(f"Using: {result.stdout.strip()}")
    except FileNotFoundError:
        print("ERROR: databricks CLI not found on PATH")
        sys.exit(1)

    test_workflow_files_generated()
    test_ci_workflow_content()
    test_cd_workflow_content()
    test_cloud_auth_blocks()
    test_ghes_workflows()
    test_workflow_yaml_lint()

    print(f"\n{'=' * 50}")
    print(f"Results: {PASSED} passed, {FAILED} failed")
    if ERRORS:
        print(f"\nFailures:")
        for name, err in ERRORS:
            print(f"  {name}:")
            for line in err.split("\n")[:3]:
                print(f"    {line}")
    print(f"{'=' * 50}")
    sys.exit(1 if FAILED > 0 else 0)
