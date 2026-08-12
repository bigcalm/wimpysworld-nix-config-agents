# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Local overlay system (`apply_local_overlay.sh`, `local/`) merging personal
  customisations into extracted output, with the `glab` GitLab CLI skill.
- `glab-api-safe.sh` wrapper enforcing a read-only policy for `glab api`.
- Codex `config.toml` output: MCP server tables plus the model, approval,
  analytics, and developer-instruction settings now land in Codex's native
  config file instead of an inert `mcp_servers.toml`.
- Claude output style (`output-styles/house-style.md`) and the house-style
  body appended to the opencode rules and pi `AGENTS.md`, mirroring the
  Nix composition.
- Codex `agents/openai.yaml` sidecars from `header.codex.toml`
  (`allow-implicit-invocation`), and `spawn-agent = false` opt-out support.
- opencode `tui.json` output (TUI settings and keybindings moved out of
  `opencode.json`), the `/init` command template, and MCP tool denies in
  the permission map.
- Behavioural test suites for both API wrappers, the overlay script, and
  `patch_agents_md.py`.
- Personal settings file `local/personal.json` (git-ignored) that the
  overlay deep-merges into `opencode.json`, so machine-specific settings
  such as a private MCP server survive extraction without touching tracked
  files.

### Fixed

- opencode output now matches the real config locations: global config is
  emitted as `opencode.json` (read from `~/.config/opencode/opencode.json`)
  and the global rules as `AGENTS.md` (read from
  `~/.config/opencode/AGENTS.md`). The previous `settings.json` with a
  `rules` key was ignored by opencode entirely — `rules` is not a valid
  config key and `settings.json` is never loaded.
- README and AGENTS.md copy targets corrected from `~/.opencode/` to
  `~/.config/opencode/`.
- `local/patch_settings.py` renamed to `local/patch_agents_md.py` and now
  patches the `AGENTS.md` rules file instead of the inert `settings.json`
  `rules` field.
- The overlay also deep-merges the git-ignored `local/personal.json` into
  `opencode.json`, so personal overrides win after the rsync merge and rules
  patch.
- `$`-prefixed keys (such as `$comment`) are stripped by the personal merge
  so they never reach `opencode.json`.
- The overlay refuses to write into an in-repo target that git does not
  ignore, and warns when an explicitly supplied personal file is missing.
- `merge_personal.py` and `patch_agents_md.py` write their outputs
  atomically (temp file + `os.replace`).
- Extractor no longer breaks on Nix comments and strings containing braces,
  quoted keys, `lib.mkDefault`-wrapped values, or `''...''` indented strings.
- Communication rules now load from the real source path
  (`assistants/styles/house-style/`).
- OAuth, disabled tools, and bearer headers are emitted for OpenCode, Codex,
  Pi, and Zed MCP configs where the source defines them; pi MCP http entries
  now carry the oauth block.
- Codex command skills keep their per-command header files.
- `glab-api-safe` blocks glued method overrides, `--hostname`, query/fragment
  suffixes, and credential-bearing endpoints; also denies `*/secure_files`,
  `*/personal_access_tokens`, and `*/impersonation_tokens`, allows the glued
  `-fquery=` form for GraphQL reads, and no longer exports the dead
  `GH_TELEMETRY` variable.
- `gh-api-safe` (now a reviewed copy in `local/opencode/bin/`) rejects
  `--hostname`, closing the exfiltration gap the glab wrapper already covered.
- The delegate-task skill is regenerated from the current compose.nix content
  (Waiting, Teardown, Authority, and Deadline sections restored).
- Descriptions are escaped for TOML and YAML output, symlinks inside skill
  directories are refused, `.sops` files are never copied, the README origin
  URL is escaped, and `--quiet` now silences skill warnings.
- Subset runs remove stale platform directories, and the generated README
  uses `cp` (not `cp -r`) for the file-targeted zed and paseo commands.
- `apply_local_overlay.sh` installs from `local/` only, checks both wrapper
  sources before installing anything, refuses symlink sources, and drops
  `rsync --update` so the overlay always wins.
- The glab skill's jq label filter matches string label arrays, and the
  `glab auth` guidance agrees with the fence policy.

## [1.0.0] - 2026-07-19

### Added

- Initial extraction script (`extract_agent_config.py`) that converts Martin Wimpress's `nix-config` agent configuration into portable directory trees for OpenCode, Claude Code, Codex CLI, Pi Agent, Zed, Cursor, and Paseo.
- MCP server parser and renderers for all supported platforms.
- Unit tests with a minimal fixture source tree under `tests/fixtures/minimal/`.
- GitHub Actions CI workflow that runs tests and validates generated output against the upstream `nix-config` repo.

### Fixed

- Python 3.8 compatibility (`_strip_git_suffix` replaces `str.removesuffix`).
- Cursor output no longer duplicates communication rules.
- OpenCode MCP renderer no longer hardcodes disabled servers.
- Claude MCP output is wrapped in `mcpServers` and includes OAuth/env support.
- Codex MCP output includes `startup_timeout_sec` (integer) and `default_tools_approval_mode`.
- Pi MCP output omits `pi.omit` servers and respects `pi.directTools`.
- Zed extensions list is built dynamically from extension-mode MCP servers.
- Quoted Nix command strings are stripped before rendering.

