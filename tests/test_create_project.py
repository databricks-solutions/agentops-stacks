"""Tests for project creation via databricks bundle init.

Verifies correct file generation, template substitution, and conditional
file inclusion across all input combinations.

Run with: python3 tests/test_create_project.py
Requires: databricks CLI v1.1.0+ on PATH
"""

import os
import subprocess
import sys
import traceback
import tempfile

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

PASSED = 0
FAILED = 0
SKIPPED = 0
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


def skip(name, reason):
    global SKIPPED
    SKIPPED += 1
    print(f"  SKIP  {name} — {reason}")


def gen(**overrides):
    """Generate project in a fresh tmpdir with given overrides."""
    tmpdir = tempfile.mkdtemp()
    return generate(tmpdir, context=overrides)


# ============================================================
# No residual Go template strings after substitution
# ============================================================

def test_no_template_strings_after_param_substitution():
    print("\n=== No template strings after substitution ===\n")

    combos = [
        ("defaults", {}),
        ("uc_functions=yes", {"input_use_uc_functions": "yes"}),
        ("uc_existing=yes", {"input_use_uc_functions": "yes", "input_uc_functions_exist": "yes"}),
        ("eval_skipped", {"input_has_eval_dataset": "yes"}),
        ("cloud=azure", {"input_cloud": "azure"}),
        ("cloud=gcp", {"input_cloud": "gcp"}),
        ("cicd=azure_devops", {"input_cicd_platform": "azure_devops"}),
        ("cicd=gitlab", {"input_cicd_platform": "gitlab"}),
    ]

    _has_vs = has_template_file("{{.input_root_dir}}", "resources", "vector_search.yml.tmpl")
    _has_lb = has_template_file("{{.input_root_dir}}", "resources", "lakebase.yml.tmpl")

    if _has_vs:
        combos.append(("vs=yes", {"input_use_vector_search": "yes"}))
        combos.append(("vs+chunked", {"input_use_vector_search": "yes", "input_has_chunked_table": "yes"}))
    if _has_lb:
        combos.append(("lakebase=yes", {"input_use_lakebase": "yes"}))
    if _has_vs and _has_lb:
        combos.append(("all_components", {
            "input_use_vector_search": "yes", "input_use_uc_functions": "yes", "input_use_lakebase": "yes",
        }))

    for label, params in combos:
        @test(f"no Go templates — {label}")
        def _(p=params):
            assert_no_go_templates(gen(**p))


# ============================================================
# No hardcoded workspace URLs in template sources
# ============================================================

def test_no_hardcoded_workspace_urls():
    print("\n=== No hardcoded workspace URLs ===\n")

    @test("no workspace URLs in template source files")
    def _():
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


# ============================================================
# Default project with default values
# ============================================================

def test_generate_project_default_values():
    print("\n=== Default project generation ===\n")
    p = gen()

    @test("project directory created with default name")
    def _(): assert p.exists() and p.name == DEFAULT_PROJECT_DIRECTORY

    @test("databricks.yml exists")
    def _(): assert file_exists(p, "databricks.yml")

    @test("README.md contains project name")
    def _():
        content = read_file(p, "README.md")
        assert DEFAULT_PROJECT_NAME in content

    @test("AGENTS.md exists")
    def _(): assert file_exists(p, "AGENTS.md")

    @test("manifest.yml records project name")
    def _():
        content = read_file(p, ".agentops-stacks/manifest.yml")
        assert DEFAULT_PROJECT_NAME in content

    @test("base resources exist")
    def _():
        for f in ["experiment.yml", "schemas.yml", "volumes.yml"]:
            assert file_exists(p, f"resources/{f}"), f"Missing: resources/{f}"

    @test("docs exist")
    def _():
        assert file_exists(p, "docs/README.md")
        assert file_exists(p, "docs/setup.md")


# ============================================================
# Agent scaffold — names and self-containment
# ============================================================

def test_generate_agent_scaffold():
    print("\n=== Agent scaffold ===\n")

    @test("default agent name creates correct directory")
    def _():
        p = gen()
        assert file_exists(p, "src/agents/default/agent.py")

    @test("custom agent name creates matching directory")
    def _():
        p = gen(input_initial_agent_name="rag_bot")
        for f in ["agent.py", "graph.py", "tools.py"]:
            assert file_exists(p, f"src/agents/rag_bot/{f}"), f"Missing: {f}"

    @test("agent has self-contained runtime files")
    def _():
        p = gen()
        agent = "src/agents/default"
        for f in ["agent.py", "graph.py", "tools.py", "app.yaml",
                   "pyproject.toml", ".env.example",
                   "app/start_server.py", "app/utils.py"]:
            assert file_exists(p, f"{agent}/{f}"), f"Missing: {agent}/{f}"

    @test("agent has eval directory")
    def _():
        p = gen()
        assert file_exists(p, "src/agents/default/eval/evaluate_agent.py")
        assert file_exists(p, "src/agents/default/eval/create_dataset.py")

    @test("agent name appears in databricks.yml app resource")
    def _():
        content = read_file(gen(input_initial_agent_name="my_rag"), "databricks.yml")
        assert "my_rag" in content
        assert "my-rag" in content  # hyphenated app name

    @test("start_server.py uses sys.path, not src.* imports")
    def _():
        content = read_file(gen(), "src/agents/default/app/start_server.py")
        assert "sys.path" in content
        assert "from src." not in content

    @test("start_server.py loads .env from agent dir (parents[1])")
    def _():
        content = read_file(gen(), "src/agents/default/app/start_server.py")
        assert "load_dotenv" in content
        assert "parents[1]" in content

    @test("graph.py imports locally, not from src.*")
    def _():
        content = read_file(gen(), "src/agents/default/graph.py")
        assert "from tools import" in content
        assert "from src." not in content

    @test("app.yaml command is relative to agent folder")
    def _():
        content = read_file(gen(), "src/agents/default/app.yaml")
        assert "app/start_server.py" in content
        assert "src/agents" not in content


# ============================================================
# databricks.yml content
# ============================================================

def test_databricks_yml_content():
    print("\n=== databricks.yml content ===\n")
    p = gen()
    content = read_file(p, "databricks.yml")

    @test("bundle name matches project")
    def _(): assert f"name: {DEFAULT_PROJECT_NAME}" in content

    @test("source_code_path points to agent folder")
    def _(): assert "source_code_path: ./src/agents/default" in content

    @test("app command uses relative path")
    def _(): assert "app/start_server.py" in content

    @test("sync includes agents")
    def _(): assert "src/agents/**" in content

    @test("three targets (dev, staging, prod)")
    def _():
        for t in ["dev:", "staging:", "prod:"]:
            assert t in content

    @test("dev is default target")
    def _(): assert "default: true" in content

    @test("catalog variables use project name suffix per target")
    def _():
        for env in ["dev", "staging", "prod"]:
            assert f"{DEFAULT_PROJECT_NAME}_{env}" in content

    @test("base resource includes")
    def _():
        for r in ["experiment.yml", "schemas.yml", "volumes.yml"]:
            assert f"./resources/{r}" in content

    @test("experiment resource binding")
    def _():
        assert "experiment" in content
        assert "CAN_MANAGE" in content


# ============================================================
# CICD platform selection
# ============================================================

def test_cicd_platform_selection():
    print("\n=== CICD platform selection ===\n")

    cicd_to_dir = {
        "github_actions": (".github", [".azure", ".gitlab"]),
        "github_actions_for_github_enterprise_servers": (".github", [".azure", ".gitlab"]),
        "azure_devops": (".azure", [".github", ".gitlab"]),
        "gitlab": (".gitlab", [".github", ".azure"]),
    }

    for platform, (expected, excluded) in cicd_to_dir.items():
        @test(f"{platform} — includes {expected}, excludes others")
        def _(plat=platform, exp=expected, excl=excluded):
            p = gen(input_cicd_platform=plat)
            assert file_exists(p, exp), f"{exp} should exist"
            for d in excl:
                assert not file_exists(p, d), f"{d} should not exist"

    @test("CICD workflow files contain project name")
    def _():
        p = gen(input_cicd_platform="github_actions")
        files = paths(p)
        github_files = [f for f in files if ".github" in f]
        assert any(DEFAULT_PROJECT_NAME in f for f in github_files)


# ============================================================
# UC Functions conditional output
# ============================================================

def test_uc_functions_output():
    print("\n=== UC Functions output ===\n")

    @test("UC enabled — registry and definitions generated")
    def _():
        p = gen(input_use_uc_functions="yes")
        assert file_exists(p, "src/components/uc_functions/registry.py")
        assert file_exists(p, "src/components/uc_functions/definitions/example_function.sql")

    @test("UC enabled — UCFunctionToolkit in tools.py")
    def _():
        content = read_file(gen(input_use_uc_functions="yes"), "src/agents/default/tools.py")
        assert "UCFunctionToolkit" in content

    @test("UC disabled — no uc_functions folder")
    def _(): assert not file_exists(gen(), "src/components/uc_functions")

    @test("UC disabled — no toolkit in tools.py")
    def _():
        content = read_file(gen(), "src/agents/default/tools.py")
        assert "UCFunctionToolkit" not in content

    @test("UC existing — registry present, definitions skipped")
    def _():
        p = gen(input_use_uc_functions="yes", input_uc_functions_exist="yes")
        assert file_exists(p, "src/components/uc_functions/registry.py")
        assert not file_exists(p, "src/components/uc_functions/definitions")


# ============================================================
# Eval conditional output
# ============================================================

def test_eval_output():
    print("\n=== Eval output ===\n")

    @test("eval dataset included by default")
    def _(): assert file_exists(gen(), "src/agents/default/eval/create_dataset.py")

    @test("eval dataset skipped when has_eval_dataset=yes")
    def _():
        p = gen(input_has_eval_dataset="yes")
        assert not file_exists(p, "src/agents/default/eval/create_dataset.py")

    @test("other eval files remain when dataset skipped")
    def _():
        p = gen(input_has_eval_dataset="yes")
        assert file_exists(p, "src/agents/default/eval/evaluate_agent.py")

    @test("shared eval scorers component exists")
    def _(): assert file_exists(gen(), "src/components/eval/scorers.py")


# ============================================================
# Manifest content
# ============================================================

def test_manifest_content():
    print("\n=== Manifest ===\n")

    @test("records project name")
    def _(): assert DEFAULT_PROJECT_NAME in read_file(gen(), ".agentops-stacks/manifest.yml")

    @test("records agent name")
    def _(): assert "default" in read_file(gen(), ".agentops-stacks/manifest.yml")

    @test("records cloud provider")
    def _(): assert "gcp" in read_file(gen(input_cloud="gcp"), ".agentops-stacks/manifest.yml")

    @test("records UC functions choice")
    def _(): assert "uc_functions: yes" in read_file(gen(input_use_uc_functions="yes"), ".agentops-stacks/manifest.yml")


# ============================================================
# Cloud × CICD matrix — all combinations generate cleanly
# ============================================================

def test_cloud_cicd_matrix():
    print("\n=== Cloud × CICD matrix ===\n")

    for platform in ["github_actions", "azure_devops", "gitlab"]:
        for cloud in ["aws", "azure", "gcp"]:
            @test(f"{platform} + {cloud}")
            def _(p=platform, c=cloud):
                proj = gen(input_cicd_platform=p, input_cloud=c)
                assert proj.exists()
                assert file_exists(proj, "databricks.yml")
                assert_no_go_templates(proj)


# ============================================================
# Component combinations
# ============================================================

def test_component_combinations():
    print("\n=== Component combinations ===\n")

    _has_vs = has_template_file("{{.input_root_dir}}", "resources", "vector_search.yml.tmpl")
    _has_lb = has_template_file("{{.input_root_dir}}", "resources", "lakebase.yml.tmpl")

    combos = [
        ("all off", {}),
        ("UC only", {"input_use_uc_functions": "yes"}),
        ("UC + eval skip", {"input_use_uc_functions": "yes", "input_has_eval_dataset": "yes"}),
        ("UC existing", {"input_use_uc_functions": "yes", "input_uc_functions_exist": "yes"}),
    ]

    if _has_vs:
        combos += [
            ("VS only", {"input_use_vector_search": "yes"}),
            ("VS + chunked", {"input_use_vector_search": "yes", "input_has_chunked_table": "yes"}),
            ("VS + UC", {"input_use_vector_search": "yes", "input_use_uc_functions": "yes"}),
        ]
    else:
        skip("VS combinations", "VS template files not on this branch")

    if _has_lb:
        combos.append(("Lakebase only", {"input_use_lakebase": "yes"}))
    else:
        skip("Lakebase combinations", "Lakebase template files not on this branch")

    if _has_vs and _has_lb:
        combos.append(("all components", {
            "input_use_vector_search": "yes",
            "input_use_uc_functions": "yes",
            "input_use_lakebase": "yes",
        }))

    for label, params in combos:
        @test(f"{label}")
        def _(p=params):
            proj = gen(**p)
            assert proj.exists()
            assert_no_go_templates(proj)

    @test("no components — no component files in output")
    def _():
        files = paths(gen())
        assert not any("retriever" in f for f in files)
        assert not any("uc_functions" in f for f in files)
        assert not any("lakebase" in f for f in files)


# ============================================================
# Invalid params should fail gracefully
# ============================================================

def test_generate_fails_with_invalid_params():
    print("\n=== Invalid params ===\n")

    invalid_cases = [
        ("project name too short", {"input_project_name": "ab", "input_root_dir": "ab"}),
        ("project name with uppercase", {"input_project_name": "MyProject", "input_root_dir": "MyProject"}),
        ("project name starts with digit", {"input_project_name": "1bad", "input_root_dir": "1bad"}),
        ("agent name too short", {"input_initial_agent_name": "ab"}),
    ]

    for label, params in invalid_cases:
        @test(f"rejects: {label}")
        def _(p=params):
            try:
                gen(**p)
                assert False, "Expected generation to fail"
            except RuntimeError:
                pass  # expected


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

    test_no_template_strings_after_param_substitution()
    test_no_hardcoded_workspace_urls()
    test_generate_project_default_values()
    test_generate_agent_scaffold()
    test_databricks_yml_content()
    test_cicd_platform_selection()
    test_uc_functions_output()
    test_eval_output()
    test_manifest_content()
    test_cloud_cicd_matrix()
    test_component_combinations()
    test_generate_fails_with_invalid_params()

    print(f"\n{'=' * 50}")
    print(f"Results: {PASSED} passed, {FAILED} failed, {SKIPPED} skipped")
    if ERRORS:
        print(f"\nFailures:")
        for name, err in ERRORS:
            print(f"  {name}:")
            for line in err.split("\n")[:3]:
                print(f"    {line}")
    print(f"{'=' * 50}")
    sys.exit(1 if FAILED > 0 else 0)
