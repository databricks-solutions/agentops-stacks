---
description: >
  Add a custom LangGraph supervisor that routes across your project's agents,
  scaffolded into databricks.yml and the manifest. First checks whether a
  supervisor is warranted.
---

Use the `add-supervisor` skill.

This command adds a supervisor to an existing AgentOps Stacks project. A
supervisor routes user queries across your agents (and managed sub-agents like
Genie spaces or Knowledge Assistants).

**Prerequisite:** `.agentops-stacks/manifest.yml` and at least one agent under
`src/agents/` must exist. Run `/add-agent` first if you only have one agent and
want the supervisor to route between several.

The skill first checks whether a supervisor is even warranted (a deterministic
router or sequential chain is often the better tool), then scaffolds a **custom
LangGraph** supervisor — a hand-written graph served as a Databricks App, fully
declared in `databricks.yml`, gated by the CI eval loop like any other agent.

(A managed "Supervisor API" pattern was removed — that API is deprecated,
EOL 2026-09-30; Databricks recommends custom agents on Apps instead.)

Defer to the skill's SKILL.md for the "is a supervisor warranted?" pre-gate,
scaffolding behavior, security posture, and next steps.
