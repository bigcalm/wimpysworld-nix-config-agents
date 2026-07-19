# Code Review and Improvement Plan

Project: `extract-agent-configs-from-wimpress-nix-config-repo`
Reviewer: OpenCode
Date: 2026-07-19

## 1. Overall Verdict

A focused, useful utility that extracts the agent configuration from the `nix-config` Nix flake and renders it into portable directory trees for OpenCode, Claude Code, Codex CLI, Pi Agent, Zed, Cursor, and Paseo.

It works against the current upstream repo and produces well-formed JSON/TOML. Phase 1 and the bulk of Phase 2 are complete: the most obvious bugs and drift are gone, the MCP parser now covers the source schema, and the generated Claude/Codex/Pi/Zed MCP blocks match the upstream renderers. The remaining work is the OpenCode `tui` nesting question, adding tests, and setting up CI.

## 2. What Works Well

- **Single-file, stdlib-only design** (`extract_agent_config.py`) matches the stated convention.
- **Clear CLI**: positional source path, `--platform` selection, `--output`, `--quiet`.
- **Sensible output layout**: one directory per platform, auto-named from the source commit.
- **Git-aware README**: links back to the source commit and lists deployment commands.
- **Generated artifacts parse correctly**: a test run against the current upstream repo produced JSON/TOML files that all pass `json.loads` / `tomllib.loads`.
- **Communication-rules marker replacement** is wired through all renderers via a single helper.

## 3. Concrete Issues

| # | Severity | Issue | Location | Notes | Status |
|---|----------|-------|----------|-------|--------|
| 1 | **Bug** | Python 3.8 compatibility | `README.md` line 39; `extract_agent_config.py:1327` | README says 3.8+, but `str.removesuffix()` was used and is **3.9+**. | **Fixed** — replaced with `_strip_git_suffix()` (`:50`). |
| 2 | **Bug** | Duplicate communication rules in Cursor output | `extract_agent_config.py:1172` | `global.mdc` expanded the marker, then a separate `communication-rules.mdc` was also written. | **Fixed** — `_expand_body` now supports `insert_rules=False` for Cursor. |
| 3 | **Bug / staleness** | OpenCode MCP renderer hardcoded disabled servers | `extract_agent_config.py:479-501` (was `:374-384`) | `linear`, `rag`, `slack`, `svelte`, `firecrawl`, `jina`, `playwright` were hardcoded. The loop skipped source servers with `enabled=false`, causing drift. | **Fixed** — hardcoded list removed; all globally-enabled source servers are rendered with `consumers.opencode.enabled` reflected. `playwrightMcpWithNixBrowser` is mapped to `playwright-mcp` via `_portable_stdio_command` (`:461`). |
| 4 | **Bug** | MCP parser is incomplete vs. source schema | `extract_agent_config.py:314-428` (was `:223-496`) | `oauth`, `env`, `startupTimeoutSec`, `defaultToolsApprovalMode`, and nested `pi`/`zed` consumers were ignored. | **Fixed** — parser now handles merged `//` attrsets, top-level `enabled`, nested consumer blocks, `oauth`, `env`, `startupTimeoutSec`, and `codex.defaultToolsApprovalMode`. |
| 5 | **Bug** | Claude MCP JSON shape | `extract_agent_config.py:505-532` | Emitted a flat object; Claude Code expects `{"mcpServers": {...}}`. | **Fixed** — output is now wrapped in `mcpServers`. `oauth` and `env` placeholders are also emitted. |
| 6 | Codex agent TOML key | `extract_agent_config.py:1007` | Uses `developer_instructions`. | **Verified** — the upstream Nix module (`codex/default.nix`) explicitly refers to `developer_instructions` as the Codex agent instruction key. |
| 7 | **Bug?** | OpenCode `tui` key flattening | `extract_agent_config.py:848-850` | Source Nix uses `tui.tui = {...}` (nested), but the extractor emits `tui = {...}`. | Open — needs verification against the real OpenCode settings schema. |
| 8 | Code quality | Dead code | `extract_agent_config.py:50` and `:81` | `read_optional` and `self.communication_rules_section` were never used. | **Fixed** — both removed. |
| 9 | Code quality | Two marker-expansion implementations | `extract_agent_config.py:628` (was `:203` and `:507`) | `expand_communication_rules` and `_expand_body` were nearly identical; `_expand_body` could leave an empty `## Communication Rules` heading. | **Fixed** — unified into one helper with marker/heading stripping. |
| 10 | Usability | `-q` does not suppress plugin warnings | `extract_agent_config.py:746, 785-788` | Plugin skip message was printed unconditionally. | **Fixed** — `render_opencode` accepts `quiet` and respects `args.quiet`. |
| 11 | Git hygiene | `_agent_configs` can be unignored | `.gitignore:2` | If the source has no git info, the output directory is `_agent_configs` (no suffix), which was not matched by `_agent_configs_*`. | **Fixed** — added `_agent_configs/` to `.gitignore`. |
| 12 | Docs | Script docstring is wrong | `extract_agent_config.py:9-12` | Usage examples omitted the required `source` argument. | **Fixed** — examples now include `/path/to/nix-config`. |
| 13 | Testing | No tests or CI | n/a | No unit tests, no schema validation, no CI to catch upstream changes. | Open |

## 4. Implementation Plan

### Phase 1: Quick fixes (low risk, high value) — completed

- [x] **Fix Python 3.8 compatibility** — replaced `str.removesuffix()` with `_strip_git_suffix()`.
- [x] **Remove dead code** — deleted `read_optional` and `self.communication_rules_section`.
- [x] **Unify communication-rules expansion** — replaced `expand_communication_rules` and `_expand_body` with a single helper that handles the marker and the `## Communication Rules` heading consistently.
- [x] **Respect `--quiet` for plugin warnings** — guarded the plugin skip message behind `args.quiet`.
- [x] **Fix `.gitignore`** — added `_agent_configs/` so the no-git-info case is also covered.
- [x] **Fix docstring usage** — included the required `source` argument in the examples.
- [x] **Fix Cursor duplicate rules** — `_expand_body(..., insert_rules=False)` now strips the marker from `global.mdc` while `communication-rules.mdc` is emitted separately.

### Phase 2: MCP correctness (medium risk, high impact) — completed

- [x] **Stop hardcoding disabled servers in OpenCode** — the hardcoded list is removed; servers are rendered from the parsed source with `enabled` reflecting `consumers.opencode.enabled`. `playwrightMcpWithNixBrowser` is mapped to the portable `playwright-mcp` command.
- [x] **Parse merged `servers` attrsets** — the parser now follows the `//` merges in `servers.nix` and extracts entries from all three attrsets instead of stopping at the first `}`.
- [x] **Parse top-level `enabled` correctly** — `extract_bool` now uses the top-level attribute indentation so nested `pi = { enabled = false; }` blocks no longer override the global `enabled` value.
- [x] **Extend the MCP parser** to extract:
  - `oauth` (`clientId`, `callbackPort`) for Claude.
  - `env` passthrough for stdio servers.
  - `startupTimeoutSec` for Codex.
  - `codex.defaultToolsApprovalMode` for Codex.
  - Nested `pi`/`zed` consumers (e.g. `pi = { enabled = false; omit = true; }`).
- [x] **Render the new MCP fields**:
  - Claude: `oauth` for HTTP, `env` placeholders for stdio, wrapped in `mcpServers`.
  - Codex: `startup_timeout_sec` and `default_tools_approval_mode`; int values are no longer quoted in TOML.
  - Pi: `pi.omit` skips servers, `pi.directTools` is respected, `env` placeholders included.
  - OpenCode: `environment` for stdio servers with `env`.
  - Zed: extensions list is built dynamically from `zed.mode = "extension"` entries.
- [x] **Verify Claude MCP shape** — confirmed against Claude Code docs; output is now wrapped in `mcpServers`.
- [x] **Verify Codex agent TOML key** — confirmed via the upstream `codex/default.nix` comment that the key is `developer_instructions`.
- [ ] **Verify OpenCode `tui` nesting** against the real OpenCode settings schema.
- [ ] **Verify Pi `mcp.json` shape** if documentation becomes available.

### Phase 3: Tests and CI — completed

- [x] **Add a test fixture** — minimal fake source tree under `tests/fixtures/minimal/` covering agents, commands, skills, instructions, communication rules, MCP servers, and OpenCode settings.
- [x] **Add unit tests** for source-tree parsing, MCP parsing, communication-rules expansion, and all platform renderers.
- [x] **Add a validation step** — every generated `.json` and `.toml` file is parsed inside the render tests.
- [x] **Add GitHub Actions CI** workflow (`.github/workflows/test.yml`) that compiles the script, runs the unit tests, and extracts the upstream `nix-config` repo to validate every generated `.json` and `.toml` file.

### Phase 4: Documentation

- [ ] **Update `README.md` and `AGENTS.md`** if any CLI usage or output format changes.
- [ ] **Add a `CHANGELOG.md` entry** for the first release.
- [ ] **Confirm the licence and copyright** in `LICENSE` are intentional.

## 5. Suggested Next Steps

1. **Add a minimal test fixture** under `tests/fixtures/` and snapshot expected output for each platform.
2. **Add a validation script** that runs the extractor against the fixture and parses every generated `.json`/`.toml`.
3. **Add GitHub Actions CI** to run the validation on every push.

These changes are the highest-leverage: they provide a safety net for future upstream schema changes and make the extractor easier to refactor confidently.

## 6. Validation Log

- `python3 -m py_compile extract_agent_config.py` passes.
- `ruff check extract_agent_config.py` passes.
- Extraction against the current upstream `nix-config` repo produces 445 files across 7 platforms.
- All generated `.json` and `.toml` files parse successfully.
- Claude `mcp.json` is now wrapped in `mcpServers` and includes Slack OAuth.
- Codex `mcp_servers.toml` includes `startup_timeout_sec` (integer) and `default_tools_approval_mode`.
- OpenCode `mcp` block includes `environment` for stdio servers with `env`.
- Pi `mcp.json` omits `pi.omit` servers and respects `pi.directTools`.
- Zed extensions list is built dynamically from extension-mode servers.
- 15 unit tests pass against the `tests/fixtures/minimal/` source tree.
- All 7 platform renderers plus a full `--platform all` run produce parseable JSON/TOML.
