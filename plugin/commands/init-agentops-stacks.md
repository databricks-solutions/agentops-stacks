---
description: Scaffold a new AgentOps Stacks project (DAB + CI/CD).
---

Use the `agentops-stacks` skill to scaffold a new multi-agent LangGraph project.

1. Verify prerequisites: Databricks CLI, uv, Node.js >=20.19.
2. Collect inputs across five phases:
   - **Phase 1 (Infrastructure):** `project_name`, `initial_agent_name`, `cloud`, `cicd_platform`, `destination`
   - **Phase 2 (Data sources):** Vector Search (RAG), Lakebase memory type
   - **Phase 3 (Tools):** local Python tools, UC functions
   - **Phase 4 (Evaluation):** eval dataset source
   - **Phase 5:** confirm enabled components, then scaffold
3. Write inputs to `/tmp/agentops-stacks-inputs.json` and run `databricks bundle init` against the agentops-stacks template repo via `--config-file`.
4. Surface the CLI's next-steps message unchanged.

Defer to the skill's SKILL.md for full details — including the Genie Code workspace flow, input constraints, and what the skill does NOT do.
