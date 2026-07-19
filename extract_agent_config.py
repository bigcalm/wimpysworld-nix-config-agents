#!/usr/bin/env python3
"""
Extract AI TUI agent configurations from Martin Wimpress' nix-config repo.

Produces portable directory trees for each supported platform that can be
copied into the agent's config directory on any system (not just NixOS).

Usage:
  python3 extract_agent_config.py /path/to/nix-config
  python3 extract_agent_config.py /path/to/nix-config --platform opencode,claude
  python3 extract_agent_config.py /path/to/nix-config --output ./my-configs
  python3 extract_agent_config.py /path/to/nix-config --help
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

COMMUNICATION_RULES_MARKER = "<!-- COMMUNICATION_RULES -->"

PLATFORM_DESCRIPTIONS = {
    "opencode": "OpenCode TUI (anomalyco/opencode) → ~/.config/opencode/",
    "claude": "Claude Code CLI (Anthropic) → ~/.claude/",
    "codex": "Codex CLI (OpenAI) → ~/.codex/",
    "pi": "Pi Agent (badlogic/pi-mono) → ~/.pi/agent/",
    "zed": "Zed Editor (agent + MCP integration) → ~/.config/zed/settings.json",
    "paseo": "Paseo agent launcher config → ~/.paseo/config.json",
    "cursor": "Cursor editor rules → .cursor/rules/",
}

ALL_PLATFORMS = sorted(PLATFORM_DESCRIPTIONS.keys())


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_stripped(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _strip_git_suffix(url):
    """Remove trailing `.git` from a remote URL (Python 3.8-compatible)."""
    if url and url.endswith(".git"):
        return url[:-4]
    return url


# ---------------------------------------------------------------------------
# Communication rules
# ---------------------------------------------------------------------------

def read_communication_rules(agentic_path):
    path = agentic_path / "hooks/communication-rules/communication-rules.md"
    return read_stripped(path) if path.exists() else None


# ---------------------------------------------------------------------------
# Source tree reader
# ---------------------------------------------------------------------------

class SourceTree:
    """Read the assistant source tree into structured data."""

    def __init__(self, source_root: Path):
        self.agentic = source_root / "home-manager/_mixins/agentic"
        self.assistants = self.agentic / "assistants"
        self.communication_rules = read_communication_rules(self.agentic)
        self.agents = self._read_agents()
        self.commands = self._read_commands()
        self.skills = self._read_skills()
        self.instructions = self._read_instructions()
        self.mcp_servers = self._parse_mcp_servers()

    def _read_agents(self):
        agents = []
        agents_path = self.assistants / "agents"
        if not agents_path.exists():
            return agents
        for name in sorted(os.listdir(agents_path)):
            d = agents_path / name
            if not d.is_dir():
                continue
            prompt = d / "prompt.md"
            if not prompt.exists():
                continue
            desc = read_stripped(d / "description.txt")
            headers = {}
            for fname in ("opencode", "claude", "codex", "pi"):
                h = d / f"header.{fname}.yaml"
                if fname == "codex":
                    h = d / "header.codex.toml"
                if h.exists():
                    headers[fname] = read_stripped(h)
            # Agent-scoped commands
            cmds = []
            cmds_dir = d / "commands"
            if cmds_dir.exists():
                for cmd_name in sorted(os.listdir(cmds_dir)):
                    cmd_d = cmds_dir / cmd_name
                    if not cmd_d.is_dir():
                        continue
                    cp = cmd_d / "prompt.md"
                    cs = cmd_d / "prompt.sops"
                    if cs.exists():
                        cmds.append({
                            "name": cmd_name,
                            "secret": True,
                            "body": None,
                            "description": read_stripped(cmd_d / "description.txt"),
                            "headers": self._read_headers(cmd_d),
                        })
                        continue
                    if not cp.exists():
                        continue
                    cmds.append({
                        "name": cmd_name,
                        "secret": False,
                        "body": read_stripped(cp),
                        "description": read_stripped(cmd_d / "description.txt"),
                        "headers": self._read_headers(cmd_d),
                    })
            agents.append({
                "name": name,
                "description": desc,
                "body": read_stripped(prompt),
                "headers": headers,
                "commands": cmds,
            })
        return agents

    def _read_commands(self):
        cmds = []
        cmds_path = self.assistants / "commands"
        if not cmds_path.exists():
            return cmds
        for name in sorted(os.listdir(cmds_path)):
            d = cmds_path / name
            if not d.is_dir():
                continue
            cp = d / "prompt.md"
            if not cp.exists():
                continue
            cmds.append({
                "name": name,
                "body": read_stripped(cp),
                "description": read_stripped(d / "description.txt"),
                "headers": self._read_headers(d),
            })
        return cmds

    def _read_headers(self, directory):
        headers = {}
        for fname in ("opencode", "claude", "codex", "pi"):
            h = directory / f"header.{fname}.yaml" if fname != "codex" else directory / "header.codex.toml"
            if h.exists():
                headers[fname] = read_stripped(h)
        return headers

    def _read_skills(self):
        skills = []
        skills_path = self.assistants / "skills"
        if not skills_path.exists():
            return skills
        for name in sorted(os.listdir(skills_path)):
            d = skills_path / name
            if not d.is_dir():
                continue
            skill_md = d / "SKILL.md"
            if not skill_md.exists():
                continue
            # Collect all files in the skill directory
            files = {}
            for item in d.rglob("*"):
                if item.is_file():
                    rel = str(item.relative_to(d))
                    files[rel] = item
            skills.append({"name": name, "source_dir": d, "files": files})
        return skills

    def _read_instructions(self):
        inst_dir = self.assistants / "instructions"
        if not inst_dir.exists():
            return {}
        data = {"body": read_stripped(inst_dir / "global.md"), "headers": {}}
        for fname in ("opencode", "claude", "codex", "pi"):
            h = inst_dir / f"header.{fname}.yaml" if fname != "codex" else inst_dir / "header.codex.toml"
            if h.exists():
                data["headers"][fname] = read_stripped(h)
        return data

    def get_agent_map(self):
        """Return {name: description} for all agents."""
        return {a["name"]: a["description"] for a in self.agents}

    # ---- MCP parsing -------------------------------------------------------

    def _parse_mcp_servers(self):
        """Parse servers.nix into structured server entries."""
        servers_nix = self.agentic / "mcp/servers.nix"
        if not servers_nix.exists():
            return []
        text = servers_nix.read_text(encoding="utf-8")

        servers_start = text.find("servers = {")
        if servers_start == -1:
            return []

        servers_line_start = text.rfind("\n", 0, servers_start) + 1
        servers_indent = len(text[servers_line_start:servers_start]) - len(text[servers_line_start:servers_start].lstrip())

        brace_depth = 0
        servers_block_start = None
        servers_block_end = -1
        for i, ch in enumerate(text[servers_start:], servers_start):
            if ch == "{":
                if brace_depth == 0 and servers_block_start is None:
                    servers_block_start = i
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0 and servers_block_start is not None:
                    line_start = text.rfind("\n", 0, i) + 1
                    after_indent = text[line_start + servers_indent:i + 2]
                    if after_indent.startswith("};"):
                        servers_block_end = i + 1
                        break
        if servers_block_end == -1:
            return []

        block = text[servers_block_start:servers_block_end]
        lines = block.split("\n")
        base_indent = servers_indent + 2

        entries = []
        i = 0
        while i < len(lines):
            m = re.match(r'^ {' + str(base_indent) + r'}(\w+)\s*=\s*\{', lines[i])
            if m:
                name = m.group(1)
                start = i
                depth = 0
                end = None
                j = i
                while j < len(lines):
                    for ch in lines[j]:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
                    j += 1
                if end is not None:
                    entries.append((name, start, end))
                    i = end
                else:
                    i += 1
            else:
                i += 1

        def extract_attr(et, attr):
            m = re.search(rf'^\s+{re.escape(attr)}\s*=\s*"([^"]*)"', et, re.MULTILINE)
            return m.group(1) if m else None

        def extract_bool(et, attr, default=True, attr_indent=None):
            if attr_indent is not None:
                m = re.search(rf'^ {{{attr_indent}}}{re.escape(attr)}\s*=\s*(false|true)', et, re.MULTILINE)
            else:
                m = re.search(rf'^\s+{re.escape(attr)}\s*=\s*(false|true)', et, re.MULTILINE)
            return m.group(1) == "true" if m else default

        def extract_consumers_bool(et, consumer, attr="enabled", default=True):
            m = re.search(rf'^\s+{re.escape(consumer)}\.{re.escape(attr)}\s*=\s*(false|true)', et, re.MULTILINE)
            return m.group(1) == "true" if m else default

        def extract_auth(et):
            if 'kind = "bearer"' in et:
                m = re.search(r'envVar\s*=\s*"(\w+)"', et)
                return m.group(1) if m else None
            return None

        def extract_args(et):
            m = re.search(r'args\s*=\s*\[(.*?)\]', et, re.DOTALL)
            return re.findall(r'"([^"]*)"', m.group(1)) if m else []

        def _parse_value(raw):
            """Parse a Nix literal (string, bool, int, list of strings)."""
            raw = raw.strip()
            if raw == "true":
                return True
            if raw == "false":
                return False
            m = re.match(r'^"([^"]*)"$', raw)
            if m:
                return m.group(1)
            m = re.match(r'^\[(.*?)\]$', raw, re.DOTALL)
            if m:
                return re.findall(r'"([^"]*)"', m.group(1))
            m = re.match(r'^(\d+)$', raw)
            if m:
                return int(m.group(1))
            return raw

        def _extract_nested_block(et, name):
            """Extract the `{ ... }` block for a nested attrset `name = { ... }`."""
            m = re.search(rf'^\s+{re.escape(name)}\s*=\s*\{{', et, re.MULTILINE)
            if not m:
                return None
            start = m.end() - 1
            depth = 0
            for i, ch in enumerate(et[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return et[start:i + 1]
            return None

        def _extract_consumer_attrs(et, consumer):
            """Return a dict of attributes for a consumer, from flat and nested forms."""
            attrs = {}
            # Flat form: consumer.attr = value;
            for m in re.finditer(rf'^\s+{re.escape(consumer)}\.(\w+)\s*=\s*([^;]+);', et, re.MULTILINE):
                attrs[m.group(1)] = _parse_value(m.group(2))
            # Nested form: consumer = { attr = value; ... };
            block = _extract_nested_block(et, consumer)
            if block:
                inner = block[1:-1]
                for m in re.finditer(r'(\w+)\s*=\s*([^;]+);', inner):
                    attrs[m.group(1)] = _parse_value(m.group(2))
            return attrs

        def extract_oauth(et):
            block = _extract_nested_block(et, "oauth")
            if not block:
                return None
            inner = block[1:-1]
            client_id = None
            callback_port = None
            m = re.search(r'clientId\s*=\s*"([^"]*)"', inner)
            if m:
                client_id = m.group(1)
            m = re.search(r'callbackPort\s*=\s*(\d+)', inner)
            if m:
                callback_port = int(m.group(1))
            if client_id is None or callback_port is None:
                return None
            return {"clientId": client_id, "callbackPort": callback_port}

        def extract_env(et):
            block = _extract_nested_block(et, "env")
            if not block:
                return None
            inner = block[1:-1]
            env = {}
            for m in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', inner):
                env[m.group(1)] = m.group(2)
            return env if env else None

        def extract_startup_timeout(et):
            m = re.search(rf'^ {{{base_indent + 2}}}startupTimeoutSec\s*=\s*(\d+)', et, re.MULTILINE)
            return int(m.group(1)) if m else None

        servers = []
        for name, start, end in entries:
            et = "\n".join(lines[start:end])
            s = {"name": name}

            global_enabled = extract_bool(et, "enabled", True, attr_indent=base_indent + 2)
            s["enabled"] = global_enabled

            transport = extract_attr(et, "transport") or "http"
            s["transport"] = transport

            url = extract_attr(et, "url")
            if url:
                s["url"] = url

            cmd_m = re.search(r'command\s*=\s*(?:lib\.getExe\s+)?([^;\n]+);', et)
            if cmd_m:
                cmd_raw = cmd_m.group(1).strip()
                pkg_m = re.match(r'config\.programs\.(\w+)\.package', cmd_raw)
                if pkg_m:
                    s["command_ref"] = f"{pkg_m.group(1)}"
                elif cmd_raw.startswith("mcpNixosNoUpdateCheck"):
                    s["command_ref"] = "mcp-nixos"
                elif cmd_raw.startswith("playwrightMcpWithNixBrowser"):
                    s["command_ref"] = "playwright-mcp"
                else:
                    s["command_ref"] = _parse_value(cmd_raw)

            args = extract_args(et)
            if args:
                s["args"] = args

            auth_env = extract_auth(et)
            if auth_env:
                s["auth_env_var"] = auth_env

            opencode_attrs = _extract_consumer_attrs(et, "opencode")
            claude_attrs = _extract_consumer_attrs(et, "claudeCode")
            codex_attrs = _extract_consumer_attrs(et, "codex")
            pi_attrs = _extract_consumer_attrs(et, "pi")
            zed_attrs = _extract_consumer_attrs(et, "zed")

            s["opencode_enabled"] = opencode_attrs.get("enabled", True)
            s["claude_enabled"] = claude_attrs.get("enabled", True)
            s["codex_enabled"] = codex_attrs.get("enabled", True)
            s["codex_default_tools_approval_mode"] = codex_attrs.get("defaultToolsApprovalMode", "approve")
            s["pi_enabled"] = pi_attrs.get("enabled", True)
            s["pi_omit"] = pi_attrs.get("omit", False)
            s["pi_direct_tools"] = pi_attrs.get("directTools", s["opencode_enabled"])
            s["zed_enabled"] = zed_attrs.get("enabled", True)
            s["zed_mode"] = zed_attrs.get("mode", "context_server")
            s["zed_id"] = zed_attrs.get("id")

            s["oauth"] = extract_oauth(et)
            s["env"] = extract_env(et)
            s["startup_timeout_sec"] = extract_startup_timeout(et)

            servers.append(s)
        return servers

    def get_mcp_for_opencode(self):
        return self._render_mcp_opencode()

    def get_mcp_for_claude(self):
        return self._render_mcp_claude()

    def get_mcp_for_codex(self):
        return self._render_mcp_codex()

    def get_mcp_for_pi(self):
        return self._render_mcp_pi()

    def get_mcp_for_zed_context(self):
        return self._render_mcp_zed_context()

    def get_mcp_zed_extensions(self):
        return [
            s["zed_id"] for s in self.mcp_servers
            if s.get("zed_mode") == "extension" and s.get("zed_id")
        ]

    def _build_auth_header(self, env_var):
        return {"Authorization": f"Bearer {{env:{env_var}}}"}

    def _build_claude_auth(self, env_var):
        return {"Authorization": f"Bearer ${{{{config.sops.placeholder.{env_var}}}}}"}

    @staticmethod
    def _portable_stdio_command(cmd_ref, args):
        """Map Nix-specific stdio wrappers to portable commands and clean args."""
        args = list(args)
        if cmd_ref == "playwrightMcpWithNixBrowser":
            cmd_ref = "playwright-mcp"
            filtered = []
            skip = False
            for a in args:
                if skip:
                    skip = False
                    continue
                if a == "--executable-path":
                    skip = True
                    continue
                filtered.append(a)
            args = filtered
        return cmd_ref, args

    def _render_mcp_opencode(self):
        config = {}
        for s in self.mcp_servers:
            if not s.get("enabled", True):
                continue
            name = s["name"]
            if name in ("codex",):
                continue
            enabled = s.get("opencode_enabled", True)

            if s["transport"] == "http":
                entry = {"type": "remote", "url": s.get("url", ""), "enabled": enabled}
                if s.get("auth_env_var"):
                    entry["headers"] = self._build_auth_header(s["auth_env_var"])
                config[name] = entry
            else:
                cmd_ref, args = self._portable_stdio_command(
                    s.get("command_ref", name), s.get("args", [])
                )
                cmd = [cmd_ref] + args
                entry = {"type": "local", "command": cmd, "enabled": enabled}
                if s.get("env"):
                    entry["environment"] = {k: f"{{env:{v}}}" for k, v in s["env"].items()}
                config[name] = entry
        return config

    def _render_mcp_claude(self):
        config = {}
        # The Claude Code format uses full JSON with sops placeholders.
        # Since we can't resolve sops, we emit env-var references.
        for s in self.mcp_servers:
            if not s.get("enabled", True):
                continue
            if not s.get("claude_enabled", True):
                continue
            name = s["name"]
            if name in ("codex",):
                continue
            if s["transport"] == "http":
                entry = {"type": "http", "url": s.get("url", "")}
                if s.get("auth_env_var"):
                    entry["headers"] = {"Authorization": f"Bearer ${{{s['auth_env_var']}}}"}
                if s.get("oauth"):
                    entry["oauth"] = s["oauth"]
                config[name] = entry
            else:
                entry = {"type": "stdio", "command": s.get("command_ref", name)}
                if s.get("args"):
                    entry["args"] = s["args"]
                if s.get("env"):
                    entry["env"] = {k: f"${{{v}}}" for k, v in s["env"].items()}
                config[name] = entry
        return {"mcpServers": config}

    def _render_mcp_codex(self):
        config = {}
        for s in self.mcp_servers:
            if not s.get("enabled", True):
                continue
            name = s["name"]
            if name in ("codex",):
                continue
            enabled = s.get("codex_enabled", True)

            if s["transport"] == "http":
                entry = {"url": s.get("url", ""), "enabled": enabled}
                if s.get("auth_env_var"):
                    entry["bearer_token_env_var"] = s["auth_env_var"]
                if s.get("startup_timeout_sec"):
                    entry["startup_timeout_sec"] = s["startup_timeout_sec"]
                entry["default_tools_approval_mode"] = s.get("codex_default_tools_approval_mode", "approve")
                config[name] = entry
            else:
                cmd_ref, args = self._portable_stdio_command(
                    s.get("command_ref", name), s.get("args", [])
                )
                entry = {"command": cmd_ref, "args": args, "enabled": enabled}
                if s.get("startup_timeout_sec"):
                    entry["startup_timeout_sec"] = s["startup_timeout_sec"]
                entry["default_tools_approval_mode"] = s.get("codex_default_tools_approval_mode", "approve")
                config[name] = entry
        return config

    def _render_mcp_pi(self):
        config = {}
        for s in self.mcp_servers:
            if not s.get("enabled", True):
                continue
            if s.get("pi_omit", False):
                continue
            name = s["name"]
            if name in ("codex",):
                continue
            enabled = s.get("pi_enabled", True)
            direct_tools = s.get("pi_direct_tools", s.get("opencode_enabled", True)) if enabled else False

            if s["transport"] == "http":
                entry = {"type": "http", "url": s.get("url", ""), "enabled": enabled, "directTools": direct_tools}
                if s.get("auth_env_var"):
                    entry["headers"] = self._build_auth_header(s["auth_env_var"])
                if s.get("env"):
                    entry["env"] = {k: f"${{{v}}}" for k, v in s["env"].items()}
                config[name] = entry
            else:
                cmd_ref, args = self._portable_stdio_command(
                    s.get("command_ref", name), s.get("args", [])
                )
                entry = {"type": "stdio", "command": cmd_ref,
                         "args": args, "enabled": enabled,
                         "directTools": direct_tools}
                if s.get("env"):
                    entry["env"] = {k: f"${{{v}}}" for k, v in s["env"].items()}
                config[name] = entry
        return config

    def _render_mcp_zed_context(self):
        config = {}
        for s in self.mcp_servers:
            if not s.get("enabled", True):
                continue
            if s.get("zed_mode") == "extension":
                continue
            if s.get("zed_mode") == "skip":
                continue
            enabled = s.get("zed_enabled", True)

            if s["transport"] == "http":
                config[s["name"]] = {
                    "enabled": enabled,
                    "command": "npx",
                    "args": ["-y", "mcp-remote", s.get("url", "")],
                }
            else:
                cmd_ref, args = self._portable_stdio_command(
                    s.get("command_ref", s["name"]), s.get("args", [])
                )
                config[s["name"]] = {
                    "enabled": enabled,
                    "command": cmd_ref,
                    "args": args,
                }
        return config


# ---------------------------------------------------------------------------
# Composition helpers (shared)
# ---------------------------------------------------------------------------

def _yaml_frontmatter(header_lines, body):
    return f"---\n{header_lines}\n---\n\n{body}\n"


def _expand_body(tree, body, context="unknown", insert_rules=True):
    """Replace COMMUNICATION_RULES_MARKER with rules text, or strip it."""
    if not body:
        return body
    count = body.count(COMMUNICATION_RULES_MARKER)
    if count > 1:
        print(f"  Warning: {count} markers in {context}")
    if insert_rules and tree.communication_rules and COMMUNICATION_RULES_MARKER in body:
        return body.replace(COMMUNICATION_RULES_MARKER, tree.communication_rules)
    if COMMUNICATION_RULES_MARKER in body:
        body = body.replace(f"\n## Communication Rules\n\n{COMMUNICATION_RULES_MARKER}", "")
        body = body.replace(COMMUNICATION_RULES_MARKER, "")
        return body
    return body


def _agent_frontmatter(agent, platform, extra_lines=None):
    """Build YAML frontmatter for an agent on a given platform."""
    lines = []
    desc = agent["description"].replace('"', '\\"')
    lines.append(f'description: "{desc}"')
    h = agent["headers"].get(platform, "")
    if h:
        lines.append(h)
    if extra_lines:
        lines.extend(extra_lines)
    return "\n".join(lines)


def _cmd_frontmatter(cmd, platform, extra_lines=None):
    lines = []
    desc = cmd["description"].replace('"', '\\"')
    lines.append(f'description: "{desc}"')
    h = cmd["headers"].get(platform, "")
    if h:
        lines.append(h)
    if extra_lines:
        lines.extend(extra_lines)
    return "\n".join(lines)


def _copy_skill_files(skill, output_dir):
    """Copy all files from a skill directory into output_dir/<name>/."""
    skill_out = output_dir / skill["name"]
    skill_out.mkdir(parents=True, exist_ok=True)
    for rel_path, src_path in skill["files"].items():
        dest = skill_out / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest)


def _generate_delegate_task(tree):
    """Generate delegate-task SKILL.md from agent registry."""
    agents = sorted(tree.get_agent_map().items())
    agent_lines = "\n".join(
        f"- **{name}**: {desc.replace('|', '\\|').replace(chr(10), ' ')}"
        for name, desc in agents
    )
    return f"""---
name: delegate-task
description: Route non-trivial work to the right specialist agent and define the delegation packet, response contract, and relay policy.
user-invocable: true
---

## Agents

{agent_lines}

## Route

Delegate before parent-thread discovery for non-trivial tool, file, research, implementation, review, validation, or documentation work. Answer directly only when delegation clearly costs more than it saves. Launch the selected specialist via the current platform's delegation mechanism.

Priority rules:
- Nix, NixOS, Home Manager, nix-darwin, flakes, packages, modules, overlays, options, registries, or `.nix` files: donatello with the `nix` skill.
- LOVE 2D, the LOVE engine, `love2d`, `.love` archives, or Lua 5.1/LuaJIT 2.1 game development: donatello with the `love` skill.
- Source-code security: dibble. Infrastructure, cloud, container, or network security: batfink.
- Non-Nix implementation from a defined plan: donatello.
- Prompts, skills, commands, or instruction files: rosey.
- Tests: brain. Documentation: velma. General research or option framing: penfold.
- If no route matches, use the smallest capable specialist or ask.

## Depth

Specialists do not launch further specialists. If a delegated task would require another specialist, return early with a packet describing what is needed; the parent routes the follow-up.

## Context

Use fresh context by default. Fork only when the user explicitly requires it or when the parent transcript is essential.

## Packet

Include only relevant fields, in this order:

```markdown
Task: <outcome required>
Context: <decisions, constraints, paths, risks, user preferences>
Scope: <files, commands, sources, APIs, behaviours, in/out of scope>
Validation: <checks to run or evidence needed>
Output: <headings, artefact shape, file path, or response contract>
Discipline: No preamble. Do not restate the task. Return user-visible output only. Omit irrelevant sections. Return raw artefacts when requested.
```

## Response contract

Non-artefact work starts with `Answer:`. Pure artefacts return only the artefact.

Suggested sections, in order: `Answer`, `Recommendations`, `Evidence`, `Files`, `Changes`, `Tests`, `Blockers`, `Artefact`. Omit irrelevant sections.

## Relay

Relay a single specialist output verbatim. Do not summarise, paraphrase, or improve it. Intervene only for safety.
"""


# ---------------------------------------------------------------------------
# OpenCode renderer
# ---------------------------------------------------------------------------

def render_opencode(tree, output_dir, quiet=False):
    agents_dir = output_dir / "agents"
    commands_dir = output_dir / "commands"
    skills_dir = output_dir / "skills"
    plugins_dir = output_dir / "plugins"

    agents_dir.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Agents
    for agent in tree.agents:
        body = _expand_body(tree, agent["body"], f"agent {agent['name']}")
        fm = _agent_frontmatter(agent, "opencode")
        (agents_dir / f"{agent['name']}.md").write_text(
            _yaml_frontmatter(fm, body), encoding="utf-8"
        )

        # Agent-scoped commands
        for cmd in agent["commands"]:
            if cmd["secret"]:
                continue
            body = _expand_body(tree, cmd["body"], f"command {cmd['name']}")
            fm = _cmd_frontmatter(cmd, "opencode")
            (commands_dir / f"{cmd['name']}.md").write_text(
                _yaml_frontmatter(fm, body), encoding="utf-8"
            )

    # Standalone commands
    for cmd in tree.commands:
        body = _expand_body(tree, cmd["body"], f"command {cmd['name']}")
        fm = _cmd_frontmatter(cmd, "opencode")
        (commands_dir / f"{cmd['name']}.md").write_text(
            _yaml_frontmatter(fm, body), encoding="utf-8"
        )

    # Skills (physical)
    for skill in tree.skills:
        _copy_skill_files(skill, skills_dir)

    # Delegate-task generated skill
    dt_dir = skills_dir / "delegate-task"
    dt_dir.mkdir(parents=True, exist_ok=True)
    (dt_dir / "SKILL.md").write_text(
        _generate_delegate_task(tree), encoding="utf-8"
    )

    # Plugins (skip files with Nix build-time template tokens @...@)
    plugins_src = tree.agentic / "opencode/plugins"
    if plugins_src.exists():
        for pf in sorted(os.listdir(plugins_src)):
            src = plugins_src / pf
            if not src.is_file():
                continue
            content = src.read_text(encoding="utf-8")
            if re.search(r'@\w+@', content):
                if not quiet:
                    print(f"  Skipping plugin {pf}: contains build-time template tokens that cannot be resolved outside Nix")
                continue
            (plugins_dir / pf).write_text(content, encoding="utf-8")

    # Settings
    settings = _build_opencode_settings(tree)
    (output_dir / "settings.json").write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return output_dir


# ---------------------------------------------------------------------------
# OpenCode settings builder
# ---------------------------------------------------------------------------

def _build_opencode_settings(tree):
    instructions = tree.instructions
    body = instructions.get("body", "")
    header = instructions.get("headers", {}).get("opencode", "")
    body = _expand_body(tree, body, "global instructions (opencode)")

    rules_text = f"---\n{header}\n---\n\n{body}\n" if header else body

    kbs = _extract_keybindings(tree.agentic)

    settings = {
        "autoupdate": False,
        "share": "disabled",
        "experimental": {"openTelemetry": False},
        "permission": {"webfetch": "deny", "websearch": "deny"},
        "model": "openai/gpt-5.5",
        "provider": {
            "openai": {
                "models": {
                    "gpt-5.5": {"options": {"reasoningEffort": "high"}}
                }
            }
        },
        "compaction": {"auto": False, "prune": True},
        "tui": {
            "diff_style": "stacked",
            "scroll_acceleration": {"enabled": True},
        },
        "rules": rules_text,
        "mcp": tree.get_mcp_for_opencode(),
        "keybinds": kbs,
    }

    # Custom /init command
    init_path = tree.agentic / "opencode/default.nix"
    if init_path.exists():
        text = init_path.read_text(encoding="utf-8")
        m = re.search(r'init\s*=\s*\{\s*\n\s*description\s*=\s*"([^"]*)"', text)
        if m:
            desc = m.group(1).replace("${robotEmoji}", "\U0001F916")
            settings.setdefault("command", {})["init"] = {
                "description": desc,
                "agent": "rosey",
            }
    return settings


def _extract_keybindings(agentic_path):
    opencode_nix = agentic_path / "opencode/default.nix"
    if not opencode_nix.exists():
        return {}
    text = opencode_nix.read_text(encoding="utf-8")
    kb_start = text.find("keybinds = {")
    if kb_start == -1:
        return {}
    search_start = text.index("{", kb_start) + 1
    depth = 1
    kb_end = -1
    for i, ch in enumerate(text[search_start:], search_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                kb_end = i
                break
    if kb_end == -1:
        return {}
    block = text[search_start:kb_end]
    kbs = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'(\w+)\s*=\s*"([^"]*)"', line)
        if m:
            kbs[m.group(1)] = m.group(2)
    return kbs


# ---------------------------------------------------------------------------
# Claude Code renderer
# ---------------------------------------------------------------------------

def render_claude(tree, output_dir):
    agents_dir = output_dir / "agents"
    commands_dir = output_dir / "commands"
    skills_dir = output_dir / "skills"
    rules_dir = output_dir / "rules"
    mcp_dir = output_dir / "mcp"

    agents_dir.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)
    mcp_dir.mkdir(parents=True, exist_ok=True)

    # Agents
    for agent in tree.agents:
        body = _expand_body(tree, agent["body"], f"claude agent {agent['name']}")
        fm = _agent_frontmatter(agent, "claude")
        (agents_dir / f"{agent['name']}.agent.md").write_text(
            _yaml_frontmatter(fm, body), encoding="utf-8"
        )

        # Agent-scoped commands (prepend @agent or use-task for Claude)
        for cmd in agent["commands"]:
            if cmd["secret"]:
                continue
            body = _expand_body(tree, cmd["body"], f"claude command {cmd['name']}")
            use_task = "use-task: true" in cmd["headers"].get("claude", "")
            if use_task:
                body = (
                    f"Use the Task tool to launch the {agent['name']} agent for the following task:\n\n"
                    f"{body}"
                )
            else:
                body = f"@{agent['name']}\n\n{body}"
            fm = _cmd_frontmatter(cmd, "claude")
            (commands_dir / f"{cmd['name']}.prompt.md").write_text(
                _yaml_frontmatter(fm, body), encoding="utf-8"
            )

    # Standalone commands
    for cmd in tree.commands:
        body = _expand_body(tree, cmd["body"], f"claude command {cmd['name']}")
        fm = _cmd_frontmatter(cmd, "claude")
        (commands_dir / f"{cmd['name']}.prompt.md").write_text(
            _yaml_frontmatter(fm, body), encoding="utf-8"
        )

    # Skills
    for skill in tree.skills:
        _copy_skill_files(skill, skills_dir)
    dt_dir = skills_dir / "delegate-task"
    dt_dir.mkdir(parents=True, exist_ok=True)
    (dt_dir / "SKILL.md").write_text(
        _generate_delegate_task(tree), encoding="utf-8"
    )

    # Global instructions
    body = tree.instructions.get("body", "")
    header = tree.instructions.get("headers", {}).get("claude", "")
    body = _expand_body(tree, body, "claude global instructions")
    (rules_dir / "instructions.md").write_text(
        _yaml_frontmatter(header, body) if header else body + "\n",
        encoding="utf-8"
    )

    # MCP servers (Claude Code JSON)
    mcp_config = tree.get_mcp_for_claude()
    (mcp_dir / "mcp.json").write_text(
        json.dumps(mcp_config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    return output_dir


# ---------------------------------------------------------------------------
# Codex CLI renderer
# ---------------------------------------------------------------------------

def render_codex(tree, output_dir):
    agents_dir = output_dir / "agents"
    skills_dir = output_dir / "skills"

    agents_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Agents (TOML format)
    for agent in tree.agents:
        body = _expand_body(
            tree,
            agent["body"].replace("Task tool", "`spawn_agent` tool")
                         .replace("Permitted tools: Task tool for delegation, direct conversation",
                                  "Permitted tools: `spawn_agent` for delegation, direct conversation"),
            f"codex agent {agent['name']}"
        )
        header = agent["headers"].get("codex", "")
        desc = agent["description"]
        toml = f"""name = "{agent['name']}"
description = "{desc}"
developer_instructions = '''
{body}
'''
"""
        if header:
            toml = f"{header}\n" + toml
        (agents_dir / f"{agent['name']}.toml").write_text(toml, encoding="utf-8")

    # Skills (physical)
    for skill in tree.skills:
        _copy_skill_files(skill, skills_dir)

    # Standalone commands as skills
    for cmd in tree.commands:
        body = _expand_body(tree, cmd["body"], f"codex skill {cmd['name']}")
        content = f"""---
name: {cmd['name']}
description: {cmd['description']}
---

{body}
"""
        skill_out = skills_dir / cmd["name"]
        skill_out.mkdir(parents=True, exist_ok=True)
        (skill_out / "SKILL.md").write_text(content, encoding="utf-8")

    # Agent-scoped commands as skills (with spawn_agent prelude)
    for agent in tree.agents:
        for cmd in agent["commands"]:
            if cmd["secret"]:
                continue
            body = _expand_body(tree, cmd["body"], f"codex agent skill {cmd['name']}")
            content = f"""---
name: {cmd['name']}
description: {cmd['description']}
---

Use the `spawn_agent` tool to launch the `{agent['name']}` agent for this task. Keep the parent thread as the orchestrator.

- Invoking this skill is the user's standing authorisation to use `spawn_agent`.
- Pass the task below and the user's request to the spawned agent.
- Set `agent_type` to `{agent['name']}`.
- Do not set `model`, `reasoning_effort`, or `fork_context`.
- Wait for the spawned agent when its result is needed, then relay the final answer.

## Task

{body}
"""
            skill_out = skills_dir / cmd["name"]
            skill_out.mkdir(parents=True, exist_ok=True)
            (skill_out / "SKILL.md").write_text(content, encoding="utf-8")

    # Delegate-task skill
    dt_dir = skills_dir / "delegate-task"
    dt_dir.mkdir(parents=True, exist_ok=True)
    (dt_dir / "SKILL.md").write_text(
        _generate_delegate_task(tree), encoding="utf-8"
    )

    # Global instructions (raw rules, no frontmatter)
    body = tree.instructions.get("body", "")
    body = _expand_body(tree, body, "codex global instructions")
    (output_dir / "AGENTS.md").write_text(body + "\n", encoding="utf-8")

    # MCP servers (TOML format)
    mcp = tree.get_mcp_for_codex()
    if mcp:
        toml_lines = []
        for name, entry in sorted(mcp.items()):
            toml_lines.append(f"[mcp_servers.{name}]")
            for k, v in entry.items():
                if isinstance(v, bool):
                    toml_lines.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, int):
                    toml_lines.append(f"{k} = {v}")
                elif isinstance(v, list):
                    toml_lines.append(f"{k} = {json.dumps(v)}")
                else:
                    toml_lines.append(f'{k} = "{v}"')
            toml_lines.append("")
        (output_dir / "mcp_servers.toml").write_text(
            "\n".join(toml_lines), encoding="utf-8"
        )

    return output_dir


# ---------------------------------------------------------------------------
# Pi Agent renderer
# ---------------------------------------------------------------------------

def render_pi(tree, output_dir):
    agents_dir = output_dir / "agents"
    prompts_dir = output_dir / "prompts"
    skills_dir = output_dir / "skills"

    agents_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Pi agent defaults
    pi_defaults = [
        "systemPromptMode: append",
        "inheritProjectContext: false",
        "inheritSkills: true",
    ]

    # Agents
    for agent in tree.agents:
        body = _expand_body(tree, agent["body"], f"pi agent {agent['name']}")
        desc = agent["description"].replace('"', '\\"')
        pi_header = agent["headers"].get("pi", "")
        lines = [
            f"name: {agent['name']}",
            f'description: "{desc}"',
        ] + pi_defaults
        if pi_header:
            lines.append(pi_header)
        (agents_dir / f"{agent['name']}.md").write_text(
            _yaml_frontmatter("\n".join(lines), body), encoding="utf-8"
        )

    # Standalone commands as prompts
    for cmd in tree.commands:
        body = _expand_body(tree, cmd["body"], f"pi prompt {cmd['name']}")
        desc = cmd["description"].replace('"', '\\"')
        pi_header = cmd["headers"].get("pi", "")
        lines = [f'description: "{desc}"']
        if pi_header:
            lines.append(pi_header)
        (prompts_dir / f"{cmd['name']}.md").write_text(
            _yaml_frontmatter("\n".join(lines), body), encoding="utf-8"
        )

    # Agent-scoped commands as prompts (with subagent prelude)
    for agent in tree.agents:
        for cmd in agent["commands"]:
            if cmd["secret"]:
                continue
            body = _expand_body(tree, cmd["body"], f"pi agent prompt {cmd['name']}")
            pi_body = (
                f"Use the subagent tool to launch the `{agent['name']}` agent for the task below.\n\n"
                f"- Set `context` to `\"fresh\"`. Do not set `\"fork\"`; the parent session is large and forking inherits parent prose without bound.\n\n"
                f"{body}"
            )
            desc = cmd["description"].replace('"', '\\"')
            pi_header = cmd["headers"].get("pi", "")
            lines = [f'description: "{desc}"']
            if pi_header:
                lines.append(pi_header)
            (prompts_dir / f"{cmd['name']}.md").write_text(
                _yaml_frontmatter("\n".join(lines), pi_body), encoding="utf-8"
            )

    # Skills
    for skill in tree.skills:
        _copy_skill_files(skill, skills_dir)
    dt_dir = skills_dir / "delegate-task"
    dt_dir.mkdir(parents=True, exist_ok=True)
    (dt_dir / "SKILL.md").write_text(
        _generate_delegate_task(tree), encoding="utf-8"
    )

    # Global instructions (raw, no frontmatter for Pi)
    body = tree.instructions.get("body", "")
    body = _expand_body(tree, body, "pi global instructions")
    (output_dir / "AGENTS.md").write_text(body + "\n", encoding="utf-8")

    # MCP servers (Pi JSON format)
    mcp = tree.get_mcp_for_pi()
    if mcp:
        (output_dir / "mcp.json").write_text(
            json.dumps(mcp, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )

    return output_dir


# ---------------------------------------------------------------------------
# Zed Editor renderer
# ---------------------------------------------------------------------------

def render_zed(tree, output_dir):
    # Zed settings are a complete settings.json with context_servers and agent_servers.
    # The user merges the relevant sections into their ~/.config/zed/settings.json.

    context_servers = tree.get_mcp_for_zed_context()
    extensions = tree.get_mcp_zed_extensions()

    # ACP agent servers (External Agent threads)
    agent_servers = {
        "Claude": {"type": "custom", "command": "claude", "args": [], "env": {}},
        "Codex": {"type": "custom", "command": "codex", "args": [], "env": {}},
        "OpenCode": {"type": "custom", "command": "opencode", "args": ["acp"], "env": {}},
    }

    settings = {
        "context_servers": context_servers,
        "agent_servers": agent_servers,
        "extensions": extensions,
    }

    (output_dir / "zed-settings-snippet.json").write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    # Also produce a keymap snippet for external agent threads
    keymap = [
        {
            "bindings": {
                "ctrl-alt-shift-c": ["agent::NewExternalAgentThread", {"agent": {"custom": {"name": "Claude"}}}]
            }
        },
        {
            "bindings": {
                "ctrl-alt-shift-x": ["agent::NewExternalAgentThread", {"agent": {"custom": {"name": "Codex"}}}]
            }
        },
        {
            "bindings": {
                "ctrl-alt-shift-o": ["agent::NewExternalAgentThread", {"agent": {"custom": {"name": "OpenCode"}}}]
            }
        },
    ]
    (output_dir / "zed-keymap-snippet.json").write_text(
        json.dumps(keymap, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    return output_dir


# ---------------------------------------------------------------------------
# Paseo renderer (template)
# ---------------------------------------------------------------------------

def render_paseo(tree, output_dir):
    # Paseo config template with placeholders for non-Nix paths.
    home = os.environ.get("HOME", "/home/user")
    config = {
        "agents": {
            "providers": {
                "claude": {
                    "label": "Claude Code",
                    "command": ["claude"],
                    "order": 10,
                },
                "opencode": {
                    "label": "OpenCode",
                    "command": ["opencode"],
                    "order": 20,
                },
                "codex": {
                    "label": "Codex CLI",
                    "command": ["codex"],
                    "order": 30,
                },
                "pi": {
                    "label": "Pi Agent",
                    "command": ["pi"],
                    "order": 40,
                },
            }
        },
        "features": {
            "dictation": {"enabled": False},
            "voiceMode": {"enabled": False},
        },
        "daemon": {
            "mcp": {"injectIntoAgents": True},
            "loopbackOnly": True,
        },
        "worktrees": {
            "root": f"{home}/Development/Paseo/worktrees",
        },
    }

    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    return output_dir


# ---------------------------------------------------------------------------
# Cursor renderer
# ---------------------------------------------------------------------------

def render_cursor(tree, output_dir):
    rules_dir = output_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    # Global instructions as Cursor rules
    body = tree.instructions.get("body", "")
    body = _expand_body(tree, body, "cursor global instructions", insert_rules=False)

    # Strip YAML frontmatter if present (Cursor doesn't use it)
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()

    (rules_dir / "global.mdc").write_text(body + "\n", encoding="utf-8")

    # Communication rules as a separate rule file
    if tree.communication_rules:
        (rules_dir / "communication-rules.mdc").write_text(
            tree.communication_rules + "\n", encoding="utf-8"
        )

    return output_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Extract AI TUI agent configurations from the nix-config flake. Usage: %(prog)s /path/to/nix-config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Supported platforms (--platform):\n"
            + "\n".join(f"  {k:12s}  {v}" for k, v in PLATFORM_DESCRIPTIONS.items())
        ),
    )
    parser.add_argument(
        "source",
        help="Path to the nix-config repository root (required).",
    )
    parser.add_argument(
        "-p", "--platform",
        default="all",
        help="Comma-separated list of platforms. Default: all. "
             "Use --help to list available platforms.",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output parent directory. Default: _agent_configs_<datetime>_<commit> in the script's directory.",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress per-file progress output.",
    )
    return parser


RENDERERS = {
    "opencode": render_opencode,
    "claude": render_claude,
    "codex": render_codex,
    "pi": render_pi,
    "zed": render_zed,
    "paseo": render_paseo,
    "cursor": render_cursor,
}


def _get_git_info(path):
    """Return (remote_url, commit_hash, commit_date) or (None, None, None)."""
    git_dir = path / ".git"
    if not git_dir.exists():
        return None, None, None
    try:
        import subprocess
        remote = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        rev = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        date = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%cd", "--date=iso-strict"],
            capture_output=True, text=True, timeout=5,
        )
        remote_url = remote.stdout.strip() if remote.returncode == 0 else None
        commit_hash = rev.stdout.strip() if rev.returncode == 0 else None
        commit_date = date.stdout.strip() if date.returncode == 0 else None
        return remote_url, commit_hash, commit_date
    except Exception:
        return None, None, None


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    source = Path(args.source).resolve()
    agentic_path = source / "home-manager/_mixins/agentic"
    if not agentic_path.exists():
        print(f"Error: agentic directory not found at {agentic_path}", file=sys.stderr)
        sys.exit(1)

    if args.platform == "all":
        selected = ALL_PLATFORMS
    else:
        selected = [p.strip() for p in args.platform.split(",")]
        for p in selected:
            if p not in RENDERERS:
                print(f"Error: unknown platform '{p}'. Use --help to list supported platforms.")
                sys.exit(1)

    source_remote, source_commit, source_commit_date = _get_git_info(source)
    if args.output is None:
        parts = []
        if source_commit_date:
            clean = source_commit_date.replace(":", "").replace("-", "").replace("+", "-").split("-")[0]
            parts.append(clean[:15])
        if source_commit:
            parts.append(source_commit[:7])
        suffix = "_".join(parts)
        output_base = REPO_ROOT / f"_agent_configs_{suffix}" if suffix else REPO_ROOT / "_agent_configs"
    else:
        output_base = Path(args.output)

    tree = SourceTree(source)

    for platform in selected:
        platform_dir = output_base / platform
        if platform_dir.exists():
            shutil.rmtree(platform_dir)
        platform_dir.mkdir(parents=True, exist_ok=True)

        render_fn = RENDERERS[platform]
        if platform == "opencode":
            render_fn(tree, platform_dir, quiet=args.quiet)
        else:
            render_fn(tree, platform_dir)

        if not args.quiet:
            # Count output
            file_count = sum(1 for _ in platform_dir.rglob("*") if _.is_file())
            print(f"  {platform}: {platform_dir} ({file_count} files)")

    # Write root README
    source_label = source_remote or source.name
    readme = output_base / "README.md"
    lines = [
        "# AI TUI Agent Configurations",
        "",
        f"Extracted from {source_label} on {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.",
    ]
    if source_commit and source_commit_date:
        lines.append("")
        if source_remote:
            lines.append(f"Source commit: [{source_commit[:7]}]({_strip_git_suffix(source_remote)}/tree/{source_commit}) ({source_commit_date})")
        else:
            lines.append(f"Source commit: {source_commit} ({source_commit_date})")
    lines += [
        "",
        "## Contents",
        "",
    ]
    for p in sorted(PLATFORM_DESCRIPTIONS):
        if p in selected:
            d = output_base / p
            fc = sum(1 for _ in d.rglob("*") if _.is_file()) if d.exists() else 0
            lines.append(f"- **{p}** — {PLATFORM_DESCRIPTIONS[p]} ({fc} files)")
    lines += [
        "",
        "## Deployment",
        "",
    ]
    for p in selected:
        desc = PLATFORM_DESCRIPTIONS[p]
        target = desc.split("→ ")[-1].rstrip("/")
        lines.append("```bash")
        lines.append(f"# {p}")
        lines.append(f"cp -r {output_base}/{p}/* {target}")
        lines.append("```")

    if "zed" in selected:
        lines += [
            "",
            "### Zed notes",
            "",
            "Zed output is a settings snippet, not a complete settings.json.",
            "Merge `zed-settings-snippet.json` into your `~/.config/zed/settings.json`",
            "under the top-level keys shown. Merge `zed-keymap-snippet.json` entries",
            "into your keymap array in `~/.config/zed/keymaps.json`.",
        ]

    if "paseo" in selected:
        lines += [
            "",
            "### Paseo notes",
            "",
            "The Paseo config template assumes agent binaries are on PATH.",
            "Adjust `command` paths if your agents are installed elsewhere.",
        ]

    output_base.mkdir(parents=True, exist_ok=True)
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not args.quiet:
        total = sum(
            sum(1 for _ in (output_base / p).rglob("*") if _.is_file())
            for p in selected if (output_base / p).exists()
        )
        print(f"\nDone! {total} files across {len(selected)} platform(s) in {output_base}")


if __name__ == "__main__":
    main()
