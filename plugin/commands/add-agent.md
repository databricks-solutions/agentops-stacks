---
description: >
  Add another agent to an existing AgentOps Stacks project: copies an existing
  agent and wires its App, experiment, and manifest entry into the bundle.
---

Use the `add-agent` skill.

This command adds an agent to an existing AgentOps Stacks project. The new
agent is a copy of an existing one (its graph, tools, eval harness, and App
config), renamed and declared in `databricks.yml` as its own Databricks App
with its own MLflow experiment.

**Prerequisite:** `databricks.yml` and `.agentops-stacks/manifest.yml` must
exist. Run `/init-agentops-stacks` first if there's no project yet.

Agent names follow the scaffold's pattern (`^[a-z][a-z0-9_]{2,}$`), and the
App name `<project>-<agent>` must fit in 30 characters.

Defer to the skill's SKILL.md for inputs, what the script changes, error
handling, and next steps.
