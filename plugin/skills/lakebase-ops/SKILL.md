---
name: lakebase-ops
description: Operate and troubleshoot the Lakebase (Autoscaling Postgres) memory component in an AgentOps Stacks project — check endpoint health, mint credentials, inspect or clear checkpointer tables, manage the Postgres schema. Use when the user's agent is having memory/persistence issues.
---

# lakebase-ops — Lakebase Memory Operations

Covers day-to-day operations for the `resources/lakebase.yml` component: the Lakebase
**Autoscaling** Postgres project used as a LangGraph checkpointer for agent conversation memory.

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
| `src/agents/<name>/graph.py` | `get_async_checkpointer()` — opens an `AsyncLakebasePool` (databricks-ai-bridge) and sets up checkpointer tables |
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
uses the async sibling `AsyncLakebasePool` because the LangGraph checkpointer is async —
for one-off ops scripts the sync client is simpler.)

If this fails, see the Troubleshooting section below.

### 3. Inspect checkpointer tables

LangGraph's `AsyncPostgresSaver` creates these tables on first call to `checkpointer.setup()`:

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

### 6. Verify env vars in `app.yaml`

The checkpointer in `graph.py` reads one env var:

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

### 7. Force checkpointer table creation

If the agent starts but the checkpointer tables don't exist yet (e.g. fresh project):

```python
import asyncio
from databricks_ai_bridge.lakebase import AsyncLakebasePool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def setup():
    endpoint = "projects/<project>-memory/branches/production/endpoints/<endpoint-id>"
    pool = AsyncLakebasePool(autoscaling_endpoint=endpoint)
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool.pool)
    await checkpointer.setup()
    print("Checkpointer tables created")
    await pool.close()

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
| `relation "checkpoints" does not exist` | `setup()` never ran | Call `checkpointer.setup()` once (step 7) |
| Agent starts fresh every call | Thread ID not passed through | Ensure `config = {"configurable": {"thread_id": ...}}` is passed to `graph.astream()` |
| Endpoint in suspended state | Idle endpoint auto-suspended (scale-to-zero) | Normal on dev; it wakes on next connection. Set `no_suspension: true` to disable |

## How credentials work

Lakebase Autoscaling uses short-lived, endpoint-scoped OAuth tokens (not static passwords).
In the agent, `databricks-ai-bridge`'s `AsyncLakebasePool` mints a token via
`w.postgres.generate_database_credential(endpoint=...)` and injects it as the Postgres
password whenever the pool opens or recycles a physical connection — so tokens stay fresh
without a background refresh loop. Do not cache credentials yourself.

```
graph.py: get_async_checkpointer()
  └── AsyncLakebasePool(autoscaling_endpoint=LAKEBASE_ENDPOINT)   ← mints + rotates tokens
        └── pool.pool  (AsyncConnectionPool)
              └── AsyncPostgresSaver(pool.pool)
                    └── graph_builder.compile(checkpointer=checkpointer)
```
