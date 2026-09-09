---
name: add-supervisor
description: Add a custom LangGraph supervisor agent that routes across an AgentOps Stacks project's agents, scaffolded into databricks.yml and the manifest so it rides the same eval-gate + dev/staging/prod lifecycle as every other agent. First checks whether a supervisor is even warranted. Triggers on "add supervisor", "add a router", "orchestrate my agents", "multi-agent supervisor", "route between agents".
---

# add-supervisor — Add a Supervisor to a Project

Adds a supervisor agent to an existing AgentOps Stacks project. A supervisor
routes user queries across the project's agents (and other managed sub-agents
like Genie spaces or Knowledge Assistants).

The supervisor is a **custom LangGraph** agent — a hand-written supervisor graph
that is *just another agent*: served as a Databricks App via MLflow AgentServer,
declared in `databricks.yml`, and gated by the same CI eval loop as every other
agent. This is a **post-scaffold pattern**, applied as the project matures —
like eval gates, governance, and monitoring. It is not part of `bundle init`.

## When to use

- The project already has **≥1 agent** (`databricks.yml` + `.agentops-stacks/manifest.yml` exist).
- The user wants a single entry point that routes to multiple specialists.
- Usually invoked *after* `/add-agent` has produced a second agent.

## Step 0 — Is a supervisor even warranted? (run this first)

Multi-agent orchestration is powerful but easy to reach for too early. The Big
Book of AgentOps names *"overcomplex architecture — using supervisor agents and
multi-agent systems when a simple sequential chain would suffice"* as an
explicit anti-pattern (orchestration overhead, harder debugging, possible loops
between agents), and its first guiding principle is **Start Narrow, Expand
Deliberately** (prefer deterministic over probabilistic). So before scaffolding,
check:

- **Only one real specialist?** → don't add a supervisor; keep the single agent.
- **Fixed, known order of steps?** → a **sequential chain / deterministic router**
  in one agent is simpler, cheaper, and easier to evaluate. Don't add a supervisor.
- **Routing that genuinely depends on the request** (intent classification across
  **≥2 non-overlapping specialists**, dynamic hand-off, chaining across domains)?
  → a supervisor is warranted. Proceed.

State your reasoning to the user. If a supervisor isn't warranted, say so and
stop — recommend the simpler shape instead.

## The pattern — custom LangGraph (GA)

A hand-written supervisor via `langgraph-supervisor`'s `create_supervisor` (or a
raw `StateGraph` router). You own the routing loop, so you control state,
guardrails, retries, and human-in-the-loop. Sub-agents can be a
`databricks_langchain.GenieAgent`, a remote serving endpoint (a deployed sibling
agent), or an in-process ReAct agent. It deploys and is eval-gated exactly like
any other agent — no extra workflow.

> **Why only custom?** A Databricks-managed "Supervisor API" pattern was
> considered and removed: that API is **deprecated and reaches end of life on
> 2026-09-30**, and Databricks' own guidance is to build multi-agent systems as
> **custom agents on Databricks Apps** — which is exactly this pattern. (The
> `manifest.yml` still records `type:` so a future GA managed pattern can be
> added without a contract change.)

## Workflow

1. **Run Step 0** — decide whether a supervisor is warranted. If not, stop.
2. **Locate the project** — find `databricks.yml` in the current dir or a parent.
3. **List existing agents** — show what's under `src/agents/` (candidate routes).
4. **Gather inputs:**
   - **Supervisor name** — must match `^[a-z][a-z0-9_]{2,}$` (and not collide with an existing agent).
   - **Routes** — comma-separated sub-agent names (**≥1 required**). Local agents are
     validated; names that aren't local agents are assumed managed sub-agents (Genie/KA/endpoint).
   - **Source agent** — which existing agent's App shape to base on (default: first found).
5. **Run the script:**
   ```bash
   python plugin/skills/agentops-stacks/scripts/add_supervisor.py \
     --name <supervisor_name> \
     --routes <agent_a,agent_b> \
     [--from <source_agent>] \
     --project-dir <project_root>
   ```
6. **Guide customization** (below) and relay the script's next-steps output unchanged.

## What the script does

1. Copies a source agent as the App shape, renaming references (parity with `add_agent.py`).
2. Overwrites `graph.py` with the supervisor graph, `tools.py` with a supervisor stub,
   and `agent.py` with a stateless supervisor handler.
3. Adds `langgraph-supervisor` to `pyproject.toml`.
4. Appends an experiment + app resource to `databricks.yml`.
5. Records the supervisor in `.agentops-stacks/manifest.yml`.
→ CI's `detect_patterns → eval_gate` picks it up automatically (it has `eval/gates.yml`).

## After adding

- Edit `graph.py` to point each route at its real backend (`GenieAgent`, remote
  endpoint, or a ReAct sub-agent).
- Add a **routing-accuracy scorer** to `eval/gates.yml`. Routing decisions are a
  *structured* output, so evaluate them **programmatically** (accuracy / F1 /
  confusion matrix over labeled expected-route examples) rather than with an LLM
  judge — per the Big Book's tiered-evaluation guidance. A supervisor whose gate
  doesn't test routing is rubber-stamping its core function.
- `uv sync`; `databricks bundle validate -t dev && databricks bundle deploy -t dev`.

## Error handling

- Name collides with an existing agent → abort.
- Invalid name format → abort with the pattern hint.
- No `--routes` → abort (a supervisor with no routes can't start).
- No `databricks.yml` found → abort (not an AgentOps Stacks project).
- No existing agents to base on → abort (scaffold an agent first).
- Manifest already has a `supervisor:` block → leave it; tell the user to edit by hand.

## Security posture (state this to the user)

- You own guardrails; scope each sub-agent's auth via MLflow `resources=[...]`,
  least-privilege per endpoint.
- Flow the **end user's identity** through to sub-agents (on-behalf-of-user, or
  an explicit non-LLM-controlled ID filter — never take the scoping value from
  model output). This is the Big Book's two-level permission model: agent/tool
  least-privilege *and* end-user identity passthrough.
- Fully within the workspace boundary.

## Reference

- Pattern deep-dive: `docs/supervisor-patterns.md` in the rendered project (scaffolded by the template).
- Custom multi-agent apps: https://docs.databricks.com/aws/en/agents/agent-framework/multi-agent-apps
