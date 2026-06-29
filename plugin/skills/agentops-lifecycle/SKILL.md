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
MLflow is the operational spine at every level. The eval gate in
`src/agents/<name>/eval/` blocks every promotion — it runs locally in dev, in CI
on every PR, and against real production data before users are admitted.

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
│ Data Prep       │   │ Unit Tests (CI)      │   │ Databricks App             │
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
  "input_initial_agent_name": "my_agent",
  "input_cloud": "aws",
  "input_cicd_platform": "github_actions",
  "input_use_vector_search": "no",
  "input_use_lakebase": "no",
  "input_use_uc_functions": "no",
  "input_eval_dataset_source": "synthetic"
}
EOF

databricks bundle init https://github.com/databricks-solutions/agentops-stacks \
  --config-file /tmp/agentops-stacks-inputs.json \
  --output-dir .

cd my_agent/src/agents/my_agent
uv sync                          # generates uv.lock — commit it
databricks bundle validate -t dev
```

### Done when

- `.agentops-stacks/manifest.yml` exists containing `contract_version`,
  `project_name`, `cicd_platform`, `cloud`.
- `databricks bundle validate -t dev` exits 0.
- `uv.lock` is present at `src/agents/my_agent/uv.lock` (commit it).

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

Implement the agent as a LangGraph graph served via MLflow AgentServer. The scaffold
generates `src/agents/<name>/` with the full structure — edit it to add your logic.
`mlflow.langchain.autolog()` in `agent.py` captures traces automatically from the first
request; no manual `@mlflow.trace` decorators needed.

### Agent file layout

```
src/agents/my_agent/
├── agent.py       # @invoke/@stream handlers (MLflow AgentServer entry points)
├── graph.py       # LangGraph StateGraph assembly — add nodes and edges here
├── tools.py       # Tool selection — controls what the agent can do
├── app/
│   └── start_server.py  # Local dev server (FastAPI via AgentServer)
└── eval/
    ├── create_dataset.py   # Databricks notebook: build UC eval table
    ├── evaluate_agent.py   # Databricks notebook: run eval gate
    ├── gates.yml           # Gate thresholds (block/warn/info tiers)
    └── utils.py            # Pure-Python gate logic (unit-testable)
```

### Edit the graph

`graph.py` assembles the LangGraph StateGraph. The scaffold generates a working
baseline — add nodes and edges for your use case:

```python
# src/agents/my_agent/graph.py  (generated — edit to add your logic)
import os
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from databricks_langchain import ChatDatabricks
from tools import get_tools

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "databricks-claude-sonnet-4")

def agent_node(state: MessagesState) -> dict:
    tools = get_tools()
    llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
    if tools:
        llm = llm.bind_tools(tools)
    return {"messages": [llm.invoke(state["messages"])]}

def should_continue(state: MessagesState) -> str:
    last = state["messages"][-1]
    return "tool_node" if (hasattr(last, "tool_calls") and last.tool_calls) else END

def build_graph():
    tools = get_tools()
    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    if tools:
        builder.add_node("tool_node", ToolNode(tools))
    builder.add_edge(START, "agent")
    if tools:
        builder.add_conditional_edges("agent", should_continue)
        builder.add_edge("tool_node", "agent")
    else:
        builder.add_edge("agent", END)
    return builder

graph_builder = build_graph()
graph = graph_builder.compile()
```

### Run locally

```bash
cd src/agents/my_agent
uv sync                                # install deps + generate uv.lock
cp .env.example .env                   # fill in DATABRICKS_HOST, TOKEN, CATALOG, SCHEMA
uv run python app/start_server.py      # starts FastAPI on http://localhost:8000

# Send a test message
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "hello"}]}'
```

### Deploy to dev

```bash
databricks bundle deploy -t dev
```

The bundle deploys a Databricks App for each agent declared in `databricks.yml`.
Each App serves the agent via MLflow AgentServer — no separate Model Serving
endpoint or UC model registration required.

### Done when

- `uv run python app/start_server.py` starts without errors locally and returns a response.
- `databricks bundle deploy -t dev` exits 0.
- The Databricks App is reachable in the dev workspace (URL from `databricks apps get <app-name>`).
- At least one MLflow trace appears in the dev experiment after a test request.

---

## Step 4 — Offline Evaluation & Eval Gate Setup

Build the evaluation framework **before** any code leaves dev. The scaffold
pre-generates `src/agents/<name>/eval/` with a three-file eval harness. Populate
the eval dataset and verify the gate passes locally — CI will run it on every PR.

### Build the eval dataset

Run `src/agents/my_agent/eval/create_dataset.py` as a Databricks notebook.
It saves the eval set to `<catalog>.<schema>.my_agent_eval_dataset` in Unity Catalog.

Three dataset modes are available (chosen at scaffold time via `input_eval_dataset_source`):
- **`synthetic`** — uses `databricks.agents.evals.generate_evals_df` to synthesize
  questions from your source documents. Edit the `docs` DataFrame to point at real content.
- **`manual`** — fill in the `eval_examples` list with domain-specific Q&A pairs.
- **`production_traces`** — filters production MLflow traces tagged `eval_candidate=true`.

After running the notebook, verify:
```bash
databricks sql statement-execute \
  --statement "SELECT COUNT(*) FROM my_agent_dev.my_agent.my_agent_eval_dataset"
```

**Minimum:** 20 examples. Target: 50–100.

### Gate thresholds

`src/agents/my_agent/eval/gates.yml` (generated by scaffold — adjust after first
baseline run):

```yaml
block:        # hard failures — block promotion if these regress
  - safety:
      floor: 4.0    # must score ≥ 4.0 out of 5

warn:         # soft failures — log and flag, do not block
  - relevance:
      tolerance: 0.05   # challenger may regress at most 5% vs champion

info:         # always logged, never blocks
  - fluency
```

### Run the gate locally

```bash
cd src/agents/my_agent
export CATALOG=my_agent_dev
export SCHEMA=my_agent
uv run python eval/evaluate_agent.py
```

Expected output on pass:
```
Gates config is valid.
Scorers to run: ['Safety', 'RelevanceToQuery', 'Fluency']
Loaded 50 examples from my_agent_dev.my_agent.my_agent_eval_dataset
Run ID: abc123...
============================================================
EVALUATION GATE RESULTS
============================================================
  PASS  safety: 4.600 (first run, no champion)
  PASS  relevance: 4.100 (first run, no champion)
  INFO  fluency: 4.500 (first run, no champion)
============================================================
Result: PASSED
All gates passed. Agent is ready for promotion.
```

If safety scores below the floor, review flagged traces in MLflow, add input/output
guardrails in `graph.py`, then re-run. **Do not lower the safety floor to pass.**

### Custom scorer (optional)

Register domain-specific scorers in `src/components/eval/scorers.py` (generated):

```python
# src/components/eval/scorers.py — add custom scorers here, then reference by name in gates.yml
import mlflow

@mlflow.trace
def domain_accuracy(inputs, outputs, expectations):
    """Score whether the answer matches domain expectations."""
    # Return a float score compatible with mlflow.genai.evaluate
    ...
```

Reference the scorer name in `gates.yml` under `block`, `warn`, or `info`.

### Done when

- Eval table `my_agent_dev.my_agent.my_agent_eval_dataset` has ≥20 examples.
- `uv run python eval/evaluate_agent.py` exits 0 — all block thresholds met.
- MLflow experiment `/Shared/my_agent_my_agent_eval` has at least one eval run.

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
        # With LangChain autolog the root span is typically "ChatDatabricks" or "agent_node"
        root_span = spans[0] if spans else None
        if root_span:
            traces.append({
                "trace_id": trace.info.request_id,
                "input": str(root_span.inputs),
                "output": str(root_span.outputs),
            })

df = pd.DataFrame(traces)
df.to_csv("docs/sme_traces_for_review.csv", index=False)
print(f"Exported {len(df)} traces to docs/sme_traces_for_review.csv")
```

Share the CSV (or a Databricks App backed by the MLflow Trace UI) with the
domain SME. Add score columns for them to fill:

| trace_id | input | output | sme_accuracy_1_5 | sme_tone_1_5 | sme_complete_1_5 | sme_safe_pass_fail |
|---|---|---|---|---|---|---|

### Calibration run

After SME scoring is returned, compare against judge scores:

```python
# Run evaluation on the same traces using the LLM judge
result = mlflow.genai.evaluate(
    data=pd.read_csv("docs/sme_traces_for_review.csv"),
    predict_fn=lambda q: ...,  # re-invoke agent on the same queries
    scorers=[mlflow.genai.scorers.Correctness(), mlflow.genai.scorers.Safety()],
)

# Compare judge scores to SME scores — compute agreement rate
import numpy as np
sme_df = pd.read_csv("docs/sme_traces_for_review.csv")
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

Create `docs/sme_calibration.md`:

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

- `docs/sme_calibration.md` exists with reviewer name, date, agreement %, and explicit sign-off.
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
  --body "Adds agent code, eval dataset (50 examples in UC), eval gate (safety floor 4.0), and SME calibration sign-off."
```

### What CI runs

The CI workflow (`.github/workflows/my_agent-bundle-ci.yml`, generated by
scaffold) runs three jobs:

```yaml
# Generated by scaffold — do not modify the gate-triggering logic
jobs:
  unit_tests:
    # uv sync (from src/agents/my_agent/) + uv run pytest ../../../tests/
  validate_bundle:
    # databricks bundle validate -t staging
  detect_patterns:
    # find src/agents -name "gates.yml" -path "*/eval/gates.yml"
  eval_gate:
    # if: detect_patterns outputs has_eval == 'true'
    # for each src/agents/*/eval/gates.yml:
    #   cd <agent_dir> && uv sync && uv run python eval/evaluate_agent.py
    # uses DATABRICKS_TOKEN: ${{ secrets.STAGING_WORKSPACE_TOKEN }}
```

CI secrets required (set in GitHub repo settings before opening the PR):
- `STAGING_WORKSPACE_TOKEN` — staging workspace token (or OIDC service principal)
- `DATABRICKS_HOST` — staging workspace URL (set in `databricks.yml` targets.staging)

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
that call the staging Databricks App:

```python
# tests/test_agent_integration.py
import os
import httpx
import pytest
import mlflow

STAGING_APP_URL = os.environ.get("STAGING_APP_URL", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")

@pytest.fixture(scope="session")
def agent_url():
    if not STAGING_APP_URL:
        pytest.skip("STAGING_APP_URL not set — get it from: databricks apps get <app-name>")
    return STAGING_APP_URL

def test_agent_returns_response(agent_url):
    resp = httpx.post(
        f"{agent_url}/invocations",
        headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"},
        json={"messages": [{"role": "user", "content": "What is Databricks?"}]},
        timeout=30.0,
    )
    assert resp.status_code == 200
    body = resp.json()
    # AgentServer response has "output" list; chat proxy response has "choices"
    assert body.get("output") or body.get("choices")

def test_agent_handles_empty_messages(agent_url):
    """Agent should return 4xx or a structured error, not 500."""
    resp = httpx.post(
        f"{agent_url}/invocations",
        headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"},
        json={"messages": []},
        timeout=30.0,
    )
    assert resp.status_code != 500

def test_mlflow_traces_logged(agent_url):
    """Each invocation must produce an MLflow trace."""
    client = mlflow.tracking.MlflowClient()
    experiment = client.get_experiment_by_name("/Shared/my_agent_my_agent_eval")
    before_count = len(client.search_traces(
        experiment_ids=[experiment.experiment_id], max_results=1000
    )) if experiment else 0
    httpx.post(
        f"{agent_url}/invocations",
        headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"},
        json={"messages": [{"role": "user", "content": "trace check"}]},
        timeout=30.0,
    )
    if experiment:
        after_count = len(client.search_traces(
            experiment_ids=[experiment.experiment_id], max_results=1000
        ))
        assert after_count > before_count, "Invocation did not log an MLflow trace"
```

Get the staging App URL after deploy:

```bash
databricks apps get <app-name> --profile <staging-profile>
# Returns the App URL — set as STAGING_APP_URL for the integration test run
```

Run locally against staging:

```bash
export STAGING_APP_URL=https://<staging-app-url>
export DATABRICKS_TOKEN=<staging-token>
cd src/agents/my_agent && uv run pytest ../../../tests/test_agent_integration.py -v
```

### Done when

- Databricks App is live and reachable in staging workspace.
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

# Get the prod App URL
databricks apps get <app-name> --profile <prod-profile>

# Smoke test — confirm agent responds
APP_URL="https://<prod-app-url>"
curl -X POST "$APP_URL/invocations" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "smoke test"}]}'
```

The App is healthy when `/health` returns HTTP 200 and the smoke test returns
a non-empty `output` (or `choices`) field.

### Done when

- CD workflow exits 0 and prod bundle is deployed.
- Databricks App is reachable at the prod workspace App URL.
- Smoke test: agent returns HTTP 200 with a non-empty response.
- MLflow traces appear in the prod experiment after the smoke test request.

---

## Step 9 — Batch Inferencing & Production Eval Baseline

Run batch inferencing on a representative production dataset to establish a
quality baseline **before opening to users**. Production data distributions
differ from golden datasets — the batch eval is the first real-world quality
check.

### Batch inferencing job

Add a Databricks Job to `resources/` for batch inference. The job calls the
agent's App endpoint for each row in the input table:

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
              app_name: "${bundle.name}_my_agent"
              input_table: "${var.catalog}.${var.schema}.batch_eval_inputs"
              output_table: "${var.catalog}.${var.schema}.batch_eval_outputs"
```

```python
# notebooks/batch_inference.py
# Databricks notebook source

# COMMAND ----------
import httpx
import pandas as pd
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("app_name", "")
dbutils.widgets.text("input_table", "")
dbutils.widgets.text("output_table", "")

app_name = dbutils.widgets.get("app_name")
input_table = dbutils.widgets.get("input_table")
output_table = dbutils.widgets.get("output_table")

# COMMAND ----------
w = WorkspaceClient()
app = w.apps.get(app_name)
app_url = f"https://{app.url}"
token = w.config.token

input_df = spark.table(input_table).toPandas()

results = []
for _, row in input_df.iterrows():
    resp = httpx.post(
        f"{app_url}/invocations",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": row["query"]}]},
        timeout=60.0,
    )
    resp.raise_for_status()
    results.append(resp.json())

output_df = pd.DataFrame({"query": input_df["query"], "response": results})
spark.createDataFrame(output_df).write.mode("overwrite").saveAsTable(output_table)
print(f"Batch inference complete: {len(output_df)} rows written to {output_table}")
```

### Run eval gate on batch output

Tag batch output traces as eval candidates, then rebuild the prod eval dataset
in Unity Catalog and re-run the eval gate:

```bash
cd src/agents/my_agent
export CATALOG=my_agent_prod
export SCHEMA=my_agent
uv run python eval/evaluate_agent.py
```

### Log baseline metrics

Create `docs/production_baseline.md`:

```markdown
# Production Eval Baseline

- **Date:** 2025-06-15
- **Dataset:** my_agent_prod.my_agent.batch_eval_inputs (500 rows)
- **Agent:** my_agent_prod_my_agent (Databricks App, v1)

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
- Eval gate passes on production batch results — all block thresholds met.
- `docs/production_baseline.md` has P95 latency, Safety/mean, Correctness/mean, cost/request.

---

## Step 10 — Production Monitoring & Continuous Feedback Loop

Wire the complete production observability stack. This step closes the
continuous improvement loop: production traces feed back into the eval dataset,
driving future iterations.

### Verify MLflow tracing on the App

The agent enables `mlflow.langchain.autolog()` in `agent.py` on startup. Traces
are sent to the MLflow tracking server configured in the App environment
(`DATABRICKS_HOST` and token from the Databricks App runtime). Verify:

```bash
# Check that traces appear in the prod MLflow experiment after a live request
databricks experiments list --max-results 10
# Find /Shared/my_agent_my_agent_eval and confirm recent runs exist
```

No additional configuration is required — the App runtime provides workspace
credentials automatically, and LangChain autolog captures every graph invocation.

### Wire user feedback

Add a `/feedback` endpoint to the agent's FastAPI app (alongside AgentServer routes):

```python
# In src/agents/my_agent/app/start_server.py — add after agent_server is constructed
import mlflow
from fastapi import Request
from fastapi.responses import JSONResponse

@agent_server.app.post("/feedback")
async def collect_feedback(req: Request):
    body = await req.json()
    mlflow.log_feedback(
        trace_id=body["trace_id"],
        name="user_satisfaction",
        value=1.0 if body.get("thumbs_up") else 0.0,
        rationale=body.get("comment", ""),
    )
    return JSONResponse({"status": "ok"})
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
- How to tag production traces as `eval_candidate=true` to grow the eval dataset

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
| `uv run python eval/evaluate_agent.py` exits non-zero with "CATALOG not set" | Env vars not exported | `export CATALOG=my_agent_dev && export SCHEMA=my_agent` |
| `Could not load eval table` in evaluate_agent.py | Eval dataset not yet created | Run `eval/create_dataset.py` as a Databricks notebook first |
| MLflow traces not appearing after App request | `mlflow.langchain.autolog()` disabled or DATABRICKS_HOST not set in App env | Confirm `mlflow.langchain.autolog()` is called in `agent.py`; check App env vars in `databricks.yml` |
| CI eval gate fails after local gate passes | Different `CATALOG`/`SCHEMA` in CI vs. local | Ensure `DATABRICKS_TOKEN` and workspace host in CI point to the staging workspace where the eval table exists |
| App returns HTTP 502 or connection refused | App not yet started or failed to deploy | Check App logs: `databricks apps logs <app-name>`; verify `app.yaml` entry point matches `start_server.py` |
| `uv sync` fails in CI | No `uv.lock` committed | Run `uv sync` locally from `src/agents/<name>/`, commit `uv.lock` |
| VS index query returns no results | Index not synced after data write | Trigger a manual sync: `w.vector_search_indexes.sync_index("my_agent_dev.my_agent.docs_index")` |
| `databricks bundle deploy -t staging` fails with auth error | Service principal not configured in CI secrets | Set `STAGING_WORKSPACE_TOKEN` secret in GitHub repo settings |

---

## Reference files

| File | Role |
|---|---|
| `src/agents/<name>/eval/evaluate_agent.py` | Eval runner — runs at dev (local), CI (PR), and staging/prod (post-deploy). Do not disable. |
| `src/agents/<name>/eval/gates.yml` | Gate thresholds — presence triggers CI eval gate. Adjust after baseline runs. |
| `src/agents/<name>/eval/create_dataset.py` | Eval dataset builder — run as a Databricks notebook to populate the UC eval table. |
| `src/agents/<name>/eval/utils.py` | Pure-Python gate logic — unit-testable without Spark or a workspace connection. |
| `docs/sme_calibration.md` | SME sign-off document (user-created). Required before staging promotion. |
| `docs/production_baseline.md` | Production quality baseline (user-created). Required before user traffic. |
| `databricks.yml` | DAB config — three targets (dev/staging/prod), vars, resources. Source of truth for what deploys. |
| `.agentops-stacks/manifest.yml` | Scaffold contract. Records which patterns have been applied. |
| `workflows/single-account-single-agent.json` | Machine-readable lifecycle definition with all validations and escalation hints. |
