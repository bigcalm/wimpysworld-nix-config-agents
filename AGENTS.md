# AGENTS.md

## Scope

This repository extracts AI TUI agent configurations from Martin Wimpress's Nix flake (`nix-config`) into portable directory trees for opencode, Claude Code, Codex CLI, Pi Agent, Zed Editor, Paseo, and Cursor.

The extraction reads agents, commands, skills, global instructions, MCP servers, and plugins from the Nix source tree and renders each platform's native format.

## Commands

| Task | Command |
|------|---------|
| Extract all platforms | `python3 extract_agent_config.py /path/to/nix-config` |
| Extract one platform | `python3 extract_agent_config.py /path/to/nix-config --platform opencode` |
| Extract to custom dir | `python3 extract_agent_config.py /path/to/nix-config --output ./out` |
| List all platforms | `python3 extract_agent_config.py --help` |

## Layout

- `extract_agent_config.py` — the extraction script (single file, no deps beyond stdlib)
- `_agent_configs_<date>_<hash>/` — output directory (gitignored, auto-named from commit)
- `session-ses_0868.md` — original design session transcript

## Conventions

- Python 3 stdlib only (argparse, json, re, shutil, pathlib)
- One required positional argument: path to the nix-config repository
- Output is `.gitignore`d and regenerated on each run
- Output directory auto-named from source commit date and hash
