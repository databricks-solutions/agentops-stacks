# Databricks notebook source
# MAGIC %md
# MAGIC # Install agentops-stacks Skills for Genie Code
# MAGIC
# MAGIC Uploads the agentops-stacks SKILL.md files to your workspace so Genie Code
# MAGIC can scaffold new DAB projects and guide them through the full production
# MAGIC lifecycle.
# MAGIC
# MAGIC Installs two skills:
# MAGIC - `agentops-stacks` — scaffolds a new project via `databricks bundle init`
# MAGIC - `agentops-lifecycle` — guides an existing scaffold through the 10-step dev→prod lifecycle
# MAGIC
# MAGIC Destination: `/Workspace/Users/<your_username>/.assistant/skills/<skill-name>/SKILL.md`
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

SKILLS = ["agentops-stacks", "agentops-lifecycle"]

w = WorkspaceClient()
username = w.current_user.me().user_name
skills_base = f"/Users/{username}/.assistant/skills"

print(f"Username: {username}")
print(f"Source:   github.com/{GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_REF}")
print(f"Target:   /Workspace{skills_base}/<skill>/SKILL.md")
print()

# Each skill is a single SKILL.md. The template tree, library, schema, and
# workflow definitions are read from the GitHub repo at run time — nothing
# needs to be vendored next to the skill files in the workspace.
for skill_name in SKILLS:
    src_url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_REF}/plugin/skills/{skill_name}/SKILL.md"
    skill_dest = f"{skills_base}/{skill_name}"

    print(f"Installing {skill_name}...")
    data = _download(src_url)
    if data is None:
        raise RuntimeError(f"Could not download {src_url}")

    _upload(w, f"{skill_dest}/SKILL.md", data)
    print(f"  OK  /Workspace{skill_dest}/SKILL.md")

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

for skill_name in ["agentops-stacks", "agentops-lifecycle"]:
    skills_path = f"{skills_base}/{skill_name}"
    try:
        entries = list(w.workspace.list(skills_path))
        print(f"{skill_name}:")
        for e in sorted(entries, key=lambda x: x.path):
            kind = "DIR " if str(e.object_type) == "ObjectType.DIRECTORY" else "FILE"
            print(f"  {kind}  {e.path.split('/')[-1]}")
    except Exception as e:
        print(f"{skill_name}: could not list — {e}")
