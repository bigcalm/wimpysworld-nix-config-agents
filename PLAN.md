# Plan: fix review findings

Whole-project review report: `/tmp/agent-reviews/wimpysworld-nix-config-agents/branch-main/whole-project-review.md`.
Head commit: `2d7dfb7`. Target: no blocking findings; close the major findings.

## Status: complete

All phases landed. Verification: 49 tests green (was 16), real-tree extraction
of all 7 platforms faithful (4 MCP servers, 41 keybindings, config.toml,
output-styles, sidecars), overlay idempotent across two runs, wrappers
smoke-tested against stubs. CHANGELOG, AGENTS.md, and README updated.

## Phase A - Security and wrapper hardening (small edits)

| # | Fix | File |
|---|-----|------|
| A1 | Deny `*/secure_files`, `*/personal_access_tokens`, `*/impersonation_tokens`; allow glued `-fquery=` for graphql reads; drop dead `GH_TELEMETRY` | `local/opencode/bin/glab-api-safe.sh` |
| A2 | Fix jq label filter (`any(. == "bug")`); align auth-status sentence with the fence policy | `local/opencode/skills/glab/SKILL.md` |
| A3 | Check both wrapper sources before installing either; drop `rsync --update`; quote `TARGET`; reject symlink sources | `apply_local_overlay.sh` |
| A4 | Add `--hostname` deny to `gh-api-safe`; ship patched copy in `local/opencode/bin/`; install from `local/` | `local/opencode/bin/gh-api-safe.sh` (new), `apply_local_overlay.sh` |
| A5 | Escape TOML description strings; escape backslashes in frontmatter; refuse symlinks in skill collection and copies; exclude `*.sops`; escape origin URL in README; honour `--quiet` for warnings | `extract_agent_config.py` |

## Phase B - Fidelity: match the Nix composition

| # | Fix | File |
|---|-----|------|
| B1 | Append communication rules to opencode instructions and pi `AGENTS.md` | `extract_agent_config.py` |
| B2 | Emit `claude/output-styles/house-style.md` (frontmatter preserved) | `extract_agent_config.py` |
| B3 | Render `codex/config.toml` with `[mcp_servers.*]` tables and model settings | `extract_agent_config.py` |
| B4 | Parse `header.codex.toml`; honour `spawn-agent`; emit `agents/openai.yaml` sidecar instead of raw TOML in frontmatter | `extract_agent_config.py` |
| B5 | Regenerate `delegate-task` skill from `compose.nix` content | `extract_agent_config.py` |
| B6 | Render opencode MCP tool denies as permission entries keyed `<server>_<tool>` | `extract_agent_config.py` |
| B7 | Pi "Task tool" to "subagent tool" replacement; pi MCP oauth; fix README `cp` lines; subset-run cleanup; `tui.json` schema; `command.init` template | `extract_agent_config.py` |

## Phase C - Tests and CI

- Wrapper table tests (deny cases, exit 64, `-fquery=`).
- Paseo content assertions; opencode keybinds/init assertions; plugin copy and `@token@` skip.
- CI smoke asserts server counts, oauth client_id, keybinds.
- Fixture: `zed.mode = "skip"` -> real mode; fixture uses the real house-style path.
- `patch_agents_md.py` drift-refusal and overlay error-path tests.
- Extractor tests for every Phase B change.

## Phase D - Verify and document

- Full suite, real-tree extraction of all 7 platforms, overlay idempotency (two runs).
- Update `CHANGELOG.md`, `AGENTS.md`, `README.md` where behaviour changed.
