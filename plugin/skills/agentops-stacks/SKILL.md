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
- [ ] Phase 1: Infrastructure inputs
- [ ] Phase 2: Data sources
- [ ] Phase 3: Tools
- [ ] Phase 4: Evaluation
- [ ] Phase 5: Validate, confirm, scaffold
- [ ] Phase 6: Surface next steps
```

Collect inputs **one at a time, in order**. Skip questions that don't apply.

### Phase 1: Infrastructure

1. **project_name** (string) — Bundle name. Must match `^[a-z][a-z0-9_]{2,}$`.
2. **initial_agent_name** (string) — Name of the first agent. Same pattern. Default: `default`.
3. **cloud** — `aws`, `azure`, or `gcp`.
4. **cicd_platform** — `github_actions`, `github_actions_for_github_enterprise_servers`, `azure_devops`, or `gitlab`.
5. **destination** (path) — Must be a Git folder. Default: cwd if it's a Git folder.

### Phase 2: Data sources

6. **use_vector_search** — "Does your agent need to search unstructured data (RAG)?" → `yes`/`no`
   - If yes → 7. **has_chunked_table** — "Do you already have a chunked Delta table?" → `yes`/`no`
7. **use_lakebase** — "Does your agent need memory (conversation history)?" → `yes`/`no`
   - If yes → 9. **memory_type** → `short_term`, `long_term`, or `both`
8. **use_genie** — "Does your agent need to query structured data via Genie?" → `yes`/`no`
   - If yes → 11. **genie_space_id** — ID or blank to configure later

### Phase 3: Tools

9. **use_local_tools** — "Include example local Python tools?" → `yes` (default) / `no`
10. **use_uc_functions** — "Will your agent call Unity Catalog functions?" → `yes`/`no`
    - If yes → 14. **uc_functions_exist** — "Already defined in your catalog?" → `yes`/`no`

### Phase 4: Evaluation

11. **has_eval_dataset** — "Do you already have an evaluation dataset?" → `yes`/`no`
12. **eval_scorers** — Comma-separated from: `relevance`, `groundedness`, `safety`, `chunk_relevance`, `guideline_adherence`. Default: `relevance,groundedness,safety`.

### Phase 5: Validate, confirm, scaffold

Write inputs to `/tmp/agentops-stacks-inputs.json` (see schema for all keys). Validate:

```bash
python scripts/validate_inputs.py --config /tmp/agentops-stacks-inputs.json
```

Confirm with user, listing enabled components. Run:

```bash
bash scripts/scaffold.sh --config /tmp/agentops-stacks-inputs.json --destination <destination>
```

### Phase 6: Next steps

See [reference/post-scaffold.md](reference/post-scaffold.md) for next-steps checklist.

After scaffolding:
1. `cd <project_name>` and run `uv sync`
2. Set up `.env` with Databricks auth profile
3. `uv run start-app` to run the agent locally
4. `uv run agent-evaluate` to run evaluation
5. `databricks bundle deploy -t dev` to deploy

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
