---
name: add-supervisor
description: Add a supervisor agent that routes across an AgentOps Stacks project's agents. Selects the best-fit supervisor pattern — custom LangGraph or Supervisor API — using a decision matrix, then scaffolds it into databricks.yml and the manifest. Triggers on "add supervisor", "add a router", "orchestrate my agents", "multi-agent supervisor", "route between agents".
---

# add-supervisor — Add a Supervisor to a Project

Adds a supervisor agent to an existing AgentOps Stacks project. A supervisor
routes user queries across the project's agents (and other managed sub-agents
like Genie spaces or Knowledge Assistants).

There are two supervisor patterns. They are **not interchangeable** — they
differ in who owns the routing loop. This skill's job is to pick the best-fit
pattern for the user's needs, then scaffold it as a minimal, one-PR addition
that rides the same DAB + eval-gate + dev/staging/prod lifecycle as every other
agent.

## When to use

- The project already has **≥1 agent** (`databricks.yml` + `.agentops-stacks/manifest.yml` exist).
- The user wants a single entry point that routes to multiple specialists.
- Usually invoked *after* `/add-agent` has produced a second agent.

This is a **post-scaffold pattern**, applied as the project matures — like eval
gates, governance, and monitoring. It is not part of `bundle init`.

## The two patterns

| | **Custom LangGraph** | **Supervisor API** |
|---|---|---|
| Routing loop owned by | Your code | Databricks (managed) |
| Artifact in the bundle | A real agent App under `src/agents/` | A thin wrapper App under `src/agents/` |
| Declarable in `databricks.yml`? | **Yes, natively** | **Yes, as a wrapper App** |
| MLflow eval gate in CI? | Yes (standard traces) | Yes (UC OTel + MLflow tracing) |
| Status | GA | Beta (AI Gateway + OTel preview) |
| Best when | Max control, portability, guardrails, HITL, custom state | Managed loop, minimal code, per-request model choice |

Both patterns are first-class DAB citizens: the supervisor is scaffolded as an
agent App, so it deploys and is eval-gated exactly like any other agent.

**Default is `custom`** — it is GA, fully DAB-declarable, and gated on real
MLflow eval end-to-end. Choose `supervisor_api` only when its specific
advantage (a managed loop with minimal code) is what the user wants.

## Selection Matrix — run these gates in order, take the first that fires

Ask the user only what you can't already infer from the project and their
description. Show your reasoning.

**D1 — Lifecycle parity is non-negotiable?**
> "The supervisor must ride the same DAB + eval gate + dev/staging/prod
> promotion as every other agent, on GA, fully in databricks.yml."
→ **custom**. (This is the default; stop here unless a later gate is explicitly required.)

**D2 — Orchestration control needed?**
Custom state, deterministic/conditional routing, input/output guardrails, HITL
interrupts, a shared Lakebase checkpointer, or tool-level retry policy?
→ **custom**.
Otherwise the job is "fan out to the right specialist over managed sub-agents" → D3.

**D3 — Managed loop wanted?**
Code-first, wants the managed loop *without* writing a graph, per-request model
choice (Haiku→Opus, GPT-5), minimal orchestration code but still packaged as a
bundle App, and an admin can enable AI Gateway + the UC OTel-traces preview?
→ **supervisor_api**.
Otherwise → **custom**.

**D4 — Compliance / Beta tolerance (override):**
- HIPAA / enhanced-security workspace, or the user needs GA + certainty that
  promotion gates on real MLflow traces → **custom** (overrides D3).
- Beta-tolerant and an admin can enable AI Gateway + the UC OTel-traces preview →
  keep the D3 answer.

### Fast discriminators

- Sub-agents are things you'd code anyway (LLM nodes, `GenieAgent`, endpoints) in one graph → **custom**
- Custom state, guardrails, HITL, or deterministic routing → **custom**
- "Lightest code, managed loop, but must live in my repo + CI" → **supervisor_api**
- "Maximum control, portable, GA, gated" → **custom**

## Workflow

1. **Locate the project** — find `databricks.yml` in the current dir or a parent.
2. **List existing agents** — show what's under `src/agents/` (these are the
   candidate routes).
3. **Run the Selection Matrix** — infer what you can, ask only what's ambiguous,
   and state which pattern you chose and why. Confirm with the user.
4. **Gather inputs:**
   - **Supervisor name** — must match `^[a-z][a-z0-9_]{2,}$` (and not collide with an existing agent).
   - **Routes** — comma-separated sub-agent names. Local agents are validated;
     names that aren't local agents are assumed managed sub-agents (Genie/KA/endpoint).
   - **Source agent** — which existing agent's App shape to base on (default: first found).
5. **Run the script:**
   ```bash
   python plugin/skills/agentops-stacks/scripts/add_supervisor.py \
     --name <supervisor_name> \
     --type <custom|supervisor_api> \
     --routes <agent_a,agent_b> \
     [--from <source_agent>] \
     --project-dir <project_root>
   ```
6. **Guide customization** (differs by pattern — see below) and relay the
   script's next-steps output unchanged.

## What the script does

Both patterns are agent Apps:
1. Copies a source agent as the App shape, renaming references (parity with `add_agent.py`).
2. Overwrites `graph.py` with the supervisor variant, `tools.py` with a supervisor stub,
   and `agent.py` with a stateless supervisor handler.
3. Adds the pattern's dependency to `pyproject.toml` (`langgraph-supervisor` or `databricks-openai`).
4. Appends an experiment + app resource to `databricks.yml`.
5. Records the supervisor in `.agentops-stacks/manifest.yml`.
→ CI's `detect_patterns → eval_gate` picks it up automatically (it has `eval/gates.yml`).

## After adding

- **custom** — edit `graph.py` to point each route at its real backend
  (`GenieAgent`, remote endpoint, or a ReAct sub-agent); add a routing-accuracy
  scorer to `eval/gates.yml`; `uv sync`; `bundle validate/deploy -t dev`.
- **supervisor_api** — enable AI Gateway + the UC OTel-traces preview; set each
  route's `<ROUTE>_ENDPOINT`/Genie id in `graph.py`; `uv sync`; deploy.

## Error handling

- Name collides with an existing agent → abort.
- Invalid name format → abort with the pattern hint.
- No `databricks.yml` found → abort (not an AgentOps Stacks project).
- No existing agents to base on → abort (scaffold an agent first).
- Manifest already has a `supervisor:` block → leave it; tell the user to edit by hand.

## Security posture (state this to the user for the chosen pattern)

- **custom** — you own guardrails; scope each sub-agent's auth via MLflow
  `resources=[...]`; least-privilege per endpoint. Fully in workspace boundary.
- **supervisor_api** — authorization respects the **caller's** UC permissions;
  traces to UC tables (OTel preview); `databricks_web_search` unavailable under HIPAA; Beta.

## Reference

- Pattern deep-dive: `docs/supervisor-patterns.md` in the rendered project (scaffolded by the template).
- Supervisor API: https://docs.databricks.com/aws/en/agents/agent-bricks/supervisor-api
- Custom multi-agent apps: https://docs.databricks.com/aws/en/agents/agent-framework/multi-agent-apps
