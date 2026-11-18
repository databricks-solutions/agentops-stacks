"""Contract tests for the AgentOps Stacks Unity Gateway DAB skill."""

import json
import os
import re
import runpy
import subprocess
import sys
import types
import urllib.request
from functools import lru_cache
from pathlib import Path

import yaml


ROOT = Path(__file__).parent.parent
SKILL_DIR = ROOT / "plugin" / "skills" / "unity-gateway-ops"
SKILL = SKILL_DIR / "SKILL.md"
REFERENCES = {
    "model-services.md",
    "model-provider-services.md",
    "mcp-services.md",
}


def read(path):
    return path.read_text()


def frontmatter(path):
    parts = read(path).split("---", 2)
    assert len(parts) == 3, f"Missing YAML frontmatter in {path}"
    return yaml.safe_load(parts[1])


def yaml_blocks(path):
    return re.findall(r"```yaml\n(.*?)```", read(path), flags=re.DOTALL)


@lru_cache(maxsize=1)
def bundle_schema():
    result = subprocess.run(
        ["databricks", "bundle", "schema"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def sdk_catalog_definition(name):
    return bundle_schema()["$defs"]["github.com"]["databricks"][
        "databricks-sdk-go"
    ]["service"][name]


def bundle_resource_definition(name):
    return bundle_schema()["$defs"]["github.com"]["databricks"]["cli"][
        "bundle"
    ]["config"][name]


def test_skill_frontmatter_is_project_scoped_and_resource_addressable():
    metadata = frontmatter(SKILL)
    description = metadata["description"]

    assert metadata["name"] == "unity-gateway-ops"
    assert "AgentOps Stacks" in description
    assert "Declarative Automation Bundle" in description
    for trigger in ("model service", "model provider service", "MCP service"):
        assert trigger in description
    assert "without saying" in description
    assert "Unity Gateway" in description
    assert "imperative Unity Gateway administration" in description


def test_mcp_routing_distinguishes_server_creation_from_gateway_registration():
    skill = read(SKILL)
    description = frontmatter(SKILL)["description"]
    mcp_reference = read(SKILL_DIR / "references" / "mcp-services.md")
    normalized_reference = " ".join(mcp_reference.split())
    right_size = read(
        ROOT / "plugin" / "skills" / "right-size-capability" / "SKILL.md"
    )
    normalized_right_size = " ".join(right_size.split())

    assert 'Clarify ambiguous "create an MCP service/server"' in description
    assert "not building the server application" in description
    assert "Do not infer Gateway registration" in skill
    assert "Build or host an MCP server on Databricks Apps" in skill
    assert "Build an MCP server outside Databricks" in skill
    assert "finish the Databricks App and its UC HTTP" in normalized_reference
    assert "external to Unity Gateway" in normalized_reference
    assert "not necessarily external to Databricks" in normalized_reference
    assert "Databricks App/component-creation workflow" in normalized_right_size
    assert (
        "Building a server outside Databricks is out of scope"
        in normalized_right_size
    )


def test_all_resource_references_are_present_and_routed_from_skill():
    actual = {path.name for path in (SKILL_DIR / "references").glob("*.md")}
    assert actual == REFERENCES

    skill = read(SKILL)
    for reference in REFERENCES:
        assert f"references/{reference}" in skill


def test_all_embedded_yaml_examples_parse_and_contain_no_plaintext_secret():
    markdown_files = [SKILL, *sorted((SKILL_DIR / "references").glob("*.md"))]
    block_count = 0

    for path in markdown_files:
        for index, block in enumerate(yaml_blocks(path), start=1):
            block_count += 1
            parsed = yaml.safe_load(block)
            assert parsed is not None, f"Empty YAML block {index} in {path}"
            assert "plaintext:" not in block, f"Plaintext secret shape in {path}"
            assert not re.search(r"(?m)^\s*unity_gateway\s*:", block), (
                f"Aggregate unity_gateway resource in {path}"
            )

    assert block_count >= 10


def test_skill_contains_no_imperative_gateway_lifecycle_commands():
    all_text = "\n".join(
        read(path)
        for path in [SKILL, *sorted((SKILL_DIR / "references").glob("*.md"))]
    )

    forbidden = (
        r"databricks\s+ai-gateway",
        r"databricks\s+api\s+(post|patch|delete)",
        r"\.ai_gateway\.(create|update|delete)_",
    )
    for pattern in forbidden:
        assert re.search(pattern, all_text) is None, pattern


def test_skill_requires_direct_engine_profiles_and_uniform_targets():
    skill = read(SKILL)
    normalized = " ".join(skill.split())

    assert "engine: direct" in skill
    assert "one configuration in every target" in normalized
    assert "do not add target-level resource overrides" in normalized
    assert "granular target configuration" in normalized

    lifecycle_commands = re.findall(
        r"(?m)^databricks bundle (validate|plan|deploy|summary) .+$", skill
    )
    assert lifecycle_commands
    for line in re.findall(
        r"(?m)^databricks bundle (?:validate|plan|deploy|summary) .+$", skill
    ):
        assert "--profile <PROFILE>" in line


def test_skill_documents_identity_parent_access_and_governance_record():
    skill = read(SKILL)

    assert "this skill does not create them" in skill
    assert "USE CATALOG" in skill
    assert "USE SCHEMA" in skill
    assert "governance/data_flows.md" in skill
    assert "governance/posture.md" in skill
    assert "prerequisite before production promotion" in skill
    assert "Missing sibling resource types do not" in skill
    assert "every generated CI/CD definition" in skill
    assert "deployment CLI cannot read" in skill
    assert "OAuth M2M" in skill
    assert "Never introduce or recommend a personal access token" in skill


def test_project_owned_services_use_the_resolved_bundle_schema():
    markdown_files = [SKILL, *sorted((SKILL_DIR / "references").glob("*.md"))]
    all_text = "\n".join(read(path) for path in markdown_files)

    resolved_parent = (
        "parent: schemas/${var.catalog}."
        "${resources.schemas.project_schema.name}"
    )
    assert resolved_parent in all_text
    assert "parent: schemas/${var.catalog}.${var.schema}" not in all_text
    assert "development-mode rewriting" in read(SKILL)


def test_generated_ci_cli_pin_supports_unity_gateway_schema():
    variables = read(ROOT / "library" / "template_variables.tmpl")
    sha_match = re.search(
        r"define `cli_version`.*?\n\s*([0-9a-f]{40})", variables, re.DOTALL
    )
    tag_match = re.search(
        r"define `cli_version_tag`.*?\n\s*v(\d+)\.(\d+)\.(\d+)",
        variables,
        re.DOTALL,
    )

    assert sha_match, "Generated CI must use an immutable setup-cli commit SHA"
    assert tag_match, "Generated CI must document the corresponding CLI tag"
    assert tuple(map(int, tag_match.groups())) >= (1, 17, 0)

    generated_root = ROOT / "template" / "{{.input_root_dir}}"
    ci_templates = [
        path
        for path in generated_root.rglob("*.tmpl")
        if {".github", ".gitlab", ".azure"} & set(path.parts)
        and "databricks/setup-cli" in read(path)
    ]
    assert ci_templates
    for path in ci_templates:
        assert "{{template `cli_version` .}}" in read(path), path


def test_installed_bundle_schema_supports_all_three_resources():
    expected_required = {
        "resources.ModelService": {"parent", "model_service_id"},
        "resources.ModelProviderService": {
            "parent",
            "model_provider_service_id",
        },
        "resources.McpService": {"parent", "mcp_service_id"},
    }

    for definition, required in expected_required.items():
        actual = set(bundle_resource_definition(definition)["oneOf"][0]["required"])
        assert actual == required


def test_installed_bundle_schema_matches_documented_fields_and_enums():
    destination_types = sdk_catalog_definition(
        "catalog.ModelServiceConfigDestinationConfigDestinationType"
    )["oneOf"][0]["enum"]
    assert set(destination_types) == {
        "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
        "DESTINATION_TYPE_PROVISIONED_THROUGHPUT_FOUNDATION_MODEL",
        "DESTINATION_TYPE_EXTERNAL_FOUNDATION_MODEL",
    }

    provider_types = sdk_catalog_definition(
        "catalog.ModelProviderServiceConfigExternalModelProviderType"
    )["oneOf"][0]["enum"]
    assert set(provider_types) == {
        "EXTERNAL_MODEL_PROVIDER_TYPE_OPENAI",
        "EXTERNAL_MODEL_PROVIDER_TYPE_AZURE_OPENAI",
        "EXTERNAL_MODEL_PROVIDER_TYPE_ANTHROPIC",
        "EXTERNAL_MODEL_PROVIDER_TYPE_AMAZON_BEDROCK",
        "EXTERNAL_MODEL_PROVIDER_TYPE_CUSTOM",
        "EXTERNAL_MODEL_PROVIDER_TYPE_MICROSOFT_FOUNDRY",
        "EXTERNAL_MODEL_PROVIDER_TYPE_GEMINI_ENTERPRISE",
        "EXTERNAL_MODEL_PROVIDER_TYPE_BEDROCK_MANTLE",
    }

    provider_secret = sdk_catalog_definition(
        "catalog.ModelProviderServiceConfigProviderSecret"
    )["oneOf"][0]["properties"]
    assert "secret_reference" in provider_secret

    mcp_config = sdk_catalog_definition("catalog.McpServiceConfig")["oneOf"][0][
        "properties"
    ]
    assert {"source_connection", "include_tool_selectors", "rate_limits"} <= set(
        mcp_config
    )


def test_local_installer_packages_skill_and_references(tmp_path):
    (tmp_path / "databricks.yml").write_text(
        "bundle:\n  name: installer-test\n  engine: direct\n"
    )
    installer = ROOT / "plugin" / "skills" / "install_skills.sh"

    result = subprocess.run(
        [str(installer)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert result.returncode == 0, result.stdout + result.stderr

    installed = tmp_path / ".claude" / "skills" / "unity-gateway-ops"
    assert (installed / "SKILL.md").is_file()
    assert {
        path.name for path in (installed / "references").glob("*.md")
    } == REFERENCES


def test_genie_installer_packages_skill_and_all_references():
    installer = read(ROOT / "plugin" / "skills" / "install_genie_code_skills.py")

    assert '"unity-gateway-ops"' in installer
    for reference in REFERENCES:
        assert f'"references/{reference}"' in installer


def test_genie_installer_uploads_skill_and_all_references(monkeypatch):
    installer = ROOT / "plugin" / "skills" / "install_genie_code_skills.py"
    uploaded_paths = []
    downloaded_urls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"test skill content"

    def fake_urlopen(url, timeout):
        assert timeout == 30
        downloaded_urls.append(url)
        return FakeResponse()

    class FakeWorkspace:
        def mkdirs(self, _path):
            return None

        def import_(self, *, path, content, format, overwrite):
            assert content
            assert format == "AUTO"
            assert overwrite is True
            uploaded_paths.append(path)

        def list(self, _path):
            return []

    class FakeCurrentUser:
        def me(self):
            return types.SimpleNamespace(user_name="tester@example.com")

    class FakeWorkspaceClient:
        def __init__(self):
            self.current_user = FakeCurrentUser()
            self.workspace = FakeWorkspace()

    databricks_module = types.ModuleType("databricks")
    sdk_module = types.ModuleType("databricks.sdk")
    service_module = types.ModuleType("databricks.sdk.service")
    workspace_module = types.ModuleType("databricks.sdk.service.workspace")
    sdk_module.WorkspaceClient = FakeWorkspaceClient
    workspace_module.ImportFormat = types.SimpleNamespace(AUTO="AUTO")

    monkeypatch.setitem(sys.modules, "databricks", databricks_module)
    monkeypatch.setitem(sys.modules, "databricks.sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "databricks.sdk.service", service_module)
    monkeypatch.setitem(
        sys.modules, "databricks.sdk.service.workspace", workspace_module
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    runpy.run_path(str(installer), run_name="__main__")

    skill_root = "/Users/tester@example.com/.assistant/skills/unity-gateway-ops"
    expected_paths = {f"{skill_root}/SKILL.md"} | {
        f"{skill_root}/references/{reference}" for reference in REFERENCES
    }
    assert expected_paths <= set(uploaded_paths)
    assert all(
        any(
            url.endswith(
                f"/unity-gateway-ops/{path.removeprefix(f'{skill_root}/')}"
            )
            for url in downloaded_urls
        )
        for path in expected_paths
    )


def test_documentation_and_advisory_routing_are_integrated():
    plugin_readme = read(ROOT / "plugin" / "README.md")
    bigbook = read(ROOT / "plugin" / "skills" / "agentops-bigbook" / "SKILL.md")
    right_size = read(
        ROOT / "plugin" / "skills" / "right-size-capability" / "SKILL.md"
    )

    assert "unity-gateway-ops" in plugin_readme
    assert "unity-gateway-ops" in bigbook
    assert "unity-gateway-ops" in right_size
    assert "existing backing MCP server" in right_size
