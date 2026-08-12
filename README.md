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
| **opencode** | agents, commands, skills, plugins, opencode.json, AGENTS.md, MCP | `~/.config/opencode/` |
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
and `glab-api-safe` (both reviewed copies in `local/opencode/bin/`) to
`~/.local/bin/`, patches `AGENTS.md` with personal rules, and deep-merges
`local/personal.json` into `opencode.json`. The script is idempotent — safe
to run multiple times.

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
│   ├── bin/                  # gh-api-safe.sh and glab-api-safe.sh wrappers
│   └── skills/glab/          # extra skill not in the Nix source
├── patch_agents_md.py        # idempotent patch for AGENTS.md rules
├── merge_personal.py         # deep-merge of personal.json into opencode.json
├── personal.json.example     # template for the git-ignored personal file
└── personal.json             # your settings (git-ignored; see below)
```

Both wrappers are reviewed copies living in `local/opencode/bin/` (the
glab wrapper is local-only; `gh-api-safe.sh` is a copy of the nix-config
wrapper with an added `--hostname` deny, kept in sync by hand). The
overlay installs both to `~/.local/bin/` (without `.sh` extension) so
they are on `$PATH`, and refuses symlink sources.

### Personal settings (`local/personal.json`)

Machine-specific settings (a private MCP server, a token, a model override)
live in `local/personal.json`, which is **git-ignored**. `apply_local_overlay.sh`
deep-merges it into `opencode/opencode.json` after the rsync and rules patch,
so personal keys win on conflicts while nested objects (like `mcp`) combine
with the extracted ones. It is idempotent.

Start from the template:

```bash
cp local/personal.json.example local/personal.json
```

Then edit `local/personal.json`. Add a private MCP server:

```json
{
  "mcp": {
    "private-mcp": {
      "type": "remote",
      "url": "https://mcp.example.com/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer {env:PRIVATE_MCP_TOKEN}"
      }
    }
  }
}
```

### Disabling MCP servers

Servers extracted from the Nix source can be switched off with an
`"enabled": false` stub. The entry stays in the config (so it can be
toggled back on without a re-extract) but opencode will not load it. The
example file disables the servers most users do not have keys for:

```json
{
  "mcp": {
    "context7": { "enabled": false },
    "linear":   { "enabled": false },
    "slack":    { "enabled": false },
    "exa":      { "enabled": false }
  }
}
```

With Exa off, Kagi (or your own search MCP) becomes the only web-search
route, and the `webfetch`/`websearch` denies keep the built-in tools blocked.

### Tokens

`{env:VAR}` references are substituted by opencode at load time, so tokens
can stay out of the repo. Set the variable in your shell profile. In fish:

```fish
set -Ux PRIVATE_MCP_TOKEN 'your-token-here'
```

`set -Ux` (universal, exported) survives restarts and applies to every new
fish session. Verify in a fresh terminal with `echo $PRIVATE_MCP_TOKEN`.
You may also paste the literal value into `local/personal.json` instead;
the file is git-ignored either way.

Any valid `opencode.json` field can be added or overridden here. Keys
starting with `$` (such as `$comment`) are documentation only and are
stripped by the merge — they never reach `opencode.json`. Re-run the
overlay after editing, then restart opencode.

### Custom output directories

Target a specific output directory:

```bash
./apply_local_overlay.sh /path/to/nix-config /path/to/custom-output
```

The overlay refuses to write into a target that sits inside this repository
and is not gitignored, because personal settings can carry bearer tokens and
a later `git add .` would commit them. The default `_agent_configs_*` tree is
already gitignored. If you point `--output` at a directory inside the repo,
add it to `.gitignore` yourself, or use a directory outside the repo (for
example `~/my-configs`).

## Licence

This project is released under the MIT licence.
