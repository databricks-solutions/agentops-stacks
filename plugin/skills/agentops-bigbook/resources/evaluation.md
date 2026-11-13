# Evaluation & Observability — the operational playbook

The single most important AgentOps capability. This file is the *how*; for the *why/principle*
see `devops-principles.md` (Flow + Feedback). Route the actual coding to
MLflow's GenAI evaluation and tracing APIs.

**Core stance:** evaluation is a first-class citizen, built **alongside** the agent, never
bolted on after. It is a revenue generator (de-risks + accelerates), not a cost center.

---

## The testing pyramid for AI systems

Build bottom-up, in this order:

1. **Manual SME review** — start here to *learn the quality patterns* and discover criteria.
2. **Automated LLM judges** — encode the discovered criteria so they apply consistently at scale.
3. **Programmatic / rules-based checks** — deterministic assertions (formats, guardrails, tool
   correctness).
4. **Online production monitoring** — the same scorers run against sampled production traces.

Do **both** offline testing (pre-deploy) and online monitoring (post-deploy). They use the same
scorers so dev and prod quality are measured the same way.

---

## Two complementary ways to design a test suite

You need a combination of both:

**Top-down** — reason from the design about what *must* work, and write those tests up front
without any traces. Example: the billing agent needs a tool to query customer spend, so write a
test that the tool returns correct results. You can also **generate personas + scenarios** and
have an LLM synthesize sample queries:
```python
SCENARIOS = {
    "billing": {
        "contexts": [
            QueryContext("billing", True, True, "concerned customer", "bill inquiry"),
            QueryContext("billing", True, True, "budget-conscious customer", "payment planning"),
            QueryContext("billing", True, True, "traveling customer", "roaming charges"),
        ],
        "base_scenarios": [
            "customer sees unexpected charges on their bill",
            "customer wants to know when payment is due",
            "customer needs breakdown of current month charges",
            "customer is questioning data usage amounts",
        ],
    },
}
```

**Bottom-up** — some failure modes only appear after **error analysis of real traces** (e.g. an
LLM SQL step mixing up product acronyms). Sample ~100 traces, categorize failures, then align
LLM-judge outputs to SME feedback to create automated tests. (Full workflow in
`devops-principles.md` → "The Scientific Approach.")

---

## Make quality measurable: structure the outputs

Quality is far easier to define when outputs are **structured JSON or binary true/false**,
because established metrics like **F1** apply. **Prioritize structured responses over free text**
wherever possible. For genuinely unstructured fields (call transcripts, chat logs, technician
notes), develop **domain-aligned LLM judges**.

**Build a "thin slice" first** — a simplified version of the workflow, just complex enough to
visualize how data flows through it, rather than trying to cover the entire business process in
one go. For each substep, define expected inputs and outputs; those become your concrete,
runnable checks (deterministic tests you define up front + judge-based evals derived from real
traces).

**Routing eval is programmatic, not LLM-judge.** A supervisor's routing decision is a
*structured output* (which sub-agent), so evaluate it with **accuracy / F1 / a confusion
matrix**, and gate **per-agent and end-to-end** — not with an LLM judge.

---

## The MLflow evaluation surface (what to reach for)

- **`mlflow.genai.evaluate()`** — run scorers over an MLflow Dataset or Pandas DataFrame
  (offline). The same scorers run online over sampled production traces collected into Delta.
- **Scorers** — MLflow GenAI built-in scorers (Correctness, Guidelines, Safety,
  RetrievalGroundedness, …) + custom scorers.
- **`make_judge`** — the unified interface for judge-based evaluation. Rather than trialing
  different eval APIs, wrap it in an opinionated base class so teams get running fast:
  ```python
  from abc import ABC, abstractmethod
  from mlflow.genai.judges import custom_prompt_judge, meets_guidelines
  from mlflow.genai.scorers import scorer

  class BaseScorer(ABC):
      def __init__(self, name, sample_rate):
          self.name = name
          self.sample_rate = sample_rate      # sampling keeps online eval cheap
      @abstractmethod
      def get_make_judge_scorer(self):
          """LLM-judge evaluation wrapping MLflow make_judge."""
          ...
  ```
- **Judge alignment** — `align()` continuously tunes judges to SME feedback; MLflow's MemAlign
  aligns judges from domain-expert feedback. A judge that agrees with itself but not with SMEs
  is false confidence.
- **`optimize_prompts()` (GEPA)** — run **immediately after** an `align()` job so aligned judges
  directly drive prompt improvements. This is the automation payoff of the SME-driven loop.

→ All of the above is wired by `agentops-lifecycle` (the eval gate in `eval/`), backed by MLflow
GenAI evaluation. To evaluate/improve an existing agent holistically (tool selection, answer
quality, cost), use the same MLflow evaluation APIs.

---

## Cost-effective evaluation

LLM-based evals cost tokens (unlike free/instant unit tests). Manage it with:
- **Sampling** — evaluate a representative sample of production traces, not all of them (put a
  `sample_rate` on scorers).
- **Field-based vs. trace-based evaluation** — evaluate the minimal field needed, not the whole
  trace, when that answers the question.
- **Smart selection** — prioritize traces that failed a cheap deterministic check or a specific
  assessment for the expensive judge pass.

---

## Observability & tracing foundation

Instrument first — everything above depends on traces. Use `mlflow.autolog()` sensible defaults
to begin, then customize. **MLflow Tracing** gives span-level capture of agent execution;
**MLflow Assessments** is the review UI; the **Feedback API** (`mlflow.log_feedback()`) records
human + automated judgments against a trace. Because traces can sync to **Delta**, you can
process raw (granular, dense) traces into digestible summaries/reports and dashboards.
→ `agentops-lifecycle` (Step 10) wires production tracing + monitoring; backed by MLflow
Tracing and its trace-retrieval, metrics-query, and trace/session-analysis APIs.

---

## Observability by persona (Big Book Ch. 5.3.3)

Same trace + feedback foundation, different views per stakeholder. Design the interface around
what each persona cares about:

- **Business SME (domain expert)** — wants transparency into agent reasoning/tool-calling and a
  way to give feedback. Give them: a conversation UI **plus a side panel showing the MLflow
  trace** (reasoning → tool calls → response); a feedback interface whose inputs are recorded as
  MLflow **assessments** attached to traces (viewable by developers in the MLflow Experiments
  page); an interface to customize **label schemas**; and a periodic **summary report**. SMEs
  often lack workspace access — host the feedback UI on **Databricks Apps** and expose it via
  **Databricks One** so they can participate without a workspace login.
- **Executive sponsor** — wants ROI (automation rate, productivity, cost reduction, revenue),
  response quality, and risk/compliance. Give them an **ROI dashboard** aggregated from Delta.
- **Customer / end user** — wants fast resolution, reliability, the ability to escalate to a
  human, and strong privacy. Give them a **Databricks App** UI: preset cards for common
  questions, **cited sources**, and quick like/dislike feedback tied to their trace via
  `mlflow.log_feedback()` on a FastAPI backend.

→ Build these UIs with Databricks Apps; enforce data access with
`governance-and-access-control.md`.

---

## Success metrics to track (Ch. 6.4)

- **Quality:** task success rate, SME agreement rate, harmful-output rate, judge-score trends,
  hallucination rate.
- **Operations:** P95 latency, error rate, incident MTTR, prompt/tool change-failure rate.
- **Cost:** cost per interaction, token input/output mix, cache-hit rate, vendor/model mix.
- **Adoption / business:** active users, retention, time saved, CSAT/NPS, revenue or cost
  avoidance.

Quality metrics behave differently than classic software metrics (a reasoning LLM can have
highly variable latency per query), and manual review can itself become an anti-pattern if one
influential stakeholder's subjective feedback drives the roadmap — so define metrics
**cross-functionally and up front**.
