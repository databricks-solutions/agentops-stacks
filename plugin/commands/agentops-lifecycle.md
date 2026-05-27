---
description: >
  Guide an agentops-stacks project through its complete production lifecycle —
  data prep, agent dev, eval gates, CI/CD promotion, and production monitoring.
  Run after `databricks bundle init` (or `/init-agentops-stacks`).
---

Use the `agentops-lifecycle` skill.

This command guides an existing agentops-stacks scaffold through the
Single-Account Single-Agent lifecycle:

- Steps 1–5 (Dev): data preparation, agent implementation, offline evaluation,
  SME calibration
- Steps 6–7 (Staging): CI gate, integration tests
- Steps 8–10 (Production): CD deploy, batch inferencing baseline, monitoring

**Prerequisite:** `.agentops-stacks/manifest.yml` must exist. Run
`/init-agentops-stacks` first if you haven't scaffolded yet.

Defer to the skill's SKILL.md for full step-by-step guidance, code examples,
validation criteria, and common issue resolutions.
