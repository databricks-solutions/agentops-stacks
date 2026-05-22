# Genie Code Workspace Flow

## Canonical flow

1. User creates an empty Git folder in the workspace via Workspace > Add > Git folder, pointing at an empty target repo (e.g., `/Workspace/Users/<user>/my-agent/`). This step is required — the scaffold must land inside a Git folder for the workspace UI Deployments panel to appear.
2. User opens Genie Code from inside that Git folder and asks to scaffold.
3. Collect the four inputs. Set `destination` to the Git folder itself (the bundle will be created as `<git-folder>/<project_name>/` — matching the layout produced by Workspace UI's "Create > Bundle").
4. Run `scaffold.sh` with the git URL form (no local clone required in the workspace).
5. The scaffold lands at `<destination>/<project_name>/`. The user commits and pushes through the workspace UI's Git controls.
6. After scaffolding, the user can deploy via either the workspace UI's Deployments panel on the bundle (Targets > `dev` > Deploy) or the CLI (`databricks bundle deploy -t dev`).

## Genie Code specifics

- Git CLI is available in Genie Code, but repo lifecycle (create, commit, push) is more reliable through the workspace UI. Treat "Git folder exists in the workspace" as a hard prerequisite and instruct the user to set it up via the UI if they haven't.
- `databricks --version` returns nothing in Genie Code — expected. The wrapped CLI doesn't expose a version. Skip the version check; let `bundle init` errors surface if anything is wrong.
- A Git folder can host multiple bundles as sibling subdirectories — the Workspace UI's Deployments pane is scoped per-bundle, not per-Git-folder. Re-running the scaffold against the same Git folder with a different `project_name` creates a coexisting bundle alongside existing ones.

## Scaffold-in-place limitation

`databricks bundle init` always creates `<destination>/<project_name>/`. There is no native flag to scaffold *into* an existing empty directory. If the user wants the scaffold contents at the root of an existing repo (instead of inside a subdirectory), scaffold to a temp location and `mv` the contents into place after. Don't attempt to outsmart the CLI with input_root_dir tricks — the path concatenation breaks in subtle ways.
