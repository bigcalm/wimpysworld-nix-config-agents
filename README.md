# Agent Config Extractor

Extracts AI TUI agent configurations from [Martin Wimpress' nix-config repo](https://github.com/wimpysworld/nix-config.git)
into portable directory trees that can be copied into each agent's config directory
on any Linux/macOS system (no Nix required).

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

## Requirements

- Python 3.8+
- The nix-config repository cloned locally

## Licence

MIT
