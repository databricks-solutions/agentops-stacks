# Sync Index Notebook

Lightweight notebook that triggers a Vector Search index sync. Used as a DAB job task — either standalone or chained after data ingestion/preparation.

## Code

```python
# Databricks notebook source

# MAGIC %md
# MAGIC # Sync Vector Search Index
# MAGIC Triggers a sync for a TRIGGERED pipeline index and waits for completion.

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "", "Unity Catalog name")
dbutils.widgets.text("schema", "", "Schema name")
dbutils.widgets.text("index_suffix", "_vs_index", "Index name suffix")
dbutils.widgets.text("project_name", "", "Project name")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
project_name = dbutils.widgets.get("project_name")
index_suffix = dbutils.widgets.get("index_suffix")

VS_INDEX_NAME = f"{catalog}.{schema}.{project_name}{index_suffix}"

# COMMAND ----------

w = WorkspaceClient()

# Trigger sync
w.vector_search_indexes.sync_index(index_name=VS_INDEX_NAME)
print(f"Sync triggered for: {VS_INDEX_NAME}")

# COMMAND ----------

# Poll until sync completes
MAX_WAIT = 1800  # 30 minutes
POLL_INTERVAL = 30  # seconds
elapsed = 0

while elapsed < MAX_WAIT:
    index = w.vector_search_indexes.get_index(index_name=VS_INDEX_NAME)
    if index.status.ready:
        print(f"Index is ONLINE. Rows indexed: {index.status.indexed_row_count}")
        break
    print(f"Waiting... status: {index.status.message} ({elapsed}s elapsed)")
    time.sleep(POLL_INTERVAL)
    elapsed += POLL_INTERVAL
else:
    raise TimeoutError(
        f"Index {VS_INDEX_NAME} did not become ready within {MAX_WAIT}s. "
        f"Last status: {index.status.message}"
    )
```

## DAB job task wiring

Pass bundle variables as task parameters:

```yaml
- task_key: sync_index
  depends_on:
    - task_key: prepare_and_chunk
  notebook_task:
    notebook_path: ./src/components/retriever/sync_index.py
    base_parameters:
      catalog: "${var.catalog}"
      schema: "${var.schema}"
      project_name: "${var.project_name}"
  job_cluster_key: pipeline_cluster
```
