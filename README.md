# agentops-stacks

A Declarative Automation Bundle (DAB) template + coding-assistant plugin for production-ready multi-agent LangGraph projects on Databricks. Scaffolds the production envelope — per-agent Databricks Apps, shared components (Vector Search, Lakebase, UC functions), dev/staging/prod targets, Unity Catalog conventions, CI/CD wiring for four platforms — and adds production patterns (evaluation gates, governance posture, monitoring, feedback loops) as the project matures.

## What you get

agentops-stacks generates the production envelope for a multi-agent LangGraph project on Databricks. The scaffold includes:

- Three-environment Declarative Automation Bundle (dev / staging / prod) with `direct` deployment engine
- Per-agent LangGraph graph served as a Databricks App via MLflow AgentServer — one App resource per agent
- Shared components scaffolded on demand: Vector Search (RAG retrieval), Lakebase (Postgres conversation memory), UC function tools
- One Unity Catalog catalog per environment, plus schemas, volumes, and per-agent MLflow experiments
- CI/CD wiring for one of four platforms — GitHub Actions, GitHub Actions for GHES, GitLab, or Azure DevOps — with PR validation, staging deploy on merge to `main`, and prod deploy on `v*` tag
- Cloud auth (Azure service principal; AWS and GCP tokens) wired into the CI/CD workflows
- Per-agent evaluation harness: `eval/gates.yml`, `eval/create_dataset.py`, `eval/evaluate_agent.py`
- `AGENTS.md` with conventions for coding assistants
- `docs/setup.md` covering UC catalogs, CLI profiles, and CI/CD credentials

Agent code lives under `src/agents/<name>/`. Shared components live under `src/components/`. New DAB resources go in `resources/`. Familiarity with Declarative Automation Bundles and CI/CD pipelines is assumed.

## Prerequisites

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) — recent enough to support the direct deployment engine (any release from the past 6 months is safe)
- [uv](https://docs.astral.sh/uv/) package manager
- [Node.js](https://nodejs.org/) >=20.19 — for the chat UI frontend bundled with each agent App
- A Databricks workspace with Unity Catalog enabled (one catalog per environment — see `docs/setup.md` in the rendered project)
- [ai-dev-kit plugin](https://github.com/databricks-solutions/ai-dev-kit) — required for the post-scaffold workflow (eval gates, monitoring, governance). Install before the plugin's post-scaffold skills land

---

## How to scaffold

There's one engine — `databricks bundle init` — and two ways to drive it.

### Run the CLI directly

Works anywhere `databricks` runs — local terminal, CI, or Genie Code.

```bash
databricks bundle init https://github.com/databricks-solutions/agentops-stacks
```

The CLI prompts for all inputs interactively. For non-interactive runs, supply the values via `--config-file <path>`:

```bash
cat > inputs.json <<'EOF'
{
  "input_project_name": "my_agentops_project",
  "input_initial_agent_name": "default",
  "input_cloud": "aws",
  "input_cicd_platform": "github_actions",
  "input_use_vector_search": "no",
  "input_use_lakebase": "no",
  "input_use_uc_functions": "no",
  "input_eval_dataset_source": "synthetic"
}
EOF
databricks bundle init https://github.com/databricks-solutions/agentops-stacks --config-file inputs.json
```

See `databricks_template_schema.json` for the full set of inputs and their allowed values (cloud, CI/CD platform, Vector Search, Lakebase memory type, UC functions, eval dataset source).

### Drive the CLI from a coding assistant

The agentops-stacks plugin is a conversational UX layer over `bundle init`. It collects inputs through the assistant, writes the config file, runs the CLI, and surfaces the result. Use it when you want a guided scaffold and follow-up help from the assistant.

See [plugin/README.md](plugin/README.md) for install and usage. Two install flavors:

- **Genie Code install** — open `plugin/skills/install_genie_code_skills.py` as a notebook in your workspace and run all cells. The skill is then available in Genie Code.
- **Local install** — clone this repo, run `./plugin/skills/install_skills.sh` from your project root. The skill is then available in Claude Code or Cursor.

### Using the plugin

Once installed, the plugin is invoked by your coding assistant. There's nothing to call directly — describe what you want and the assistant runs the skill.

1. **Open your coding assistant** in the target directory:
   - **Genie Code** — pre-create the destination via the workspace UI (Workspace → Add → Git folder for a repo-backed project, or just create an empty folder under `/Workspace/Users/<you>/`), then open Genie Code from inside that directory.
   - **Claude Code / Cursor** — open the assistant in the directory where you want the scaffold to land.

2. **Ask the assistant to scaffold a project.** Either:
   - Type `/init-agentops-stacks` (Claude Code / Cursor only), or
   - Say "scaffold a new agentops-stacks project" — the assistant matches the skill's description and starts the flow.

3. **Answer the prompts.** The skill collects inputs in five phases: infrastructure (project name, agent name, cloud, CI/CD platform, destination), data sources (Vector Search, Lakebase memory), tools (local Python tools, UC functions), evaluation (dataset source), then confirms and runs the scaffold. Defaults are sensible — confirm or adjust.

4. **Follow the next-steps message.** The CLI prints the post-scaffold sequence — `uv sync`, fill in `databricks.yml` workspace hosts, validate, deploy. The assistant relays it unchanged.

---

## After scaffolding

```bash
cd <project_name>/src/agents/<agent_name>
uv sync                            # generates uv.lock — commit it
cp .env.example .env               # configure Databricks auth
uv run python app/start_server.py  # run the agent locally
uv run agent-evaluate              # run the evaluation harness
databricks bundle deploy -t dev    # deploy to Databricks
```

Set workspace hosts and Unity Catalog grants per `docs/setup.md` in the rendered project before deploying to staging or prod.

### Adding more agents

Once the first scaffold is in place, use the `/add-agent` command (or say "add a new agent") to wire a second agent into the same bundle:

```bash
# In your coding assistant:
/add-agent
# or: "add a support agent to this project"
```

If the bundle was scaffolded inside a Databricks **Git folder** in the workspace (the recommended path for Genie Code users), the workspace UI also surfaces a **Deployments panel** on the bundle that lets you pick a target and deploy with one click — no terminal required. This matches the layout produced by the workspace UI's native "Create → Bundle" flow.

---

## Production lifecycle

The scaffold generates the envelope. The **AgentOps Lifecycle** skill guides
the project through the complete Single-Account Single-Agent lifecycle — from
first data ingestion to production monitoring — across three phases and 10 steps:

| Phase | Steps | What happens |
|-------|-------|--------------|
| **Dev** | 1–5 | Data prep + Vector Search indexing, agent implementation with MLflow tracing, offline eval gate, SME calibration |
| **Staging** | 6–7 | CI gate (unit tests + bundle validate + eval gate on PR), staging deploy + integration tests |
| **Production** | 8–10 | CD deploy, batch inferencing baseline, real-time monitoring + SME feedback loop |

MLflow is the operational spine at every level: experiment tracking in dev,
eval gate in CI, trace logging in prod, user feedback via `mlflow.log_feedback()`.
The `evaluation/gate.py` pattern (generated by the scaffold) runs at three
points — locally in dev, in CI on every PR, and against production data before
users are admitted — so quality regressions are caught before they reach users.

### Using the lifecycle skill

Install the plugin, then ask your coding assistant to continue from where the
scaffold left off:

```bash
# Install (Claude Code / Cursor)
./plugin/skills/install_skills.sh

# Then in the assistant:
/agentops-lifecycle
# or: "walk me through the agentops lifecycle"
```

In **Genie Code**, run `install_genie_code_skills.py` as a notebook to install,
then say "walk me through the agentops lifecycle."

The skill provides step-by-step agent actions, copy-paste code examples
grounded in the generated project files, validation criteria, and common issue
resolutions for each of the 10 steps.

### Machine-readable workflow definition

`workflows/single-account-single-agent.json` is a structured definition of the
10-step lifecycle with all actions, validations, escalation hints, and phase
metadata. It can be consumed programmatically by workflow engines (e.g.,
`/innovate`) or used as a reference when building custom automation on top of
the scaffold.

---

## Documentation

- `template/{{.input_root_dir}}/README.md.tmpl` — what a rendered project looks like
- `template/{{.input_root_dir}}/AGENTS.md.tmpl` — conventions and guidance for coding agents
- `template/{{.input_root_dir}}/docs/setup.md.tmpl` — end-to-end configuration guide
- [Declarative Automation Bundles](https://docs.databricks.com/dev-tools/bundles/)
- [MLflow 3 + Unity Catalog](https://docs.databricks.com/mlflow3/)
