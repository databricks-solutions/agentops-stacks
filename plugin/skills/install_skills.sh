#!/bin/bash
#
# agentops-stacks plugin installer
#
# Installs agentops-stacks skills (SKILL.md files) into a project at
# .claude/skills/<skill-name>/. Skills shell out to the Databricks CLI and
# reference the template tree, schema, and workflow definitions from this repo
# at run time — nothing is vendored next to the skill files.
#
# Usage:
#   ./install_skills.sh                              # install from local repo
#   ./install_skills.sh --install-to-genie           # also upload to workspace
#   ./install_skills.sh --install-to-genie --profile prod
#   ./install_skills.sh --list
#   ./install_skills.sh --help

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKILL_NAMES=("agentops-stacks" "agentops-lifecycle")
SKILLS_DIR=".claude/skills"
INSTALL_TO_GENIE=false
DB_PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_help() {
    echo -e "${BLUE}agentops-stacks Skills Installer${NC}"
    echo ""
    echo "Usage:"
    echo "  ./install_skills.sh [options]"
    echo ""
    echo "Options:"
    echo "  --help, -h              Show this help message"
    echo "  --list, -l              List available skills"
    echo "  --install-to-genie      Also upload .claude/skills to workspace"
    echo "                          /Users/<you>/.assistant/skills for Genie Code"
    echo "  --profile <name>        Databricks CLI profile (default: DEFAULT or \$DATABRICKS_CONFIG_PROFILE)"
    echo ""
    echo "Examples:"
    echo "  ./install_skills.sh                                # Install all agentops-stacks skills"
    echo "  ./install_skills.sh --install-to-genie             # Install + upload to workspace"
    echo "  ./install_skills.sh --install-to-genie --profile prod"
    echo ""
    echo -e "${GREEN}Available skills:${NC}"
    echo "  - agentops-stacks:    Scaffold a new DAB project with CI/CD and UC conventions"
    echo "  - agentops-lifecycle: Guide an existing scaffold through the 10-step dev→prod lifecycle"
    echo ""
}

list_skills() {
    echo -e "${BLUE}Available Skills:${NC}"
    echo ""
    echo -e "  ${GREEN}agentops-stacks${NC}"
    echo "    Scaffold a new DAB project (dev/staging/prod, UC conventions, CI/CD)"
    echo ""
    echo -e "  ${GREEN}agentops-lifecycle${NC}"
    echo "    10-step lifecycle guide: data prep → agent dev → eval gate → CI → staging → prod monitoring"
    echo ""
}

install_skill() {
    local skill_name="$1"
    local dest="$SKILLS_DIR/$skill_name"
    local src="$SCRIPT_DIR/$skill_name"

    if [ ! -f "$src/SKILL.md" ]; then
        echo -e "${RED}Error: SKILL.md not found at $src${NC}"
        return 1
    fi

    rm -rf "$dest"
    mkdir -p "$dest"
    cp "$src/SKILL.md" "$dest/SKILL.md"
    echo -e "  ${GREEN}✓${NC} $skill_name/SKILL.md"
}

check_prereqs() {
    local missing=()

    if ! command -v databricks >/dev/null 2>&1; then
        missing+=("Databricks CLI (https://docs.databricks.com/dev-tools/cli/install.html)")
    fi

    # ai-dev-kit is a soft prereq — needed for post-scaffold work but not for
    # the scaffold step itself. Best-effort detection across plugin install
    # layouts (Claude Code plugin cache, vibe marketplace, explicit skills).
    local adk_found=false
    for candidate in \
        "$HOME/.claude/plugins/cache"/*/databricks-ai-dev-kit \
        "$HOME/.vibe/marketplace/plugins/databricks-ai-dev-kit" \
        ".claude/skills/databricks-bundles" \
        ".claude/skills/databricks-mlflow-evaluation"; do
        if [ -e "$candidate" ]; then
            adk_found=true
            break
        fi
    done
    if [ "$adk_found" = false ]; then
        missing+=("ai-dev-kit plugin (post-scaffold workflows route to its skills)")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}Prerequisites not detected:${NC}"
        for item in "${missing[@]}"; do
            echo -e "  - $item"
        done
        echo -e "${YELLOW}Install both before using the scaffold skill. The installer will continue.${NC}"
        echo ""
    fi
}

upload_skill_to_genie_workspace() {
    local skill_dir="$1"
    local skills_path="$2"
    local db_profile="$3"

    skill_dir="${skill_dir%/}"
    local skill_name
    skill_name=$(basename "$skill_dir")

    if [[ ! -f "$skill_dir/SKILL.md" ]]; then
        return 0
    fi

    echo -e "  ${GREEN}Uploading${NC} $skill_name"
    databricks workspace mkdirs "$skills_path/$skill_name" --profile "$db_profile" 2>/dev/null || true
    databricks workspace import "$skills_path/$skill_name/SKILL.md" \
        --file "$skill_dir/SKILL.md" --profile "$db_profile" \
        --format AUTO --overwrite 2>/dev/null || true
}

install_skills_to_genie_workspace() {
    if ! command -v databricks >/dev/null 2>&1; then
        echo -e "${RED}Error: databricks CLI not found. Install it to use --install-to-genie.${NC}"
        return 1
    fi

    if [ ! -d "$SKILLS_DIR" ]; then
        echo -e "${RED}Error: $SKILLS_DIR not found (run from the directory where skills were installed).${NC}"
        return 1
    fi
    local abs_skills_dir
    abs_skills_dir="$(cd "$SKILLS_DIR" && pwd)"

    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Uploading skills to workspace (Genie Code)${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "Databricks profile: ${DB_PROFILE}"
    echo -e "Local skills: ${SKILLS_DIR}/ → ${abs_skills_dir}"
    echo ""

    local user_name
    user_name=$(databricks current-user me --profile "$DB_PROFILE" --output json 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('userName', ''))" 2>/dev/null || echo "")
    if [ -z "$user_name" ]; then
        echo -e "${RED}Error: Could not determine workspace user. Check auth and --profile.${NC}"
        return 1
    fi

    local skills_path="/Users/$user_name/.assistant/skills"
    echo -e "Workspace user: ${user_name}"
    echo -e "Workspace path: ${skills_path}"
    echo ""

    echo -e "${GREEN}Creating workspace skills directory...${NC}"
    databricks workspace mkdirs "$skills_path" --profile "$DB_PROFILE" 2>/dev/null || true

    echo -e "${GREEN}Uploading skills...${NC}"
    local skill_dir
    for skill_dir in "$abs_skills_dir"/*/; do
        [ -d "$skill_dir" ] || continue
        upload_skill_to_genie_workspace "$skill_dir" "$skills_path" "$DB_PROFILE"
    done

    echo ""
    echo -e "${GREEN}Workspace listing:${NC}"
    databricks workspace list "$skills_path" --profile "$DB_PROFILE" 2>/dev/null || echo -e "  ${YELLOW}(Could not list workspace path)${NC}"

    echo ""
    echo -e "${GREEN}Genie Code upload complete.${NC}"
    echo ""
    return 0
}

# Argument parsing
while [ $# -gt 0 ]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --list|-l)
            list_skills
            exit 0
            ;;
        --install-to-genie|--deploy-to-assistant)
            INSTALL_TO_GENIE=true
            shift
            ;;
        --profile)
            if [ -z "$2" ] || [ "${2:0:1}" = "-" ]; then
                echo -e "${RED}Error: --profile requires a profile name${NC}"
                exit 1
            fi
            DB_PROFILE="$2"
            shift 2
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information."
            exit 1
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            echo "This installer only supports flags. Use --help for usage."
            exit 1
            ;;
    esac
done

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          agentops-stacks Plugin Installer                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ ! -d ".git" ] && [ ! -f "pyproject.toml" ] && [ ! -f "package.json" ] && [ ! -f "databricks.yml" ]; then
    echo -e "${YELLOW}Warning: This doesn't look like a project root directory.${NC}"
    echo -e "Current directory: $(pwd)"
    read -p "Continue anyway? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 1
    fi
fi

check_prereqs

if [ ! -d "$SKILLS_DIR" ]; then
    echo -e "${GREEN}Creating $SKILLS_DIR directory...${NC}"
    mkdir -p "$SKILLS_DIR"
fi

echo -e "${GREEN}Installing skills...${NC}"
for skill in "${SKILL_NAMES[@]}"; do
    install_skill "$skill"
done

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Installation complete.${NC}"
echo -e "${BLUE}Skills installed to: ${SKILLS_DIR}/${NC}"
echo ""

if [ "$INSTALL_TO_GENIE" = true ]; then
    install_skills_to_genie_workspace || exit 1
fi
