#!/usr/bin/env python3
"""Behavioural tests for the gh-api-safe and glab-api-safe wrappers.

The wrappers delegate to the real CLI through the GLAB_API_SAFE_GLAB and
GH_API_SAFE_GH environment hooks. Tests stub those binaries and assert
the exit-64 policy contract.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GLAB_WRAPPER = REPO_ROOT / "local/opencode/bin/glab-api-safe.sh"
GH_WRAPPER = REPO_ROOT / "local/opencode/bin/gh-api-safe.sh"

EX_POLICY = 64


class WrapperTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wrapper-test-"))
        self.stub = self.tmp / "stub"
        self.stub.write_text(
            "#!/usr/bin/env bash\nprintf 'ARGS: %s\\n' \"$*\"\nexit 0\n"
        )
        self.stub.chmod(0o755)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp)

    def run_glab(self, *argv):
        env = dict(os.environ)
        env["GLAB_API_SAFE_GLAB"] = str(self.stub)
        return subprocess.run(
            [str(GLAB_WRAPPER), *argv],
            capture_output=True,
            text=True,
            env=env,
        )

    def run_gh(self, *argv):
        env = dict(os.environ)
        env["GH_API_SAFE_GH"] = str(self.stub)
        return subprocess.run(
            [str(GH_WRAPPER), *argv],
            capture_output=True,
            text=True,
            env=env,
        )


class TestGlabPolicyDenies(WrapperTestCase):
    def assert_denied(self, *argv, reason=""):
        r = self.run_glab(*argv)
        self.assertEqual(r.returncode, EX_POLICY, f"{argv} should exit {EX_POLICY}: {r.stderr}")
        self.assertIn("glab-api-safe:", r.stderr)
        if reason:
            self.assertIn(reason, r.stderr)

    def test_deny_lists(self):
        self.assert_denied("personal_access_tokens")
        self.assert_denied("users/5/personal_access_tokens", reason="personal access tokens")
        self.assert_denied("projects/1/secure_files/2", reason="secure files")
        self.assert_denied("users/5/impersonation_tokens", reason="impersonation tokens")
        self.assert_denied("admin/sidekiq")
        self.assert_denied("projects/1/variables")
        self.assert_denied("projects/1/secrets")
        self.assert_denied("projects/1/runners")
        self.assert_denied("projects/1/access_tokens")
        self.assert_denied("projects/1/deploy_tokens")
        self.assert_denied("user/support_pin")
        self.assert_denied("user/emails")

    def test_flag_denies(self):
        self.assert_denied("projects/1/issues", "-X", "POST")
        self.assert_denied("projects/1/issues", "-XPOST")
        self.assert_denied("projects/1/issues", "--method", "PUT")
        self.assert_denied("projects/1/issues", "--input")
        self.assert_denied("projects/1/issues", "-f", "state=closed")
        self.assert_denied("projects/1/issues", "--hostname", "gitlab.example.com")
        self.assert_denied("projects/1/issues", "--hostname=gitlab.example.com")

    def test_query_suffix_stripped(self):
        self.assert_denied("projects/1/variables?x=y", reason="CI/CD variables")
        self.assert_denied("projects/1/issues.json", reason="format suffix")

    def test_graphql_mutation_rejected(self):
        self.assert_denied("graphql", "-f", "query=mutation { updateIssue }")
        self.assert_denied("graphql", "-fquery=mutation { updateIssue }")
        self.assert_denied("graphql", "-f", "query=@payload.graphql")

    def test_glab_allow_cases(self):
        for argv in [
            ("projects/1/issues",),
            ("projects/2/merge_requests/7",),
            ("user",),
            ("graphql", "-f", "query={ currentUser { username } }"),
            ("graphql", "-fquery={ currentUser { username } }"),
            ("graphql", "-F", "query={ project(fullPath: \"x\") { id } }"),
        ]:
            r = self.run_glab(*argv)
            self.assertEqual(r.returncode, 0, f"{argv} should pass: {r.stderr}")


class TestGhPolicyDenies(WrapperTestCase):
    def test_hostname_denied(self):
        r = self.run_gh("--hostname", "evil.example.com", "repos/x")
        self.assertEqual(r.returncode, EX_POLICY)
        self.assertIn("--hostname", r.stderr)

    def test_existing_denies_hold(self):
        r = self.run_gh("user/keys")
        self.assertEqual(r.returncode, EX_POLICY)
        r = self.run_gh("repos/x/y/actions/secrets")
        self.assertEqual(r.returncode, EX_POLICY)
        r = self.run_gh("repos/x", "-X", "POST")
        self.assertEqual(r.returncode, EX_POLICY)

    def test_gh_allow_cases(self):
        for argv in [
            ("repos/wimpysworld/nix-config/issues",),
            ("search/issues?q=repo:wimpysworld/nix-config",),
            ("graphql", "-f", "query={ viewer { login } }"),
            ("rate_limit",),
        ]:
            r = self.run_gh(*argv)
            self.assertEqual(r.returncode, 0, f"{argv} should pass: {r.stderr}")


class TestWrapperHelp(WrapperTestCase):
    def test_glab_help(self):
        r = self.run_glab("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("POLICY", r.stdout)

    def test_gh_help(self):
        r = self.run_gh("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("POLICY", r.stdout)

    def test_missing_endpoint(self):
        r = self.run_glab()
        self.assertEqual(r.returncode, EX_POLICY)


if __name__ == "__main__":
    unittest.main()
