#!/usr/bin/env python3
"""Tests for extract_agent_config.py using a minimal fixture source tree."""

import json
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

# Add the repo root to the path so we can import the script.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import extract_agent_config as e


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal"


class TestSourceTreeParsing(unittest.TestCase):
    def test_loads_agents(self):
        tree = e.SourceTree(FIXTURE)
        self.assertEqual(len(tree.agents), 1)
        agent = tree.agents[0]
        self.assertEqual(agent["name"], "brain")
        self.assertEqual(agent["description"], "Test engineering specialist")
        self.assertIn("opencode", agent["headers"])
        self.assertIn("codex", agent["headers"])
        self.assertEqual(len(agent["commands"]), 2)
        self.assertEqual({c["name"] for c in agent["commands"]}, {"review-tests", "draft-secret"})

    def test_marks_secret_commands(self):
        tree = e.SourceTree(FIXTURE)
        brain = next(a for a in tree.agents if a["name"] == "brain")
        secret = next(c for c in brain["commands"] if c["name"] == "draft-secret")
        self.assertTrue(secret["secret"])
        self.assertIsNone(secret["body"])

    def test_loads_commands(self):
        tree = e.SourceTree(FIXTURE)
        self.assertEqual(len(tree.commands), 1)
        self.assertEqual(tree.commands[0]["name"], "create-skill")

    def test_loads_skills(self):
        tree = e.SourceTree(FIXTURE)
        self.assertEqual(len(tree.skills), 1)
        self.assertEqual(tree.skills[0]["name"], "write-skill")

    def test_loads_communication_rules(self):
        tree = e.SourceTree(FIXTURE)
        self.assertIsNotNone(tree.communication_rules)
        self.assertIn("short sentences", tree.communication_rules)

    def test_loads_global_instructions(self):
        tree = e.SourceTree(FIXTURE)
        self.assertIn("Delegate", tree.instructions["body"])
        self.assertIn("opencode", tree.instructions["headers"])

    def test_parses_mcp_servers(self):
        tree = e.SourceTree(FIXTURE)
        servers = {s["name"]: s for s in tree.mcp_servers}

        # HTTP servers
        self.assertEqual(servers["context7"]["transport"], "http")
        self.assertEqual(servers["context7"]["auth_env_var"], "CONTEXT7_API_KEY")
        self.assertEqual(servers["context7"]["startup_timeout_sec"], 10)
        self.assertEqual(servers["context7"]["zed_mode"], "extension")
        self.assertEqual(servers["context7"]["zed_id"], "mcp-server-context7")

        self.assertEqual(servers["exa"]["transport"], "http")
        self.assertEqual(servers["exa"]["opencode_enabled"], True)

        # OAuth
        self.assertEqual(servers["slack"]["oauth"]["clientId"], "12345")
        self.assertEqual(servers["slack"]["oauth"]["callbackPort"], 3000)
        self.assertEqual(servers["slack"]["oauth"]["redirectUri"], "http://localhost:3000/callback")

        # lib.mkDefault-wrapped URL is unwrapped
        self.assertEqual(servers["slack"]["url"], "https://mcp.slack.com/mcp")

        # Top-level binding resolved in disabledTools/excludeTools
        self.assertEqual(servers["slack"]["opencode_disabled_tools"], ["slack_send_message", "slack_update_canvas"])
        self.assertEqual(servers["slack"]["codex_disabled_tools"], ["slack_send_message", "slack_update_canvas"])
        self.assertEqual(servers["slack"]["pi_exclude_tools"], ["slack_send_message", "slack_update_canvas"])

        # Nested pi consumers
        self.assertEqual(servers["slack"]["pi_omit"], True)
        self.assertEqual(servers["linear"]["pi_omit"], True)
        self.assertEqual(servers["linear"]["codex_default_tools_approval_mode"], "prompt")

        # Global enabled
        self.assertEqual(servers["nixos"]["enabled"], True)
        self.assertEqual(servers["mcpGoogleCse"]["enabled"], True)

        # Quoted key parsed; ''...'' string and comment with } handled
        self.assertEqual(servers["mcpGoogleCse"]["env"], {"API_KEY": "GOOGLE_CSE_API_KEY"})
        # Quoted command value is stripped
        self.assertEqual(servers["mcpGoogleCse"]["command_ref"], "${pkgs.uv}/bin/uvx")


class TestRenderers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="extract-test-"))
        self.tree = e.SourceTree(FIXTURE)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_opencode_output(self):
        out = e.render_opencode(self.tree, self.tmp, quiet=True)
        settings = json.loads((out / "opencode.json").read_text())

        self.assertIn("mcp", settings)
        self.assertEqual(settings["mcp"]["context7"]["type"], "remote")
        self.assertEqual(
            settings["mcp"]["context7"]["headers"]["Authorization"],
            "Bearer {env:CONTEXT7_API_KEY}"
        )
        self.assertEqual(settings["mcp"]["nixos"]["enabled"], False)
        self.assertEqual(settings["mcp"]["playwright"]["command"], ["playwright-mcp", "--headless"])
        self.assertEqual(settings["mcp"]["mcpGoogleCse"]["environment"]["API_KEY"], "{env:GOOGLE_CSE_API_KEY}")
        slack = settings["mcp"]["slack"]
        self.assertEqual(slack["oauth"]["clientId"], "12345")
        self.assertEqual(slack["oauth"]["redirectUri"], "http://localhost:3000/callback")
        self.assertEqual(slack["url"], "https://mcp.slack.com/mcp")

        self.assertTrue((out / "agents" / "brain.md").exists())
        self.assertTrue((out / "commands" / "create-skill.md").exists())
        self.assertTrue((out / "skills" / "write-skill" / "SKILL.md").exists())

        # The legacy settings.json must not be emitted alongside opencode.json.
        self.assertFalse((out / "settings.json").exists())
        # Global rules ship as AGENTS.md, not as a config `rules` key.
        self.assertNotIn("rules", settings)
        self.assertTrue((out / "AGENTS.md").exists())

    def test_opencode_tui_and_init(self):
        out = e.render_opencode(self.tree, self.tmp, quiet=True)
        settings = json.loads((out / "opencode.json").read_text())
        tui = json.loads((out / "tui.json").read_text())

        # tui and keybinds moved out of opencode.json into tui.json.
        self.assertNotIn("tui", settings)
        self.assertNotIn("keybinds", settings)
        self.assertEqual(tui["tui"]["diff_style"], "stacked")
        self.assertEqual(tui["keybinds"]["app_exit"], "ctrl+d")
        self.assertEqual(tui["keybinds"]["input_submit"], "return")
        # /init carries the template read from the rosey command.
        init = settings["command"]["init"]
        self.assertEqual(init["agent"], "rosey")
        self.assertIn("AGENTS.md", init["template"])

    def test_opencode_permission_denies(self):
        out = e.render_opencode(self.tree, self.tmp, quiet=True)
        settings = json.loads((out / "opencode.json").read_text())
        permission = settings["permission"]
        self.assertEqual(permission["webfetch"], "deny")
        self.assertEqual(permission["slack_slack_send_message"], "deny")
        self.assertEqual(permission["slack_slack_update_canvas"], "deny")
        self.assertNotIn("exa_", " ".join(permission))

    def test_opencode_rules_carry_house_style(self):
        out = e.render_opencode(self.tree, self.tmp, quiet=True)
        settings = json.loads((out / "opencode.json").read_text())
        rules = (out / "AGENTS.md").read_text()
        # Rules live in AGENTS.md, not in the config file.
        self.assertNotIn("rules", settings)
        self.assertNotIn("---", rules.splitlines()[0] if rules.splitlines() else "")
        self.assertEqual(rules.count("short sentences"), 1)

    def test_plugin_copy_skips_template_tokens(self):
        out = e.render_opencode(self.tree, self.tmp, quiet=True)
        plugins = out / "plugins"
        self.assertTrue((plugins / "safe-plugin.js").exists())
        self.assertFalse((plugins / "token-plugin.js").exists())

    def test_claude_output(self):
        out = e.render_claude(self.tree, self.tmp)
        mcp = json.loads((out / "mcp" / "mcp.json").read_text())
        self.assertIn("mcpServers", mcp)
        self.assertEqual(mcp["mcpServers"]["slack"]["oauth"]["clientId"], "12345")
        self.assertIn("mcpServers", mcp)
        self.assertEqual(mcp["mcpServers"]["context7"]["type"], "http")
        self.assertTrue((out / "rules" / "instructions.md").exists())

    def test_claude_output_style(self):
        out = e.render_claude(self.tree, self.tmp)
        style = (out / "output-styles" / "house-style.md").read_text()
        self.assertTrue(style.startswith("---"))
        self.assertIn("short sentences", style)

    def test_codex_output(self):
        out = e.render_codex(self.tree, self.tmp)
        cfg = tomllib.loads((out / "config.toml").read_text())
        mcp = cfg["mcp_servers"]
        self.assertEqual(mcp["context7"]["startup_timeout_sec"], 10)
        self.assertEqual(mcp["linear"]["default_tools_approval_mode"], "prompt")
        self.assertEqual(mcp["playwright"]["command"], "playwright-mcp")
        self.assertEqual(mcp["mcpGoogleCse"]["command"], "${pkgs.uv}/bin/uvx")
        slack = mcp["slack"]
        self.assertEqual(slack["disabled_tools"], ["slack_send_message", "slack_update_canvas"])
        self.assertEqual(slack["oauth"]["client_id"], "12345")
        self.assertEqual(cfg["approval_policy"], "never")
        self.assertEqual(cfg["model"], "gpt-5.6-sol")
        self.assertIn("short sentences", cfg["developer_instructions"])
        self.assertTrue((out / "agents" / "brain.toml").exists())

    def test_codex_command_skill_sidecar(self):
        out = e.render_codex(self.tree, self.tmp)
        # allow-implicit-invocation in header.codex.toml emits openai.yaml.
        yaml = (out / "skills" / "create-skill" / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: false", yaml)
        # Raw TOML must not land inside the SKILL.md frontmatter.
        skill = (out / "skills" / "create-skill" / "SKILL.md").read_text()
        self.assertNotIn("allow-implicit-invocation", skill)

    def test_codex_spawn_agent_opt_out(self):
        out = e.render_codex(self.tree, self.tmp)
        # review-tests sets spawn-agent = false: the owning agent's persona
        # is embedded and no spawn_agent prelude is written.
        skill = (out / "skills" / "review-tests" / "SKILL.md").read_text()
        self.assertIn("Expert test engineer", skill)
        self.assertNotIn("spawn_agent", skill)

    def test_pi_output(self):
        out = e.render_pi(self.tree, self.tmp)
        mcp = json.loads((out / "mcp.json").read_text())
        self.assertNotIn("slack", mcp)
        self.assertNotIn("linear", mcp)
        self.assertEqual(mcp["context7"]["directTools"], True)
        self.assertEqual(mcp["mcpGoogleCse"]["env"]["API_KEY"], "${GOOGLE_CSE_API_KEY}")
        self.assertEqual(mcp["context7"]["headers"]["Authorization"], "Bearer ${CONTEXT7_API_KEY}")

    def test_pi_oauth_and_house_style(self):
        out = e.render_pi(self.tree, self.tmp)
        mcp = json.loads((out / "mcp.json").read_text())
        self.assertEqual(mcp["exa"]["oauth"]["clientId"], "exa-456")
        self.assertEqual(mcp["exa"]["oauth"]["redirectUri"], "http://localhost:3001/callback")
        agents_md = (out / "AGENTS.md").read_text()
        self.assertEqual(agents_md.count("short sentences"), 1)

    def test_pi_agent_prompt_subagent_tool(self):
        out = e.render_pi(self.tree, self.tmp)
        agent = (out / "agents" / "brain.md").read_text()
        self.assertNotIn("Task tool", agent)

    def test_zed_output(self):
        out = e.render_zed(self.tree, self.tmp)
        snippet = json.loads((out / "zed-settings-snippet.json").read_text())
        self.assertEqual(snippet["extensions"], ["mcp-server-context7"])
        self.assertNotIn("context7", snippet["context_servers"])
        self.assertIn("mcpGoogleCse", snippet["context_servers"])
        self.assertTrue((out / "zed-keymap-snippet.json").exists())

    def test_paseo_output(self):
        out = e.render_paseo(self.tree, self.tmp)
        config = json.loads((out / "config.json").read_text())
        providers = config["agents"]["providers"]
        self.assertEqual(
            sorted(providers),
            ["claude", "codex", "opencode", "pi"],
        )
        self.assertEqual(providers["claude"]["command"], ["claude"])
        self.assertTrue(config["worktrees"]["root"].startswith("/"))
        self.assertEqual(config["features"]["voiceMode"]["enabled"], False)

    def test_delegate_task_content(self):
        out = e.render_claude(self.tree, self.tmp)
        skill = (out / "skills" / "delegate-task" / "SKILL.md").read_text()
        self.assertIn("## Waiting", skill)
        self.assertIn("## Teardown", skill)
        self.assertIn("Authority: <external mutations", skill)
        self.assertIn("Deadline: <hard stop", skill)
        self.assertIn("## Agents", skill)

    def test_cursor_output(self):
        out = e.render_cursor(self.tree, self.tmp)
        global_mdc = (out / "rules" / "global.mdc").read_text()
        rules_mdc = (out / "rules" / "communication-rules.mdc").read_text()
        self.assertNotIn("Communication Rules", global_mdc)
        self.assertIn("short sentences", rules_mdc)


class TestCommunicationRulesExpansion(unittest.TestCase):
    def test_inserts_rules_when_present(self):
        tree = e.SourceTree(FIXTURE)
        body = e._expand_body(tree, "# Rules\n<!-- COMMUNICATION_RULES -->\n", "test")
        self.assertIn("short sentences", body)
        self.assertNotIn("<!-- COMMUNICATION_RULES -->", body)

    def test_strips_marker_when_no_rules(self):
        class FakeTree:
            communication_rules = None
        body = e._expand_body(FakeTree(), "# Rules\n<!-- COMMUNICATION_RULES -->\n", "test")
        self.assertNotIn("<!-- COMMUNICATION_RULES -->", body)


class TestFullExtraction(unittest.TestCase):
    def test_all_platforms_output_is_parseable(self):
        out = Path(tempfile.mkdtemp(prefix="extract-test-"))
        try:
            with patch.object(sys, "argv", ["extract_agent_config.py", str(FIXTURE), "--output", str(out), "--platform", "all", "--quiet"]):
                e.main()

            for platform_dir in out.iterdir():
                if not platform_dir.is_dir():
                    continue
                for path in platform_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    suffix = path.suffix
                    text = path.read_text(encoding="utf-8")
                    # No sops secret body may leak into any output file.
                    self.assertNotIn("secret-body-must-never-leak", text)
                    if suffix == ".json":
                        json.loads(text)
                    elif suffix == ".toml":
                        tomllib.loads(text)

            expected_dirs = {"opencode", "claude", "codex", "pi", "zed", "paseo", "cursor"}
            self.assertEqual(expected_dirs, {p.name for p in out.iterdir() if p.is_dir()})
            # Settings rules must be non-empty markdown in AGENTS.md.
            settings = json.loads((out / "opencode" / "opencode.json").read_text())
            self.assertNotIn("rules", settings)
            rules = (out / "opencode" / "AGENTS.md").read_text()
            self.assertGreater(len(rules), 100)
        finally:
            shutil.rmtree(out)

    def test_readme_deployment_commands_are_valid(self):
        out = Path(tempfile.mkdtemp(prefix="extract-test-"))
        try:
            with patch.object(sys, "argv", ["extract_agent_config.py", str(FIXTURE), "--output", str(out), "--platform", "all", "--quiet"]):
                e.main()
            readme = (out / "README.md").read_text()
            # File targets get cp, not cp -r: `cp -r dir/* file` fails.
            self.assertIn(f"cp {out}/zed/zed-settings-snippet.json ~/.config/zed/settings.json", readme)
            self.assertIn(f"cp {out}/paseo/config.json ~/.paseo/config.json", readme)
            self.assertIn(f"cp -r {out}/opencode/* ~/.config/opencode", readme)
        finally:
            shutil.rmtree(out)

    def test_subset_run_removes_stale_platform_dirs(self):
        out = Path(tempfile.mkdtemp(prefix="extract-test-"))
        try:
            with patch.object(sys, "argv", ["extract_agent_config.py", str(FIXTURE), "--output", str(out), "--platform", "all", "--quiet"]):
                e.main()
            self.assertTrue((out / "opencode").exists())
            with patch.object(sys, "argv", ["extract_agent_config.py", str(FIXTURE), "--output", str(out), "--platform", "claude", "--quiet"]):
                e.main()
            dirs = {p.name for p in out.iterdir() if p.is_dir()}
            self.assertEqual(dirs, {"claude"})
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
