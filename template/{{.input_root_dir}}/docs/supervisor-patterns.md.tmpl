# Supervisor Patterns

A supervisor agent routes user queries across your project's agents. When you
have more than one agent, add a supervisor with the `/add-supervisor` skill (or
`plugin/skills/agentops-stacks/scripts/add_supervisor.py`). It is scaffolded as
an agent App, so it deploys and is eval-gated like any other agent.

## First: is a supervisor warranted?

Multi-agent orchestration is easy to reach for too early. Prefer the simplest
shape that works:

- **One real specialist** → keep the single agent; no supervisor.
- **Fixed, known order of steps** → a **deterministic router / sequential chain**
  in one agent is simpler, cheaper, and easier to evaluate.
- **Routing that genuinely depends on the request** (intent classification across
  ≥2 non-overlapping specialists, dynamic hand-off) → a supervisor is warranted.

Using a supervisor when a sequential chain would do adds orchestration overhead,
debugging complexity, and the risk of loops between agents.

## The pattern — custom LangGraph (GA)

A hand-written supervisor graph (via `langgraph-supervisor`'s `create_supervisor`
or a raw `StateGraph` router). It is **just another agent**: served as a
Databricks App via MLflow AgentServer, declared in `databricks.yml`, and gated
by the same CI eval loop.

- **You control** routing logic, state, guardrails, retries, HITL.
- **Sub-agents** can be `databricks_langchain.GenieAgent`, remote serving
  endpoints (your deployed sibling agents), or in-process ReAct agents.
- **Deploy**: `databricks bundle deploy -t dev` — no extra steps.

Scaffolded files: `src/agents/<name>/graph.py` (supervisor), `agent.py`
(stateless supervisor handler), `tools.py`, `eval/` (inherited), plus an app +
experiment in `databricks.yml`.

> **Why not a managed supervisor?** Databricks' managed "Supervisor API" is
> **deprecated (end of life 2026-09-30)**, and its own replacement guidance is to
> build multi-agent systems as **custom agents on Databricks Apps** — this
> pattern. (The Agent Bricks managed "Supervisor Agent" is also on a sunset
> path.) So the durable choice is custom LangGraph.

## Evaluating a supervisor

Routing decisions are a **structured** output — evaluate them **programmatically**
(accuracy / F1 / a confusion matrix over labeled expected-route examples), not
with an LLM judge. Add a routing scorer to the supervisor's `eval/gates.yml`; a
gate that only checks safety and answer quality doesn't test the supervisor's
core job. Evaluate the whole chain end-to-end, not just the final answer.

## Manifest contract

The supervisor is recorded in `.agentops-stacks/manifest.yml`:

```yaml
supervisor:
  type: custom
  name: <supervisor_agent_name>
  routes: [agent_a, agent_b]
```

CI and tooling read this contract without needing to know how the supervisor was
created. (`type` is kept so a future GA managed pattern can be added.)

## Security posture

- You own guardrails; scope each sub-agent's auth via MLflow `resources`,
  least-privilege per endpoint.
- Flow the **end user's identity** through to sub-agents (on-behalf-of-user, or
  an explicit non-LLM-controlled ID filter — never from model output).
- In the workspace boundary.
