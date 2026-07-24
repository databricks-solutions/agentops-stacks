---
name: lakebase-ops
description: Operate and troubleshoot the Lakebase (Autoscaling Postgres) memory component in an AgentOps Stacks project — check endpoint health, mint credentials, inspect or clear checkpointer (short-term) and store (long-term) tables, manage the Postgres schema. Use when the user's agent is having memory/persistence issues.
---

# lakebase-ops — Lakebase Memory Operations

Covers day-to-day operations for the `resources/lakebase.yml` component: the Lakebase
**Autoscaling** Postgres project used for agent memory. Depending on the project's
`input_memory_type`, it backs:

- **Short-term memory** — a LangGraph checkpointer (`databricks_langchain.AsyncCheckpointSaver`,
  a thin `AsyncPostgresSaver` subclass) storing conversation history in the `checkpoints*` tables.
- **Long-term memory** — a per-user semantic store (`databricks_langchain.AsyncDatabricksStore`)
  storing durable facts in the LangGraph store table, scoped by a `("user_memories", user_id)` namespace.

## When to use

- "agent lost conversation history"
- "lakebase connection failed"
- "token expired" or "authentication error connecting to postgres"
- "how do I clear memory for a user?"
- "inspect what's stored in the checkpointer"
- "the checkpointer isn't working"

## Key resources in the project

| File | Purpose |
|---|---|
| `resources/lakebase.yml` | DAB resource: `postgres_projects.memory` (Autoscaling project + auto-created `production` branch and read-write endpoint) |
| `src/agents/<name>/graph.py` | `get_async_checkpointer()` — opens an `AsyncCheckpointSaver` (short-term); `get_async_store()` — opens an `AsyncDatabricksStore` (long-term), both from databricks-langchain |
| `src/agents/<name>/tools.py` | `memory_tools()` — the `get`/`save`/`delete_user_memory` long-term tools (present only when long-term memory is enabled) |
| `src/agents/<name>/app.yaml` | `LAKEBASE_ENDPOINT` env var (full endpoint path) |

The project is named `<project>-memory`. Its default branch is `production` and the default
database is `databricks_postgres`. The endpoint path looks like
`projects/<project>-memory/branches/production/endpoints/<endpoint-id>`.

Autoscaling uses the `databricks postgres` CLI group and the `w.postgres` SDK namespace
(the old Provisioned `databricks database-instances` / `w.database` do not apply here).

---

## Operations

### 1. Check project and endpoint health

```bash
# List projects
databricks postgres list-projects

# Get the memory project
databricks postgres get-project projects/<project>-memory

# List endpoints on the production branch (find the read-write endpoint + its state)
databricks postgres list-endpoints projects/<project>-memory/branches/production
```

In Python:
```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

endpoint = "projects/<project>-memory/branches/production/endpoints/<endpoint-id>"
ep = w.postgres.get_endpoint(name=endpoint)
print(ep.status.current_state)     # endpoint state (running / suspended / etc.)
print(ep.status.hosts.host)        # host to use in a connection string
```

A scaled-to-zero (suspended) endpoint wakes on the first connection — expect brief
latency and retry.

### 2. Test database connectivity

Use `databricks-ai-bridge`'s `LakebaseClient` — it mints and rotates the short-lived,
Lakebase-scoped OAuth credentials for you (no manual `generate_database_credential`), so
the same SDK the agent relies on is used for ops too. Pass the endpoint path:

```python
from databricks_ai_bridge.lakebase import LakebaseClient

ENDPOINT = "projects/<project>-memory/branches/production/endpoints/<endpoint-id>"

with LakebaseClient(autoscaling_endpoint=ENDPOINT) as client:
    rows = client.execute("SELECT version()")
    print(rows[0])
print("Connection OK")
```

`LakebaseClient` is synchronous and wraps a psycopg connection pool. (The agent runtime
uses async classes — `AsyncCheckpointSaver` / `AsyncDatabricksStore` — because the LangGraph
runtime is async; for one-off ops scripts the sync client is simpler.)

If this fails, see the Troubleshooting section below.

### 3. Inspect checkpointer tables (short-term memory)

The `AsyncCheckpointSaver` (a LangGraph `AsyncPostgresSaver`) creates these tables on first call
to `checkpointer.setup()`:

- `checkpoints` — one row per (thread_id, checkpoint_id)
- `checkpoint_blobs` — serialized graph state
- `checkpoint_writes` — pending writes (cleared after commit)

```python
with LakebaseClient(autoscaling_endpoint=ENDPOINT) as client:
    # List threads with saved state
    rows = client.execute(
        "SELECT thread_id, MAX(checkpoint_id) AS latest FROM checkpoints GROUP BY thread_id ORDER BY latest DESC LIMIT 20"
    )
    for r in rows or []:
        print(r)

    # Count rows per table
    for t in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        n = client.execute(f"SELECT COUNT(*) FROM {t}")[0][0]
        print(f"{t}: {n} rows")
```

### 4. Clear memory for a thread

To reset a conversation thread (e.g. for a specific user session). `LakebaseClient.execute()`
autocommits, so the deletes persist immediately:

```python
thread_id = "user-123-session-abc"

with LakebaseClient(autoscaling_endpoint=ENDPOINT) as client:
    client.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
    client.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
    client.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))

print(f"Cleared memory for thread {thread_id}")
```

### 5. Clear all memory (reset checkpointer)

**Destructive.** Use in dev/staging only.

```python
with LakebaseClient(autoscaling_endpoint=ENDPOINT) as client:
    client.execute("TRUNCATE checkpoint_writes, checkpoint_blobs, checkpoints")
print("All checkpointer tables cleared")
```

### 5a. Inspect and clear long-term memory (store)

Only present when the project enables long-term memory (`input_memory_type` = `long_term` or `both`).
`AsyncDatabricksStore.setup()` creates the LangGraph store table (`store`, plus a vector table for
embeddings). Rows are namespaced; this project uses `("user_memories", <user-id>)` with the user id's
dots replaced by hyphens.

```python
with LakebaseClient(autoscaling_endpoint=ENDPOINT) as client:
    # List per-user memory namespaces and row counts
    rows = client.execute(
        "SELECT prefix, COUNT(*) FROM store GROUP BY prefix ORDER BY 2 DESC LIMIT 20"
    )
    for r in rows or []:
        print(r)
```

Clear one user's long-term memory (`user_id` with dots replaced by hyphens, matching the agent):

```python
user_ns = "user_memories.user-123"   # prefix is stored dot-joined: ("user_memories", "user-123")
with LakebaseClient(autoscaling_endpoint=ENDPOINT) as client:
    client.execute("DELETE FROM store WHERE prefix = %s", (user_ns,))
print(f"Cleared long-term memory for {user_ns}")
```

The exact store column/table names come from LangGraph's `PostgresStore` schema; if a query fails,
confirm them with `\d store` (psql) or inspect via `information_schema.columns`. To wipe all long-term
memory in dev, `TRUNCATE store` (and its vector companion table if present).

### 6. Verify env vars in `app.yaml`

The checkpointer in `graph.py` reads `LAKEBASE_ENDPOINT`; long-term memory additionally reads
`DATABRICKS_EMBEDDING_ENDPOINT` (default `databricks-gte-large-en`):

```yaml
# src/agents/<name>/app.yaml
env:
  - name: LAKEBASE_ENDPOINT
    value: projects/<project>-memory/branches/production/endpoints/<endpoint-id>
```

Get the endpoint path:
```bash
databricks postgres list-endpoints projects/<project>-memory/branches/production --output json | jq -r '.[].name'
```

After updating `app.yaml`:
```bash
databricks bundle deploy -t dev
```

### 7. Force memory table creation

If the agent starts but the memory tables don't exist yet (e.g. fresh project), run the same
`setup()` the agent runs on startup. `AsyncCheckpointSaver` / `AsyncDatabricksStore` are async
context managers that open the Lakebase pool on entry.

```python
import asyncio
from databricks_langchain import AsyncCheckpointSaver, AsyncDatabricksStore

ENDPOINT = "projects/<project>-memory/branches/production/endpoints/<endpoint-id>"

async def setup():
    # Short-term memory tables
    async with AsyncCheckpointSaver(autoscaling_endpoint=ENDPOINT) as checkpointer:
        await checkpointer.setup()
        print("Checkpointer tables created")

    # Long-term memory tables (only if long-term memory is enabled)
    async with AsyncDatabricksStore(
        autoscaling_endpoint=ENDPOINT,
        embedding_endpoint="databricks-gte-large-en",
        embedding_dims=1024,
    ) as store:
        await store.setup()
        print("Store tables created")

asyncio.run(setup())
```

### 8. Resize the endpoint

In `resources/lakebase.yml`, the compute range lives under `default_endpoint_settings`
(defaults 0.5–2 CU). Autoscale range is 0.5–32 CU with `max - min <= 16`.

```yaml
resources:
  postgres_projects:
    memory:
      default_endpoint_settings:
        autoscaling_limit_min_cu: 1
        autoscaling_limit_max_cu: 4   # increase for higher concurrency
```

Scale-to-zero is controlled by `suspend_timeout_duration` (e.g. `300s`); set
`no_suspension: true` to keep the endpoint always-on (lower latency, higher cost). The
template enables scale-to-zero on dev and leaves staging/prod always-on. Then redeploy:

```bash
databricks bundle deploy -t staging
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Running without memory` in agent logs | `LAKEBASE_ENDPOINT` not set in `app.yaml` | Add the env var and redeploy |
| `permission denied for schema` | App SP doesn't own the schema (you connected locally first) | Deploy the app before running locally so the SP creates and owns the schema; or drop the schema and redeploy |
| `Connection refused` / long first-call latency | Endpoint scaled to zero and is waking up | Retry with backoff; the endpoint wakes on first connection |
| `authentication failed` | Workspace-scoped token used as password | Use `w.postgres.generate_database_credential(endpoint=...)`, not `w.config.token` |
| `SSL connection required` | Missing `sslmode=require` | Verify the connection string includes `?sslmode=require` |
| `relation "checkpoints" does not exist` | `setup()` never ran | Call `setup()` once (step 7) |
| Agent starts fresh every call | Thread ID not passed through | Ensure `config = {"configurable": {"thread_id": ...}}` is passed to `graph.astream()` |
| Long-term memory tools always say "no user_id provided" | `user_id` not in `custom_inputs` | Pass `custom_inputs={"user_id": "..."}` in the request |
| `save_user_memory` fails with embedding/endpoint error | App SP can't query the embedding endpoint | Grant the app SP `CAN QUERY` on `databricks-gte-large-en` (or `DATABRICKS_EMBEDDING_ENDPOINT`) |
| Endpoint in suspended state | Idle endpoint auto-suspended (scale-to-zero) | Normal on dev; it wakes on next connection. Set `no_suspension: true` to disable |

## How credentials work

Lakebase Autoscaling uses short-lived, endpoint-scoped OAuth tokens (not static passwords).
In the agent, `databricks-langchain`'s `AsyncCheckpointSaver` / `AsyncDatabricksStore` wrap a
Lakebase connection pool (from `databricks-ai-bridge`) that mints a token via
`w.postgres.generate_database_credential(endpoint=...)` and injects it as the Postgres
password whenever the pool opens or recycles a physical connection — so tokens stay fresh
without a background refresh loop. Do not cache credentials yourself.

```
# Short-term memory
graph.py: get_async_checkpointer()
  └── AsyncCheckpointSaver(autoscaling_endpoint=LAKEBASE_ENDPOINT)   ← mints + rotates tokens
        └── graph_builder.compile(checkpointer=checkpointer)

# Long-term memory
graph.py: get_async_store()
  └── AsyncDatabricksStore(autoscaling_endpoint=LAKEBASE_ENDPOINT,   ← mints + rotates tokens
                           embedding_endpoint=DATABRICKS_EMBEDDING_ENDPOINT, embedding_dims=1024)
        ├── graph_builder.compile(store=store)
        └── config["configurable"]["store"]  → tools.py memory_tools() (get/save/delete_user_memory)
```
