---
description: >
  Add a new agent to an existing AgentOps Stacks project by copying an existing
  agent and wiring it into databricks.yml and the manifest.
---

Use the `add-agent` skill.

This command adds an agent to an existing AgentOps Stacks project. The new agent
is a copy of an existing one, renamed throughout, with its own Databricks App,
MLflow experiment, and manifest entry.

**Prerequisite:** `databricks.yml`, `.agentops-stacks/manifest.yml`, and at least
one agent under `src/agents/` must exist. Run `/init-agentops-stacks` first if
you haven't scaffolded yet.

Defer to the skill's SKILL.md for input rules, the script invocation, and next
steps.
