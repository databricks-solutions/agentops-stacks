"""Static validity of the plugin: skills, commands, installers, scripts, docs.

No skill is invoked and no LLM runs. Checks parse files and compare the places
that list skills against each other so they cannot drift.
"""

import ast
import json
import pathlib
import re
import subprocess

import pytest
import yaml

from utils import (
    RESOURCE_TEMPLATE_ROOT_DIRECTORY,
    docstring_violations,
    pyflakes_messages,
)

ROOT = pathlib.Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY)
PLUGIN = ROOT / "plugin"
SKILLS_DIR = PLUGIN / "skills"
COMMANDS_DIR = PLUGIN / "commands"
SCRIPTS_DIR = SKILLS_DIR / "agentops-stacks" / "scripts"

SKILLS = sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md"))
COMMANDS = sorted(p.stem for p in COMMANDS_DIR.glob("*.md"))

SKILL_NAME_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MAX_NAME = 64
MAX_DESCRIPTION = 1024

MARKDOWN_FILES = sorted(
    {
        *PLUGIN.rglob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / "examples").rglob("*.md"),
        *(ROOT / "workflows").rglob("*.md"),
        ROOT / "README.md",
        ROOT / "AGENTS.md",
    }
)


def rel(path):
    return str(pathlib.Path(path).relative_to(ROOT))


def frontmatter(path):
    text = pathlib.Path(path).read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{rel(path)}: missing --- frontmatter block"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), f"{rel(path)}: frontmatter is not a mapping"
    return data, text[m.end() :]


def assert_none(found, label):
    assert not found, f"{label} violations:\n  " + "\n  ".join(sorted(found))


# ---------------------------------------------------------------------------
# Skills and commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_frontmatter(skill):
    meta, body = frontmatter(SKILLS_DIR / skill / "SKILL.md")
    name, desc = meta.get("name"), meta.get("description")
    assert name == skill, f"{skill}: frontmatter name {name!r} != directory name"
    assert (
        SKILL_NAME_RE.fullmatch(name) and len(name) <= MAX_NAME
    ), f"{skill}: invalid name"
    assert isinstance(desc, str) and desc.strip(), f"{skill}: description missing"
    assert (
        len(" ".join(desc.split())) <= MAX_DESCRIPTION
    ), f"{skill}: description > {MAX_DESCRIPTION}"
    assert body.strip(), f"{skill}: empty body"


SIBLING_REF_RE = re.compile(r"(?<![\w./-])((?:[a-z_]+)/[A-Za-z0-9_./-]+\.[a-z]+)")


TEMPLATE_PROJECT = ROOT / "template" / "{{.input_root_dir}}"


def is_project_path(path):
    """True if the template generates this path (e.g. scripts/x.sh in the project)."""
    return (TEMPLATE_PROJECT / path).exists() or (
        TEMPLATE_PROJECT / f"{path}.tmpl"
    ).exists()


def sibling_refs(skill):
    """Paths in SKILL.md that point at files inside the skill directory.

    A path counts when its top folder exists inside the skill and the template
    does not generate it. `resources/lakebase.yml` in an ops skill, or
    `scripts/create_usage_policy.sh` in agentops-stacks, point into the
    generated project instead.
    """
    skill_dir = SKILLS_DIR / skill
    text = (skill_dir / "SKILL.md").read_text()
    refs = set()
    for path in SIBLING_REF_RE.findall(text):
        path = path.rstrip(".")
        top = path.split("/", 1)[0]
        if (skill_dir / top).is_dir() and not is_project_path(path):
            refs.add(path)
    return refs


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_sibling_refs_exist(skill):
    missing = sorted(
        r for r in sibling_refs(skill) if not (SKILLS_DIR / skill / r).exists()
    )
    assert not missing, f"{skill}/SKILL.md references missing files: {missing}"


def single_file_violations():
    """Installers ship SKILL.md only, so a SKILL.md must not rely on sibling files."""
    return {
        f"single-file install: {skill} references {ref}"
        for skill in SKILLS
        for ref in sibling_refs(skill)
    }


def test_installed_skills_are_self_contained():
    assert_none(single_file_violations(), "single-file install")


@pytest.mark.parametrize("command", COMMANDS)
def test_command_frontmatter_and_skill(command):
    meta, body = frontmatter(COMMANDS_DIR / f"{command}.md")
    assert isinstance(meta.get("description"), str) and meta["description"].strip()
    skills = re.findall(r"Use the `([a-z0-9-]+)` skill", body)
    assert skills, f"commands/{command}.md does not name a skill"
    for s in skills:
        assert s in SKILLS, f"commands/{command}.md references unknown skill {s}"


# ---------------------------------------------------------------------------
# Every list of skills/commands agrees with the directories
# ---------------------------------------------------------------------------


def install_sh_skills():
    text = (SKILLS_DIR / "install_skills.sh").read_text()
    m = re.search(r"^SKILL_NAMES=\(([^)]*)\)", text, re.M)
    assert m, "SKILL_NAMES not found in install_skills.sh"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def install_genie_skills():
    tree = ast.parse((SKILLS_DIR / "install_genie_code_skills.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SKILLS" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    pytest.fail("SKILLS not found in install_genie_code_skills.py")


def readme_tables():
    text = (PLUGIN / "README.md").read_text()
    skills = set(re.findall(r"^\|\s*\*\*`([a-z0-9-]+)`\*\*\s*\|", text, re.M))
    commands = dict(
        re.findall(r"^\|\s*`/([a-z0-9-]+)`\s*\|\s*`([a-z0-9-]+)`\s*\|", text, re.M)
    )
    return skills, commands


def listing_violations():
    found = set()
    dirs = set(SKILLS)
    for label, listed in [
        ("install_skills.sh", install_sh_skills()),
        ("install_genie_code_skills.py", install_genie_skills()),
        ("plugin/README.md skills table", readme_tables()[0]),
    ]:
        found |= {f"{label}: missing skill {s}" for s in dirs - listed}
        found |= {f"{label}: unknown skill {s}" for s in listed - dirs}
    readme_commands = readme_tables()[1]
    for cmd in set(readme_commands) - set(COMMANDS):
        found.add(f"plugin/README.md commands table: /{cmd} has no commands/{cmd}.md")
    for cmd in set(COMMANDS) - set(readme_commands):
        found.add(f"plugin/README.md commands table: missing /{cmd}")
    for cmd, skill in readme_commands.items():
        path = COMMANDS_DIR / f"{cmd}.md"
        if path.exists() and f"`{skill}` skill" not in path.read_text():
            found.add(
                f"plugin/README.md commands table: /{cmd} maps to {skill}, file disagrees"
            )
    return found


def test_skill_and_command_listings_agree():
    assert_none(listing_violations(), "listing")


# ---------------------------------------------------------------------------
# Plugin scripts
# ---------------------------------------------------------------------------

PY_FILES = sorted(p for p in PLUGIN.rglob("*.py") if "__pycache__" not in p.parts)
SH_FILES = sorted(PLUGIN.rglob("*.sh"))
SUPERVISOR_TEMPLATES = sorted((SCRIPTS_DIR / "supervisor_templates").glob("*.py.tmpl"))
SUPERVISOR_SUBS = {
    "SUPERVISOR_NAME": "router",
    "PROJECT_NAME": "my_proj",
    "ROUTES_PY_LIST": repr(["rag", "support_bot"]),
    "ROUTES_COMMENT": "rag, support_bot",
}


def render_supervisor(path):
    """Fill placeholders the way add_supervisor.render() does."""
    text = path.read_text()
    for key, val in SUPERVISOR_SUBS.items():
        text = text.replace("{{" + key + "}}", val)
    assert "{{" not in text, f"{rel(path)}: unknown placeholder left after render"
    return text


def python_sources():
    sources = {rel(p): p.read_text() for p in PY_FILES}
    sources.update({rel(p): render_supervisor(p) for p in SUPERVISOR_TEMPLATES})
    return sources


@pytest.mark.parametrize("path", sorted(python_sources()))
def test_plugin_python_syntax(path):
    try:
        ast.parse(python_sources()[path], filename=path)
    except SyntaxError as e:
        pytest.fail(f"{path}:{e.lineno}: {e.msg}")


def python_violations():
    found = set()
    for path, source in python_sources().items():
        found |= {f"pyflakes: {m}" for m in pyflakes_messages(path, source)}
        found |= {f"docstring: {m}" for m in docstring_violations(path, source)}
    return found


def test_plugin_python_lint_and_docstrings():
    assert_none(python_violations(), "plugin python")


@pytest.mark.parametrize("path", [rel(p) for p in SH_FILES])
def test_shell_syntax(path):
    result = subprocess.run(
        ["bash", "-n", str(ROOT / path)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"{path}: {result.stderr}"


# ---------------------------------------------------------------------------
# Markdown: fenced code blocks parse, relative links resolve
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"^( *)```([A-Za-z]+)[^\n]*\n(.*?)^\1```", re.S | re.M)
PLACEHOLDER_RE = re.compile(r"<[A-Za-z][\w.:/-]*(?: [\w.:/-]+)*>")
LANGS = {
    "python": "python",
    "py": "python",
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
}


def code_blocks(path):
    text = path.read_text()
    for m in FENCE_RE.finditer(text):
        lang = LANGS.get(m.group(2).lower())
        if not lang:
            continue
        indent = len(m.group(1))
        code = "\n".join(line[indent:] for line in m.group(3).splitlines())
        line = text[: m.start()].count("\n") + 1
        yield lang, line, code


def block_error(lang, code):
    """Parse error for a code block, or None. `<placeholder>` tokens are allowed."""
    try:
        if lang == "python":
            ast.parse(PLACEHOLDER_RE.sub("PLACEHOLDER", code))
        elif lang == "yaml":
            list(yaml.safe_load_all(code))
        elif lang == "json":
            json.loads(code)
        elif lang == "bash":
            r = subprocess.run(
                ["bash", "-n"],
                input=PLACEHOLDER_RE.sub("PLACEHOLDER", code),
                capture_output=True,
                text=True,
            )
            if r.returncode:
                return r.stderr.strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001 - report any parser error
        return str(e).splitlines()[0]
    return None


def code_block_violations():
    found = set()
    for path in MARKDOWN_FILES:
        for lang, line, code in code_blocks(path):
            if block_error(lang, code):
                found.add(f"{rel(path)}:{line} [{lang}]")
    return found


@pytest.mark.parametrize("path", [rel(p) for p in MARKDOWN_FILES])
def test_markdown_code_blocks_parse(path):
    errors = []
    for lang, line, code in code_blocks(ROOT / path):
        err = block_error(lang, code)
        key = f"{path}:{line} [{lang}]"
        if err:
            errors.append(f"{key}: {err}")
    assert not errors, "Code blocks that do not parse:\n  " + "\n  ".join(errors)


LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def link_violations():
    found = set()
    for source in MARKDOWN_FILES:
        text = re.sub(r"```.*?```", "", source.read_text(), flags=re.S)
        for target in LINK_RE.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            file_part = target.split("#", 1)[0]
            if file_part and not (source.parent / file_part).exists():
                found.add(f"link: {rel(source)} -> {target}")
    return found


def test_markdown_relative_links_resolve():
    assert_none(link_violations(), "broken link")
