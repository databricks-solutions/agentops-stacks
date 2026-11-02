# After Scaffolding

## Next steps

Surface these to the user after a successful scaffold:

1. `cd <destination>/<project_name>`
2. Review `.agentops-stacks/manifest.yml` and `databricks.yml`
3. Set workspace hosts and Unity Catalog grants — see `docs/setup.md` in the rendered project
4. `uv sync` (generates `uv.lock` — must be committed)
5. `databricks bundle validate -t dev`
6. If usage tracking is enabled (`enable_cost_tags: yes`) without a `usage_policy_id`, set one up: run `scripts/create_usage_policy.sh` (needs an account-level CLI profile; it also wires the IDs in), or have a workspace admin create them in Settings → Compute → Serverless usage policies (see `docs/usage-tracking.md`) and then run `python3 scripts/enable_usage_policy.py dev=<id> staging=<id> prod=<id>`. Resource tags work without it, but serverless usage stays untagged.

Do not attempt step 5 (or create usage policies in step 6) from within this skill — it requires the user's workspace authentication and is the first thing they'll exercise themselves.

## Two paths to deploy

- **Workspace UI (Genie Code default).** If the scaffold landed inside a Git folder, open the bundle in the workspace UI — the Deployments panel lets you pick a target (`dev`) and Deploy with one click. No terminal needed.
- **CLI.** `databricks bundle deploy -t dev`, then `databricks bundle run <agent> -t dev` (per agent App) from the bundle's root directory. Works on every surface.

## Routing to ai-dev-kit skills

For the development work that follows (agent code, evaluation, monitoring), route to ai-dev-kit skills:

- `databricks-bundles` — bundle authoring, deployment, lifecycle
- `databricks-mlflow-evaluation` — MLflow 3 evaluation, scorers, judges
- `databricks-vector-search` — RAG, semantic search, similarity matching
- `databricks-app-python` — Databricks Apps in Python
- `databricks-genie` / `databricks-agent-bricks` — Genie Spaces, Knowledge Assistants, MAS

## What this skill does NOT do

- Doesn't apply evaluation, governance, or monitoring patterns. Those are separate skills coming later in the agentops-stacks plugin.
- Doesn't create or clone git repos. The user owns repo creation.
- Doesn't deploy. The user runs `databricks bundle deploy` from their authenticated environment.
- Doesn't modify an existing scaffold. For retrofitting an existing project, a future `/adopt` workflow will handle that.
