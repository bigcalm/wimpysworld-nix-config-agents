# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

