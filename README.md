# Agent Config Extractor

[![Tests](https://github.com/bigcalm/wimpysworld-nix-config-agents/actions/workflows/test.yml/badge.svg)](https://github.com/bigcalm/wimpysworld-nix-config-agents/actions/workflows/test.yml)

Extracts AI TUI agent configurations from [Martin Wimpress' nix-config repo](https://github.com/wimpysworld/nix-config.git)
into portable directory trees that can be copied into each agent's config directory
on any Linux/macOS system (no Nix required).

Source: https://github.com/bigcalm/wimpysworld-nix-config-agents

## Usage

```bash
python3 extract_agent_config.py /path/to/nix-config
```

By default all 7 platforms are extracted. Select specific platforms with `--platform`:

```bash
python3 extract_agent_config.py /path/to/nix-config --platform opencode,claude
```

Output goes to `_agent_configs_<commitdate>_<commithash>/<platform>/` by default (auto-named from the source repo's commit). Customise with `--output` to use a fixed path:

```bash
python3 extract_agent_config.py /path/to/nix-config --output ~/my-configs
```

## What gets extracted

| Platform | Contents | Copy to |
|----------|----------|---------|
| **opencode** | agents, commands, skills, plugins, settings.json, MCP | `~/.config/opencode/` |
| **claude** | agents, commands, skills, rules/instructions.md, MCP | `~/.claude/` |
| **codex** | agents (TOML), skills, AGENTS.md, MCP | `~/.codex/` |
| **pi** | agents, prompts, skills, AGENTS.md, MCP | `~/.pi/agent/` |
| **zed** | settings snippet, keymap snippet | `~/.config/zed/` |
| **cursor** | global rules, communication rules | `.cursor/rules/` |
| **paseo** | config template | `~/.paseo/config.json` |

## Tests

The repository includes a minimal fixture source tree and a unit-test suite:

```bash
python3 -m unittest discover -s tests -v
```

A GitHub Actions workflow runs the tests and validates the generated output against the upstream `nix-config` repo on every push and pull request.

## Requirements

- Python 3.8+
- The nix-config repository cloned locally
- `rsync` (for the local overlay script)

## Full workflow: extract, overlay, install

The `nix-config` source is a read-only clone. Personal customisations (extra
skills, CLI wrappers, settings patches) live in `local/<platform>/` and are
merged into the extracted output by `apply_local_overlay.sh`.

### 1. Clone the nix-config source

```bash
git clone https://github.com/wimpysworld/nix-config.git /path/to/nix-config
```

### 2. Extract

```bash
python3 extract_agent_config.py /path/to/nix-config --platform opencode --quiet
```

### 3. Apply the local overlay

```bash
./apply_local_overlay.sh /path/to/nix-config
```

This merges `local/opencode/` into the extracted tree, installs `gh-api-safe`
from the nix-config source and `glab-api-safe` from `local/` to `~/.local/bin/`,
and patches `settings.json` with personal rules. The script is idempotent —
safe to run multiple times.

### 4. Copy to the agent config directory

```bash
cp -r _agent_configs_*/opencode/* ~/.config/opencode/
# or, with rsync:
rsync -a _agent_configs_*/opencode/ ~/.config/opencode/
```

### 5. Verify

```bash
gh-api-safe --help
glab-api-safe --help
```

Both wrappers should be on `$PATH` via `~/.local/bin/`.

### One-liner

```bash
python3 extract_agent_config.py /path/to/nix-config --platform opencode --quiet && ./apply_local_overlay.sh /path/to/nix-config && rsync -a _agent_configs_*/opencode/ ~/.config/opencode/
```

## Local overlay

Customisations live in `local/<platform>/` and are merged by `apply_local_overlay.sh`.

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

Target a specific output directory:

```bash
./apply_local_overlay.sh /path/to/custom-output
```

## Licence

This project is released under the MIT licence.
