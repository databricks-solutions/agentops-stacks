---
name: right-size-capability
description: >
  Decide whether a new agent capability should be a UC-function tool, an MCP
  server, or an Agent Skill — and push back when the user names the wrong one.
  Runs an invariant cascade, then a falsification pass that argues against the
  requested option before recommending. Use FIRST when adding a capability to an
  AgentOps Stacks agent. Triggers on "add a tool", "write an MCP server", "add a
  skill", "should this be a tool or an MCP server", "wrap this API for my agent",
  "give my agent the ability to…", "connect my agent to <system>".
---

# right-size-capability — Tool vs MCP vs Skill

Before you add a capability to an agent, decide which *kind* it should be. Agent
builders routinely name the artifact ("write me an MCP server", "add a tool")
before the requirement is settled — and often the other kind is cheaper, safer,
and more observable. This skill decides from the **requirement, not the request**,
and argues against the named artifact before agreeing to it.

It is the capability-level sibling of the `add-supervisor` "is a supervisor even
warranted?" pre-gate: same Big Book instinct — **start narrow, expand
deliberately; don't reach for the heavier mechanism when a simpler one suffices.**

## When to use

- The user wants the agent to *do*, *reach*, or *know* something new.
- They named a mechanism ("an MCP server", "a tool", "a skill") — or they didn't,
  and you're about to pick one.
- Run this **before** `uc-functions-ops` (tool), before standing up an MCP
  server, and before writing an Agent Skill.

Skip only when it's unambiguous and trivial (a one-off deterministic lookup over
a UC table is a UC function — just say so and route on).

## The three kinds (AgentOps Stacks)

| Kind | It changes… | Use when | Mechanism here |
|---|---|---|---|
| **UC-function tool** | what the agent *can touch* (deterministic) | a governed, deterministic action/compute/fetch the agent invokes and you can unit-test | `uc-functions-ops` — add a `.py`/`.sql` def, register, grant EXECUTE |
| **MCP server** | what the agent *can touch* (served) | a **served** capability: external system, managed/multi-user auth, server-side state, long-running, or reused across agents/clients | connect the agent to an MCP server (Databricks-hosted or external) |
| **Agent Skill** | what the agent *knows to do* | procedure / judgment / domain knowledge over the tools it already has — classification, drafting, multi-step orchestration | a markdown Agent Skill the agent loads |

**Default: UC-function tool.** It runs in the agent's own workspace, is governed
by Unity Catalog (grants + lineage), and is traced as a tool call for free — so
it wins for anything that touches Databricks data or is a deterministic action.
Reach past it only when a later gate fires.

## Step 1 — Recover the true requirement

Strip the artifact the user named. Restate the need in one sentence, in these
terms, with the artifact word removed:

- Does this change what the agent **knows to do**, or what it **can touch**?
- Is the result **deterministic and testable**, or a **judgment/procedure**?
- Can it run as a **governed function in this workspace**, or does it need a
  **separate served process** (its own auth, state, lifecycle)?
- Does **only this agent** need it, or **multiple agents/clients/teams**?

That sentence — not "MCP server" / "tool" / "skill" — is what you decide on.

## Step 2 — Invariant cascade (first gate that fires leads)

1. **Knowledge vs action.** If the need is "teach the agent how to decide,
   handle, phrase, or sequence X" with **no new external touch** → **Agent
   Skill**. It changes context, not capability. If it's a new thing the agent
   must *do* or *reach* → continue.
2. **Governed-in-workspace vs served.** Deterministic, runs against this
   workspace's catalog/compute, stateless between calls, testable →
   **UC-function tool**. Needs managed/multi-user auth, server-side state,
   long-running operations, or a process of its own → **MCP server**.
3. **Tenancy / reuse.** Only this agent needs it → keep the above. The *same*
   served capability is reused across agents, teams, or non-agent clients →
   **MCP server** (a UC function hand-rolling cross-client auth/state is a smell).

**Governance & observability tiebreak (Big Book).** UC functions get UC grants,
lineage, and automatic trace spans; prefer them for anything inside the
Databricks boundary. Reach for MCP only when the capability genuinely lives
outside it.

## Step 3 — Falsification pass (the adversarial step — run BEFORE recommending)

Do **not** state a recommendation yet. First try to break the leading answer and
the one the user asked for:

1. **Steelman the two kinds you are NOT leading toward** — the single strongest
   good-faith case each is right for *this* requirement.
2. **Falsification test for the leading answer** — write its necessary condition
   and check it against real evidence in the request:
   - *MCP server* only if: served process **or** managed/multi-user auth **or**
     server-side state / long-running **or** reused beyond this agent. Evidence: ___
   - *UC-function tool* only if: deterministic, governed, in-workspace, testable
     action the agent invokes. Evidence: ___
   - *Agent Skill* only if: procedure/judgment/knowledge over existing tools, no
     new external touch. Evidence: ___
   If the leading answer fails its own test, drop it and re-run the cascade.
3. **Rebut the named artifact explicitly** when it differs from where the
   evidence lands. The most common real case: *"you asked for an MCP server, but
   this is a deterministic lookup over a UC table that only this agent needs — a
   UC function does it with governance and lineage and no served process to run
   or secure."* Second most common: *"you asked for a tool, but this is 'decide
   which of the agent's existing tools to use and in what order' — that's an
   Agent Skill; a tool adds a capability you don't need."*

Only once a surviving answer clears its own falsification test do you proceed.

## Step 4 — Escalation trigger (structural; inline-logging seam)

The falsification pass runs **inline** (one context). On the calls where inline
self-critique is least trustworthy, flag for an *independent* steelman. The
trigger is **structural** — keyed to the cascade's outputs, never a self-reported
"feels close" — because an anchored context suppresses the very doubt it needs.

**Fire when ANY holds:**
- The user asked for an **MCP server** and the governed-vs-served gate did **not**
  hard-decide it (MCP over-build — a served process to run, secure, and maintain —
  is the expensive mistake; bias toward checking it).
- The cascade's **top-two kinds sit within one discriminator** (nothing hard-decided).
- The user **named a kind** and the requirement is **ambiguous on the
  served / multi-client axis**.

Tune **eager**: a false positive costs a little latency; a false negative ships a
rubber-stamp, which defeats the gate.

**Default when fired = inline + log (the seam).** Do the steelman inline (Step 3)
and append one decision record so we can later measure how often the trigger
fires and whether inline was shown wrong:

```bash
mkdir -p ~/.claude/logs
printf '%s\n' "$RECORD_JSON" >> ~/.claude/logs/right-size-decisions.jsonl
```

**Independent steelman (flag `RIGHT_SIZE_ESCALATE=fork`, off by default).** When
enabled, on a fired trigger spawn ONE independent subagent (Task; `fork` for full
context or `general-purpose` for a clean room) briefed only: *"Make the strongest
case that this requirement should be `<rival kind>`. Requirement: <Step-1
sentence>. Assume no kind was pre-chosen."* Give it the requirement sentence only
— not the user's ask, not your lead — so its reasoning is un-anchored. Adjudicate
its case against the cascade; if it fails or times out, degrade to the inline
result.

This is a **conditional single** escalation, not a standing multi-agent system —
it stays on the right side of the same "is more orchestration warranted?" gate
`add-supervisor` applies. Do not grow it into a per-kind debate swarm.

## Step 5 — Output contract

Emit, in order:

1. **Recommendation** — `uc-function tool` · `mcp server` · `agent skill`.
2. **Why** — the invariant/discriminator that decided it (one line).
3. **Rebuttal** — if it differs from what the user asked for, say plainly why the
   named kind is over- or under-provisioned here.
4. **Decision record** — the JSON below (also what gets logged).

```json
{
  "requirement": "<one sentence, artifact word removed>",
  "asked_for": "tool|mcp|skill|unspecified",
  "recommended": "uc_function|mcp|skill",
  "deciding_invariant": "knowledge_vs_action|governed_vs_served|tenancy|governance_observability",
  "trigger_fired": true,
  "escalation": "none|inline_logged|fork",
  "overturned_ask": true
}
```

## Step 6 — Hand off to the mechanism

- **UC-function tool** → `uc-functions-ops`: add a `.py`/`.sql` definition under
  `src/components/tools/definitions/`, re-run registration, grant EXECUTE, wire
  into `src/agents/<name>/tools.py`.
- **MCP server** → connect the agent to the MCP endpoint (Databricks-hosted or
  external); scope its auth to the app service principal or pass the caller's
  identity. *(Not scaffolded by the template today — this is guidance, not a
  generator.)*
- **Agent Skill** → author a markdown skill the agent loads; it changes the
  agent's instructions, not its tool list. *(Not scaffolded by the template today
  — guidance.)*

If the recommendation is a UC-function tool, hand control to `uc-functions-ops`.
Otherwise stop — the right move may be *not* building the thing that was asked.

## Grounding

This gate applies the Big Book of AgentOps operating principles directly: **start
narrow, expand deliberately** (prefer the simplest mechanism that meets the
need); **govern tools, data, and actions centrally** (UC as the boundary —
grants, lineage, audit); **design for observability** (UC-function tool calls are
traced by default). The same instincts drive `add-supervisor`'s pre-gate — right-
size the mechanism before you scaffold it.
