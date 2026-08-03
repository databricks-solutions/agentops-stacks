---
description: >
  Add a supervisor agent that routes across your project's agents. Picks the
  best-fit pattern — custom LangGraph or Supervisor API — via a decision matrix,
  then scaffolds it into databricks.yml and the manifest.
---

Use the `add-supervisor` skill.

This command adds a supervisor to an existing AgentOps Stacks project. A
supervisor routes user queries across your agents (and managed sub-agents like
Genie spaces or Knowledge Assistants).

**Prerequisite:** `.agentops-stacks/manifest.yml` and at least one agent under
`src/agents/` must exist. Run `/add-agent` first if you only have one agent and
want the supervisor to route between several.

The skill runs a Selection Matrix to choose between two patterns:

- **custom** (GA, default) — a hand-written LangGraph supervisor, served as a
  Databricks App, fully declared in `databricks.yml`, gated by the CI eval loop.
- **supervisor_api** (Beta) — the Databricks-managed loop wrapped in a
  declarable App; minimal code, per-request model choice.

Defer to the skill's SKILL.md for the full decision matrix, per-pattern
scaffolding behavior, security posture, and next steps.
