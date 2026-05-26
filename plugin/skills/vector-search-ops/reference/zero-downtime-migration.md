# Zero-Downtime Index Migration

When you need to change an immutable index property (embedding model, columns_to_sync, endpoint type) in production without downtime.

## Why you need this

Vector Search indexes cannot be altered after creation. Changing any of these requires delete + recreate:

- `embedding_model_endpoint_name`
- `columns_to_sync`
- `embedding_dimension` (self-managed)
- Endpoint type (Standard ↔ Storage-Optimized)

Deleting the active index means the agent has no retriever until the new index is synced and online. For production, this is unacceptable.

## Strategy: Blue-green index swap

### Prerequisites

The index name must be a bundle variable so you can swap it without code changes:

```yaml
# databricks.yml
variables:
  vs_index_suffix:
    description: Index name suffix (change for blue-green migration)
    default: "_vs_index"
```

The app reads this at runtime:

```python
# search.py
import os
CATALOG = os.environ["CATALOG"]
SCHEMA = os.environ["SCHEMA"]
VS_INDEX_SUFFIX = os.environ.get("VS_INDEX_SUFFIX", "_vs_index")
VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.{project_name}{VS_INDEX_SUFFIX}"
```

### Migration steps

```
1. Create new index (green)
   └─ Name: {project}_vs_index_v2
   └─ New config (model, columns, etc.)
   └─ Same endpoint (or new endpoint if changing type)

2. Sync green index and wait for ONLINE
   └─ Monitor: w.vector_search_indexes.get_index() → status.ready

3. Validate green index
   └─ Run eval suite against green index
   └─ Compare retrieval quality metrics vs blue (current)

4. Swap: update bundle variable
   └─ vs_index_suffix: "_vs_index_v2"
   └─ databricks bundle deploy -t prod

5. Verify agent is using green index
   └─ Check app logs, query traces

6. Decommission blue index
   └─ w.vector_search_indexes.delete_index(index_name="..._vs_index")
```

### Script

```python
# migration_create_green.py — Run manually or as a one-off job
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    PipelineType,
)

w = WorkspaceClient()

# --- Config: edit these ---
CATALOG = "my_project_prod"
SCHEMA = "my_project"
PROJECT = "my_project"
ENDPOINT = "prod-my_project-vs-endpoint"
NEW_SUFFIX = "_vs_index_v2"
NEW_MODEL = "databricks-qwen3-embedding-0-6b"  # the change
COLUMNS = ["chunk_id", "content", "doc_uri"]
SOURCE_TABLE = f"{CATALOG}.{SCHEMA}.{PROJECT}_chunked_docs"
# --------------------------

NEW_INDEX = f"{CATALOG}.{SCHEMA}.{PROJECT}{NEW_SUFFIX}"

w.vector_search_indexes.create_index(
    name=NEW_INDEX,
    endpoint_name=ENDPOINT,
    primary_key="chunk_id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
        source_table=SOURCE_TABLE,
        pipeline_type=PipelineType.TRIGGERED,
        embedding_source_columns=[
            EmbeddingSourceColumn(
                name="content",
                embedding_model_endpoint_name=NEW_MODEL,
            )
        ],
        columns_to_sync=COLUMNS,
    ),
)

print(f"Created green index: {NEW_INDEX}")

# Trigger sync
w.vector_search_indexes.sync_index(index_name=NEW_INDEX)
print("Sync triggered. Monitor with: w.vector_search_indexes.get_index()")
```

### Endpoint type migration

If changing endpoint type (e.g., Standard → Storage-Optimized), you also need a new endpoint:

1. Create new endpoint with desired type
2. Create green index on the new endpoint
3. After swap, delete old index, then delete old endpoint

Endpoints are also immutable — you cannot change their type after creation.

### Rollback

If the green index has quality issues:

1. Revert `vs_index_suffix` to the original value
2. Redeploy: `databricks bundle deploy -t prod`
3. Delete the green index

The blue index is still serving until you explicitly delete it — so rollback is just a variable change.
