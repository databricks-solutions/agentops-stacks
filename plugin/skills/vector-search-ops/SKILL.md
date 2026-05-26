---
name: vector-search-ops
description: Operational guide for Databricks Vector Search in DAB projects — sync scheduling, environment strategy, index lifecycle, monitoring, and cost. Use when deploying, promoting, or operating a RAG agent. Triggers on "vector search ops", "VS sync job", "how should I deploy my index", "vector search monitoring", "RAG ops", "vector search environments".
---

# VectorSearchOps — Operational Decisions for Vector Search

This skill guides the operational setup for Vector Search in a DAB-managed agent project. It does **not** cover coding patterns or API usage — it covers what infrastructure, jobs, monitoring, and environment strategy you need based on your design choices.

## When to Use

- Deploying a RAG agent to dev/staging/prod
- Deciding how to schedule index syncs
- Planning multi-environment promotion for Vector Search
- Setting up monitoring and alerts for index health
- Estimating or reducing Vector Search costs
- Migrating an index (new embedding model, new columns, endpoint type change)

## Decision Tree

Work through these in order. Each decision emits concrete DAB resources or runbook steps.

```
1. Sync strategy?
   ├─ TRIGGERED → Need a sync job (question 2)
   └─ CONTINUOUS → No job, but always-on cost (skip to question 3)

2. Sync frequency?
   ├─ After each ingestion → Chain sync as downstream task in ingestion job
   ├─ On a schedule → Cron job (hourly, daily, etc.)
   └─ Manual only → No job, user calls sync_index() ad hoc

3. Environment strategy?
   ├─ Dev: Shared endpoint? Sampled data? Skip index entirely?
   ├─ Staging: Representative data? Same endpoint type as prod?
   └─ Prod: Dedicated endpoint, full data, real config

4. How does CI test retrieval?
   ├─ Mock the retriever (fastest, no infra needed)
   ├─ Shared long-lived test index (moderate, needs maintenance)
   └─ Ephemeral index from sample data (slowest, most realistic)

5. What do we monitor?
   └─ See monitoring section below

6. How do we handle config changes (model, columns)?
   └─ See migration section below
```

## 1. Sync Strategy

### TRIGGERED (recommended default)

The index only updates when you call `sync_index()`. You control cost and timing.

**You need a job.** Two patterns:

#### Pattern A: Chain sync after ingestion

Best when the ingestion job is already a DAB job. Add a sync task as a downstream dependency.

```yaml
# resources/jobs/data_pipeline.yml
resources:
  jobs:
    data_pipeline:
      name: "${bundle.target}-${var.project_name}-data-pipeline"
      tasks:
        - task_key: ingest
          notebook_task:
            notebook_path: ./src/components/retriever/data_ingestion.py
            base_parameters:
              catalog: "${var.catalog}"
              schema: "${var.schema}"
          job_cluster_key: pipeline_cluster

        - task_key: prepare_and_chunk
          depends_on:
            - task_key: ingest
          notebook_task:
            notebook_path: ./src/components/retriever/data_preparation.py
            base_parameters:
              catalog: "${var.catalog}"
              schema: "${var.schema}"
              embedding_model_endpoint: "${var.embedding_model_endpoint}"
              vs_columns_to_sync: "${var.vs_columns_to_sync}"
          job_cluster_key: pipeline_cluster

        - task_key: sync_index
          depends_on:
            - task_key: prepare_and_chunk
          notebook_task:
            notebook_path: ./src/components/retriever/sync_index.py
            base_parameters:
              catalog: "${var.catalog}"
              schema: "${var.schema}"
          job_cluster_key: pipeline_cluster

      job_clusters:
        - job_cluster_key: pipeline_cluster
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            num_workers: 0
            node_type_id: "${var.node_type_id}"

      schedule:
        quartz_cron_expression: "0 0 2 * * ?"  # Daily at 2 AM
        timezone_id: "UTC"
```

#### Pattern B: Standalone sync job

Best when ingestion happens outside the bundle (e.g., Lakeflow Connect, external ETL).

```yaml
# resources/jobs/vs_sync.yml
resources:
  jobs:
    vs_sync:
      name: "${bundle.target}-${var.project_name}-vs-sync"
      tasks:
        - task_key: sync
          notebook_task:
            notebook_path: ./src/components/retriever/sync_index.py
            base_parameters:
              catalog: "${var.catalog}"
              schema: "${var.schema}"
      schedule:
        quartz_cron_expression: "0 0 * * * ?"  # Hourly
        timezone_id: "UTC"
```

Both patterns need a `sync_index.py` notebook. See [reference/sync-index-notebook.md](reference/sync-index-notebook.md).

### CONTINUOUS

No sync job needed. The DLT pipeline runs continuously and picks up source table changes automatically.

**Constraints:**
- Only works on STANDARD endpoints (not Storage-Optimized)
- Always-on compute cost for the DLT pipeline
- Cannot call `sync_index()` manually

**When to use:** Source data changes frequently (minutes, not hours) AND query freshness is critical AND cost is acceptable.

## 2. Environment Strategy

Not every environment needs a full production-grade index.

| Environment | Endpoint | Index | Source Data | Purpose |
|-------------|----------|-------|-------------|---------|
| **Dev** | Shared across dev targets | Small index from sampled table | 100-1000 rows | Validate agent logic, retriever wiring |
| **Staging** | Dedicated, same type as prod | Representative index | Full or large sample | Validate sync pipeline, query latency, eval suite |
| **Prod** | Dedicated | Full index | Full data | Production serving |

### Dev: Minimize cost

Dev doesn't need its own endpoint. Options:

**Option A: Shared dev endpoint (recommended)**

Define one endpoint in a shared resource file. All dev targets use it.

```yaml
# databricks.yml — dev target
targets:
  dev:
    variables:
      vs_endpoint_name: "shared-dev-vs-endpoint"
```

**Option B: Skip index creation in dev, mock the retriever**

In `search.py`, fall back gracefully if the index doesn't exist:

```python
import os

def get_relevant_chunks(query: str, k: int = 5) -> list[str]:
    if os.environ.get("MOCK_RETRIEVER", "false") == "true":
        return ["[mock] Sample chunk for development testing."]
    # ... real retriever logic
```

Set `MOCK_RETRIEVER=true` in the dev app config.

**Option C: Point dev at staging's index (read-only)**

If staging has a representative index, dev agents can query it. No dev index needed at all. Just set the index name variable to point to staging's index.

### Staging: Validate the full pipeline

Staging should run the complete data_preparation notebook to validate:
- CDF is enabled correctly on the source table
- Index creation is idempotent
- Sync completes without errors
- Eval suite passes with the real retriever

Use the same endpoint type as prod so latency characteristics match.

### Prod: No surprises

Prod uses its own dedicated endpoint, full source data, and the real embedding model. The only thing that should differ between staging and prod is the data volume and the target variables (`catalog`, `schema`).

### DAB variables for per-environment config

```yaml
variables:
  vs_endpoint_name:
    description: Vector Search endpoint name
    default: "${bundle.target}-${var.project_name}-vs-endpoint"

targets:
  dev:
    variables:
      vs_endpoint_name: "shared-dev-vs-endpoint"
  staging:
    variables:
      vs_endpoint_name: "staging-${var.project_name}-vs-endpoint"
  prod:
    variables:
      vs_endpoint_name: "prod-${var.project_name}-vs-endpoint"
```

## 3. CI Testing Strategy

| Approach | Speed | Realism | Infra Cost | Best For |
|----------|-------|---------|------------|----------|
| **Mock retriever** | Fast | Low | None | Unit tests, agent logic validation |
| **Shared test index** | Medium | Medium | Low (one index) | Integration tests in CI |
| **Ephemeral index from sample** | Slow (minutes) | High | Medium | Pre-merge validation |

**Recommendation:** Mock for unit tests, shared test index for integration tests. Ephemeral indexes are too slow for CI unless you run them nightly.

For the shared test index approach, create a small fixture table (50-100 rows) in a CI catalog and a persistent index. CI jobs query this index — they don't create or sync it.

## 4. Monitoring

### What to monitor

| Signal | How | Alert Threshold |
|--------|-----|-----------------|
| **Index sync status** | `w.vector_search_indexes.get_index()` → `status.ready` | `ready == False` for >30 min after sync trigger |
| **Endpoint health** | `w.vector_search_endpoints.get_endpoint()` → `endpoint_status.state` | `YELLOW_STATE` or `RED_STATE` |
| **Row count drift** | Compare `indexed_row_count` vs source table `COUNT(*)` | Drift > 10% after sync completes |
| **Query latency** | Application-level metrics (MLflow traces) | p99 > 500ms (Standard) or p99 > 2s (Storage-Optimized) |
| **Sync job failures** | DAB job alerts (built-in) | Any failure |

### DAB job alert for sync failures

```yaml
# In the sync job definition
email_notifications:
  on_failure:
    - "team-alerts@company.com"
```

### Monitoring notebook

See [reference/monitoring-notebook.md](reference/monitoring-notebook.md) for a ready-to-use health check notebook that can run as a scheduled job.

## 5. Cost Model

| Component | Cost Driver | How to Reduce |
|-----------|------------|---------------|
| **Endpoint** | Always-on compute. Standard costs ~7x more than Storage-Optimized | Use Storage-Optimized unless you need <100ms latency |
| **Sync pipeline** | DLT compute per sync. CONTINUOUS = always running | Use TRIGGERED with appropriate frequency |
| **Embedding compute** | Per-token cost on FMAPI endpoint during sync | Use provisioned throughput for predictable cost at scale |
| **Storage** | Proportional to `columns_to_sync` × row count | Only sync columns you need in query results |
| **Dev/staging endpoints** | Same as prod if dedicated | Share endpoints in dev, reduce data volume in staging |

**Quick cost estimate:** For a typical RAG index with 100K chunks, a Standard endpoint costs ~$X/month (always-on) + sync compute. Storage-Optimized is ~7x cheaper on the endpoint alone. The biggest lever is endpoint type selection.

## 6. Index Migration (Config Changes)

Vector Search indexes are **immutable** — you cannot alter the embedding model, columns_to_sync, or endpoint type after creation. Any config change requires delete + recreate.

### Migration runbook

1. **Update bundle variables** (`embedding_model_endpoint`, `vs_columns_to_sync`) in `databricks.yml`
2. **Deploy to staging** — the data_preparation notebook will detect the existing index name and skip creation
3. **Delete the old staging index** manually or via a migration script:
   ```python
   w.vector_search_indexes.delete_index(index_name="...")
   ```
4. **Re-run data_preparation** — creates the index with new config
5. **Run eval suite** on staging to validate retrieval quality
6. **Repeat for prod** once staging passes

### Zero-downtime migration (advanced)

For prod where you can't tolerate downtime:

1. Create a new index with a versioned name (e.g., `_vs_index_v2`)
2. Sync and wait for ONLINE
3. Update the `VS_INDEX_NAME` variable and redeploy the agent app
4. Delete the old index

This requires the index name to be a bundle variable. See [reference/zero-downtime-migration.md](reference/zero-downtime-migration.md).

## 7. Access Control Checklist

| Principal | Needs | On What |
|-----------|-------|---------|
| **Deploying user / SP** | `CREATE TABLE` | Target schema |
| **Deploying user / SP** | Endpoint management | VS endpoint |
| **Deploying user / SP** | Model serving access | Embedding model endpoint |
| **App service principal** | Query index | VS index |
| **App service principal** | `USE CATALOG`, `USE SCHEMA` | Target catalog/schema |

## Reference Files

| Topic | File |
|-------|------|
| Sync index notebook | [reference/sync-index-notebook.md](reference/sync-index-notebook.md) |
| Monitoring notebook | [reference/monitoring-notebook.md](reference/monitoring-notebook.md) |
| Zero-downtime migration | [reference/zero-downtime-migration.md](reference/zero-downtime-migration.md) |
