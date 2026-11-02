---
name: vector-search-ops
description: Operate and troubleshoot the Vector Search component in an AgentOps Stacks project — check index status, trigger sync, test the retriever, update the DLT data pipeline. Use when the user needs to manage their VS index or debug retrieval quality.
---

# vector-search-ops — Vector Search Operations

Covers day-to-day operations for the `resources/vector_search.yml` component scaffolded by AgentOps Stacks: endpoint health, index sync, retriever testing, and DLT pipeline changes.

## When to use

- "my retriever isn't returning results"
- "how do I re-sync the index after adding documents?"
- "check vector search status"
- "the DLT pipeline failed"
- "test the retriever"
- "how do I update the embedding source?"

## Key resources in the project

| File | Purpose |
|---|---|
| `resources/vector_search.yml` | DAB resource: VS endpoint + delta-sync index |
| `src/components/retriever/data_pipeline.py` | DLT pipeline: raw docs → chunked docs → VS index |
| `src/agents/<name>/graph.py` | Retriever wiring (`get_relevant_chunks`, `retriever_node`) |

The index is named `<catalog>.<schema>.<project>_vs_index` and syncs from `<catalog>.<schema>.<project>_chunked_docs`.

With usage tracking enabled, the VS endpoint is attributed via `budget_policy_id: ${var.usage_policy_id}` (a serverless usage policy). VS endpoints don't take custom tags directly. The data pipeline carries `tags` (`project`, `environment`). Keep both when editing these resources, and add them to any new endpoint or pipeline. See the `usage-tracking-ops` skill.

---

## Operations

### 1. Check endpoint and index status

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# Endpoint
ep = w.vector_search_endpoints.get_endpoint("<project>_vs_endpoint")
print(ep.endpoint_status)  # ONLINE / OFFLINE / PROVISIONING

# Index
idx = w.vector_search_indexes.get_index(
    index_name="<catalog>.<schema>.<project>_vs_index"
)
print(idx.status)           # ONLINE / PROVISIONING / FAILED
print(idx.index_url)        # endpoint URL
```

Or via CLI:
```bash
databricks vector-search endpoints get --name <project>_vs_endpoint
databricks vector-search indexes get-index --index-name <catalog>.<schema>.<project>_vs_index
```

### 2. Trigger a manual sync

The index uses `pipeline_type: TRIGGERED` — it does NOT auto-sync on table writes. Trigger it explicitly after new documents are ingested:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

w.vector_search_indexes.sync_index(
    index_name="<catalog>.<schema>.<project>_vs_index"
)
print("Sync triggered — check status with get_index()")
```

Wait for sync to complete before testing:
```python
import time
while True:
    idx = w.vector_search_indexes.get_index(index_name="<catalog>.<schema>.<project>_vs_index")
    if idx.status.detailed_state in ("ONLINE", "ONLINE_NO_PENDING_UPDATE"):
        break
    print(f"  {idx.status.detailed_state} — waiting...")
    time.sleep(15)
```

### 3. Test the retriever

Run a quick retrieval test without starting the full agent:

```python
from databricks.sdk import WorkspaceClient
from databricks_langchain import DatabricksVectorSearch
import os

w = WorkspaceClient()
vs_index = "<catalog>.<schema>.<project>_vs_index"

retriever = DatabricksVectorSearch(
    index_name=vs_index,
    columns=["content", "doc_uri"],
    workspace_client=w,
).as_retriever(search_kwargs={"k": 5})

docs = retriever.invoke("your test query here")
for doc in docs:
    print(f"[{doc.metadata.get('doc_uri', '?')}]\n{doc.page_content[:200]}\n")
```

### 4. Ingest new documents

New documents go into the UC Volume at `/Volumes/<catalog>/<schema>/artifacts/raw_docs/`.

After uploading:
1. Run the DLT pipeline (`data_pipeline.py`) to update the `_chunked_docs` table
2. Trigger the VS index sync (step 2 above)

```bash
# Upload a file to the volume
databricks fs cp my_doc.pdf dbfs:/Volumes/<catalog>/<schema>/artifacts/raw_docs/

# Run DLT pipeline via bundle
databricks bundle run -t dev data_pipeline

# Then trigger sync (Python snippet above or SDK)
```

### 5. Update the DLT pipeline (chunking logic)

Edit `src/components/retriever/data_pipeline.py`. The two DLT tables are:

- `<project>_raw_docs` — reads from the UC Volume
- `<project>_chunked_docs` — apply chunking here

Common changes:
- **Different source format** — swap `cloudFiles.format` in `raw_docs()`
- **Custom chunking** — replace the body of `chunked_docs()` (LangChain splitters, unstructured.io, etc.)
- **Add metadata columns** — extend `.select()` and `columns_to_sync` in `vector_search.yml`

After editing, redeploy:
```bash
databricks bundle deploy -t dev
databricks bundle run -t dev data_pipeline
# then trigger sync
```

### 6. Change the embedding model

In `resources/vector_search.yml`, update the `embedding_model_endpoint` variable or the `embedding_model_endpoint_name` field on the index. The built-in default is `databricks-gte-large-en`.

**Note:** Changing the embedding model requires rebuilding the index from scratch. Delete and recreate the index (or undeploy + redeploy the bundle resource).

```bash
databricks bundle destroy -t dev  # removes VS endpoint + index
databricks bundle deploy -t dev   # recreates with new model
databricks bundle run -t dev data_pipeline
# then sync
```

### 7. Increase `k` (number of retrieved chunks)

In `src/agents/<name>/graph.py`, `get_relevant_chunks(query, k=5)` — increase `k` for broader retrieval, decrease for more precise context.

Also adjustable per-call:
```python
retriever.as_retriever(search_kwargs={"k": 10})
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Index stuck `PROVISIONING` | VS endpoint not ready | Wait; endpoint creation takes 5–10 min on first deploy |
| Empty results | Index not synced after ingestion | Trigger sync (step 2) |
| Empty results | Chunked docs table empty | Run DLT pipeline first |
| `FAILED` index status | Embedding model endpoint down | Check `databricks-gte-large-en` is available in your workspace |
| Retriever returns irrelevant chunks | `k` too high or chunking too coarse | Reduce `k`, improve chunking in `data_pipeline.py` |
| `403` on `sync_index` | App SP lacks permission | Grant `SELECT` on the chunked_docs table to the app SP |
| Column not returned in results | Column not in `columns_to_sync` | Add it in `resources/vector_search.yml` and re-sync |

## Environment variables (set in `databricks.yml`)

The agent App's env lives in `resources.apps.<agent>.config.env`, resolved per target:

```yaml
env:
  - name: CATALOG
    value: ${var.catalog}
  - name: SCHEMA
    value: ${resources.schemas.project_schema.name}   # dev-prefixed in development mode
```

The retriever in `graph.py` reads `os.environ["CATALOG"]` and `os.environ["SCHEMA"]` to build the index name at runtime.
