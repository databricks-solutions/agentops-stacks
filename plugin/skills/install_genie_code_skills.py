# Databricks notebook source
# MAGIC %md
# MAGIC # Install agentops-stacks Skills for Genie Code
# MAGIC
# MAGIC Uploads the agentops-stacks skills (each skill's whole directory: SKILL.md
# MAGIC plus its scripts, reference and resource files) to your workspace so Genie
# MAGIC Code can scaffold new DAB projects and guide them through the full
# MAGIC production lifecycle.
# MAGIC
# MAGIC Installs ten skills:
# MAGIC - `agentops-bigbook` — advisory reference (Big Book of AgentOps): patterns, anti-patterns, eval, governance
# MAGIC - `agentops-stacks` — scaffolds a new project via `databricks bundle init`
# MAGIC - `agentops-lifecycle` — guides an existing scaffold through the 10-step dev→prod lifecycle
# MAGIC - `add-agent` — adds a second agent to an existing scaffold
# MAGIC - `add-supervisor` — adds a supervisor that routes across agents (custom LangGraph)
# MAGIC - `right-size-capability` — decides tool vs MCP server vs skill before you build a capability
# MAGIC - `vector-search-ops` — operates and troubleshoots the Vector Search component
# MAGIC - `lakebase-ops` — operates and troubleshoots the Lakebase memory component
# MAGIC - `uc-functions-ops` — registers, grants, and manages UC function tools
# MAGIC - `usage-tracking-ops` — tags resources and attaches usage policies for cost attribution
# MAGIC
# MAGIC Destination: `/Workspace/Users/<your_username>/.assistant/skills/<skill-name>/`
# MAGIC
# MAGIC **Prereqs in your workspace:** the Databricks CLI (already present in
# MAGIC Genie Code) and the ai-dev-kit plugin skills installed under
# MAGIC `/Workspace/Users/<you>/.assistant/skills/` for post-scaffold work.
# MAGIC
# MAGIC **How to use:** Run all cells top to bottom. Edit the GITHUB_REF below
# MAGIC if you want to install from a branch other than the default.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# -- Configuration ----------------------------------------------------------
# Source repo and ref. GITHUB_REF defaults to "main" and can be overridden
# via the AGENTOPS_GITHUB_REF env var when running this file as a regular
# Python script (useful for testing branches before merging).
import os

GITHUB_OWNER = "databricks-solutions"
GITHUB_REPO = "agentops-stacks"
GITHUB_REF = os.environ.get("AGENTOPS_GITHUB_REF", "main")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install

# COMMAND ----------

import base64
import json
import posixpath
import urllib.request

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat


def _download(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"  download error: {e}")
        return None


def _upload(w, workspace_path, content):
    w.workspace.mkdirs(posixpath.dirname(workspace_path))
    w.workspace.import_(
        path=workspace_path,
        content=base64.b64encode(content).decode(),
        format=ImportFormat.AUTO,
        overwrite=True,
    )


# ── Main ───────────────────────────────────────────────────────────────────

# Keep in sync with SKILL_NAMES in install_skills.sh.
SKILLS = ["agentops-bigbook", "agentops-stacks", "agentops-lifecycle", "add-agent", "add-supervisor", "right-size-capability", "vector-search-ops", "lakebase-ops", "uc-functions-ops", "usage-tracking-ops"]


def _skill_files():
    """Map each skill to the repo paths of every file in its directory at GITHUB_REF (one GitHub API call)."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/trees/{GITHUB_REF}?recursive=1"
    data = _download(url)
    if data is None:
        raise RuntimeError(f"Could not list {url}")
    tree = json.loads(data)
    if tree.get("truncated"):
        raise RuntimeError(f"GitHub truncated the file listing for {GITHUB_REF}")
    files = {skill: [] for skill in SKILLS}
    for entry in tree["tree"]:
        parts = entry["path"].split("/")
        if entry["type"] == "blob" and parts[:2] == ["plugin", "skills"] and len(parts) > 3 \
                and parts[2] in files and "__pycache__" not in parts:
            files[parts[2]].append(entry["path"])
    return files


w = WorkspaceClient()
username = w.current_user.me().user_name
skills_base = f"/Users/{username}/.assistant/skills"

print(f"Username: {username}")
print(f"Source:   github.com/{GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_REF}")
print(f"Target:   /Workspace{skills_base}/<skill>/")
print()

# Copy each skill's whole directory: SKILL.md refers to its own scripts/,
# reference/ and resources/ files. The template itself is read from the
# GitHub repo at run time, so it isn't copied.
for skill_name, paths in _skill_files().items():
    if not any(path.endswith(f"/{skill_name}/SKILL.md") for path in paths):
        raise RuntimeError(f"No SKILL.md for {skill_name} at {GITHUB_REF}")
    print(f"Installing {skill_name}...")
    for path in paths:
        src_url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_REF}/{path}"
        data = _download(src_url)
        if data is None:
            raise RuntimeError(f"Could not download {src_url}")
        dest = f"{skills_base}/{path.removeprefix('plugin/skills/')}"
        _upload(w, dest, data)
    print(f"  OK  /Workspace{skills_base}/{skill_name}/ ({len(paths)} files)")

print()
print("Done.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Installation

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
username = w.current_user.me().user_name
skills_base = f"/Users/{username}/.assistant/skills"

for skill_name in SKILLS:
    skills_path = f"{skills_base}/{skill_name}"
    try:
        entries = list(w.workspace.list(skills_path))
        print(f"{skill_name}:")
        for e in sorted(entries, key=lambda x: x.path):
            kind = "DIR " if str(e.object_type) == "ObjectType.DIRECTORY" else "FILE"
            print(f"  {kind}  {e.path.split('/')[-1]}")
    except Exception as e:
        print(f"{skill_name}: could not list — {e}")
