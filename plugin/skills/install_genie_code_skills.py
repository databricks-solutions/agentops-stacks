# Databricks notebook source
# MAGIC %md
# MAGIC # Install agentops-stacks Skills for Genie Code
# MAGIC
# MAGIC Uploads the agentops-stacks skill folders to your workspace so Genie Code
# MAGIC can scaffold new DAB projects and guide them through the full production
# MAGIC lifecycle. Each folder is copied whole: SKILL.md plus any resources/,
# MAGIC reference/, or scripts/ it points at.
# MAGIC
# MAGIC Installs ten skills:
# MAGIC - `agentops-bigbook` — advisory reference (Big Book of AgentOps): patterns, anti-patterns, eval, governance
# MAGIC - `agentops-stacks` — scaffolds a new project via `databricks bundle init`
# MAGIC - `agentops-lifecycle` — guides an existing scaffold through the 10-step dev→prod lifecycle
# MAGIC - `add-agent` — adds a second agent to an existing scaffold
# MAGIC - `add-supervisor` — adds a supervisor that routes across the project's agents
# MAGIC - `right-size-capability` — decides whether a capability should be a UC-function tool, MCP server, or Agent Skill
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
import io
import posixpath
import tarfile
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

SKILLS = [
    "agentops-bigbook",
    "agentops-stacks",
    "agentops-lifecycle",
    "add-agent",
    "add-supervisor",
    "right-size-capability",
    "vector-search-ops",
    "lakebase-ops",
    "uc-functions-ops",
    "usage-tracking-ops",
]

w = WorkspaceClient()
username = w.current_user.me().user_name
skills_base = f"/Users/{username}/.assistant/skills"

print(f"Username: {username}")
print(f"Source:   github.com/{GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_REF}")
print(f"Target:   /Workspace{skills_base}/<skill>/")
print()

# Copy each skill folder whole. One repo tarball download replaces a request
# per file; members are read in memory and never extracted to disk.
ARCHIVE_URL = (
    f"https://codeload.github.com/{GITHUB_OWNER}/{GITHUB_REPO}/tar.gz/{GITHUB_REF}"
)
SKILLS_PREFIX = "/plugin/skills/"


def _skill_files(archive):
    """Map skill name -> {relative path: bytes} for every file under plugin/skills/."""
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or SKILLS_PREFIX not in member.name:
                continue
            rest = member.name.split(SKILLS_PREFIX, 1)[1]
            skill, _, rel = rest.partition("/")
            parts = rel.split("/")
            if (
                skill not in SKILLS
                or not rel
                or ".." in parts
                or "__pycache__" in parts
            ):
                continue
            files.setdefault(skill, {})[rel] = tar.extractfile(member).read()
    return files


print(f"Downloading {ARCHIVE_URL} ...")
archive = _download(ARCHIVE_URL)
if archive is None:
    raise RuntimeError(f"Could not download {ARCHIVE_URL}")
skill_files = _skill_files(archive)

for skill_name in SKILLS:
    files = skill_files.get(skill_name, {})
    if "SKILL.md" not in files:
        raise RuntimeError(f"{skill_name}/SKILL.md not found in {ARCHIVE_URL}")
    skill_dest = f"{skills_base}/{skill_name}"
    print(f"Installing {skill_name} ({len(files)} files)...")
    for rel, data in sorted(files.items()):
        _upload(w, f"{skill_dest}/{rel}", data)
        print(f"  OK  /Workspace{skill_dest}/{rel}")

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
