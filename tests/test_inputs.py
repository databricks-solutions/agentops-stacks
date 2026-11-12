"""Template inputs: valid inputs are accepted, invalid inputs are rejected.

Three layers judge inputs today:
  1. databricks_template_schema.json (enforced by `databricks bundle init`)
  2. plugin/skills/agentops-stacks/scripts/validate_inputs.py (the skill's pre-check)
  3. the name regexes in add_agent.py / add_supervisor.py

One case table runs through layers 1 and 2 and both must match the expected
verdict. Layer 3 and validate_inputs.py's constants are checked against the
schema directly so they cannot drift.
"""

import ast
import importlib.util
import json
import pathlib
import re

import pytest

from utils import (
    DEFAULT_PARAMS,
    EXAMPLE_USAGE_POLICY_ID,
    RESOURCE_TEMPLATE_ROOT_DIRECTORY,
    generate,
)

ROOT = pathlib.Path(RESOURCE_TEMPLATE_ROOT_DIRECTORY)
SCHEMA = json.loads((ROOT / "databricks_template_schema.json").read_text())
PROPS = SCHEMA["properties"]
SCRIPTS = ROOT / "plugin" / "skills" / "agentops-stacks" / "scripts"


def _load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate_inputs = _load(SCRIPTS / "validate_inputs.py")


# ---------------------------------------------------------------------------
# Schema well-formedness
# ---------------------------------------------------------------------------


def test_schema_orders_unique_and_contiguous():
    orders = sorted(p["order"] for p in PROPS.values())
    assert orders == list(range(1, len(PROPS) + 1)), orders


@pytest.mark.parametrize("name", sorted(PROPS))
def test_schema_property_well_formed(name):
    prop = PROPS[name]
    assert prop.get("type") == "string", f"{name}: type must be string"
    assert prop.get("description", "").strip(), f"{name}: description missing"
    assert "default" in prop, f"{name}: default missing"
    if "enum" in prop:
        assert prop["default"] in prop["enum"], f"{name}: default not in enum"
        assert len(prop["enum"]) == len(
            set(prop["enum"])
        ), f"{name}: duplicate enum values"
    if "pattern" in prop:
        assert re.fullmatch(
            prop["pattern"], prop["default"]
        ), f"{name}: default fails pattern"
        assert prop.get(
            "pattern_match_failure_message"
        ), f"{name}: failure message missing"


@pytest.mark.parametrize(
    "name", sorted(n for n, p in PROPS.items() if "skip_prompt_if" in p)
)
def test_schema_skip_prompt_if_references_exist(name):
    for ref, cond in PROPS[name]["skip_prompt_if"]["properties"].items():
        assert ref in PROPS, f"{name}: skip_prompt_if references unknown {ref}"
        assert (
            PROPS[ref]["order"] < PROPS[name]["order"]
        ), f"{name}: depends on a later prompt"
        if "enum" in PROPS[ref]:
            assert (
                cond["const"] in PROPS[ref]["enum"]
            ), f"{name}: const not a value of {ref}"


def test_test_defaults_match_schema():
    """tests/utils.DEFAULT_PARAMS must cover every input and use schema defaults."""
    assert set(DEFAULT_PARAMS) == set(PROPS)
    for name, value in DEFAULT_PARAMS.items():
        if name == "input_root_dir":  # schema default is a template expression
            continue
        assert value == PROPS[name]["default"], f"{name}: {value!r} != schema default"


# ---------------------------------------------------------------------------
# Drift: validator constants and name regexes vs the schema
# ---------------------------------------------------------------------------

VALIDATOR_ENUMS = {
    "input_cloud": "VALID_CLOUDS",
    "input_cicd_platform": "VALID_CICD",
    "input_memory_type": "VALID_MEMORY_TYPES",
    "input_eval_dataset_source": "VALID_EVAL_SOURCES",
}


@pytest.mark.parametrize("name", sorted(n for n, p in PROPS.items() if "enum" in p))
def test_validator_enum_matches_schema(name):
    const = VALIDATOR_ENUMS.get(name, "YES_NO")
    assert set(getattr(validate_inputs, const)) == set(
        PROPS[name]["enum"]
    ), f"validate_inputs.{const} differs from schema enum for {name}"


@pytest.mark.parametrize(
    "name", sorted(n for n, p in PROPS.items() if "enum" in p or "pattern" in p)
)
def test_validator_checks_every_constrained_input(name):
    source = (SCRIPTS / "validate_inputs.py").read_text()
    assert f'"{name}"' in source, f"validate_inputs.py never checks {name}"


def _regex_literals(path):
    """String literals passed to re.compile / re.match / re.fullmatch in a file."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"compile", "match", "fullmatch"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith("^[a-z]")
        ):
            found.append(node.args[0].value)
    return found


@pytest.mark.parametrize(
    "script", ["validate_inputs.py", "add_agent.py", "add_supervisor.py"]
)
def test_name_regexes_match_schema(script):
    patterns = _regex_literals(SCRIPTS / script)
    assert patterns, f"{script}: no name regex found"
    for pattern in patterns:
        assert (
            pattern == PROPS["input_initial_agent_name"]["pattern"]
        ), f"{script}: {pattern}"
    assert (
        PROPS["input_project_name"]["pattern"]
        == PROPS["input_initial_agent_name"]["pattern"]
    )


def _name_check_calls(path):
    """(method, pattern) for each regex call that checks a name in a script.

    Covers `re.<method>("^[a-z]...", x)` and `NAME.<method>(x)` where
    `NAME = re.compile("^[a-z]...")`, so the test judges the call actually made.
    """
    tree = ast.parse(path.read_text())
    compiled = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "compile"
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    compiled[target.id] = node.value.args[0].value
    calls = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"match", "fullmatch", "search"}
            and isinstance(node.func.value, ast.Name)
        ):
            continue
        owner, method = node.func.value.id, node.func.attr
        if owner == "re" and node.args and isinstance(node.args[0], ast.Constant):
            pattern = node.args[0].value
        elif owner in compiled:
            pattern = compiled[owner]
        else:
            continue
        if isinstance(pattern, str) and pattern.startswith("^[a-z]"):
            calls.append((method, pattern))
    return calls


@pytest.mark.parametrize(
    "script", ["validate_inputs.py", "add_agent.py", "add_supervisor.py"]
)
def test_name_check_rejects_trailing_newline(script):
    """Python's `$` with re.match accepts "abc\n". Go's `$` (the CLI) does not."""
    calls = _name_check_calls(SCRIPTS / script)
    assert calls, f"{script}: no name check call found"
    for method, pattern in calls:
        assert not getattr(re, method)(
            pattern, "abc\n"
        ), f"{script}: {method}({pattern!r}) accepts a trailing newline"


# ---------------------------------------------------------------------------
# Case table: every case through bundle init and validate_inputs.validate
# ---------------------------------------------------------------------------

VALID_NAMES = [
    "abc",
    "my_agent",
    "rag_bot_v2",
    "a1_",
    "agent_with_a_long_but_legal_name",
]
INVALID_NAMES = {
    "too_short": "ab",
    "empty": "",
    "uppercase": "MyProject",
    "leading_digit": "1bad",
    "leading_underscore": "_bad",
    "hyphen": "bad-name",
    "spaces": "name with spaces",
    "slashes": "name/with/slashes",
    "backslashes": "name\\with\\backslashes",
    "periods": "name.with.periods",
    "non_ascii": "näme",
    "trailing_newline": "abc\n",
}


VALID_POLICY_IDS = {
    "blank": "",
    "lowercase": EXAMPLE_USAGE_POLICY_ID,
    "uppercase": EXAMPLE_USAGE_POLICY_ID.upper(),
}
INVALID_POLICY_IDS = {
    "not_uuid": "not-a-policy-id",
    "short": EXAMPLE_USAGE_POLICY_ID[:-1],
    "braces": "{" + EXAMPLE_USAGE_POLICY_ID + "}",
    "no_hyphens": EXAMPLE_USAGE_POLICY_ID.replace("-", ""),
    "whitespace": " ",
    "trailing_newline": EXAMPLE_USAGE_POLICY_ID + "\n",
}


def _bogus_enum_values(enum):
    first = enum[0]
    return {
        "bogus": "bogus",
        "empty": "",
        "wrong_case": first.upper(),
        "padded": f" {first}",
    }


def _cases():
    cases = []
    for name in ("input_project_name", "input_initial_agent_name"):
        short = name.removeprefix("input_")
        for v in VALID_NAMES:
            cases.append((f"{short}-valid-{v}", {name: v}, True))
        for label, v in INVALID_NAMES.items():
            cases.append((f"{short}-invalid-{label}", {name: v}, False))
    for label, v in VALID_POLICY_IDS.items():
        cases.append(
            (f"usage_policy_id-valid-{label}", {"input_usage_policy_id": v}, True)
        )
    for label, v in INVALID_POLICY_IDS.items():
        cases.append(
            (f"usage_policy_id-invalid-{label}", {"input_usage_policy_id": v}, False)
        )
    for name, prop in sorted(PROPS.items()):
        if "enum" not in prop:
            continue
        short = name.removeprefix("input_")
        for v in prop["enum"]:
            cases.append((f"{short}-valid-{v}", {name: v}, True))
        for label, v in _bogus_enum_values(prop["enum"]).items():
            cases.append((f"{short}-invalid-{label}", {name: v}, False))
    return cases


CASES = _cases()


def _cli_verdict(tmp_path, overrides):
    """(accepted, error text) from `databricks bundle init`."""
    try:
        generate(tmp_path, overrides)
        return True, ""
    except RuntimeError as e:
        return False, str(e)


def _validator_accepts(overrides):
    errors, _ = validate_inputs.validate({**DEFAULT_PARAMS, **overrides})
    return not errors


@pytest.mark.parametrize("case_id,overrides,expected", CASES, ids=[c[0] for c in CASES])
def test_input_case(tmp_path, case_id, overrides, expected):
    cli_ok, cli_error = _cli_verdict(tmp_path, overrides)
    if not cli_ok and not expected:
        # A rejection only counts if the CLI blamed the input under test, not
        # an unrelated init failure.
        assert any(
            name in cli_error for name in overrides
        ), f"{case_id}: bundle init failed for another reason:\n{cli_error}"
    verdicts = {
        "bundle_init": cli_ok,
        "validate_inputs": _validator_accepts(overrides),
    }
    wrong = sorted(layer for layer, ok in verdicts.items() if ok != expected)
    assert (
        not wrong
    ), f"{case_id}: expected {'accept' if expected else 'reject'}, wrong in {wrong}"
