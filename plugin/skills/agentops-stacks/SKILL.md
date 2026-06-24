---
name: agentops-stacks
description: Scaffold a new AgentOps Stacks project — a multi-agent LangGraph bundle (DAB) with shared components, per-agent Databricks Apps, evaluation, and CI/CD. Use when the user wants to start a new AI agent project on Databricks. Triggers on "scaffold a new agentops project", "new DAB with CI/CD", "start a new Databricks AI project", "create agentops-stacks project".
---

# agentops-stacks — Agent Project Scaffold

Generates a production-ready multi-agent project on Databricks: shared components (retriever, memory, tools), per-agent LangGraph graphs served as Databricks Apps via MLflow AgentServer, evaluation with ConversationSimulator, and CI/CD workflows.

The first scaffold creates the bundle with one agent. Additional agents are added later via `/add-agent` or manually under `src/agents/`.

## Prerequisites

1. **Databricks CLI** installed and on PATH. Verify with `databricks --version` (skip in Genie Code).
2. **uv** for Python dependency management.
3. **Node.js >=20.19** for the chat UI frontend.

If any are missing, surface install instructions and stop.

## Scaffold workflow

```
Scaffold Progress:
- [ ] Phase 0: Infer intent
- [ ] Phase 1: Infrastructure inputs
- [ ] Phase 2: Data sources
- [ ] Phase 3: Tools
- [ ] Phase 4: Evaluation
- [ ] Phase 5: Validate, confirm, scaffold
- [ ] Phase 6: Surface next steps
```

### Phase 0: Infer intent from what the user said

Before asking anything, read the user's description and pre-fill as many inputs as you can. Only ask about inputs that are genuinely unknown or ambiguous. Show what you've inferred so the user can correct it.

**Keyword → input mapping:**

| If the user mentions… | Infer |
|---|---|
| "RAG", "retrieval", "search documents", "knowledge base", "unstructured data" | `use_vector_search: yes` |
| "already chunked", "existing Delta table", "I have a chunked table" | `has_chunked_table: yes` |
| "memory", "remember conversations", "conversation history", "persistent context" | `use_lakebase: yes` — still ask `memory_type` unless they specified it |
| "short-term memory", "session memory", "within-session" | `use_lakebase: yes`, `memory_type: short_term` |
| "long-term memory", "cross-session memory", "persistent memory" | `use_lakebase: yes`, `memory_type: long_term` |
| "UC functions", "Unity Catalog tools", "catalog functions", "SQL tools" | `use_uc_functions: yes` |
| "functions already exist", "existing UC functions" | `use_uc_functions: yes`, `uc_functions_exist: yes` |
| "GitHub", "GitHub Actions" | `cicd_platform: github_actions` |
| "GitHub Enterprise", "GHES" | `cicd_platform: github_actions_for_github_enterprise_servers` |
| "GitLab" | `cicd_platform: gitlab` |
| "Azure DevOps", "ADO" | `cicd_platform: azure_devops` |
| "AWS", "Amazon" | `cloud: aws` |
| "Azure" (non-DevOps context) | `cloud: azure` |
| "GCP", "Google Cloud" | `cloud: gcp` |
| "synthetic", "generate test data", "LLM simulator" | `eval_dataset_source: synthetic` |
| "production traces", "from prod", "from logs" | `eval_dataset_source: production_traces` |
| "existing dataset", "I already have eval data" | `eval_dataset_source: existing` |

After inference, present a summary like:

> Based on what you described, I'll configure:
> - Vector Search (RAG): **yes**
> - Lakebase memory: **no** ← _ask if unsure_
> - UC functions: **no**
> - Eval dataset: **synthetic**
>
> Does that look right, or would you like to change anything?

Then only ask for inputs still missing.

### Phase 1: Infrastructure

Collect any of these not already known:

1. **project_name** (string) — Bundle name. Must match `^[a-z][a-z0-9_]{2,}$`.
2. **initial_agent_name** (string) — Name of the first agent. Same pattern. Default: `default`.
3. **cloud** — `aws`, `azure`, or `gcp`.
4. **cicd_platform** — `github_actions`, `github_actions_for_github_enterprise_servers`, `azure_devops`, or `gitlab`.
5. **destination** (path) — Must be a Git folder. Default: cwd if it's a Git folder.

### Phase 2: Data sources

Confirm or ask only for inputs not inferred:

6. **use_vector_search** — `yes`/`no`
   - If yes → **has_chunked_table** — "Do you already have a chunked Delta table to sync from? If no, the scaffold includes ingestion and preparation notebooks." → `yes`/`no`
7. **use_lakebase** — `yes`/`no`
   - If yes and `memory_type` not inferred → **memory_type** — `short_term`, `long_term`, or `both`

### Phase 3: Tools

8. **use_uc_functions** — `yes`/`no`
   - If yes and `uc_functions_exist` not inferred → **uc_functions_exist** — "Are those UC functions already defined in your catalog?" → `yes`/`no`

### Phase 4: Evaluation

9. **eval_dataset_source** — only ask if not inferred from context:
    - `synthetic` — generate a golden dataset using an LLM simulator (default)
    - `manual` — scaffold a notebook with example rows to fill in manually
    - `production_traces` — build from production traces filtered by tag
    - `existing` — skip dataset creation (you already have one)

### Phase 5: Validate, confirm, scaffold

Write all collected inputs to `/tmp/agentops-stacks-inputs.json` using these exact keys:

```json
{
  "input_project_name": "<value>",
  "input_initial_agent_name": "<value>",
  "input_cloud": "<value>",
  "input_cicd_platform": "<value>",
  "input_use_vector_search": "yes|no",
  "input_has_chunked_table": "yes|no",
  "input_use_lakebase": "yes|no",
  "input_memory_type": "short_term|long_term|both",
  "input_use_uc_functions": "yes|no",
  "input_uc_functions_exist": "yes|no",
  "input_eval_dataset_source": "synthetic|manual|production_traces|existing"
}
```

Omit conditional keys whose parent is `no` (e.g. omit `input_has_chunked_table` if `input_use_vector_search` is `no`). The schema defaults handle those. Validate:

```bash
python scripts/validate_inputs.py --config /tmp/agentops-stacks-inputs.json
```

Show the user a summary of which components are enabled, then confirm before running:

```bash
bash scripts/scaffold.sh --config /tmp/agentops-stacks-inputs.json --destination <destination>
```

### Phase 6: Next steps

See [reference/post-scaffold.md](reference/post-scaffold.md) for the full next-steps checklist.

After scaffolding:
1. `cd <destination>/<project_name>` and run `uv sync`
2. Set workspace hosts in `databricks.yml` and create Unity Catalog catalogs — see `docs/setup.md`
3. `databricks bundle validate -t dev`
4. `databricks bundle deploy -t dev` to deploy

Point the user at the reference example closest to what they just scaffolded:

| If they enabled... | Best reference example |
|---|---|
| Vector Search (RAG) | [`examples/simple-rag/`](../../../examples/simple-rag/) — full RAG agent: VS ingestion, retrieval, Foundation Model API, Databricks App, eval gate |
| Lakebase memory or multiple agents | [`examples/multi-agent/`](../../../examples/multi-agent/) — three agents sharing tools, each an independent App, per-agent eval datasets |
| Neither (minimal start) | [`examples/hello-agent/`](../../../examples/hello-agent/) — minimal pyfunc agent: register → evaluate → gate loop |

Each example is a complete reference with agent code, DAB resources, setup notebooks, and an eval gate. Encourage the user to copy patterns from the nearest example rather than starting from scratch.

## Adding more agents

1. Create `src/agents/<new_name>/` with `agent.py`, `tools.py`, `app/`, `eval/`
2. Add a new `resources.apps.<name>` entry in `databricks.yml`
3. Add to `.agentops-stacks/manifest.yml` under `agents:`
4. Add entry points in `pyproject.toml` (or use `AGENT_MODULE` env var)

A future `/add-agent` skill will automate this.

## Additional references

- **Genie Code flow**: See [reference/genie-code.md](reference/genie-code.md)
- **Troubleshooting**: See [reference/common-issues.md](reference/common-issues.md)
- **Template repo**: <https://github.com/databricks-solutions/agentops-stacks>
- **Official app template**: <https://github.com/databricks/app-templates/tree/main/agent-langgraph>
