---
name: agentops-lifecycle
description: >
  Guide an agentops-stacks project through its full production lifecycle — data
  preparation, agent development, evaluation gates, CI/CD promotion, and
  production monitoring — following the Single-Account Single-Agent pattern from
  the Big Book of AgentOps. Use after `databricks bundle init` has been run and
  `.agentops-stacks/manifest.yml` exists. Triggers on "walk me through the
  agentops lifecycle", "next step after scaffolding", "set up eval gate",
  "deploy agent to staging", "wire production monitoring".
---

# AgentOps Lifecycle — Single-Account Single-Agent

## Overview

This skill guides a project scaffolded with agentops-stacks through its complete
production lifecycle: 10 steps across three phases (dev → staging → prod).
MLflow is the operational spine at every level. The `evaluation/gate.py` pattern
from the scaffold blocks every promotion — it runs locally in dev, in CI on every
PR, and against real production data before users are admitted.

**Before using this skill:** run `databricks bundle init` (via the
`agentops-stacks` skill or directly) and confirm `.agentops-stacks/manifest.yml`
exists in the project root.

### Architecture

```
Git provider
─────────────────────────────────────────────────────────────────────────────
  feature branch ──commit──► PR to main ──CI gate──► main ──tag/release──► CD
        │                         │                             │
        ▼                         ▼                             ▼
┌─────────────────┐   ┌──────────────────────┐   ┌────────────────────────────┐
│ DEV WORKSPACE   │   │ STAGING WORKSPACE    │   │ PRODUCTION WORKSPACE       │
│                 │   │                      │   │                            │
│ Data Prep       │   │ Unit Tests (CI)      │   │ App + Model Serving        │
│  └─ Ingest      │   │ Bundle Validate      │   │ Batch Inferencing Job      │
│  └─ Embed       │   │ Eval Gate (CI)       │   │ Automated Eval             │
│  └─ VS Index    │   │ Integration Tests    │   │ SME HITL sampling          │
│                 │   │ Validation Tests     │   │ Monitoring Dashboard       │
│ Agent Dev       │   │ Staging MLflow       │   │ Feedback Loop              │
│  └─ Tools       │   └──────────────────────┘   └────────────────────────────┘
│  └─ Agent Code  │
│  └─ MLflow      │         Unity Catalog (one metastore, three catalogs)
│     Traces      │   ──────────────────────────────────────────────────────────
│                 │   dev catalog  → dev compute only
│ Offline Eval    │   staging catalog → staging compute only
│ SME HITL (dev)  │   prod catalog → READ-ONLY from dev; prod agent exclusive
└─────────────────┘
```

### Phase overview

| Phase | Steps | Entry gate | Exit gate |
|-------|-------|------------|-----------|
| Dev | 1–5 | scaffold exists | SME sign-off + local eval gate passing |
| Staging | 6–7 | PR opened | all CI checks green + integration tests pass |
| Production | 8–10 | CD triggered | smoke test + batch eval baseline + monitoring live |

---

## Step 1 — Scaffold AgentOps Project

**Do this once at project start.** Bootstrap the production envelope that the
entire lifecycle runs inside.

If the scaffold already exists (`.agentops-stacks/manifest.yml` present), skip
to Step 2.

### Run

```bash
# Non-interactive scaffold — fill in your values
cat > /tmp/agentops-stacks-inputs.json <<'EOF'
{
  "input_project_name": "my_agent",
  "input_cloud": "aws",
  "input_cicd_platform": "github_actions"
}
EOF

databricks bundle init https://github.com/databricks-solutions/agentops-stacks \
  --config-file /tmp/agentops-stacks-inputs.json \
  --output-dir .

cd my_agent
uv sync
databricks bundle validate -t dev
```

### Done when

- `.agentops-stacks/manifest.yml` exists containing `contract_version`,
  `project_name`, `cicd_platform`, `cloud`.
- `databricks bundle validate -t dev` exits 0.
- `uv.lock` is present (commit it).

---

## Step 2 — Data Preparation & Vector Search Indexing

Build the data foundation for the agent. Unoptimized retrieval degrades every
downstream step — hybrid search (BM25 + semantic) and metadata filters are
non-negotiable from the start.

> **Note:** Vector Search indexes are not yet a DAB resource type. Create the
> index via notebook until DAB support lands. Document the creation notebook
> path in a comment in `databricks.yml` so it's findable.

### Ingestion notebook pattern

```python
# notebooks/01_ingest.py  — run against dev workspace
# Databricks notebook source

# COMMAND ----------
# Ingest and parse source documents
from databricks.sdk import WorkspaceClient
import mlflow

mlflow.set_experiment("/Shared/my_agent/data_prep")

w = WorkspaceClient()

# For unstructured documents (PDFs, DOCX, HTML):
# ai_parse_document is a Databricks AI Function available in SQL
spark.sql("""
  CREATE OR REPLACE TABLE my_agent_dev.my_agent.raw_docs AS
  SELECT
    path,
    ai_parse_document(content) AS parsed
  FROM read_files('/Volumes/my_agent_dev/my_agent/raw/', format => 'binaryFile')
""")

# COMMAND ----------
# Chunk and embed for Vector Search
spark.sql("""
  CREATE OR REPLACE TABLE my_agent_dev.my_agent.chunked_docs AS
  SELECT
    path,
    chunk_index,
    chunk_text,
    ai_embed_text(chunk_text) AS embedding
  FROM (
    SELECT
      path,
      posexplode(
        ai_chunk_text(parsed.content, 512, 64)
      ) AS (chunk_index, chunk_text)
    FROM my_agent_dev.my_agent.raw_docs
  )
""")
```

### Vector Search index

```python
# Create index via SDK — not yet a DAB resource type
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import VectorIndexType, DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn

w = WorkspaceClient()

w.vector_search_indexes.create(
    name="my_agent_dev.my_agent.docs_index",
    endpoint_name="my_agent_vs_endpoint",  # pre-existing VS endpoint
    primary_key="path",
    index_type=VectorIndexType.DELTA_SYNC,
    delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
        source_table="my_agent_dev.my_agent.chunked_docs",
        pipeline_type="TRIGGERED",
        embedding_source_columns=[
            EmbeddingSourceColumn(
                name="chunk_text",
                embedding_model_endpoint_name="databricks-gte-large-en",
            )
        ],
    ),
)
```

### Done when

- `databricks bundle validate -t dev` still passes after any new resources are
  added to `databricks.yml`.
- VS index is queryable: `w.vector_search_indexes.query_index("my_agent_dev.my_agent.docs_index", columns=["path", "chunk_text"], query_text="test query")` returns results.
- Ingestion notebook runs end-to-end on sample data without errors.

---

## Step 3 — Agent Development & Dev Deployment

Implement the agent with `@mlflow.trace` on every decision point. MLflow tracing
is **mandatory from the first deploy** — traces are required for eval gate
feedback, SME review, and production monitoring. An agent with no traces cannot
be evaluated.

### Agent class pattern

```python
# src/my_agent.py
import mlflow
from mlflow.pyfunc import PythonModel
from databricks.sdk import WorkspaceClient
import pandas as pd


class MyAgent(PythonModel):
    """Production agent with full MLflow tracing and guardrails."""

    def __init__(self):
        self._vs_client = None

    @property
    def vs_client(self):
        if self._vs_client is None:
            self._vs_client = WorkspaceClient()
        return self._vs_client

    @mlflow.trace(name="predict", span_type="CHAIN")
    def predict(self, context, model_input: pd.DataFrame) -> list[dict]:
        rows = model_input.to_dict(orient="records")
        return [self._handle(row) for row in rows]

    @mlflow.trace(span_type="CHAIN")
    def _handle(self, row: dict) -> dict:
        query = self._validate_input(row.get("query", ""))
        context_docs = self._retrieve(query)
        response = self._generate(query, context_docs)
        return {"response": response, "sources": [d["path"] for d in context_docs]}

    @mlflow.trace(span_type="GUARDRAIL")
    def _validate_input(self, query: str) -> str:
        # PII scrub, injection detection, length limits
        if not query or len(query) > 2000:
            raise ValueError("Query must be 1–2000 characters")
        return query.strip()

    @mlflow.trace(span_type="RETRIEVER")
    def _retrieve(self, query: str) -> list[dict]:
        import os
        catalog = os.environ["DATABRICKS_CATALOG"]
        schema = os.environ.get("DATABRICKS_SCHEMA", "my_agent")
        result = self.vs_client.vector_search_indexes.query_index(
            index_name=f"{catalog}.{schema}.docs_index",
            columns=["path", "chunk_text"],
            query_text=query,
            num_results=5,
        )
        return [
            {"path": r.get("path", ""), "text": r.get("chunk_text", "")}
            for r in (result.result.data_array or [])
        ]

    @mlflow.trace(span_type="LLM")
    def _generate(self, query: str, docs: list[dict]) -> str:
        context = "\n\n".join(d["text"] for d in docs)
        # Replace with your actual LLM call (e.g., MLflow AI Gateway, SDK)
        from mlflow.deployments import get_deploy_client
        client = get_deploy_client("databricks")
        response = client.predict(
            endpoint="databricks-meta-llama-3-1-70b-instruct",
            inputs={
                "messages": [
                    {"role": "system", "content": f"Answer using this context:\n{context}"},
                    {"role": "user", "content": query},
                ]
            },
        )
        return response["choices"][0]["message"]["content"]
```

### Register to Unity Catalog

Run `notebooks/register_agent.py` (generated by the scaffold). Set the
`catalog` and `schema` widgets before running:

```python
# In the notebook (already generated by scaffold):
# catalog = "my_agent_dev"
# schema = "my_agent"
# model_name = f"{catalog}.{schema}.my_agent"
```

After running, verify:

```bash
# Check @champion alias is set
databricks models get-alias my_agent_dev.my_agent.my_agent champion
```

### Deploy dev bundle

```bash
databricks bundle deploy -t dev
uv run pytest  # exit 0 or exit 5 (no tests) both acceptable at this stage
```

### Done when

- Model exists in Unity Catalog with `@champion` alias: `models:/my_agent_dev.my_agent.my_agent@champion`.
- At least one MLflow trace is present in the dev experiment for a sample prediction.
- `databricks bundle deploy -t dev` exits 0.
- If a Databricks App is declared in `databricks.yml`, the App URL is reachable in the dev workspace.

---

## Step 4 — Offline Evaluation & Eval Gate Setup

Build the evaluation framework **before** any code leaves dev. The `evaluation/`
directory is generated by the scaffold. Populate it and verify the gate passes
locally — it will run in CI on every PR.

### Golden dataset

`evaluation/golden_dataset.jsonl` — one JSON object per line:

```jsonl
{"query": "What is the return policy?", "expected_response": "Items can be returned within 30 days with receipt.", "context": "Optional: known good context chunk"}
{"query": "How do I reset my password?", "expected_response": "Visit account settings and click 'Forgot password'.", "context": ""}
```

**Minimum:** 20 labeled examples. Target: 50–100. More examples = more stable
eval scores. SME or domain expert should label the `expected_response` values.

### Thresholds

`evaluation/thresholds.yml` (generated by scaffold — adjust thresholds after
first baseline run):

```yaml
model:
  uri: "models:/{catalog}.{schema}.my_agent@champion"

dataset:
  path: "evaluation/golden_dataset.jsonl"

scorers:
  - name: Safety
    severity: blocking    # hard failure: gate blocks CI
    threshold: 1.0        # all responses must be Safe
  - name: Correctness
    severity: warning     # soft failure: gate warns but does not block
    threshold: 0.8        # >= 80% match expected_response
```

### Run the gate locally

```bash
export DATABRICKS_CATALOG=my_agent_dev
export DATABRICKS_SCHEMA=my_agent
uv run python evaluation/gate.py
```

Expected output on pass:
```
Loading model: models:/my_agent_dev.my_agent.my_agent@champion
Evaluating against 50 examples with 2 scorer(s)
PASS — Safety: 1.000 (threshold 1.000, blocking)
PASS — Correctness: 0.863 (threshold 0.800, warning)
Eval gate: all blocking thresholds met.
```

If Safety < 1.0, review flagged traces in MLflow, add output guardrails to the
agent's `_validate_input` or response post-processing, then re-evaluate. **Do
not lower the Safety threshold to pass.**

### Custom scorer (optional)

```python
# In evaluation/gate.py — extend SCORER_REGISTRY with domain-specific criteria
from mlflow.genai import make_judge

domain_scorer = make_judge(
    name="AnswerGrounded",
    judge_prompt=(
        "Is the answer grounded in the provided context? "
        "Score 1 if fully grounded, 0 if hallucinated."
    ),
    score_type="int",
)

SCORER_REGISTRY["AnswerGrounded"] = lambda: domain_scorer
```

### Done when

- `evaluation/golden_dataset.jsonl` has ≥20 labeled examples.
- `uv run python evaluation/gate.py` exits 0 — all blocking thresholds met.
- MLflow experiment has at least one eval run with `safety/mean` and
  `correctness/mean` metrics.

---

## Step 5 — SME Human-in-the-Loop (Dev)

Calibrate the LLM judge against real domain expert judgment **before** staging.
An uncalibrated judge that passes CI is worse than no judge — it becomes a
rubber stamp.

### Export traces for SME review

```python
import mlflow
import pandas as pd

client = mlflow.tracking.MlflowClient()
experiment = client.get_experiment_by_name("/Shared/my_agent/dev")

# Pull recent traces for review
runs = client.search_runs(
    experiment_ids=[experiment.experiment_id],
    max_results=50,
    order_by=["start_time DESC"],
)

traces = []
for run in runs:
    for trace in client.search_traces(experiment_ids=[experiment.experiment_id],
                                       filter_string=f"run_id = '{run.info.run_id}'",
                                       max_results=1):
        spans = trace.data.spans
        predict_span = next((s for s in spans if s.name == "predict"), None)
        if predict_span:
            traces.append({
                "trace_id": trace.info.request_id,
                "query": predict_span.inputs.get("query", ""),
                "response": predict_span.outputs.get("response", ""),
            })

df = pd.DataFrame(traces)
df.to_csv("evaluation/traces_for_sme_review.csv", index=False)
print(f"Exported {len(df)} traces to evaluation/traces_for_sme_review.csv")
```

Share the CSV (or a Databricks App backed by the MLflow Trace UI) with the
domain SME. Add score columns for them to fill:

| trace_id | query | response | sme_accuracy_1_5 | sme_tone_1_5 | sme_complete_1_5 | sme_safe_pass_fail |
|---|---|---|---|---|---|---|

### Calibration run

After SME scoring is returned, compare against judge scores:

```python
# Run evaluation on the same traces using the LLM judge
result = mlflow.genai.evaluate(
    data=pd.read_csv("evaluation/traces_for_sme_review.csv"),
    predict_fn=lambda q: ...,  # re-invoke agent on the same queries
    scorers=[mlflow.genai.scorers.Correctness(), mlflow.genai.scorers.Safety()],
)

# Compare judge scores to SME scores — compute agreement rate
import numpy as np
sme_df = pd.read_csv("evaluation/traces_for_sme_review.csv")
judge_scores = result.tables["eval_results"]

# Agreement: abs(judge_correctness - sme_accuracy/5) < 0.2
agreement = (
    (judge_scores["correctness/score"] - sme_df["sme_accuracy_1_5"] / 5).abs() < 0.2
).mean()
print(f"Judge-SME agreement: {agreement:.1%}")
```

Target: ≥80% agreement. If <80%, refine the Correctness judge prompt using
disagreement examples as few-shots via `mlflow.genai.align()`.

### Sign-off document

Create `evaluation/sme_calibration.md`:

```markdown
# SME Calibration Sign-Off

- **Reviewer:** Jane Smith (jane.smith@company.com)
- **Date:** 2025-06-01
- **Traces reviewed:** 50
- **Agreement rate:** 84%
- **Judge threshold adjustments:** Correctness raised from 0.80 → 0.82 post-calibration
- **Sign-off:** ✓ Judge calibrated. Approved for promotion to staging.
```

### Done when

- `evaluation/sme_calibration.md` exists with reviewer name, date, agreement %, and explicit sign-off.
- Agreement rate ≥80% (documented).

---

## Step 6 — CI Gate: PR to Main

Open the PR to main. The CI workflow runs `unit_tests`, `validate_bundle`, and
`eval_gate` in a clean environment. **Do not skip or suppress CI checks.**

### Open the PR

```bash
git checkout -b feature/my_agent_initial
git add -A
git commit -m "[my_agent] Initial implementation + eval gate"
git push -u origin feature/my_agent_initial

gh pr create \
  --title "[my_agent] Initial implementation + eval gate" \
  --body "Adds agent code, golden dataset (50 examples), eval gate (Safety 1.0, Correctness 0.82), and SME calibration sign-off."
```

### What CI runs

The CI workflow (`.github/workflows/my_agent-bundle-ci.yml`, generated by
scaffold) runs three jobs:

```yaml
# Generated by scaffold — do not modify the gate-triggering logic
jobs:
  unit_tests:
    # uv run pytest
  validate_bundle:
    # databricks bundle validate -t staging
  eval_gate:
    # if: hashFiles('evaluation/thresholds.yml') != ''
    # uv run python evaluation/gate.py
    # env:
    #   DATABRICKS_CATALOG: ${{ vars.STAGING_CATALOG }}
    #   DATABRICKS_SCHEMA: ${{ vars.STAGING_SCHEMA }}
```

CI secrets required (set in GitHub repo settings before opening the PR):
- `DATABRICKS_STAGING_HOST` — staging workspace URL
- `DATABRICKS_STAGING_TOKEN` or OIDC wiring for the service principal
- `STAGING_CATALOG` variable — e.g., `my_agent_staging`

### Address failures

- **`validate_bundle` fails:** check staging workspace host in `databricks.yml`
  targets.staging.workspace.host; verify secrets are configured in CI.
- **`eval_gate` fails:** fix the agent — do not disable the gate or lower
  thresholds to pass. A CI gate failure is a signal that the agent regressed.

### Done when

- All CI jobs green: `unit_tests`, `validate_bundle`, `eval_gate`.
- PR merged to main (squash merge).

---

## Step 7 — Staging Deployment & Integration Tests

Deploy to staging and run the full integration + validation test suites.
Staging mirrors production configuration — this is where cross-component
integration is verified against real endpoints.

### Deploy to staging

CD is triggered automatically on merge to main by
`.github/workflows/my_agent-bundle-cd-staging.yml`. To trigger manually:

```bash
databricks bundle deploy -t staging
```

### Integration tests

`tests/` contains unit tests generated by the scaffold. Add integration tests
that call real staging endpoints:

```python
# tests/test_agent_integration.py
import os
import mlflow
import pandas as pd
import pytest

@pytest.fixture(scope="session")
def staging_model():
    catalog = os.environ["DATABRICKS_CATALOG"]  # my_agent_staging
    schema = os.environ.get("DATABRICKS_SCHEMA", "my_agent")
    return mlflow.pyfunc.load_model(f"models:/{catalog}.{schema}.my_agent@champion")

def test_agent_returns_response(staging_model):
    result = staging_model.predict(pd.DataFrame([{"query": "What is the return policy?"}]))
    assert isinstance(result, list)
    assert len(result) == 1
    assert "response" in result[0]
    assert len(result[0]["response"]) > 0

def test_agent_handles_empty_query(staging_model):
    """Agent should raise or return a structured error, not crash."""
    with pytest.raises(Exception):
        staging_model.predict(pd.DataFrame([{"query": ""}]))

def test_mlflow_traces_logged(staging_model):
    """Each prediction must produce an MLflow trace."""
    import mlflow
    client = mlflow.tracking.MlflowClient()
    experiment = client.get_experiment_by_name(
        f"/Shared/my_agent/staging"
    )
    before_count = len(client.search_traces(
        experiment_ids=[experiment.experiment_id], max_results=1000
    ))
    staging_model.predict(pd.DataFrame([{"query": "trace check"}]))
    after_count = len(client.search_traces(
        experiment_ids=[experiment.experiment_id], max_results=1000
    ))
    assert after_count > before_count, "Prediction did not log an MLflow trace"
```

Run locally against staging:

```bash
export DATABRICKS_CATALOG=my_agent_staging
uv run pytest tests/test_agent_integration.py -v
```

### Done when

- Databricks App and Model Serving endpoint are live in staging workspace.
- Staging MLflow experiment has at least one trace from the integration test run.
- All integration tests pass.
- All validation tests pass (edge cases, schema validation, timeout behaviors).

---

## Step 8 — Production Deployment via CD

Merge to the release branch (or tag a release) to trigger CD to production.

### Trigger CD

```bash
# Create a release tag on main
git checkout main
git pull
git tag v1.0.0
git push origin v1.0.0
# GitHub Actions picks up the v* tag and runs the CD prod workflow
```

Or: merge `main` → `release` branch if your CD is branch-triggered.

### Verify deployment

```bash
# Monitor CD via GitHub Actions or run manually
databricks bundle deploy -t prod

# Smoke test — confirm agent responds
databricks serving-endpoints query my_agent_prod \
  --request '{"dataframe_records": [{"query": "smoke test query"}]}'
```

The endpoint is healthy when it returns HTTP 200 on `/health`. The smoke test
passes when it returns a non-empty `response` field.

### Register production model

```bash
# Run notebooks/register_agent.py with prod catalog/schema widgets
# Then verify @champion alias in prod UC
databricks models get-alias my_agent_prod.my_agent.my_agent champion
```

### Done when

- CD workflow exits 0 and prod bundle is deployed.
- Model Serving endpoint returns HTTP 200 on `/health`.
- Smoke test: agent returns non-error, non-empty response.
- Prod UC schema has model with `@champion` alias.

---

## Step 9 — Batch Inferencing & Production Eval Baseline

Run batch inferencing on a representative production dataset to establish a
quality baseline **before opening to users**. Production data distributions
differ from golden datasets — the batch eval is the first real-world quality
check.

### Batch inferencing job

Add a Databricks Job to `resources/` for batch inference:

```yaml
# resources/batch_inference_job.yml
resources:
  jobs:
    batch_inference:
      name: "${bundle.name}_batch_inference"
      tasks:
        - task_key: run_batch
          notebook_task:
            notebook_path: notebooks/batch_inference.py
            base_parameters:
              input_table: "${var.catalog}.${var.schema}.batch_eval_inputs"
              output_table: "${var.catalog}.${var.schema}.batch_eval_outputs"
              model_uri: "models:/${var.catalog}.${var.schema}.${bundle.name}@champion"
```

```python
# notebooks/batch_inference.py
# Databricks notebook source

# COMMAND ----------
import mlflow
import pandas as pd
from pyspark.sql import functions as F

dbutils.widgets.text("input_table", "")
dbutils.widgets.text("output_table", "")
dbutils.widgets.text("model_uri", "")

input_table = dbutils.widgets.get("input_table")
output_table = dbutils.widgets.get("output_table")
model_uri = dbutils.widgets.get("model_uri")

# COMMAND ----------
# Load model once and broadcast across partitions
model = mlflow.pyfunc.load_model(model_uri)

input_df = spark.table(input_table).toPandas()
results = model.predict(input_df[["query"]])

output_df = pd.DataFrame(results)
output_df["query"] = input_df["query"].values

spark.createDataFrame(output_df).write.mode("overwrite").saveAsTable(output_table)
print(f"Batch inference complete: {len(output_df)} rows written to {output_table}")
```

### Run eval gate on batch output

```bash
# Point the gate at batch results instead of golden dataset
export DATABRICKS_CATALOG=my_agent_prod
export DATABRICKS_SCHEMA=my_agent
# Override dataset path via environment or edit thresholds.yml temporarily
uv run python evaluation/gate.py
```

### Log baseline metrics

Create `evaluation/production_baseline.md`:

```markdown
# Production Eval Baseline

- **Date:** 2025-06-15
- **Dataset:** my_agent_prod.my_agent.batch_eval_inputs (500 rows)
- **Model:** models:/my_agent_prod.my_agent.my_agent@champion (v1)

| Metric | Value |
|---|---|
| P95 Latency | 1.2s |
| Safety/mean | 1.00 |
| Correctness/mean | 0.84 |
| Cost/request | $0.003 |

Staging baseline for comparison: Correctness 0.82. Production +0.02 — within bounds.
```

### Done when

- Batch inferencing job completes without errors.
- Eval gate passes on production batch results — all blocking thresholds met.
- `evaluation/production_baseline.md` has P95 latency, Safety/mean, Correctness/mean, cost/request.

---

## Step 10 — Production Monitoring & Continuous Feedback Loop

Wire the complete production observability stack. This step closes the
continuous improvement loop: production traces feed back into the eval dataset,
driving future iterations.

### Verify MLflow autolog on the endpoint

The Model Serving endpoint should have `MLFLOW_TRACKING_URI` wired to the prod
MLflow server. Verify by checking the endpoint environment in `databricks.yml`:

```yaml
# In resources/model_serving.yml (or wherever the serving endpoint is declared)
resources:
  model_serving_endpoints:
    my_agent_endpoint:
      name: "${bundle.name}_endpoint"
      config:
        served_models:
          - model_name: "${var.catalog}.${var.schema}.${bundle.name}"
            model_version: "1"
            workload_size: Small
            scale_to_zero_enabled: true
        auto_capture_config:
          catalog_name: "${var.catalog}"
          schema_name: "${var.schema}"
          table_name_prefix: "inference_table"
          enabled: true        # enables inference table for offline eval
```

`mlflow.autolog()` is active by default when the endpoint is serving an MLflow
model. Confirm traces appear within 5 minutes of a live request.

### Wire user feedback

```python
# In your Databricks App backend (app.py)
import mlflow
from flask import request, jsonify

@app.route("/feedback", methods=["POST"])
def collect_feedback():
    body = request.json
    mlflow.log_feedback(
        trace_id=body["trace_id"],
        name="user_satisfaction",
        value=1.0 if body["thumbs_up"] else 0.0,
        rationale=body.get("comment", ""),
    )
    return jsonify({"status": "ok"})
```

Test manually:

```python
import mlflow
# Find a recent trace ID from the prod MLflow experiment
mlflow.log_feedback(trace_id="<trace_id>", name="user_satisfaction", value=1.0)
```

### Monitoring dashboard

Deploy a Databricks App that surfaces:
- P95 latency (from inference table)
- Error rate
- Safety/mean (from online eval or periodic eval job)
- Correctness/mean trend
- User satisfaction (from `mlflow.log_feedback()`)
- Cost per request (from MLflow token logging)

### Alerts

Configure in Databricks SQL Alerts or Databricks Workflows:

| Alert | Threshold | Action |
|---|---|---|
| P95 latency > 2s | Warning | Page on-call |
| P95 latency > 5s | Critical | Page + auto-scale |
| Error rate > 2% | Warning | Investigate traces |
| Safety/mean < 0.99 | Critical | Pause serving, escalate |
| Cost/request > $0.05 | Warning | Review model config |

### Weekly SME sampling job

```yaml
# resources/sme_sampling_job.yml
resources:
  jobs:
    weekly_sme_sampling:
      name: "${bundle.name}_sme_sampling"
      schedule:
        quartz_cron_expression: "0 0 9 ? * MON"   # every Monday 9am UTC
        timezone_id: "UTC"
      tasks:
        - task_key: export_traces
          notebook_task:
            notebook_path: notebooks/export_traces_for_sme.py
            base_parameters:
              sample_size: "50"
              output_path: "/Volumes/${var.catalog}/${var.schema}/sme_review/"
```

### Monitoring runbook

Create `docs/monitoring-runbook.md` documenting:
- What each alert means
- Who owns it (PagerDuty rotation, Slack channel)
- Response playbook (example: "Safety < 0.99 → immediately disable serving → root-cause trace review → fix + re-eval before re-enabling")
- How to add new production traces to the golden dataset for the next iteration

### Done when

- MLflow traces appear for live production requests.
- Production monitoring Databricks App is accessible and displaying live metrics.
- At least latency, error rate, and Safety score alerts are configured and enabled.
- `mlflow.log_feedback()` verified with a manual test.

---

## Escalation path

If a step fails after 3 retries:

1. Capture the MLflow trace for the failing prediction — it shows exactly which
   span failed and why.
2. Check the `escalation_hint` for the step (in `workflows/single-account-single-agent.json`).
3. Escalate to the team lead with: step number, error message, and trace URL.
4. Root-cause in the dev environment first, then re-promote. Do **not** hotfix
   directly in staging or prod.

---

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| `uv run python evaluation/gate.py` exits non-zero with "DATABRICKS_CATALOG not set" | Env vars not exported | `export DATABRICKS_CATALOG=my_agent_dev && export DATABRICKS_SCHEMA=my_agent` |
| `Failed to load model from models:/...@champion` | register_agent.py not yet run, or run with wrong catalog | Run `notebooks/register_agent.py` with correct catalog/schema widgets |
| MLflow traces not appearing after prediction | Endpoint MLFLOW_TRACKING_URI misconfigured | Check endpoint environment vars in the DAB resources config; redeploy |
| CI eval gate fails after local gate passes | Different DATABRICKS_CATALOG in CI vs. local | Ensure CI vars `STAGING_CATALOG` and `STAGING_SCHEMA` match what the model is registered under |
| Safety score 0.0 on all responses | Output schema mismatch — safety scorer expects a `response` string field | Verify agent returns `[{"response": "..."}]` — check `hello_agent.py` for reference |
| VS index query returns no results | Index not synced after data write | Trigger a manual sync: `w.vector_search_indexes.sync_index("my_agent_dev.my_agent.docs_index")` |
| `databricks bundle deploy -t staging` fails with auth error | Service principal not configured in CI secrets | Set `DATABRICKS_STAGING_HOST` and `DATABRICKS_STAGING_TOKEN` secrets in GitHub repo settings |
| Production traces not in MLflow experiment | `auto_capture_config` not set on serving endpoint | Add `auto_capture_config` block to the endpoint resource in `databricks.yml`, redeploy |

---

## Reference files

| File | Role |
|---|---|
| `evaluation/gate.py` | Eval gate — runs at dev (local), CI (PR), and prod (batch). Do not disable. |
| `evaluation/thresholds.yml` | Gate thresholds — presence triggers CI eval gate. Adjust after baseline runs. |
| `evaluation/golden_dataset.jsonl` | SME-labeled evaluation dataset. Grow it with production trace failures. |
| `evaluation/sme_calibration.md` | SME sign-off document. Required before staging promotion. |
| `evaluation/production_baseline.md` | Production quality baseline. Required before user traffic. |
| `notebooks/register_agent.py` | Registers model to UC with `@champion` alias. Re-run on code changes. |
| `databricks.yml` | DAB config — three targets (dev/staging/prod), vars, resources. Source of truth for what deploys. |
| `.agentops-stacks/manifest.yml` | Scaffold contract. Records which patterns have been applied. |
| `workflows/single-account-single-agent.json` | Machine-readable lifecycle definition with all validations and escalation hints. |
