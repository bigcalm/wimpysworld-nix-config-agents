#!/usr/bin/env bash
# apply_local_overlay.sh — Merge local customisations into the latest extracted output.
#
# Usage:
#   ./apply_local_overlay.sh <nix-config-path>              # uses latest _agent_configs_* dir
#   ./apply_local_overlay.sh <nix-config-path> <output-dir> # explicit target
#   ./apply_local_overlay.sh <nix-config-path> <output-dir> <personal-json>
#
# This script:
#   1. Copies local/opencode/ over the extracted opencode/ tree (rsync merge)
#   2. Installs gh-api-safe and glab-api-safe from local/opencode/bin/
#   3. Runs patch_agents_md.py to inject glab rules into AGENTS.md
#   4. Deep-merges local/personal.json (git-ignored) into opencode.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="${SCRIPT_DIR}/local"
PATCH_SCRIPT="${LOCAL_DIR}/patch_agents_md.py"
MERGE_SCRIPT="${LOCAL_DIR}/merge_personal.py"

if [[ $# -lt 1 ]]; then
    echo "apply_local_overlay: missing nix-config path" >&2
    echo "Usage: $0 <nix-config-path> [<output-dir>] [<personal-json>]" >&2
    exit 1
fi

NIX_CONFIG="$1"
GH_API_SAFE_SRC="${LOCAL_DIR}/opencode/bin/gh-api-safe.sh"
GLAB_API_SAFE_SRC="${LOCAL_DIR}/opencode/bin/glab-api-safe.sh"

# Both wrapper sources must exist and be regular files before anything is
# installed, so a missing source cannot leave the merge half done. Symlink
# sources are refused: `install` dereferences symlinks, and the wrapper
# ends up executable on $PATH.
for src in "${GH_API_SAFE_SRC}" "${GLAB_API_SAFE_SRC}"; do
    if [[ ! -f "${src}" ]]; then
        echo "apply_local_overlay: wrapper source not found at ${src}" >&2
        exit 1
    fi
    if [[ -L "${src}" ]]; then
        echo "apply_local_overlay: refusing symlink wrapper source ${src}" >&2
        exit 1
    fi
done

# Find the target directory
if [[ $# -ge 2 ]]; then
    TARGET="$2"
else
    # Pick the most recent _agent_configs_* directory
    TARGET="$(ls -d "${SCRIPT_DIR}"/_agent_configs_* 2>/dev/null | sort | tail -1)" || {
        echo "apply_local_overlay: no _agent_configs_* directory found" >&2
        exit 1
    }
fi

if [[ ! -d "${TARGET}" ]]; then
    echo "apply_local_overlay: ${TARGET} does not exist" >&2
    exit 1
fi

# Refuse to write personal settings into a git-tracked target. Personal
# settings can carry bearer tokens; if the target sits inside this repository
# and git does not ignore it, a later `git add .` would commit them. The
# default _agent_configs_* tree is gitignored, so only custom in-repo targets
# trip this guard.
TARGET_ABS="$(readlink -f "${TARGET}")"
GIT_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "${GIT_ROOT}" && "${TARGET_ABS}" == "${GIT_ROOT}"/* ]]; then
    if ! git -C "${SCRIPT_DIR}" check-ignore -q "${TARGET_ABS}/opencode/opencode.json"; then
        echo "apply_local_overlay: refusing to write into ${TARGET_ABS}: inside the git repo and not gitignored (personal settings could be committed)" >&2
        exit 1
    fi
fi

if [[ ! -d "${LOCAL_DIR}/opencode" ]]; then
    echo "apply_local_overlay: ${LOCAL_DIR}/opencode not found" >&2
    exit 1
fi

OPENCODE_DIR="${TARGET}/opencode"
if [[ ! -d "${OPENCODE_DIR}" ]]; then
    echo "apply_local_overlay: ${OPENCODE_DIR} not found" >&2
    exit 1
fi

echo "apply_local_overlay: merging local/opencode/ → ${OPENCODE_DIR}/"

# Merge local files over extracted tree (preserves existing files not in local/)
# No --update: the overlay must win even when the extracted copy is newer.
# bin/ holds the wrapper sources for the install step below; it is not part
# of the tree an agent reads, so exclude it from the merge.
rsync -a --exclude=bin/ "${LOCAL_DIR}/opencode/" "${OPENCODE_DIR}/"

# Install bin wrappers to ~/.local/bin/ so they are on $PATH
echo "apply_local_overlay: installing bin wrappers to ~/.local/bin/"
install -Dm755 "${GH_API_SAFE_SRC}" "${HOME}/.local/bin/gh-api-safe"
install -Dm755 "${GLAB_API_SAFE_SRC}" "${HOME}/.local/bin/glab-api-safe"

# Patch AGENTS.md rules
echo "apply_local_overlay: patching AGENTS.md"
python3 "${PATCH_SCRIPT}" "${OPENCODE_DIR}"

# Deep-merge personal settings (git-ignored local/personal.json) into
# opencode.json. The merge runs last so personal overrides win over both the
# extracted config and the patch script's rules.
PERSONAL_JSON="${3:-${LOCAL_DIR}/personal.json}"
if [[ -f "${PERSONAL_JSON}" ]]; then
    echo "apply_local_overlay: merging personal settings → opencode.json"
    python3 "${MERGE_SCRIPT}" "${OPENCODE_DIR}" "${PERSONAL_JSON}"
elif [[ $# -ge 3 ]]; then
    echo "apply_local_overlay: personal file ${PERSONAL_JSON} not found; continuing without it" >&2
fi

echo "apply_local_overlay: done → ${OPENCODE_DIR}"
