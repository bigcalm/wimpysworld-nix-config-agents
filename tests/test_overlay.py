#!/usr/bin/env python3
"""Tests for apply_local_overlay.sh and local/patch_agents_md.py.

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
        self.run_overlay("dummy-nix-config-path", str(self.target))
        first = (self.target / "opencode" / "AGENTS.md").read_text()
        self.assertIn("Keep GitLab mutations", first)
        self.assertTrue((self.home / ".local/bin/glab-api-safe").is_file())
        self.assertTrue((self.home / ".local/bin/gh-api-safe").is_file())
        self.run_overlay("dummy-nix-config-path", str(self.target))
        self.assertEqual((self.target / "opencode" / "AGENTS.md").read_text(), first)

    def test_missing_wrapper_source_fails_before_install(self):
        shutil.move(str(GLAB_WRAPPER), str(GLAB_WRAPPER) + ".bak")
        try:
            r = self.run_overlay("dummy-nix-config-path", str(self.target), expected_exit=1)
            self.assertIn("wrapper source not found", r.stderr)
            # Nothing installed, settings untouched.
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
