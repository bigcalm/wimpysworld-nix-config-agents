#!/usr/bin/env python3
"""Tests for apply_local_overlay.sh, local/patch_agents_md.py, and
local/merge_personal.py.

The overlay installs wrappers to $HOME/.local/bin, so every run uses a
scratch HOME and a scratch extracted tree.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY = REPO_ROOT / "apply_local_overlay.sh"
PATCH = REPO_ROOT / "local/patch_agents_md.py"
MERGE = REPO_ROOT / "local/merge_personal.py"
GLAB_WRAPPER = REPO_ROOT / "local/opencode/bin/glab-api-safe.sh"
GH_WRAPPER = REPO_ROOT / "local/opencode/bin/gh-api-safe.sh"

GH_TOOL_LINE = (
    "For GitHub, load the `gh` skill. "
    "For reads, prefer the constrained CLI path when available: "
    "use a dedicated `gh` subcommand first, then `gh-api-safe` for raw REST or GraphQL reads."
)


def make_agents_dir(root: Path) -> Path:
    """Build an extracted-like opencode tree with a patchable AGENTS.md."""
    opencode = root / "opencode"
    opencode.mkdir(parents=True)
    rules = (
        "# Rules\n\n"
        f"{GH_TOOL_LINE}\n\n"
        "Keep GitHub mutations on named, authorised paths.\n\n"
        "Other section.\n"
    )
    (opencode / "AGENTS.md").write_text(rules)
    (opencode / "opencode.json").write_text(
        json.dumps({
            "model": "openai/gpt-5.5",
            "mcp": {"context7": {"type": "remote", "url": "https://mcp.context7.com/mcp"}},
        }) + "\n"
    )
    return opencode


class TestPatchAgents(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="patch-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_patch(self, opencode_dir, expected_exit=0):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT)
        r = subprocess.run(
            ["python3", str(PATCH), str(opencode_dir)],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(
            r.returncode, expected_exit,
            f"expected exit {expected_exit}, got {r.returncode}: {r.stderr}",
        )
        return r

    def test_applies_then_idempotent(self):
        opencode = make_agents_dir(self.tmp)
        self.run_patch(opencode)
        rules = (opencode / "AGENTS.md").read_text()
        self.assertIn("Keep GitLab mutations on named, authorised paths.", rules)
        self.assertEqual(rules.count("Keep GitLab mutations on named, authorised paths."), 1)
        self.assertIn("For GitLab, load the `glab` skill", rules)
        self.assertIn("glab-api-safe", rules)
        # Second run is a no-op.
        self.run_patch(opencode)
        rules2 = (opencode / "AGENTS.md").read_text()
        self.assertEqual(rules, rules2)

    def test_refuses_when_github_paragraph_drifted(self):
        opencode = make_agents_dir(self.tmp)
        agents_path = opencode / "AGENTS.md"
        text = agents_path.read_text().replace(
            "use a dedicated `gh` subcommand first",
            "use a dedicated `gh` subcommand initially",
        )
        agents_path.write_text(text)
        r = self.run_patch(opencode, expected_exit=1)
        self.assertIn("refusing to patch silently", r.stderr)

    def test_refuses_when_github_section_missing(self):
        opencode = self.tmp / "opencode"
        opencode.mkdir()
        (opencode / "AGENTS.md").write_text("# Rules\n\nNothing here.\n")
        r = self.run_patch(opencode, expected_exit=1)
        self.assertIn("expected GitHub rules paragraphs not found", r.stderr)

    def test_missing_agents_md(self):
        r = subprocess.run(
            ["python3", str(PATCH), str(self.tmp)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("not found", r.stderr)


class TestMergePersonal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="merge-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_merge(self, opencode_dir, personal, expected_exit=0):
        r = subprocess.run(
            ["python3", str(MERGE), str(opencode_dir), str(personal)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            r.returncode, expected_exit,
            f"expected exit {expected_exit}, got {r.returncode}: {r.stderr}",
        )
        return r

    def test_deep_merge_adds_and_combines(self):
        opencode = make_agents_dir(self.tmp)
        personal = self.tmp / "personal.json"
        personal.write_text(json.dumps({
            "model": "anthropic/claude-sonnet-4-5",
            "mcp": {
                "kagi": {
                    "type": "remote",
                    "url": "https://mcp.example.com/mcp",
                    "headers": {"Authorization": "Bearer {env:PRIVATE_MCP_TOKEN}"},
                },
                "context7": {"enabled": False},
            },
        }) + "\n")
        self.run_merge(opencode, personal)

        settings = json.loads((opencode / "opencode.json").read_text())
        # Personal wins on the scalar conflict.
        self.assertEqual(settings["model"], "anthropic/claude-sonnet-4-5")
        # Nested mcp objects combine: context7 keys survive and merge.
        self.assertEqual(settings["mcp"]["context7"]["type"], "remote")
        self.assertEqual(settings["mcp"]["context7"]["enabled"], False)
        # New server added, with the bearer header preserved.
        self.assertEqual(
            settings["mcp"]["kagi"]["headers"]["Authorization"],
            "Bearer {env:PRIVATE_MCP_TOKEN}",
        )
        # Second run is a no-op.
        self.run_merge(opencode, personal)
        self.assertEqual(
            json.loads((opencode / "opencode.json").read_text()),
            settings,
        )

    def test_missing_personal_skips(self):
        opencode = make_agents_dir(self.tmp)
        r = self.run_merge(opencode, self.tmp / "nope.json", expected_exit=0)
        self.assertIn("skipping", r.stderr)
        self.assertEqual(
            json.loads((opencode / "opencode.json").read_text())["model"],
            "openai/gpt-5.5",
        )

    def test_missing_opencode_json_fails(self):
        opencode = self.tmp / "opencode"
        opencode.mkdir()
        personal = self.tmp / "personal.json"
        personal.write_text("{}")
        r = self.run_merge(opencode, personal, expected_exit=1)
        self.assertIn("not found", r.stderr)

    def test_malformed_personal_json_fails(self):
        opencode = make_agents_dir(self.tmp)
        personal = self.tmp / "personal.json"
        personal.write_text("{ not valid json")
        r = self.run_merge(opencode, personal, expected_exit=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error", r.stderr)

    def test_malformed_opencode_json_fails(self):
        opencode = self.tmp / "opencode"
        opencode.mkdir()
        (opencode / "opencode.json").write_text("{ not valid json")
        personal = self.tmp / "personal.json"
        personal.write_text("{}")
        r = self.run_merge(opencode, personal, expected_exit=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error", r.stderr)

    def test_meta_keys_never_merge(self):
        opencode = make_agents_dir(self.tmp)
        personal = self.tmp / "personal.json"
        personal.write_text(json.dumps({
            "$comment": "documentation only",
            "model": "anthropic/claude-sonnet-4-5",
            "mcp": {
                "kagi": {"type": "remote", "url": "https://mcp.example.com/mcp"},
            },
        }) + "\n")
        self.run_merge(opencode, personal)
        settings = json.loads((opencode / "opencode.json").read_text())
        self.assertNotIn("$comment", settings)
        self.assertEqual(settings["model"], "anthropic/claude-sonnet-4-5")


class TestApplyLocalOverlay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="overlay-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.target = self.tmp / "out"
        self.target.mkdir()
        make_agents_dir(self.target)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_overlay(self, *args, expected_exit=0):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        r = subprocess.run(
            [str(OVERLAY), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(
            r.returncode, expected_exit,
            f"expected exit {expected_exit}, got {r.returncode}: {r.stderr}",
        )
        return r

    def test_idempotent_merge_and_install(self):
        # Scratch personal file keeps the test hermetic: it never touches the
        # developer's git-ignored local/personal.json, which exists only on
        # some machines.
        personal = self.tmp / "personal.json"
        personal.write_text(json.dumps({
            "mcp": {"scratch-server": {"type": "remote", "url": "https://mcp.example.com/mcp"}},
        }) + "\n")
        self.run_overlay("dummy-nix-config-path", str(self.target), str(personal))
        first_agents = (self.target / "opencode" / "AGENTS.md").read_text()
        first_settings = (self.target / "opencode" / "opencode.json").read_text()
        self.assertIn("Keep GitLab mutations", first_agents)
        self.assertIn("scratch-server", first_settings)
        self.assertTrue((self.home / ".local/bin/glab-api-safe").is_file())
        self.assertTrue((self.home / ".local/bin/gh-api-safe").is_file())
        self.run_overlay("dummy-nix-config-path", str(self.target), str(personal))
        self.assertEqual((self.target / "opencode" / "AGENTS.md").read_text(), first_agents)
        self.assertEqual((self.target / "opencode" / "opencode.json").read_text(), first_settings)

    def test_explicit_missing_personal_warns(self):
        r = self.run_overlay(
            "dummy-nix-config-path", str(self.target),
            str(self.tmp / "nope.json"), expected_exit=0,
        )
        self.assertIn("not found; continuing without it", r.stderr)

    def test_in_repo_unignored_target_refused(self):
        # A target inside the repo that git does not ignore must be refused,
        # so personal tokens cannot be committed by a later `git add .`.
        in_repo = REPO_ROOT / ".review-untracked-target"
        in_repo.mkdir(exist_ok=True)
        (in_repo / "opencode").mkdir(parents=True, exist_ok=True)
        (in_repo / "opencode" / "opencode.json").write_text("{}\n")
        try:
            r = self.run_overlay(
                "dummy-nix-config-path", str(in_repo), expected_exit=1,
            )
            self.assertIn("refusing to write into", r.stderr)
        finally:
            shutil.rmtree(in_repo, ignore_errors=True)

    def test_personal_json_merged(self):
        personal = self.tmp / "personal.json"
        personal.write_text(json.dumps({
            "mcp": {"kagi": {"type": "remote", "url": "https://mcp.example.com/mcp"}},
        }) + "\n")
        self.run_overlay("dummy-nix-config-path", str(self.target), str(personal))
        settings = json.loads((self.target / "opencode" / "opencode.json").read_text())
        self.assertEqual(
            settings["mcp"]["kagi"]["url"],
            "https://mcp.example.com/mcp",
        )
        # Extracted mcp entries survive the merge.
        self.assertIn("context7", settings["mcp"])
        # Idempotent: rerun does not duplicate or error.
        self.run_overlay("dummy-nix-config-path", str(self.target), str(personal))
        self.assertEqual(
            json.loads((self.target / "opencode" / "opencode.json").read_text()),
            settings,
        )

    def test_missing_wrapper_source_fails_before_install(self):
        shutil.move(str(GLAB_WRAPPER), str(GLAB_WRAPPER) + ".bak")
        try:
            r = self.run_overlay("dummy-nix-config-path", str(self.target), expected_exit=1)
            self.assertIn("wrapper source not found", r.stderr)
            # Nothing installed, AGENTS.md untouched.
            self.assertFalse((self.home / ".local/bin/glab-api-safe").exists())
            self.assertFalse((self.home / ".local/bin/gh-api-safe").exists())
            self.assertNotIn("Keep GitLab mutations", (self.target / "opencode" / "AGENTS.md").read_text())
        finally:
            shutil.move(str(GLAB_WRAPPER) + ".bak", str(GLAB_WRAPPER))

    def test_symlink_wrapper_source_refused(self):
        src = REPO_ROOT / "local/opencode/bin/gh-api-safe.sh"
        bak = REPO_ROOT / "local/opencode/bin/gh-api-safe.sh.bak"
        shutil.move(str(src), str(bak))
        try:
            os.symlink(bak, src)
            r = self.run_overlay("dummy-nix-config-path", str(self.target), expected_exit=1)
            self.assertIn("refusing symlink wrapper source", r.stderr)
            self.assertFalse((self.home / ".local/bin/gh-api-safe").exists())
        finally:
            os.unlink(src)
            shutil.move(str(bak), str(src))

    def test_missing_output_dir_fails(self):
        r = self.run_overlay("dummy-nix-config-path", str(self.tmp / "nope"), expected_exit=1)
        self.assertIn("does not exist", r.stderr)

    def test_missing_arguments_fail(self):
        r = subprocess.run(
            [str(OVERLAY)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing nix-config path", r.stderr)


if __name__ == "__main__":
    unittest.main()
