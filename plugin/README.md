# agentops-stacks plugin

A portable plugin that scaffolds AgentOps Stacks projects from inside a coding assistant. The plugin is a conversational UX layer over `databricks bundle init` — it collects the project's inputs from the user, writes them to a config file, and shells out to the CLI. Works in Claude Code, Cursor, and Genie Code.

The plugin and the [DAB template](../template/) share the same scaffold contract (`.agentops-stacks/manifest.yml`). The CLI alone is sufficient for scaffolding; the plugin is the additive on-ramp for users working inside a coding assistant.

## What this plugin ships

### Skills

| Skill | Trigger | What it does |
|-------|---------|--------------|
| **`agentops-bigbook`** | `agentops best practices`, `which deployment pattern`, `is multi-agent warranted`, `agent evaluation strategy` | Advisory reference distilled from the Big Book of AgentOps — deployment patterns, the project pipeline, DevOps principles, anti-patterns, evaluation & observability, governance, and stakeholder management. The "why / which / what not to do" that comes before you scaffold; routes to the other skills to execute. |
| **`agentops-stacks`** | `scaffold a new agentops project` | Scaffolds a new multi-agent LangGraph project (per-agent Databricks Apps, shared components, UC schema and volume, MLflow experiments, CI/CD wiring). One-time use at project start. |
| **`agentops-lifecycle`** | `walk me through the agentops lifecycle` | Guides an existing scaffold through the complete Single-Account Single-Agent lifecycle — data prep, agent dev, eval gate, SME calibration, CI/CD promotion, batch eval baseline, and production monitoring. 10 steps across dev → staging → prod. |
| **`add-agent`** | `add agent`, `new agent`, `create another agent` | Adds a new agent to an existing project — copies an existing agent as a template and wires it into `databricks.yml` and the manifest. |
| **`add-supervisor`** | `add supervisor`, `add a router`, `orchestrate my agents` | Checks whether a supervisor is warranted, then scaffolds a custom LangGraph supervisor that routes across the project's agents into `databricks.yml` and the manifest — gated by the same eval loop as any agent. |
| **`right-size-capability`** | `add a tool`, `write an MCP server`, `add a skill` | Decides whether a new capability should be a UC-function tool, an MCP server, or an Agent Skill, and pushes back when the requested one is the wrong fit. Use before adding a capability. |
| **`vector-search-ops`** | `vector search index`, `sync the index`, `retrieval quality` | Operates and troubleshoots the Vector Search component: index status, sync, retriever tests, the DLT data pipeline. |
| **`lakebase-ops`** | `agent memory`, `lakebase`, `checkpointer` | Operates and troubleshoots the Lakebase memory component: endpoint health, credentials, short- and long-term memory tables, the Postgres schema. |
| **`uc-functions-ops`** | `register a UC function`, `EXECUTE grant`, `UC tools` | Registers UC functions, updates EXECUTE grants, lists available functions, and re-runs the registration job. |
| **`usage-tracking-ops`** | `track usage`, `cost attribution`, `tag resources`, `usage policy` | Tags project resources (`project`/`environment`/`agent`) and attaches a serverless usage policy for cost attribution. Retrofits tags onto existing scaffolds and queries attributed usage in `system.billing.usage`. |

### Commands

| Command | Skill |
|---------|-------|
| `/init-agentops-stacks` | `agentops-stacks` |
| `/agentops-lifecycle` | `agentops-lifecycle` |
| `/add-agent` | `add-agent` |
| `/add-supervisor` | `add-supervisor` |

### Installers

Under `skills/`, mirroring [ai-dev-kit's pattern](https://github.com/databricks-solutions/ai-dev-kit#installation):
- `install_skills.sh` — CLI installer. Copies each skill's whole directory into `.claude/skills/` and the commands into `.claude/commands/`, with optional `--install-to-genie` to also upload the skills to the workspace.
- `install_genie_code_skills.py` — Databricks notebook for in-workspace installs without a local clone. It installs the same skill directories.

## Prerequisites

- **Databricks CLI** on every surface. The skill shells out to `databricks bundle init`. Genie Code's wrapped CLI is fine; local environments need a current install ([install docs](https://docs.databricks.com/dev-tools/cli/install.html)).
- **ai-dev-kit plugin** for the post-scaffold workflow. The skill is self-contained for scaffolding, but the eval, governance, and monitoring guidance routes to ai-dev-kit skills (`databricks-bundles`, `databricks-mlflow-evaluation`, `databricks-vector-search`, etc.).

## Try it — Genie Code

Prerequisites: a Databricks workspace, write access to your own `/Workspace/Users/<you>/` path. Two install paths.

### Option A — `install_skills.sh --install-to-genie` (recommended)

From a local clone of this repo:

```bash
git clone https://github.com/databricks-solutions/agentops-stacks.git
cd agentops-stacks
./plugin/skills/install_skills.sh --install-to-genie --profile <your-databricks-profile>
```

The installer lands each skill's directory under `.claude/skills/` locally, then uploads each one to `/Workspace/Users/<you>/.assistant/skills/<skill>/`. Mirrors the ai-dev-kit install pattern.

### Option B — in-workspace notebook

If you can't run a script locally:

1. In your workspace, open [`plugin/skills/install_genie_code_skills.py`](skills/install_genie_code_skills.py) as a notebook. The simplest way is to clone this repo as a Git folder via Workspace → Add → Git folder, then open the file.
2. Run all cells. The notebook pulls every skill's files from GitHub and uploads them to `/Workspace/Users/<you>/.assistant/skills/<skill>/`. Defaults: `GITHUB_OWNER=databricks-solutions`, `GITHUB_REF=main`. To install from a branch, set the `AGENTOPS_GITHUB_REF` env var when running as a Python script, or edit the configuration cell.

### Use it

After either install:

1. Pre-create a **Git folder** in the workspace via Workspace → Add → Git folder, pointing at an empty target repo. The bundle must land inside a Git folder for the workspace UI's Deployments panel to appear on it post-scaffold — matching the layout produced by Workspace UI's own "Create → Bundle" flow. The bundle lands at `<git-folder>/<project_name>/`, and the generated CI/CD workflows only run from a repo root, so move the bundle's contents to the Git folder root if you want CI/CD (see [genie-code.md](skills/agentops-stacks/reference/genie-code.md)).
2. Open Genie Code from inside that Git folder and say "scaffold a new agentops-stacks project."
3. The skill collects inputs in phases (infrastructure, data sources, tools, usage tracking, evaluation), confirms them, writes a temp config file under `/tmp/`, and runs:
   ```
   databricks bundle init https://github.com/databricks-solutions/agentops-stacks \
     --config-file <tmp> --output-dir <destination>
   ```
4. The CLI's success message and next-steps prints verbatim. After that, you can deploy via the workspace UI's Deployments panel on the bundle (Targets → `dev` → Deploy) or via `databricks bundle deploy -t dev` in the terminal.

## Try it — Claude Code or Cursor

Prerequisites: `databricks` CLI installed, a coding assistant that loads `.claude/skills/`.

1. Clone this repo:
   ```bash
   git clone https://github.com/databricks-solutions/agentops-stacks.git
   ```

2. From the directory you'll open the assistant in, which is the *parent* of the project to scaffold, run the installer pointing at the cloned repo:
   ```bash
   /path/to/agentops-stacks/plugin/skills/install_skills.sh
   ```
   The installer copies each skill's directory (its `SKILL.md` plus any scripts and reference files) to `.claude/skills/` and the slash commands to `.claude/commands/` in the current directory. `databricks bundle init` reads the template from this repo at run time, so the template itself isn't copied.

3. Open Claude Code or Cursor in that directory and either:
   - Type `/init-agentops-stacks`, or
   - Say "scaffold a new agentops-stacks project."

   The assistant collects the inputs and runs `bundle init`, which creates `<project_name>/`. Make that folder its own git repository: the generated CI/CD workflows only run from a repo root.

4. To use `/agentops-lifecycle`, `/add-agent` and the other skills from inside the new project, run the installer again in `<project_name>/`.

## Layout

```
plugin/
├── README.md                                    # this file
├── commands/
│   ├── init-agentops-stacks.md                  # scaffold command
│   ├── agentops-lifecycle.md                    # lifecycle command
│   ├── add-agent.md                             # add-agent command
│   └── add-supervisor.md                        # add-supervisor command
└── skills/
    ├── install_skills.sh                        # local + Genie upload installer
    ├── install_genie_code_skills.py             # in-workspace notebook installer
    ├── agentops-bigbook/
    │   ├── SKILL.md                             # advisory reference (Big Book of AgentOps)
    │   └── resources/                           # patterns, pipeline, eval, governance, etc.
    ├── agentops-stacks/
    │   ├── SKILL.md                             # scaffold skill (phased input collection)
    │   ├── reference/                           # post-scaffold, Genie Code, common issues docs
    │   └── scripts/
    │       ├── validate_inputs.py               # input checks run before bundle init
    │       ├── scaffold.sh                      # validate + bundle init
    │       ├── add_agent.py                     # /add-agent engine
    │       ├── add_supervisor.py                # /add-supervisor engine (custom LangGraph)
    │       └── supervisor_templates/            # supervisor graph/agent/tools templates
    ├── agentops-lifecycle/SKILL.md              # lifecycle skill (10-step dev→prod guide)
    ├── add-agent/SKILL.md                       # wires a new agent into an existing project
    ├── add-supervisor/SKILL.md                  # supervisor that routes across agents
    ├── right-size-capability/SKILL.md           # tool vs MCP server vs skill
    ├── vector-search-ops/SKILL.md               # Vector Search operations
    ├── lakebase-ops/SKILL.md                    # Lakebase memory operations
    ├── uc-functions-ops/SKILL.md                # UC function tools
    └── usage-tracking-ops/SKILL.md              # tags and usage policies
```

Each skill is a directory: its `SKILL.md` plus any scripts, reference or
resource files it uses, which the installers copy along with it. There's no
Python renderer and no vendored template tree: `databricks bundle init` reads
the template directly from this repo at scaffold time, and the lifecycle skill
references generated project files by their scaffold-relative paths.

## Known UX notes

- **Genie Code safety heuristic.** Genie Code blocks programmatic file deletion (`os.remove`, `Path.unlink`) even for paths under `/tmp/`. The skill leaves its temp config file in place rather than cleaning it up, so the scaffold ends on the CLI's success message instead of a confusing "Code execution blocked" prompt. The OS cleans `/tmp/` on its own.
- **Git workflow in Genie Code.** The git CLI is available in Genie Code, but repo lifecycle (create remote, commit, push) is currently more reliable through the workspace UI. In Genie Code the skill scaffolds into a Git folder, so set one up via the workspace UI before scaffolding.
- **Scaffold-in-place limitation.** `databricks bundle init` always creates `<destination>/<project_name>/`. If you've pre-created a Git folder and want the scaffold contents at its root (instead of nested inside), you'll need to scaffold to a temp location and move the contents into place. See [SKILL.md](skills/agentops-stacks/SKILL.md) for details.
- **CLI auth refresh.** On local surfaces, `bundle init` eagerly refreshes the default profile's token. If your token is expired, run `databricks auth login` before scaffolding (auth is required for the next step, `bundle validate`, anyway).
