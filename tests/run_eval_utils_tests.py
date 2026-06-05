"""Standalone test runner for eval gate utils — no external dependencies needed.

Run with: python3 tests/run_eval_utils_tests.py
"""

import sys
import os
import tempfile
import traceback
from pathlib import Path


def setup_utils_module():
    """Load utils.py.tmpl, strip Go template lines, and make it importable."""
    tmpl_path = (
        Path(__file__).parents[1]
        / "template"
        / "{{.input_root_dir}}"
        / "src"
        / "agents"
        / "{{.input_initial_agent_name}}"
        / "eval"
        / "utils.py.tmpl"
    )
    content = tmpl_path.read_text()
    # Replace Go template vars with placeholder values
    import re
    clean = re.sub(r'\{\{[^}]+\}\}', 'test_agent', content)

    # Provide mock modules for imports that aren't needed for gate logic
    import types
    mock_yaml = types.ModuleType("yaml")
    mock_yaml.safe_load = lambda f: {}
    sys.modules["yaml"] = mock_yaml

    mock_mlflow_scorers = types.ModuleType("mlflow.genai.scorers")
    for cls_name in ("Fluency", "RelevanceToQuery", "Safety", "ToolCallCorrectness", "Completeness"):
        setattr(mock_mlflow_scorers, cls_name, type(cls_name, (), {}))
    setattr(mock_mlflow_scorers, "get_scorer", lambda name: None)
    sys.modules["mlflow"] = types.ModuleType("mlflow")
    sys.modules["mlflow.genai"] = types.ModuleType("mlflow.genai")
    sys.modules["mlflow.genai.scorers"] = mock_mlflow_scorers

    # Write to temp dir and add to sys.path
    tmpdir = tempfile.mkdtemp()
    mod_path = os.path.join(tmpdir, "utils.py")
    with open(mod_path, "w") as f:
        f.write(clean)
    sys.path.insert(0, tmpdir)
    return tmpdir


# --- Mock pandas.Series for champion tests ---
class FakeSeries(dict):
    """Minimal dict subclass that mimics pandas Series .get()"""
    pass


# --- Test runner ---
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


# --- Tests ---

def run_tests():
    from utils import validate_gates, apply_gates

    print("\n=== validate_gates tests ===\n")

    @test("valid config passes")
    def _():
        config = {
            "block": [{"safety": {"floor": 4.0}}],
            "warn": [{"relevance": {"tolerance": 0.05}}],
            "info": ["fluency"],
        }
        errors, warnings = validate_gates(config)
        assert errors == [], f"Expected no errors, got: {errors}"
        assert warnings == [], f"Expected no warnings, got: {warnings}"

    @test("conflict: same scorer in two tiers")
    def _():
        config = {
            "block": [{"safety": {"floor": 4.0}}],
            "warn": [{"safety": {"tolerance": 0.1}}],
            "info": [],
        }
        errors, _ = validate_gates(config)
        assert len(errors) == 1, f"Expected 1 error, got: {errors}"
        assert "Conflict" in errors[0]

    @test("same scorer, different filters = no conflict")
    def _():
        config = {
            "block": [],
            "warn": [
                {"relevance": {"tolerance": 0.05, "dataset_filter": "category = 'core'"}},
                {"relevance": {"tolerance": 0.15, "dataset_filter": "category = 'edge_case'"}},
            ],
            "info": [],
        }
        errors, _ = validate_gates(config)
        assert errors == [], f"Expected no errors, got: {errors}"

    @test("tolerance in block tier warns")
    def _():
        config = {
            "block": [{"safety": {"floor": 4.0, "tolerance": 0.1}}],
            "warn": [],
            "info": [],
        }
        _, warnings = validate_gates(config)
        assert len(warnings) == 1
        assert "tolerance" in warnings[0]

    @test("invalid floor type errors")
    def _():
        config = {"block": [{"safety": {"floor": "high"}}], "warn": [], "info": []}
        errors, _ = validate_gates(config)
        assert len(errors) == 1
        assert "number" in errors[0]

    @test("tolerance out of range errors")
    def _():
        config = {"block": [], "warn": [{"relevance": {"tolerance": 1.5}}], "info": []}
        errors, _ = validate_gates(config)
        assert len(errors) == 1
        assert "between 0 and 1" in errors[0]

    @test("negative tolerance errors")
    def _():
        config = {"block": [], "warn": [{"relevance": {"tolerance": -0.1}}], "info": []}
        errors, _ = validate_gates(config)
        assert len(errors) == 1

    @test("empty config passes")
    def _():
        config = {"block": [], "warn": [], "info": []}
        errors, warnings = validate_gates(config)
        assert errors == []
        assert warnings == []

    @test("None entries treated as empty")
    def _():
        config = {"block": None, "warn": None, "info": None}
        errors, warnings = validate_gates(config)
        assert errors == []

    @test("simple string entries work")
    def _():
        config = {"block": ["safety"], "warn": ["relevance"], "info": ["fluency"]}
        errors, _ = validate_gates(config)
        assert errors == []

    print("\n=== apply_gates tests ===\n")

    @test("first run, no champion, all pass")
    def _():
        config = {
            "block": [{"safety": {"floor": 4.0}}],
            "warn": [{"relevance": {"tolerance": 0.05}}],
            "info": ["fluency"],
        }
        metrics = {"safety/mean": 4.5, "relevance_to_query/mean": 3.0, "fluency/mean": 4.0}
        passed, report = apply_gates(config, metrics, champion=None)
        assert passed is True, f"Expected pass, report: {report}"

    @test("floor failure blocks")
    def _():
        config = {"block": [{"safety": {"floor": 4.0}}], "warn": [], "info": []}
        metrics = {"safety/mean": 3.5}
        passed, report = apply_gates(config, metrics, champion=None)
        assert passed is False, f"Expected fail, report: {report}"
        assert any("FAIL" in line for line in report)

    @test("floor pass")
    def _():
        config = {"block": [{"safety": {"floor": 4.0}}], "warn": [], "info": []}
        metrics = {"safety/mean": 4.5}
        passed, _ = apply_gates(config, metrics, champion=None)
        assert passed is True

    @test("champion comparison — equal passes")
    def _():
        config = {"block": [], "warn": [{"relevance": {"tolerance": 0.05}}], "info": []}
        metrics = {"relevance_to_query/mean": 4.0}
        champion = FakeSeries({"metrics.relevance_to_query/mean": 4.0})
        passed, _ = apply_gates(config, metrics, champion=champion)
        assert passed is True

    @test("champion comparison — within tolerance passes")
    def _():
        config = {"block": [], "warn": [{"relevance": {"tolerance": 0.10}}], "info": []}
        metrics = {"relevance_to_query/mean": 3.8}  # 5% worse, 10% allowed
        champion = FakeSeries({"metrics.relevance_to_query/mean": 4.0})
        passed, _ = apply_gates(config, metrics, champion=champion)
        assert passed is True

    @test("champion comparison — exceeds tolerance fails")
    def _():
        config = {"block": [], "warn": [{"relevance": {"tolerance": 0.05}}], "info": []}
        metrics = {"relevance_to_query/mean": 3.4}  # 15% worse, 5% allowed
        champion = FakeSeries({"metrics.relevance_to_query/mean": 4.0})
        passed, report = apply_gates(config, metrics, champion=champion)
        assert passed is False, f"Expected fail, report: {report}"

    @test("block tier — any regression fails (no tolerance)")
    def _():
        config = {"block": ["safety"], "warn": [], "info": []}
        metrics = {"safety/mean": 3.9}
        champion = FakeSeries({"metrics.safety/mean": 4.0})
        passed, _ = apply_gates(config, metrics, champion=champion)
        assert passed is False

    @test("info tier never blocks")
    def _():
        config = {"block": [], "warn": [], "info": ["fluency"]}
        metrics = {"fluency/mean": 1.0}
        champion = FakeSeries({"metrics.fluency/mean": 5.0})
        passed, report = apply_gates(config, metrics, champion=champion)
        assert passed is True
        assert any("INFO" in line for line in report)

    @test("missing metric skips (doesn't fail)")
    def _():
        config = {"block": [{"safety": {"floor": 4.0}}], "warn": [], "info": []}
        metrics = {}
        passed, report = apply_gates(config, metrics, champion=None)
        assert passed is True
        assert any("SKIP" in line for line in report)

    @test("metric name mapping: groundedness -> completeness")
    def _():
        config = {"block": [], "warn": [{"groundedness": {"tolerance": 0.05}}], "info": []}
        metrics = {"completeness/mean": 4.0}
        passed, report = apply_gates(config, metrics, champion=None)
        assert passed is True
        assert any("groundedness" in line and "PASS" in line for line in report)

    @test("metric name mapping: relevance -> relevance_to_query")
    def _():
        config = {"block": [], "warn": [{"relevance": {"tolerance": 0.05}}], "info": []}
        metrics = {"relevance_to_query/mean": 4.0}
        passed, report = apply_gates(config, metrics, champion=None)
        assert passed is True
        assert any("relevance" in line and "PASS" in line for line in report)

    @test("mixed tiers — block failure overrides warn pass")
    def _():
        config = {
            "block": [{"safety": {"floor": 4.0}}],
            "warn": [{"relevance": {"tolerance": 0.05}}],
            "info": ["fluency"],
        }
        metrics = {"safety/mean": 3.0, "relevance_to_query/mean": 4.0, "fluency/mean": 4.0}
        passed, _ = apply_gates(config, metrics, champion=None)
        assert passed is False


if __name__ == "__main__":
    tmpdir = setup_utils_module()
    run_tests()

    print(f"\n{'=' * 40}")
    print(f"Results: {PASSED} passed, {FAILED} failed")
    if ERRORS:
        print(f"\nFailures:")
        for name, err in ERRORS:
            print(f"  {name}: {err[:200]}")
    print(f"{'=' * 40}")
    sys.exit(1 if FAILED > 0 else 0)
