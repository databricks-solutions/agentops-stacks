# hello_agent

AgentOps Stacks project — a Declarative Automation Bundle scaffold for production-ready AI solutions.

This project ships the structure, CI/CD wiring, and Unity Catalog configuration to take an AI solution to production. Build your solution under `src/` and apply evaluation, governance, and monitoring patterns as you go — manually, with a coding assistant, or via the agentops-stacks plugin.

## Quick start

1. Follow **[`docs/setup.md`](docs/setup.md)** — end-to-end configuration guide (UC catalogs and grants, CLI profiles, service principals, CI/CD credentials).
2. Fill in the TODO placeholders in `databricks.yml` (workspace hosts, `run_as` identities).
3. `cd src/agents/hello_agent` then `uv sync` — generates `uv.lock`. **Commit `uv.lock` to git** (CI caches against it).
4. `cp .env.example .env` — configure Databricks auth for local runs.
5. `uv run python app/start_server.py` — run the agent locally.
6. `databricks bundle validate -t dev --profile <dev-profile>`
7. `databricks bundle deploy -t dev --profile <dev-profile>`

## Project layout

| Path | Purpose |
|------|---------|
| `databricks.yml` | Bundle root: variables, targets, resource includes, deployment engine |
| `resources/` | DAB resource definitions (`experiment.yml`, `schemas.yml`, `volumes.yml`) |
| `.agentops-stacks/manifest.yml` | agentops-stacks recognition marker, contract version, agent registry |
| `src/agents/hello_agent/` | Agent code: `agent.py`, `graph.py`, `tools.py`, `app/`, `eval/` |
| `src/components/` | Shared components (tool registry) |
| `tests/` | Unit and integration tests |
| `docs/` | Project documentation; `docs/setup.md` is the configuration guide |
| `.github/`, `.gitlab/`, `.azure/` | CI/CD pipelines for the selected platform |
| `AGENTS.md` | Project conventions for AI coding agents (tool-agnostic) |

## Deployment targets

| Target | Mode | Trigger |
|--------|------|---------|
| dev | development | Manual (`databricks bundle deploy -t dev`) |
| staging | production | CI/CD on push to `main` |
| prod | production | CI/CD on tag matching `v*` |

Each target has its own catalog. Dev mode prefixes resource names with user info to isolate parallel dev work. Production mode rejects user-scoped paths and uses fixed names.

## Production patterns

Evaluation gates are pre-scaffolded under `src/agents/<name>/eval/`. Governance and monitoring are applied as the project matures:

- **Evaluation gates** — `eval/gates.yml` defines quality thresholds; `eval/evaluate_agent.py` runs the harness. CI workflows gate promotion on them. Run locally with `uv run agent-evaluate`.
- **Governance posture** — apply by adding `governance/posture.md` and `governance/data_flows.md`; the prod-promotion workflow checks for presence.
- **Monitoring** — apply per-resource as you deploy them (trace destination in code, alert rules per endpoint, etc.).

Use the agentops-stacks plugin (Claude Code, Cursor, or Genie Code) for step-by-step guidance. Run `/agentops-lifecycle` or say "walk me through the agentops lifecycle."

## Resources

- [Declarative Automation Bundles](https://docs.databricks.com/dev-tools/bundles/)
- [MLflow 3 + Unity Catalog](https://docs.databricks.com/mlflow3/)
- [Direct deployment engine](https://docs.databricks.com/dev-tools/bundles/direct)
