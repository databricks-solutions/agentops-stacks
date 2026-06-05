"""General template generation tests — all input combinations.

Verifies that databricks bundle init produces the correct files for every
combination of inputs. Feature-specific code tests live in their own
feature-tests branches.

Run with: python3 tests/run_general_tests.py
Requires: databricks CLI v1.1.0+ on PATH
"""

import subprocess
import sys
import traceback

from helpers import (
    generate, exists, read, all_files, assert_no_go_templates, has_template_file,
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


# ============================================================
# 1. Default generation — all defaults
# ============================================================

def test_defaults():
    print("\n=== 1. Default generation ===\n")
    p = generate()

    @test("project directory exists")
    def _(): assert p.exists()

    @test("databricks.yml exists")
    def _(): assert exists(p, "databricks.yml")

    @test("README.md exists")
    def _(): assert exists(p, "README.md")

    @test("AGENTS.md exists")
    def _(): assert exists(p, "AGENTS.md")

    @test("manifest.yml exists")
    def _(): assert exists(p, ".agentops-stacks/manifest.yml")

    @test("base resources exist")
    def _():
        for f in ["experiment.yml", "schemas.yml", "volumes.yml"]:
            assert exists(p, f"resources/{f}"), f"Missing: resources/{f}"

    @test("docs exist")
    def _():
        assert exists(p, "docs/README.md")
        assert exists(p, "docs/setup.md")

    @test("no Go template strings in output")
    def _(): assert_no_go_templates(p)


# ============================================================
# 2. Agent scaffold — names and structure
# ============================================================

def test_agent_scaffold():
    print("\n=== 2. Agent scaffold ===\n")

    @test("default agent name — test_agent directory")
    def _():
        p = generate()
        assert exists(p, "src/agents/test_agent")

    @test("custom agent name — creates matching directory")
    def _():
        p = generate(input_initial_agent_name="rag_bot")
        assert exists(p, "src/agents/rag_bot")
        assert exists(p, "src/agents/rag_bot/agent.py")
        assert exists(p, "src/agents/rag_bot/graph.py")
        assert exists(p, "src/agents/rag_bot/tools.py")

    @test("agent has app entry point")
    def _():
        p = generate()
        assert exists(p, "src/agents/test_agent/app/start_server.py")
        assert exists(p, "src/agents/test_agent/app/utils.py")

    @test("agent has pyproject.toml")
    def _(): assert exists(generate(), "src/agents/test_agent/pyproject.toml")

    @test("agent has app.yaml")
    def _(): assert exists(generate(), "src/agents/test_agent/app.yaml")

    @test("agent has .env.example")
    def _(): assert exists(generate(), "src/agents/test_agent/.env.example")

    @test("agent has eval directory")
    def _():
        p = generate()
        assert exists(p, "src/agents/test_agent/eval/evaluate_agent.py")
        assert exists(p, "src/agents/test_agent/eval/create_dataset.py")

    @test("custom agent name in databricks.yml")
    def _():
        content = read(generate(input_initial_agent_name="my_rag"), "databricks.yml")
        assert "my_rag" in content
        assert "my-rag" in content  # hyphenated app name

    @test("custom project name in databricks.yml")
    def _():
        p = generate(input_project_name="cool_project", input_root_dir="cool_project")
        content = read(p, "databricks.yml")
        assert "cool_project" in content or "cool-project" in content

    @test("custom agent — no Go templates")
    def _(): assert_no_go_templates(generate(input_initial_agent_name="custom_bot"))


# ============================================================
# 3. CICD platform selection
# ============================================================

def test_cicd():
    print("\n=== 3. CICD platform ===\n")

    @test("github_actions — .github only")
    def _():
        p = generate(input_cicd_platform="github_actions")
        assert exists(p, ".github")
        assert not exists(p, ".azure")
        assert not exists(p, ".gitlab")

    @test("github_actions_for_github_enterprise_servers — .github only")
    def _():
        p = generate(input_cicd_platform="github_actions_for_github_enterprise_servers")
        assert exists(p, ".github")
        assert not exists(p, ".azure")
        assert not exists(p, ".gitlab")

    @test("azure_devops — .azure only")
    def _():
        p = generate(input_cicd_platform="azure_devops")
        assert exists(p, ".azure")
        assert not exists(p, ".github")
        assert not exists(p, ".gitlab")

    @test("gitlab — .gitlab only")
    def _():
        p = generate(input_cicd_platform="gitlab")
        assert exists(p, ".gitlab")
        assert not exists(p, ".github")
        assert not exists(p, ".azure")

    @test("CICD files use project name")
    def _():
        p = generate(input_cicd_platform="github_actions")
        files = all_files(p)
        github_files = [f for f in files if ".github" in f]
        assert any("test_project" in f for f in github_files), f"No project name in: {github_files}"


# ============================================================
# 4. databricks.yml content
# ============================================================

def test_databricks_yml():
    print("\n=== 4. databricks.yml content ===\n")

    @test("bundle name matches project")
    def _():
        content = read(generate(), "databricks.yml")
        assert "name: test_project" in content

    @test("app source_code_path points to agent folder")
    def _():
        content = read(generate(), "databricks.yml")
        assert "source_code_path: ./src/agents/test_agent" in content

    @test("app command uses relative path")
    def _():
        content = read(generate(), "databricks.yml")
        assert "app/start_server.py" in content

    @test("sync includes agents")
    def _():
        content = read(generate(), "databricks.yml")
        assert "src/agents/**" in content

    @test("three targets defined")
    def _():
        content = read(generate(), "databricks.yml")
        for target in ["dev:", "staging:", "prod:"]:
            assert target in content, f"Missing target: {target}"

    @test("dev is default target")
    def _():
        content = read(generate(), "databricks.yml")
        assert "default: true" in content

    @test("catalog variables use project name suffix")
    def _():
        content = read(generate(), "databricks.yml")
        assert "test_project_dev" in content
        assert "test_project_staging" in content
        assert "test_project_prod" in content

    @test("experiment resource binding")
    def _():
        content = read(generate(), "databricks.yml")
        assert "experiment" in content
        assert "CAN_MANAGE" in content


# ============================================================
# 5. UC Functions component
# ============================================================

def test_uc_functions():
    print("\n=== 5. UC Functions ===\n")

    @test("UC enabled — registry and definitions exist")
    def _():
        p = generate(input_use_uc_functions="yes")
        assert exists(p, "src/components/uc_functions/registry.py")
        assert exists(p, "src/components/uc_functions/definitions/example_function.sql")

    @test("UC enabled — toolkit in tools.py")
    def _():
        content = read(generate(input_use_uc_functions="yes"), "src/agents/test_agent/tools.py")
        assert "UCFunctionToolkit" in content
        assert "UC_FUNCTION_NAMES" in content

    @test("UC disabled — no uc_functions folder")
    def _():
        p = generate(input_use_uc_functions="no")
        assert not exists(p, "src/components/uc_functions")

    @test("UC disabled — no toolkit in tools.py")
    def _():
        content = read(generate(input_use_uc_functions="no"), "src/agents/test_agent/tools.py")
        assert "UCFunctionToolkit" not in content

    @test("UC existing — registry exists, definitions skipped")
    def _():
        p = generate(input_use_uc_functions="yes", input_uc_functions_exist="yes")
        assert exists(p, "src/components/uc_functions/registry.py")
        assert not exists(p, "src/components/uc_functions/definitions")

    @test("UC enabled — no Go templates")
    def _(): assert_no_go_templates(generate(input_use_uc_functions="yes"))

    @test("UC existing — no Go templates")
    def _(): assert_no_go_templates(generate(input_use_uc_functions="yes", input_uc_functions_exist="yes"))


# ============================================================
# 6. Eval dataset
# ============================================================

def test_eval():
    print("\n=== 6. Eval dataset ===\n")

    @test("eval dataset included by default")
    def _():
        assert exists(generate(), "src/agents/test_agent/eval/create_dataset.py")

    @test("eval dataset skipped when existing")
    def _():
        p = generate(input_has_eval_dataset="yes")
        assert not exists(p, "src/agents/test_agent/eval/create_dataset.py")

    @test("eval dataset skipped — other eval files remain")
    def _():
        p = generate(input_has_eval_dataset="yes")
        assert exists(p, "src/agents/test_agent/eval/evaluate_agent.py")

    @test("shared eval scorers exist")
    def _():
        assert exists(generate(), "src/components/eval/scorers.py")


# ============================================================
# 7. Agent self-containment
# ============================================================

def test_self_contained():
    print("\n=== 7. Agent self-containment ===\n")

    @test("agent folder has all runtime files")
    def _():
        p = generate()
        agent = "src/agents/test_agent"
        for f in ["agent.py", "graph.py", "tools.py", "app.yaml", "pyproject.toml",
                   ".env.example", "app/start_server.py", "app/utils.py"]:
            assert exists(p, f"{agent}/{f}"), f"Missing: {agent}/{f}"

    @test("start_server.py adds agent dir to sys.path")
    def _():
        content = read(generate(), "src/agents/test_agent/app/start_server.py")
        assert "sys.path" in content

    @test("start_server.py loads .env from agent folder")
    def _():
        content = read(generate(), "src/agents/test_agent/app/start_server.py")
        assert "load_dotenv" in content
        # Should reference parents[1] (agent dir), not parents[3] (project root)
        assert "parents[1]" in content

    @test("graph.py imports from local, not src.*")
    def _():
        content = read(generate(), "src/agents/test_agent/graph.py")
        assert "from tools import" in content
        assert "from src." not in content

    @test("app.yaml command is relative to agent folder")
    def _():
        content = read(generate(), "src/agents/test_agent/app.yaml")
        assert "app/start_server.py" in content
        assert "src/agents" not in content


# ============================================================
# 8. Manifest
# ============================================================

def test_manifest():
    print("\n=== 8. Manifest ===\n")

    @test("manifest records project name")
    def _():
        content = read(generate(), ".agentops-stacks/manifest.yml")
        assert "test_project" in content

    @test("manifest records agent name")
    def _():
        content = read(generate(), ".agentops-stacks/manifest.yml")
        assert "test_agent" in content

    @test("manifest records cloud")
    def _():
        content = read(generate(input_cloud="gcp"), ".agentops-stacks/manifest.yml")
        assert "gcp" in content

    @test("manifest records component choices")
    def _():
        content = read(generate(input_use_uc_functions="yes"), ".agentops-stacks/manifest.yml")
        assert "uc_functions: yes" in content


# ============================================================
# 9. Cloud variations
# ============================================================

def test_clouds():
    print("\n=== 9. Cloud variations ===\n")

    for cloud in ["aws", "azure", "gcp"]:
        @test(f"{cloud} — generates successfully")
        def _(c=cloud):
            p = generate(input_cloud=c)
            assert p.exists()
            assert exists(p, "databricks.yml")

        @test(f"{cloud} — no Go templates")
        def _(c=cloud):
            assert_no_go_templates(generate(input_cloud=c))


# ============================================================
# 10. Combined component permutations
# ============================================================

def test_combinations():
    print("\n=== 10. Component combinations ===\n")

    combos = [
        {"label": "all off", "params": {}},
        {"label": "UC only", "params": {"input_use_uc_functions": "yes"}},
        {"label": "UC + eval skip", "params": {"input_use_uc_functions": "yes", "input_has_eval_dataset": "yes"}},
        {"label": "UC existing", "params": {"input_use_uc_functions": "yes", "input_uc_functions_exist": "yes"}},
    ]

    # Add VS/Lakebase combos only if template files exist
    _has_vs = has_template_file("{{.input_root_dir}}", "resources", "vector_search.yml.tmpl")
    _has_lb = has_template_file("{{.input_root_dir}}", "resources", "lakebase.yml.tmpl")

    if _has_vs:
        combos += [
            {"label": "VS only", "params": {"input_use_vector_search": "yes"}},
            {"label": "VS + chunked", "params": {"input_use_vector_search": "yes", "input_has_chunked_table": "yes"}},
            {"label": "VS + UC", "params": {"input_use_vector_search": "yes", "input_use_uc_functions": "yes"}},
        ]
    if _has_lb:
        combos += [
            {"label": "Lakebase only", "params": {"input_use_lakebase": "yes"}},
        ]
    if _has_vs and _has_lb:
        combos += [
            {"label": "all components", "params": {
                "input_use_vector_search": "yes", "input_use_uc_functions": "yes", "input_use_lakebase": "yes",
            }},
        ]

    if not _has_vs:
        skip("VS combos", "VS template files not on this branch")
    if not _has_lb:
        skip("Lakebase combos", "Lakebase template files not on this branch")

    for combo in combos:
        @test(f"{combo['label']} — generates without error")
        def _(c=combo):
            p = generate(**c["params"])
            assert p.exists()

        @test(f"{combo['label']} — no Go templates")
        def _(c=combo):
            assert_no_go_templates(generate(**c["params"]))


# ============================================================
# 11. CICD × Cloud matrix
# ============================================================

def test_cicd_cloud_matrix():
    print("\n=== 11. CICD × Cloud matrix ===\n")

    platforms = ["github_actions", "azure_devops", "gitlab"]
    clouds = ["aws", "azure", "gcp"]

    for platform in platforms:
        for cloud in clouds:
            @test(f"{platform} + {cloud} — generates")
            def _(p=platform, c=cloud):
                proj = generate(input_cicd_platform=p, input_cloud=c)
                assert proj.exists()
                assert exists(proj, "databricks.yml")

            @test(f"{platform} + {cloud} — no Go templates")
            def _(p=platform, c=cloud):
                assert_no_go_templates(generate(input_cicd_platform=p, input_cloud=c))


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

    test_defaults()
    test_agent_scaffold()
    test_cicd()
    test_databricks_yml()
    test_uc_functions()
    test_eval()
    test_self_contained()
    test_manifest()
    test_clouds()
    test_combinations()
    test_cicd_cloud_matrix()

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
