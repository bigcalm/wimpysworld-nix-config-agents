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
        settings = json.loads((out / "settings.json").read_text())

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

    def test_claude_output(self):
        out = e.render_claude(self.tree, self.tmp)
        mcp = json.loads((out / "mcp" / "mcp.json").read_text())
        self.assertIn("mcpServers", mcp)
        self.assertEqual(mcp["mcpServers"]["slack"]["oauth"]["clientId"], "12345")
        self.assertIn("mcpServers", mcp)
        self.assertEqual(mcp["mcpServers"]["context7"]["type"], "http")
        self.assertTrue((out / "rules" / "instructions.md").exists())

    def test_codex_output(self):
        out = e.render_codex(self.tree, self.tmp)
        mcp = tomllib.loads((out / "mcp_servers.toml").read_text())
        self.assertEqual(mcp["mcp_servers"]["context7"]["startup_timeout_sec"], 10)
        self.assertEqual(mcp["mcp_servers"]["linear"]["default_tools_approval_mode"], "prompt")
        self.assertEqual(mcp["mcp_servers"]["playwright"]["command"], "playwright-mcp")
        self.assertEqual(mcp["mcp_servers"]["mcpGoogleCse"]["command"], "${pkgs.uv}/bin/uvx")
        slack = mcp["mcp_servers"]["slack"]
        self.assertEqual(slack["disabled_tools"], ["slack_send_message", "slack_update_canvas"])
        self.assertEqual(slack["oauth"]["client_id"], "12345")
        self.assertTrue((out / "agents" / "brain.toml").exists())

    def test_pi_output(self):
        out = e.render_pi(self.tree, self.tmp)
        mcp = json.loads((out / "mcp.json").read_text())
        self.assertNotIn("slack", mcp)
        self.assertNotIn("linear", mcp)
        self.assertEqual(mcp["context7"]["directTools"], True)
        self.assertEqual(mcp["mcpGoogleCse"]["env"]["API_KEY"], "${GOOGLE_CSE_API_KEY}")
        self.assertEqual(mcp["context7"]["headers"]["Authorization"], "Bearer ${CONTEXT7_API_KEY}")

    def test_zed_output(self):
        out = e.render_zed(self.tree, self.tmp)
        snippet = json.loads((out / "zed-settings-snippet.json").read_text())
        self.assertEqual(snippet["extensions"], ["mcp-server-context7"])
        self.assertNotIn("context7", snippet["context_servers"])

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
            # Settings rules must be non-empty markdown.
            settings = json.loads((out / "opencode" / "settings.json").read_text())
            self.assertTrue(settings["rules"].startswith("---"))
            self.assertGreater(len(settings["rules"]), 100)
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
