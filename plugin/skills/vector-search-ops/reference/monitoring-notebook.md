# Monitoring Notebook

Health check notebook for Vector Search endpoints and indexes. Run as a scheduled DAB job (e.g., every 15 minutes) to detect issues before they impact the agent.

## Code

```python
# Databricks notebook source

# MAGIC %md
# MAGIC # Vector Search Health Check

# COMMAND ----------

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("endpoint_name", "", "VS endpoint name")
dbutils.widgets.text("index_name", "", "Fully qualified index name")
dbutils.widgets.text("source_table", "", "Fully qualified source table name")

endpoint_name = dbutils.widgets.get("endpoint_name")
index_name = dbutils.widgets.get("index_name")
source_table = dbutils.widgets.get("source_table")

w = WorkspaceClient()
issues = []

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check endpoint health

# COMMAND ----------

endpoint = w.vector_search_endpoints.get_endpoint(endpoint_name=endpoint_name)
state = endpoint.endpoint_status.state.value

if state in ("YELLOW_STATE", "RED_STATE", "OFFLINE"):
    issues.append(f"Endpoint {endpoint_name} is {state}: {endpoint.endpoint_status.message}")
    print(f"WARN: Endpoint is {state}")
else:
    print(f"OK: Endpoint is {state}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check index health

# COMMAND ----------

index = w.vector_search_indexes.get_index(index_name=index_name)

if not index.status.ready:
    issues.append(f"Index {index_name} is NOT READY: {index.status.message}")
    print(f"WARN: Index not ready — {index.status.message}")
else:
    print(f"OK: Index is ready. Rows indexed: {index.status.indexed_row_count}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check row count drift

# COMMAND ----------

if index.status.ready and source_table:
    source_count = spark.table(source_table).count()
    indexed_count = index.status.indexed_row_count or 0
    drift_pct = abs(source_count - indexed_count) / max(source_count, 1) * 100

    if drift_pct > 10:
        issues.append(
            f"Row count drift: source={source_count}, indexed={indexed_count} ({drift_pct:.1f}%)"
        )
        print(f"WARN: {drift_pct:.1f}% row count drift (source={source_count}, indexed={indexed_count})")
    else:
        print(f"OK: Row count aligned (source={source_count}, indexed={indexed_count}, drift={drift_pct:.1f}%)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

if issues:
    summary = "VECTOR SEARCH HEALTH CHECK FAILED:\n" + "\n".join(f"  - {i}" for i in issues)
    print(summary)
    # Raise to trigger DAB job failure alerts
    raise RuntimeError(summary)
else:
    print("All checks passed.")
```

## DAB job definition

```yaml
resources:
  jobs:
    vs_health_check:
      name: "${bundle.target}-${var.project_name}-vs-health-check"
      tasks:
        - task_key: check
          notebook_task:
            notebook_path: ./src/components/retriever/health_check.py
            base_parameters:
              endpoint_name: "${var.vs_endpoint_name}"
              index_name: "${var.catalog}.${var.schema}.${var.project_name}_vs_index"
              source_table: "${var.catalog}.${var.schema}.${var.project_name}_chunked_docs"
      schedule:
        quartz_cron_expression: "0 */15 * * * ?"  # Every 15 minutes
        timezone_id: "UTC"
      email_notifications:
        on_failure:
          - "team-alerts@company.com"
```
