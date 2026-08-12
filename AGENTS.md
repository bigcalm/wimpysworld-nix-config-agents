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
| Apply local overlay | `./apply_local_overlay.sh /path/to/nix-config` |
| Extract + overlay | `python3 extract_agent_config.py /path/to/nix-config --platform opencode --quiet && ./apply_local_overlay.sh /path/to/nix-config` |

## Layout

- `extract_agent_config.py` — the extraction script (single file, no deps beyond stdlib)
- `_agent_configs_<date>_<hash>/` — output directory (gitignored, auto-named from commit)
- `local/` — personal overlay merged into extracted output after extraction
- `apply_local_overlay.sh` — merges `local/` into the latest `_agent_configs_*` tree
- `session-ses_0868.md` — original design session transcript

## Local overlay

The `nix-config` source is a read-only clone. Personal customisations (extra skills,
bin wrappers, settings patches) live in `local/<platform>/` and are merged into the
extracted output by `apply_local_overlay.sh`. The script is idempotent — running it
twice produces the same result.

Workflow:

```bash
python3 extract_agent_config.py /path/to/nix-config --platform opencode --quiet
./apply_local_overlay.sh /path/to/nix-config
```

Or target a specific output directory:

```bash
./apply_local_overlay.sh /path/to/nix-config /path/to/custom-output
```

Overlay structure:

```
local/
├── opencode/
│   └── skills/glab/          # extra skill not in the Nix source
└── patch_settings.py         # idempotent JSON patch for settings.json rules
```

The overlay script copies `gh-api-safe.sh` directly from the nix-config source
(`home-manager/_mixins/development/github/`) and `glab-api-safe.sh` from
`local/opencode/bin/`, installing both to `~/.local/bin/` (without `.sh`
extension) so they are on `$PATH`.

## Conventions

- Python 3 stdlib only (argparse, json, re, shutil, pathlib)
- One required positional argument: path to the nix-config repository
- Output is `.gitignore`d and regenerated on each run
- Output directory auto-named from source commit date and hash
