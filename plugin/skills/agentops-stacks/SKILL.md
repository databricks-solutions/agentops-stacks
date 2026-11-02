---
name: agentops-stacks
description: Scaffold a new AgentOps Stacks project — a multi-agent LangGraph bundle (DAB) with shared components, per-agent Databricks Apps, evaluation, and CI/CD. Use when the user wants to start a new AI agent project on Databricks. Triggers on "scaffold a new agentops project", "new DAB with CI/CD", "start a new Databricks AI project", "create agentops-stacks project".
---

# agentops-stacks — Agent Project Scaffold

Generates a production-ready multi-agent project on Databricks: shared components (retriever, memory, tools), per-agent LangGraph graphs served as Databricks Apps via MLflow AgentServer, per-agent evaluation gates (`mlflow.genai.evaluate` plus `eval/gates.yml`), and CI/CD workflows.

The first scaffold creates the bundle with one agent. Additional agents are added later via `/add-agent` or manually under `src/agents/`.

## Prerequisites

1. **Databricks CLI** installed and on PATH. Verify with `databricks --version` (skip in Genie Code).
2. **uv** for Python dependency management.

Each agent App is API-only (no chat UI is bundled), so Node.js isn't needed.

If any are missing, surface install instructions and stop.

## Scaffold workflow

```
Scaffold Progress:
- [ ] Phase 0: Infer intent
- [ ] Phase 1: Infrastructure inputs
- [ ] Phase 2: Data sources
- [ ] Phase 3: Tools
- [ ] Phase 4: Usage tracking
- [ ] Phase 5: Evaluation
- [ ] Phase 6: Validate, confirm, scaffold
- [ ] Phase 7: Surface next steps
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
| "cost attribution", "chargeback", "track usage", "tag resources", "usage policy" | `enable_cost_tags: yes` (still ask for `usage_policy_id`) |
| "no tags", "don't tag", "skip tagging" | `enable_cost_tags: no` |
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
2. **initial_agent_name** (string) — Name of the first agent. Same pattern. Default: `default`. Its App is named `<project_name>-<initial_agent_name>` with underscores as hyphens, and Databricks App names are limited to 30 characters, so keep the pair short (`validate_inputs.py` and `bundle init` both reject longer ones).
3. **cloud** — `aws`, `azure`, or `gcp`.
4. **cicd_platform** — `github_actions`, `github_actions_for_github_enterprise_servers`, `azure_devops`, or `gitlab`.
5. **destination** (path) — The *parent* folder: the scaffold creates `<destination>/<project_name>/`. Default: cwd. The generated CI/CD files (`.github/`, `.gitlab-ci.yml`, `.azure/`) only run when `<project_name>/` is the root of its git repository, so don't scaffold inside an existing repo unless the user only wants workspace deploys (the Genie Code Git folder flow; see [reference/genie-code.md](reference/genie-code.md)). `scaffold.sh` warns when the destination is inside a git repo.

### Phase 2: Data sources

Confirm or ask only for inputs not inferred:

6. **use_vector_search** — `yes`/`no`
   - If yes → **has_chunked_table** — "Do you already have a chunked Delta table to sync from? If no, the scaffold includes ingestion and preparation notebooks." → `yes`/`no`
7. **use_lakebase** — `yes`/`no`
   - If yes and `memory_type` not inferred → **memory_type** — `short_term`, `long_term`, or `both`

### Phase 3: Tools

8. **use_uc_functions** — `yes`/`no`
   - If yes and `uc_functions_exist` not inferred → **uc_functions_exist** — "Are those UC functions already defined in your catalog?" → `yes`/`no`

### Phase 4: Usage tracking

9. **enable_cost_tags**: `yes`/`no` (default `yes`). Tags every taggable resource with `project`, `environment` (bundle target), and `agent` (experiments) so usage can be attributed in `system.billing.usage`. With `no`, nothing is tagged.
   - If yes → **usage_policy_id**: "Do you have an existing serverless usage policy ID to attribute serverless usage (Apps, Vector Search, Lakebase)? Leave blank if not." It must be a UUID or blank.
   - **Never create a usage policy yourself.** Creating one needs a workspace admin (or the "Serverless usage policy: Manager" permission). If the user has no ID, leave it blank. The scaffold renders the `budget_policy_id` lines commented out, plus `scripts/create_usage_policy.sh` (create + wire), `scripts/enable_usage_policy.py` (wire existing IDs), and `docs/usage-tracking.md` with creation steps. Point them there in Phase 7, or to the `usage-tracking-ops` skill.
   - Call these "usage policies", not "budget policies". The purpose is tracking, not spend limits. The bundle field is still named `budget_policy_id`.

### Phase 5: Evaluation

10. **eval_dataset_source** — only ask if not inferred from context:
    - `synthetic` — generate a golden dataset using an LLM simulator (default)
    - `manual` — scaffold a notebook with example rows to fill in manually
    - `production_traces` — build from production traces filtered by tag
    - `existing` — skip dataset creation (you already have one)

### Phase 6: Validate, confirm, scaffold

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
  "input_enable_cost_tags": "yes|no",
  "input_usage_policy_id": "<uuid or empty string>",
  "input_eval_dataset_source": "synthetic|manual|production_traces|existing"
}
```

Omit conditional keys whose parent is `no` (e.g. omit `input_has_chunked_table` if `input_use_vector_search` is `no`, and `input_usage_policy_id` if `input_enable_cost_tags` is `no`). The schema defaults handle those. Validate:

```bash
# <skill-dir> is this skill's directory: .claude/skills/agentops-stacks/ once installed.
python <skill-dir>/scripts/validate_inputs.py --config /tmp/agentops-stacks-inputs.json
```

Show the user a summary of which components are enabled, then confirm before running:

```bash
bash <skill-dir>/scripts/scaffold.sh --config /tmp/agentops-stacks-inputs.json --destination <destination>
```

### Phase 7: Next steps

See [reference/post-scaffold.md](reference/post-scaffold.md) for the full next-steps checklist.

After scaffolding:
1. `cd <destination>/<project_name>/src/agents/<agent>` and run `uv sync` (each agent has its own `pyproject.toml` and `uv.lock`)
2. Set workspace hosts in `databricks.yml` and create Unity Catalog catalogs — see `docs/setup.md`
3. `databricks bundle validate -t dev`
4. `databricks bundle deploy -t dev` to deploy, then `databricks bundle run <agent> -t dev` to ship the code to the agent App and start it
5. If `enable_cost_tags: yes` and no `usage_policy_id` was given: serverless usage stays untagged until a usage policy is set. See `docs/usage-tracking.md`.

Reference examples aren't published yet (see [`examples/README.md`](../../../examples/README.md)). For what to do next, point the user at the `agentops-lifecycle` skill (`/agentops-lifecycle`), which walks the project they just scaffolded from data prep to production.

## Adding more agents

Use `/add-agent` (the `add-agent` skill): it copies an existing agent and wires its App into `databricks.yml` and the manifest. By hand:

1. Copy `src/agents/<existing>/` to `src/agents/<new_name>/` and replace the old agent name with the new one in the copied files.
2. In `databricks.yml`, copy the `resources.apps.<existing>` block under the new name, keeping its `config` (command and env) and `resources`. The App `name` must be at most 30 characters of lowercase letters, digits and hyphens. To keep the new agent's traces separate, also add an experiment for it and point the App's `experiment` resource at it.
3. Add the agent to `.agentops-stacks/manifest.yml` under `agents:`.

## Additional references

- **Genie Code flow**: See [reference/genie-code.md](reference/genie-code.md)
- **Troubleshooting**: See [reference/common-issues.md](reference/common-issues.md)
- **Template repo**: <https://github.com/databricks-solutions/agentops-stacks>
- **Official app template**: <https://github.com/databricks/app-templates/tree/main/agent-langgraph>
