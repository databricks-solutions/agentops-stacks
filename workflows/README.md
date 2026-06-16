# Workflows

Machine-readable lifecycle definitions for agentops-stacks projects. Each file
defines a complete end-to-end workflow that can be consumed programmatically by
workflow engines (e.g., `/innovate`) or used as a reference when building custom
automation on top of an agentops-stacks scaffold.

## Schema

Each workflow JSON has the following top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable workflow name |
| `description` | string | What this workflow covers |
| `version` | string | Semver |
| `tags` | string[] | Searchable tags |
| `max_retries` | int | Retry count per step before escalation |
| `steps` | Step[] | Ordered lifecycle steps |
| `routing_notes` | object | Architecture decisions governing the workflow |

Each step has: `name`, `display_name`, `phase` (dev/staging/prod),
`description`, `agent_actions` (ordered list of actions for the coding
assistant to execute), `validations` (named checks that must pass before
advancing), `bigbook_reference` (citation from the Big Book of AgentOps),
and `escalation_hint` (what to do when the step fails after max_retries).

## Available workflows

| File | Pattern | Steps | Complexity |
|------|---------|-------|------------|
| `single-account-single-agent.json` | Single-Account, Single-Agent (Pattern 1) | 10 | Low — 2–5 engineers, first agentic project |
