# AgentOps Stacks

A Declarative Automation Bundle (DAB) template plus a portable coding-assistant plugin
that scaffold production-ready AI projects on Databricks and guide them through
orchestration, governance, and lifecycle as the solution develops. Agent code,
data pipelines, and platform resources come from coding assistants (Claude Code,
Cursor, Genie Code) or manual development — agentops-stacks owns the operational
envelope around them.

## Design Priorities (in order)

1. **Scaffold first, then guide. Don't ship components.** The template generates
   the production envelope — DAB layout, dev/staging/prod targets, UC conventions,
   CI/CD wiring, scaffold contract. The plugin provides review, proposal, and
   lifecycle skills that work alongside whatever the developer builds inside the
   scaffold. Agent code and Databricks resources themselves are out of scope —
   they come from ai-dev-kit, other coding assistants, or hand-written code.

2. **Opinionated evaluation gates.** When evaluation patterns are applied to a
   scaffold, they ship eval-on by default. Where evaluation isn't yet possible
   (e.g., pending SDK support for Genie Benchmarks or KA Guidelines), the
   proposal includes a stub that documents what will be evaluated and exits
   cleanly.

3. **Closed-loop operations, not demos.** Every operational pattern this project
   proposes must close the loop back to development action. Production eval
   results feed back as new eval dataset entries. User/SME feedback becomes
   annotation candidates. Monitoring alerts map to runbooks. A pattern that only
   demonstrates a capability without connecting it to the feedback loop is
   incomplete.

4. **Challenge assumptions at every step.** After completing a design decision or
   implementation step, surface what's still uncertain, what could break the
   assumption, or what the next decision depends on. Every review should end with
   "what are we missing?"

5. **Security built into every pattern.** For each production pattern the project
   proposes, document: what data flows through it, where that data is stored or
   logged, and what compliance implications that creates.

   Key principles:
   - **No lazy defaults.** UC-governed resources, scoped credentials,
     least-privilege permissions, and workspace-boundary data flows by default.
   - **Practical security documentation per pattern.** What to configure, what to
     restrict, what to watch for. Written for the deployer, not the compliance
     auditor.
   - **DASF 3.0 posture visibility.** Each pattern documents which DASF practices
     it implements by default, which require customer configuration, and which
     are out of scope.
   - **GA vs preview diligence.** Model: MLflow 3 core is HIPAA-supported under
     CSP, but Prompt Registry (Beta) is not listed under "Supported preview
     features" — so non-PHI only. Apply this level of scrutiny to every pattern.

6. **Integrate with coding assistants, don't replace them.** The project
   integrates with Claude Code, Cursor, Genie Code, and
   [ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit). Coding
   assistants and ai-dev-kit provide the component-creation surface (agents, MCP
   servers, vector indexes, jobs). agentops-stacks provides the orchestration,
   governance, and lifecycle surface above them. The scaffold step is reachable
   through the Databricks CLI alone (`databricks bundle init`); the plugin is
   the conversational UX over that same CLI. ai-dev-kit is a hard prereq for
   the post-scaffold workflow on every surface today — its trajectory is
   asymmetric, with Genie Code potentially absorbing equivalent capability
   natively over time while Claude Code and Cursor continue to depend on it.

## Standing Requirements

- **DAB direct engine only.** All generated `databricks.yml` files include
  `bundle: engine: direct`. The legacy Terraform-backed engine is not supported.
  Deploy commands use plain `databricks bundle deploy -t <target>` — the engine
  setting in `databricks.yml` handles engine selection. Do not pass engine flags
  on the CLI.

- **Declarative DAB resources over notebook-created resources.** If a resource is
  a first-class DAB resource type, define it in `databricks.yml`. Notebooks only
  create resources DAB doesn't yet support. Document why so it can be migrated
  when support lands. Reference:
  https://docs.databricks.com/aws/en/dev-tools/bundles/resources
  Known notebook-required: Vector Search index (not yet a DAB resource type).
  <!-- Add others here as discovered. Remove when DAB support lands. -->

- **One DAB = one deployment unit.** Cross-DAB dependency orchestration is out
  of scope.

- **Concise, actionable documentation.** What this is, what to configure, how to
  deploy, relevant links. Assume Databricks and CI/CD familiarity. No
  editorializing.

## Architecture

### Target Solution Architecture

The production pattern is a three-environment lifecycle with eval-gated promotion:

```
  Git Provider
  (feature branch)──────────(main branch)────────────(release branch)──────────────
        │                        │                          │
        ▼                        ▼                          ▼
  ┌─────────────────┐    ┌───────────────────┐    ┌──────────────────────┐
  │  DEVELOPMENT    │    │  STAGING /        │    │  PRODUCTION          │
  │                 │    │  VALIDATION       │    │                      │
  │  Data Prep      │    │  Unit Tests       │    │  Continuous Deploy   │
  │  Agent Dev      │    │  Integration      │    │  App / Endpoint      │
  │  Evaluation     │    │  Validation       │    │  Batch Inference     │
  │  App Deploy     │    │  Pre-prod Eval    │    │  Monitoring          │
  │  (dev target)   │    │  Gates            │    │  Online Eval         │
  └────────┬────────┘    └────────┬──────────┘    └──────────┬───────────┘
           │                      │                          │
      Dev Catalog            Test Catalog              Prod Catalog
           └──────────────────────┴──────────────────────────┘
                            Unity Catalog
```

This scales along two axes: single/multi-agent and single/multi-account.
Multi-account variants add Data Sharing between accounts. Multi-agent variants
add per-agent workflow blocks and routing.

### Tooling Architecture

One engine, two ways to drive it:

- **DAB template (canonical).** The scaffold is generated by `databricks
  bundle init`. Runs in any environment with the Databricks CLI — local
  terminal, CI, or Genie Code. Produces the bundle layout, CI/CD wiring, and
  scaffold contract.
- **agentops-stacks plugin.** Portable coding-assistant skills (SKILL.md +
  installer scripts) for Claude Code, Cursor, and Genie Code. The scaffold
  skill is a conversational UX layer over `databricks bundle init` — it
  collects inputs through the assistant, writes a config file, runs the CLI,
  and surfaces the result. Subsequent skills (eval gates, governance,
  monitoring) provide authoring help on top of an existing scaffold. The
  plugin is optional for the scaffold step; the CLI alone is sufficient.

Both paths land at the same scaffold contract — `.agentops-stacks/manifest.yml`
— that records which patterns have been applied. CI/CD and tooling read this
contract without needing to know how the project was created.

## Production Patterns

The scaffold ships structural pieces only. Production patterns are applied as
the solution develops, not pre-installed:

- **Eval gates** — scaffolded per agent (`src/agents/<agent>/eval/gates.yml` +
  `eval/evaluate_agent.py`); CI on every platform runs them per agent and
  gates promotion on them.
- **Governance posture** — add `governance/posture.md` and
  `governance/data_flows.md`; the prod-promotion workflow checks for presence.
- **Monitoring** — configure trace destination, alert rules, and dashboards per
  resource as you deploy them.

Each pattern is one PR's worth of additions to an existing scaffold. The plugin
can propose and review these; a developer can apply them by hand from the docs.

## Governance & Platform Constraints

From the Databricks AI Governance Strategy (March 2026).

- **UC securables expanding (summer 2026).** Avoid hardcoding current resource
  type assumptions.
- **AI Gateway is the governance enforcement layer.** Design guardrails around
  it.
- **Tool Gateway / MCP governance coming.** MCP servers will be UC securables
  with identity propagation. Document integration path.
- **Structured observability.** Use MLflow/OTel trace formats. No custom log
  schemas. Compatible with Lakewatch (platform AI-optimized SIEM, in
  development).
- **External agents are a future hosting pattern.** Current pattern: UC
  connections + registry table + pyfunc wrapper. Eval/monitoring should work
  against any agent that emits standard traces.
- **Identity propagation (OBO)** — document in pattern docs as customer actions.
- **Cost tracking** as a default when agent patterns are applied (MLflow token
  logging).

## Validation

- `databricks bundle validate` must pass after any change.
- `databricks bundle deploy --target dev` is the deployment command. The direct
  engine is configured in `databricks.yml` — do not use the legacy Terraform
  engine.
