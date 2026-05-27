# agentops-stacks

A Declarative Automation Bundle (DAB) template + coding-assistant plugin for AI projects on Databricks. Scaffolds the production envelope — dev/staging/prod targets, Unity Catalog conventions, CI/CD wiring for four platforms — and adds production patterns (evaluation gates, governance posture, monitoring, feedback loops) as the project matures.

## What you get

agentops-stacks generates the production envelope for an AI project on Databricks. The scaffold includes:

- Three-environment Declarative Automation Bundle (dev / staging / prod) with `direct` deployment engine
- One Unity Catalog catalog per environment, plus a schema and managed volume for artifacts
- MLflow experiment configured to land artifacts in the volume
- CI/CD wiring for one of four platforms — GitHub Actions, GitHub Actions for GHES, GitLab, or Azure DevOps — with PR validation, staging deploy on merge to `main`, and prod deploy on `v*` tag
- Cloud auth (Azure service principal; AWS and GCP tokens) wired into the CI/CD workflows
- `AGENTS.md` with conventions for coding assistants
- `docs/setup.md` covering UC catalogs, CLI profiles, and CI/CD credentials

Application code, pipelines, model serving, jobs, and apps go under `src/` and new files in `resources/`. Familiarity with Declarative Automation Bundles and CI/CD pipelines is assumed.

## Prerequisites

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) — recent enough to support the direct deployment engine (any release from the past 6 months is safe)
- [uv](https://docs.astral.sh/uv/) package manager
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

The CLI prompts for `project_name`, `cloud`, and `cicd_platform`. For non-interactive runs, supply the values via `--config-file <path>`:

```bash
cat > inputs.json <<'EOF'
{
  "input_project_name": "my_agent",
  "input_cloud": "aws",
  "input_cicd_platform": "github_actions"
}
EOF
databricks bundle init https://github.com/databricks-solutions/agentops-stacks --config-file inputs.json
```

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

3. **Answer the prompts.** The skill asks for project name, cloud (aws / azure / gcp), CI/CD platform, and destination. Defaults are sensible — confirm or adjust.

4. **Follow the next-steps message.** The CLI prints the post-scaffold sequence — `uv sync`, fill in `databricks.yml` workspace hosts, validate, deploy. The assistant relays it unchanged.

---

## After scaffolding

```bash
cd <project_name>
uv sync                                                       # generates uv.lock — commit it
databricks bundle validate -t dev --profile <dev-profile>
databricks bundle deploy -t dev --profile <dev-profile>
```

Set workspace hosts and Unity Catalog grants per `docs/setup.md` in the rendered project before deploying.

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
