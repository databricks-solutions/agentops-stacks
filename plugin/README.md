# agentops-stacks plugin

A portable plugin that scaffolds AgentOps Stacks projects from inside a coding assistant. The plugin is a conversational UX layer over `databricks bundle init` — it collects the four required inputs from the user, writes them to a config file, and shells out to the CLI. Works in Claude Code, Cursor, and Genie Code.

The plugin and the [DAB template](../template/) share the same scaffold contract (`.agentops-stacks/manifest.yml`). The CLI alone is sufficient for scaffolding; the plugin is the additive on-ramp for users working inside a coding assistant.

## What this plugin ships

### Skills

| Skill | Trigger | What it does |
|-------|---------|--------------|
| **`agentops-stacks`** | `scaffold a new agentops project` | Scaffolds a new multi-agent LangGraph project (per-agent Databricks Apps, shared components, UC schema and volume, MLflow experiments, CI/CD wiring). One-time use at project start. |
| **`agentops-lifecycle`** | `walk me through the agentops lifecycle` | Guides an existing scaffold through the complete Single-Account Single-Agent lifecycle — data prep, agent dev, eval gate, SME calibration, CI/CD promotion, batch eval baseline, and production monitoring. 10 steps across dev → staging → prod. |
| **`add-agent`** | `add agent`, `new agent`, `create another agent` | Adds a new agent to an existing project — copies an existing agent as a template and wires it into `databricks.yml` and the manifest. |

### Commands

| Command | Skill |
|---------|-------|
| `/init-agentops-stacks` | `agentops-stacks` |
| `/agentops-lifecycle` | `agentops-lifecycle` |
| `/add-agent` | `add-agent` |

### Installers

Under `skills/`, mirroring [ai-dev-kit's pattern](https://github.com/databricks-solutions/ai-dev-kit#installation):
- `install_skills.sh` — CLI installer. Lands skills into `.claude/skills/` locally, with optional `--install-to-genie` to also upload to the workspace.
- `install_genie_code_skills.py` — Databricks notebook for in-workspace installs without a local clone.

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

The installer lands `.claude/skills/agentops-stacks/SKILL.md` locally, then uploads it to `/Workspace/Users/<you>/.assistant/skills/agentops-stacks/SKILL.md`. Mirrors the ai-dev-kit install pattern.

### Option B — in-workspace notebook

If you can't run a script locally:

1. In your workspace, open [`plugin/skills/install_genie_code_skills.py`](skills/install_genie_code_skills.py) as a notebook. The simplest way is to clone this repo as a Git folder via Workspace → Add → Git folder, then open the file.
2. Run all cells. The notebook pulls `SKILL.md` from GitHub and uploads it to `/Workspace/Users/<you>/.assistant/skills/agentops-stacks/`. Defaults: `GITHUB_OWNER=databricks-solutions`, `GITHUB_REF=main`. To install from a branch, set the `AGENTOPS_GITHUB_REF` env var when running as a Python script, or edit the configuration cell.

### Use it

After either install:

1. Pre-create a **Git folder** in the workspace via Workspace → Add → Git folder, pointing at an empty target repo. The bundle must land inside a Git folder for the workspace UI's Deployments panel to appear on it post-scaffold — matching the layout produced by Workspace UI's own "Create → Bundle" flow.
2. Open Genie Code from inside that Git folder and say "scaffold a new agentops-stacks project."
3. The skill collects inputs across five phases (infrastructure, data sources, tools, evaluation, then confirm), writes a temp config file under `/tmp/`, and runs:
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

2. From your *target project's* root directory, run the installer pointing at the cloned repo:
   ```bash
   /path/to/agentops-stacks/plugin/skills/install_skills.sh
   ```
   The installer creates `.claude/skills/agentops-stacks/SKILL.md` in the current directory. That single file is the skill — `databricks bundle init` reads the template tree and schema from this repo at run time, so nothing else needs to ship alongside.

3. Open Claude Code or Cursor in that directory and either:
   - Type `/init-agentops-stacks`, or
   - Say "scaffold a new agentops-stacks project."

   The assistant collects the four inputs one at a time and runs `bundle init`.

## Layout

```
plugin/
├── README.md                                    # this file
├── commands/
│   ├── init-agentops-stacks.md                  # scaffold command
│   ├── agentops-lifecycle.md                    # lifecycle command
│   └── common-issues.md                         # troubleshooting reference
└── skills/
    ├── install_skills.sh                        # local + Genie upload installer
    ├── install_genie_code_skills.py             # in-workspace notebook installer
    ├── agentops-stacks/
    │   ├── SKILL.md                             # scaffold skill (5-phase input collection)
    │   └── reference/                           # post-scaffold, Genie Code, common issues docs
    ├── agentops-lifecycle/
    │   └── SKILL.md                             # lifecycle skill (10-step dev→prod guide)
    └── add-agent/
        └── SKILL.md                             # add-agent skill (wires new agent into existing project)
```

Each skill is a single `SKILL.md`. There's no Python renderer and no vendored
template tree — `databricks bundle init` reads the template directly from this
repo at scaffold time, and the lifecycle skill references generated project
files by their scaffold-relative paths.

## Known UX notes

- **Genie Code safety heuristic.** Genie Code blocks programmatic file deletion (`os.remove`, `Path.unlink`) even for paths under `/tmp/`. The skill leaves its temp config file in place rather than cleaning it up, so the scaffold ends on the CLI's success message instead of a confusing "Code execution blocked" prompt. The OS cleans `/tmp/` on its own.
- **Git workflow in Genie Code.** The git CLI is available in Genie Code, but repo lifecycle (create remote, commit, push) is currently more reliable through the workspace UI. The skill requires a Git folder as the destination — set up the target Git folder via the workspace UI before scaffolding.
- **Scaffold-in-place limitation.** `databricks bundle init` always creates `<destination>/<project_name>/`. If you've pre-created a Git folder and want the scaffold contents at its root (instead of nested inside), you'll need to scaffold to a temp location and move the contents into place. See [SKILL.md](skills/agentops-stacks/SKILL.md) for details.
- **CLI auth refresh.** On local surfaces, `bundle init` eagerly refreshes the default profile's token. If your token is expired, run `databricks auth login` before scaffolding (auth is required for the next step, `bundle validate`, anyway).
