---
name: add-agent
description: Add a new agent to an existing AgentOps Stacks project. Creates the agent folder, app resource, experiment, and manifest entry. Triggers on "add agent", "new agent", "create another agent", "add-agent".
---

# add-agent — Add Agent to Project

Adds a new agent to an existing AgentOps Stacks project by copying an existing agent as a template and wiring it into `databricks.yml` and the manifest.

## When to use

- User wants to add a second (or third, etc.) agent to their project
- User says "add agent", "new agent", "create another agent"
- The project already exists (has `databricks.yml` and `.agentops-stacks/manifest.yml`)

## Workflow

1. **Locate the project** — find `databricks.yml` in the current directory or parents
2. **List existing agents** — show what agents already exist under `src/agents/`
3. **Gather inputs**:
   - **Agent name** — must match `^[a-z][a-z0-9_]{2,}$`
   - **Source agent** — which existing agent to copy from (default: first found)
4. **Run the script**:
   ```bash
   python plugin/skills/agentops-stacks/scripts/add_agent.py \
     --name <agent_name> \
     --from <source_agent> \
     --project-dir <project_root>
   ```
5. **Guide customization** — tell the user to edit:
   - `src/agents/<name>/graph.py` — agent behavior and component wiring
   - `src/agents/<name>/tools.py` — which tools this agent uses
   - `src/agents/<name>/eval/gates.yml` — quality bar for this agent
   - `src/agents/<name>/app.yaml` — runtime env vars if different from source

## What the script does

1. Copies `src/agents/<source>/` to `src/agents/<new_name>/`
2. Replaces all references to the source agent name with the new name
3. Appends a per-agent experiment resource to `databricks.yml`
4. Appends a new app resource to `databricks.yml`
5. Adds the agent to `.agentops-stacks/manifest.yml`

## Error handling

- Agent name already exists → abort
- Invalid name format → abort with pattern hint
- Source agent not found → abort, show available agents
- No `databricks.yml` found → abort, not an AgentOps Stacks project

## Example

```
User: add a support agent to this project
Assistant: I'll add a new agent based on your existing "rag" agent.

> python .../add_agent.py --name support --from rag --project-dir .

Created: src/agents/support/
Updated: databricks.yml
Updated: manifest.yml

Next, customize the agent:
  - Edit src/agents/support/graph.py for this agent's behavior
  - Edit src/agents/support/tools.py for tool selection
  - Run: databricks bundle deploy -t dev
```
