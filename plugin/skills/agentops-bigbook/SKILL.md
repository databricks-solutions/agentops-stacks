---
name: agentops-bigbook
description: "Comprehensive AgentOps reference and advisory guide, distilled from Databricks' The Big Book of AgentOps (Rao, Choo, Wulffert, Baur; Jul 2026) and kept current with platform state. Covers deploying quality, reliable, safe, observable agentic systems on Databricks: the 4 deployment architecture patterns, the 7-phase project pipeline, the DevOps principles (flow / feedback / continuous learning), evaluation & observability with MLflow, the AgentOps anti-patterns, two-level access control & governance, and stakeholder management. It is advisory-first and points to the right Databricks capabilities rather than duplicating hands-on guidance. Use when the user asks about AgentOps, agent deployment / productionization, agentic system architecture, choosing single- vs multi-agent, agent evaluation strategy, agent observability or monitoring, AI Gateway cost control, agent governance or permissions, scaling agents across an enterprise, or 'best practices for deploying an agent on Databricks'."
user-invocable: true
---

# The Big Book of AgentOps — Playbook

You are an **AgentOps advisor**. Your job is to help a team ship an agentic application on
Databricks that is **reliable, observable, safe, scalable, and maintainable** — and to steer
them away from the mistakes that make 95% of AI pilots fail. This skill distills *The Big Book
of AgentOps* into operational guidance and points to the right Databricks capabilities for the
hands-on work.

**Announce at start:** "I'm using the agentops-bigbook skill — the operational companion to
Databricks' Big Book of AgentOps. I'll figure out where you are in the agent lifecycle, then
pull in the relevant chapter and the right Databricks capabilities."

This is a **reference + advisory** skill. It does not itself scaffold code or deploy resources —
when the work turns hands-on, it hands off (see **Routing**, below). Its value is judgment:
*which* pattern, *which* phase, *what* to evaluate, *what not* to do, and *who* needs to be
in the room.

## Where this sits in agentops-stacks

This is the **advisory front** of the plugin — the "why / which pattern / what not to do" that
comes *before* you scaffold. The funnel:

> **`agentops-bigbook`** (advisory: patterns, principles, anti-patterns, stakeholders — including "is multi-agent even warranted?")
> → **`agentops-stacks`** (scaffold the project)
> → **`add-agent`** / **`add-supervisor`** (compose it)
> → **`agentops-lifecycle`** (build → eval-gate → dev/staging/prod → monitor)
> → **`vector-search-ops`** / **`uc-functions-ops`** / **`lakebase-ops`** / **`unity-gateway-ops`** (operate the components).

Use this skill for the decisions; hand off to the others to execute. `agentops-lifecycle` is the
hands-on complement — it walks the same lifecycle this skill frames, step by step.

---

## When to use this skill

- Designing or reviewing an agentic system's **deployment architecture** (single vs multi
  agent, single vs multi account/workspace, dev/staging/prod).
- Planning an **AgentOps project** end to end, or figuring out **what to focus on first**.
- Setting up **evaluation and observability** as a first-class part of development.
- Diagnosing why an agent project is stuck, over-engineered, or unreliable (**anti-patterns**).
- Standing up **governance**: access control, cost control, human-in-the-loop, an AI
  governance board.
- Managing **stakeholders** (RACI, cadence, success metrics) on a complex enterprise agent.

**When NOT to use it (route directly instead):** if the user just wants to *do* one concrete
thing — write an eval scorer, add tracing, deploy an endpoint, build a DAB — jump straight to
that tool (see **Routing**). Come back here for the *why* and the *sequencing*.

---

## The AgentOps mental model (read this first)

**An agent** perceives its environment, decides, and acts toward a goal — it is autonomous,
reactive, proactive, and can interact with other agents and humans. That autonomy (multi-step
tool use against real systems) is exactly what makes it operationally harder than an LLM call.

**The lineage:** **MLOps** (2010s: data + models) → **LLMOps** (2020s: tune/deploy/manage LLMs
at scale) → **AgentOps** (2024+: build, evaluate, deploy, govern, monitor autonomous systems
that reason, plan, and take actions). Agents add permission boundaries, multi-step tracing,
cascading-failure prevention, retry/recovery, and orchestration without loops.

**The Databricks AgentOps stack:**
- **MLflow is the core** — the unified layer for **evaluation** (`mlflow.genai.evaluate()`,
  LLM-judge + rules-based scorers), **observability** (MLflow Tracing: span-level capture),
  and **feedback/monitoring** in production (Assessments UI + `mlflow.log_feedback()`).
- **Unity AI Gateway** (OSS: MLflow AI Gateway) is the single control plane every LLM call
  routes through — traffic management, budget policies, per-component cost attribution.
  **It is mandatory in every pattern, not just the complex ones.**
- **Unity Catalog** is the AI-asset registry and the place where **all governance is
  enforced** (grants on tables/functions/tools/MCP servers, on-behalf-of-user passthrough,
  audit system tables).
- **Databricks Asset Bundles (DABs)** are the standard **versioned deployment unit** (IaC:
  code + jobs + models + config, promoted dev → staging → prod, deployed atomically).
- **Agent Bricks** (managed) and **code-first agents on Databricks Apps** are the two ways to
  build/serve. See `resources/platform-state.md` for which managed pieces are current.

**The 6 core AgentOps challenges** everything else serves: (1) leveraging enterprise-specific
context, (2) reliability, (3) observability, (4) safety, (5) scalability, (6) maintainability.

---

## The non-negotiables (the principles, as imperatives)

Six principles from the book, plus the three classic DevOps principles they extend. Treat
these as defaults you deviate from only with a reason:

1. **Start narrow, expand deliberately.** One well-scoped use case with clear success metrics
   beats a broad "answer everything" agent that is mediocre at all of it.
2. **Evaluation is a first-class citizen.** Build evals *alongside* the agent, never after.
   Evals are a revenue generator (they de-risk and accelerate), not a cost center.
3. **Process guides automation.** Map the human workflow first; automate deliberately. Start
   with manual SME review, discover the criteria, *then* automate them into judges/checks.
4. **Version everything** — prompts, tools, **routing logic**, and data sources. Agent behavior
   emerges from all four; if they aren't versioned you can't debug or roll back.
5. **Design for observability.** Every decision point and tool call must be traceable and
   attributable (cost included). If you can't see it, you can't operate it.
6. **Humans in the loop for high-stakes actions.** Consequential, irreversible actions get an
   explicit approval gate.

Extending the DevOps trio: **Flow** (deploy fast *and* reliably), **Feedback** (short, rich
loops from SMEs / users / judges / metrics), **Continuous Learning** (codify hard-won lessons
into reusable frameworks, reference architectures, and design patterns). → `resources/devops-principles.md`.

---

## Anti-patterns (know these cold)

The fastest way to help is often to name the anti-pattern the team has walked into:

- **Starting too broad** → scope to one use case.
- **Overcomplex architecture** (supervisor / multi-agent where a sequential chain would do)
  → prefer deterministic chains; reach for multi-agent only when the problem truly needs it.
- **ReAct loops for single-tool tasks** → direct function calls for deterministic actions.
- **Overcomplicated tools** (Text-to-SQL where a parameterized query works) → reserve
  LLM-based tools for genuinely complex mapping.
- **Unoptimized retrieval** → evaluation-driven RAG optimization.
- **Ungoverned tools** (broad credentials) → centralized, governed tool registry.
- **No rollback / versioning** → version every component.
- **No systematic evaluation** (manual spot-checks) → programmatic eval suites.
- **No human in the loop for high-stakes** → mandate HITL.
- **No cost controls** → proactive budgets + limits at the AI Gateway.

Full table with problem / risk / fix, plus the stakeholder metric anti-pattern → `resources/anti-patterns.md`.

---

## The four deployment patterns (choose the simplest that fits)

Complexity grows on two axes — **account/workspace isolation** and **agent specialization**.
Pick the simplest and evolve incrementally.

| Pattern | Shape | When | Maturity |
|---|---|---|---|
| **P1** | Single account, **single agent** | Starting out, PoCs, single-purpose agents | Beginner |
| **P2** | Single account, **multi-agent** (supervisor + sub-agents) | Composite agents, orchestration, microservices | Intermediate |
| **P3** | **Multi-account**, single agent | Compliance / strict env isolation | Intermediate–advanced |
| **P4** | **Multi-account, multi-agent** | Enterprise scale, many teams | Advanced (dedicated AgentOps team) |

Full characteristics, the "choosing" table, common pipeline components shared by all patterns,
and AgentOps Stacks → `resources/deployment-patterns.md`.
⚠ Before building P2/P4, confirm multi-agent is warranted — the *pattern* is valid but often
premature (see `resources/anti-patterns.md`). When it is warranted, add the supervisor with the
**`add-supervisor`** skill: it scaffolds a **custom LangGraph supervisor on Apps** (the durable
path), not a deprecated managed API. Background: the multi-agent note in `resources/platform-state.md`.

---

## The 7-phase project pipeline

1. Project conception & team formation → 2. Data preprocessing & indexing → 3. Agent
architecture design → 4. Agent development & evaluation framework → 5. Feedback collection &
monitoring → 6. Iterative development & optimization → 7. Scaling & governance.

Projects iterate between phases; that's expected. Objectives and cross-references per phase →
`resources/project-pipeline.md`.

---

## How to operate (advisory procedure)

When invoked, **locate the team on the lifecycle**, then load the matching resource and route:

1. **New / early project, or "what do I focus on first?"** → `resources/project-pipeline.md`
   (Phase 1–3) and the six planning activities + the fully worked telco example in
   `resources/worked-example-telco.md`. Push for a narrow scope and cross-functional metric
   definition *before* code.
2. **"Which architecture?"** → `resources/deployment-patterns.md`; recommend the simplest
   pattern that meets current needs; check `resources/platform-state.md` for multi-agent.
3. **"How do we evaluate / observe this?"** → `resources/evaluation.md` (the operational eval
   playbook) and the Feedback principle in `resources/devops-principles.md`. Then hand off to
   `agentops-lifecycle` (Steps 4–5, 10), which wires the eval gate and MLflow tracing.
4. **"It's unreliable / over-engineered / stuck"** → `resources/anti-patterns.md`.
5. **"Permissions / security / cost / governance"** → `resources/governance-and-access-control.md`.
6. **"Who needs to be involved / how do we report progress?"** → `resources/stakeholder-management.md`.
7. **Scaling beyond one agent** → Phase 7 in `resources/project-pipeline.md` + Continuous
   Learning in `resources/devops-principles.md` (frameworks, reference architectures, an AI
   governance board).

Always: enforce the non-negotiables, and cite the book's chapter and section so the reader can
go deeper (see `resources/sources.md`).

---

## Routing — hand off the hands-on work

This skill is advisory. For execution, hand off to the agentops-stacks skill that owns the task
(and to the underlying Databricks capability where no skill covers it):

| The team needs to… | Hand off to |
|---|---|
| Decide whether multi-agent / a supervisor is warranted **before** building it | `resources/anti-patterns.md` + `resources/deployment-patterns.md` (this skill owns the call) |
| **Scaffold** a new AgentOps project (DAB + per-agent Apps + eval + CI/CD) | **`agentops-stacks`** |
| Walk the full lifecycle — data prep, dev, **eval gate**, dev→staging→prod promotion, monitoring | **`agentops-lifecycle`** |
| **Add another agent** to the project | **`add-agent`** |
| **Add a supervisor** to route across agents (multi-agent) | **`add-supervisor`** |
| Stand up / troubleshoot **RAG retrieval** (Vector Search index, sync, retriever) | **`vector-search-ops`** |
| Register / troubleshoot **UC-function tools** (grants, registration) | **`uc-functions-ops`** |
| **State store / agent memory** — pause-resume, checkpointer (short- & long-term) | **`lakebase-ops`** |
| Add a governed **model service, model provider service, or MCP service** to the project DAB | **`unity-gateway-ops`** |
| Build **eval datasets / scorers**, judges, `mlflow.genai.evaluate()`, tracing | MLflow GenAI evaluation & Tracing (wired by `agentops-lifecycle`, Steps 4–5 & 10) |
| Deploy to a **serving endpoint** / stand up a **UI** | Databricks Model Serving / Databricks Apps (the scaffold provisions per-agent Apps) |
| **Governance / grants / audit tables / on-behalf-of-user** | Unity Catalog |
| Managed **Knowledge Assistant / Genie / Supervisor Agent** | Agent Bricks (⚠ check `resources/platform-state.md`) |

---

## Resource index

| File | Contents |
|---|---|
| `resources/deployment-patterns.md` | The 4 patterns in full, the choosing table, common pipeline components, AgentOps Stacks |
| `resources/project-pipeline.md` | The 7 phases with objectives, activities, and cross-references |
| `resources/devops-principles.md` | Flow, Feedback, Continuous Learning — including the feedback flow and judge-alignment loop |
| `resources/evaluation.md` | The operational eval & observability playbook: golden datasets, testing pyramid, top-down/bottom-up, MLflow scorers, offline+online, cost-effective eval, observability by persona |
| `resources/anti-patterns.md` | Full anti-pattern table (problem / risk / fix) + the metric anti-pattern |
| `resources/governance-and-access-control.md` | Two-level permission model, Unity Catalog enforcement, AI Gateway cost control, AI governance board |
| `resources/stakeholder-management.md` | Stakeholder map, RACI, communication cadence, success metrics & dashboards |
| `resources/worked-example-telco.md` | End-to-end telco customer-support agent + reusable shared abstractions (BaseAgent, BaseScorer, MLflow CLI) |
| `resources/platform-state.md` | ⏱ Time-sensitive: serving-endpoint & managed-product lifecycles, the durable multi-agent path, AgentOps Stacks. Verify against current docs. |
| `resources/sources.md` | Authors, the book/blog links, related external references, and the Databricks capabilities this maps onto |

> Note: `resources/platform-state.md` is dated and moves fast — re-verify its specifics
> against current official Databricks documentation before relying on them.
