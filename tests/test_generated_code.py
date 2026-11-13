"""Static validity of generated projects.

Every check parses or lints generated files. Nothing generated is executed and
no workspace is contacted. Projects are generated once per input combination
(session-scoped) and shared across checks.

Default run: a pairwise covering set of the code-affecting inputs plus every
cloud x CI/CD pair. `--large` also runs the full product.
"""

import ast
import json
import pathlib
import re
import subprocess
import tomllib

import jsonschema
import pytest
import yaml

from utils import (
    NOTEBOOK_HEADER,
    assert_no_go_templates,
    docstring_violations,
    is_notebook,
    pyflakes_messages,
    assert_no_missing_template_values,
    cicd_combinations,
    code_combinations,
    generate,
    paths,
)

CODE_COMBOS = code_combinations()
CODE_COMBOS_FULL = code_combinations(full=True)
CICD_COMBOS = cicd_combinations()
ALL_COMBOS = CODE_COMBOS + CICD_COMBOS


def by_combo(combos):
    """Parametrize a test over (id, params) combinations."""
    return pytest.mark.parametrize(
        "params", [p for _, p in combos], ids=[i for i, _ in combos]
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def project_factory(tmp_path_factory):
    cache = {}

    def make(params):
        key = tuple(sorted(params.items()))
        if key not in cache:
            cache[key] = generate(tmp_path_factory.mktemp("gen"), params)
        return cache[key]

    return make


def _go_regex_to_python(pattern):
    """Translate the Go unicode classes the bundle schema uses into Python `re`."""
    return pattern.replace(r"[\p{L}\p{N}]", r"[^\W_]").replace(r"\p{L}", r"[^\W\d_]")


def _translate_patterns(node):
    if isinstance(node, dict):
        return {
            k: _go_regex_to_python(v) if k == "pattern" else _translate_patterns(v)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_translate_patterns(v) for v in node]
    return node


@pytest.fixture(scope="session")
def bundle_schema():
    """JSON schema for databricks.yml, from the CLI under test (offline)."""
    out = subprocess.run(
        ["databricks", "bundle", "schema"], capture_output=True, text=True, check=True
    ).stdout
    return _translate_patterns(json.loads(out))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def files_with_suffix(project, *suffixes):
    return sorted(p for p in paths(project) if p.endswith(suffixes))


def requires_python_minor(project):
    """Lowest Python 3 minor version allowed by the agent's requires-python."""
    pyprojects = [p for p in paths(project) if p.endswith("pyproject.toml")]
    minors = []
    for p in pyprojects:
        spec = tomllib.loads((project / p).read_text())["project"].get(
            "requires-python", ""
        )
        m = re.search(r">=\s*3\.(\d+)", spec)
        if m:
            minors.append(int(m.group(1)))
    return max(minors) if minors else 9


def assert_none(found, label):
    assert not found, f"{label} violations:\n  " + "\n  ".join(sorted(found))


def load_yaml(path):
    return yaml.safe_load(pathlib.Path(path).read_text())


def bundle_documents(project):
    """databricks.yml plus every included resource file, as {relpath: doc}."""
    root = load_yaml(project / "databricks.yml")
    docs = {"databricks.yml": root}
    for inc in root.get("include", []) or []:
        rel = inc.removeprefix("./")
        docs[rel] = load_yaml(project / rel) if (project / rel).exists() else None
    return docs


# ---------------------------------------------------------------------------
# Template substitution
# ---------------------------------------------------------------------------


@by_combo(ALL_COMBOS)
def test_no_template_residue(project_factory, params):
    project = project_factory(params)
    assert_no_go_templates(project)
    assert_no_missing_template_values(project)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


@by_combo(CODE_COMBOS)
def test_python_syntax(project_factory, params):
    project = project_factory(params)
    minor = requires_python_minor(project)
    for rel in files_with_suffix(project, ".py"):
        source = (project / rel).read_text()
        try:
            ast.parse(source, filename=rel, feature_version=(3, minor))
        except SyntaxError as e:
            pytest.fail(f"{rel}:{e.lineno}: {e.msg} (Python 3.{minor} grammar)")


@by_combo(CODE_COMBOS)
def test_python_lint(project_factory, params):
    project = project_factory(params)
    found = set()
    for rel in files_with_suffix(project, ".py"):
        found |= pyflakes_messages(rel, (project / rel).read_text())
    assert_none(found, "pyflakes")


@by_combo(CODE_COMBOS)
def test_docstrings(project_factory, params):
    project = project_factory(params)
    found = set()
    for rel in files_with_suffix(project, ".py"):
        found |= docstring_violations(rel, (project / rel).read_text())
    assert_none(found, "docstring")


@by_combo(CODE_COMBOS)
def test_shell_syntax(project_factory, params):
    project = project_factory(params)
    for rel in files_with_suffix(project, ".sh"):
        result = subprocess.run(
            ["bash", "-n", str(project / rel)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{rel}: {result.stderr}"


@by_combo(CODE_COMBOS)
def test_notebook_headers(project_factory, params):
    """A file with notebook cell separators must declare itself a notebook."""
    project = project_factory(params)
    for rel in files_with_suffix(project, ".py"):
        source = (project / rel).read_text()
        if "# COMMAND ----------" in source:
            assert is_notebook(
                source
            ), f"{rel} has cells but no '{NOTEBOOK_HEADER}' header"


# ---------------------------------------------------------------------------
# YAML / TOML / JSON
# ---------------------------------------------------------------------------


@by_combo(ALL_COMBOS)
def test_yaml_parses(project_factory, params):
    project = project_factory(params)
    for rel in files_with_suffix(project, ".yml", ".yaml"):
        try:
            list(yaml.safe_load_all((project / rel).read_text()))
        except yaml.YAMLError as e:
            pytest.fail(f"{rel}: {e}")


@by_combo(CODE_COMBOS)
def test_pyproject_valid(project_factory, params):
    project = project_factory(params)
    pyprojects = files_with_suffix(project, "pyproject.toml")
    assert pyprojects
    for rel in pyprojects:
        data = tomllib.loads((project / rel).read_text())
        meta = data.get("project", {})
        assert meta.get("name"), f"{rel}: [project].name missing"
        assert meta.get("requires-python"), f"{rel}: [project].requires-python missing"
        deps = meta.get("dependencies", [])
        assert isinstance(deps, list) and all(isinstance(d, str) for d in deps), rel
        assert len(deps) == len(set(deps)), f"{rel}: duplicate dependencies"


@by_combo(CODE_COMBOS)
def test_json_parses(project_factory, params):
    project = project_factory(params)
    for rel in files_with_suffix(project, ".json"):
        json.loads((project / rel).read_text())


@by_combo(CODE_COMBOS)
def test_env_example_format(project_factory, params):
    project = project_factory(params)
    for rel in files_with_suffix(project, ".env.example"):
        for n, line in enumerate((project / rel).read_text().splitlines(), 1):
            s = line.strip()
            if s and not s.startswith("#"):
                assert re.match(
                    r"^[A-Z_][A-Z0-9_]*=", s
                ), f"{rel}:{n}: not KEY=VALUE: {line!r}"


# ---------------------------------------------------------------------------
# Bundle configuration
# ---------------------------------------------------------------------------


def _strip_unvalidatable(doc):
    """Remove the parts of databricks.yml the JSON schema cannot judge.

    - targets.*.resources: partial overrides that DABs merge into the base
      definition; the schema wrongly demands every required field on them.
    - targets.*.workspace.host: left empty on purpose for the user to fill in.
    """
    doc = json.loads(json.dumps(doc))
    for target in (doc.get("targets") or {}).values():
        if not isinstance(target, dict):
            continue
        target.pop("resources", None)
        ws = target.get("workspace")
        if isinstance(ws, dict) and ws.get("host") is None:
            ws.pop("host")
            if not ws:
                target.pop("workspace")
    return doc


def assert_bundle_schema_valid(project, schema):
    validator = jsonschema.validators.validator_for(schema)(schema)
    for rel, doc in bundle_documents(project).items():
        assert doc is not None, f"included file missing: {rel}"
        if rel == "databricks.yml":
            doc = _strip_unvalidatable(doc)
        error = jsonschema.exceptions.best_match(validator.iter_errors(doc))
        if error is not None:
            path = ".".join(str(p) for p in error.absolute_path) or "<root>"
            pytest.fail(f"{rel} at {path}: {error.message[:300]}")


@by_combo(CODE_COMBOS)
def test_bundle_schema(project_factory, bundle_schema, params):
    assert_bundle_schema_valid(project_factory(params), bundle_schema)


REF_RE = re.compile(r"\$\{resources\.([a-z_]+)\.([A-Za-z0-9_]+)")
VAR_RE = re.compile(r"\$\{var\.([A-Za-z0-9_]+)")


@by_combo(CODE_COMBOS)
def test_bundle_references_resolve(project_factory, params):
    """include paths exist; ${resources.*} and ${var.*} point at real definitions."""
    project = project_factory(params)
    docs = bundle_documents(project)
    missing = [rel for rel, d in docs.items() if d is None]
    assert not missing, f"include paths that do not exist: {missing}"

    defined = set()
    for doc in docs.values():
        for rtype, entries in ((doc or {}).get("resources") or {}).items():
            defined |= {(rtype, key) for key in (entries or {})}
    variables = set()
    for doc in docs.values():
        variables |= set(((doc or {}).get("variables") or {}).keys())

    texts = {rel: (project / rel).read_text() for rel in docs}
    for rel in files_with_suffix(project, "app.yaml"):
        texts[rel] = (project / rel).read_text()
    for rel, text in texts.items():
        for rtype, key in REF_RE.findall(text):
            assert (
                rtype,
                key,
            ) in defined, f"{rel}: ${{resources.{rtype}.{key}}} is not defined"
        for var in VAR_RE.findall(text):
            assert (
                var in variables
            ), f"{rel}: ${{var.{var}}} is not declared under variables"


def _command_script(command):
    scripts = [c for c in command or [] if isinstance(c, str) and c.endswith(".py")]
    return scripts[0] if scripts else None


@by_combo(CODE_COMBOS)
def test_app_commands_resolve(project_factory, params):
    """Each app's source path exists and its command points at a real script."""
    project = project_factory(params)
    apps = (load_yaml(project / "databricks.yml").get("resources") or {}).get(
        "apps"
    ) or {}
    assert apps, "no apps defined"
    for key, app in apps.items():
        src = project / app["source_code_path"]
        assert (
            src.is_dir()
        ), f"app {key}: source_code_path {app['source_code_path']} missing"
        script = _command_script((app.get("config") or {}).get("command"))
        assert (
            script and (src / script).exists()
        ), f"app {key}: command script {script} missing"
        app_yaml = src / "app.yaml"
        if app_yaml.exists():
            script = _command_script(load_yaml(app_yaml).get("command"))
            assert (
                script and (src / script).exists()
            ), f"{app_yaml}: command script {script} missing"


# ---------------------------------------------------------------------------
# Eval gates
# ---------------------------------------------------------------------------

GATE_TIERS = {"block", "warn", "info"}
GATE_OPTIONS = {"tolerance", "floor", "dataset_filter"}


def registered_scorer_names(project):
    """Keys of the `builtin_scorers = {...}` dict literal in scorers.py."""
    tree = ast.parse((project / "src/components/eval/scorers.py").read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "builtin_scorers"
                for t in node.targets
            )
            and isinstance(node.value, ast.Dict)
        ):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    pytest.fail("builtin_scorers dict not found in scorers.py")


@by_combo(CODE_COMBOS)
def test_gates_reference_registered_scorers(project_factory, params):
    project = project_factory(params)
    scorers = registered_scorer_names(project)
    for rel in files_with_suffix(project, "eval/gates.yml"):
        gates = load_yaml(project / rel) or {}
        assert (
            set(gates) <= GATE_TIERS
        ), f"{rel}: unknown tiers {set(gates) - GATE_TIERS}"
        seen = set()
        for tier, entries in gates.items():
            for entry in entries or []:
                if isinstance(entry, str):
                    name, opts = entry, {}
                else:
                    assert (
                        isinstance(entry, dict) and len(entry) == 1
                    ), f"{rel}: bad entry {entry}"
                    ((name, opts),) = entry.items()
                    opts = opts or {}
                assert (
                    name in scorers
                ), f"{rel}: scorer '{name}' is not registered in scorers.py"
                assert (
                    set(opts) <= GATE_OPTIONS
                ), f"{rel}: unknown options {set(opts) - GATE_OPTIONS}"
                slot = (name, opts.get("dataset_filter"))
                assert (
                    slot not in seen
                ), f"{rel}: '{name}' appears in more than one tier"
                seen.add(slot)


# ---------------------------------------------------------------------------
# Full matrix (--large)
# ---------------------------------------------------------------------------


@pytest.mark.large
@by_combo(CODE_COMBOS_FULL)
def test_full_matrix_static(project_factory, bundle_schema, params):
    """The full product, with the parse/lint/schema checks above in one pass."""
    project = project_factory(params)
    assert_no_go_templates(project)
    assert_no_missing_template_values(project)
    flakes, docs = set(), set()
    minor = requires_python_minor(project)
    for rel in files_with_suffix(project, ".py"):
        source = (project / rel).read_text()
        ast.parse(source, filename=rel, feature_version=(3, minor))
        flakes |= pyflakes_messages(rel, source)
        docs |= docstring_violations(rel, source)
    assert_none(flakes, "pyflakes")
    assert_none(docs, "docstring")
    for rel in files_with_suffix(project, ".yml", ".yaml"):
        list(yaml.safe_load_all((project / rel).read_text()))
    assert_bundle_schema_valid(project, bundle_schema)
