#!/usr/bin/env python3
"""
Patch opencode/AGENTS.md with local rules additions.

This script merges the glab skill references and GitLab fence policy into
the global rules file opencode reads from ~/.config/opencode/AGENTS.md.
It is idempotent: running it multiple times produces the same result.

Usage:
    python3 patch_agents_md.py <path-to-opencode-output-dir>
"""

import os
import sys
import tempfile
from pathlib import Path


def patch_agents_md(opencode_dir: Path):
    agents_path = opencode_dir / "AGENTS.md"
    if not agents_path.exists():
        print(f"patch_agents_md: {agents_path} not found", file=sys.stderr)
        sys.exit(1)

    rules = agents_path.read_text(encoding="utf-8")

    # Check if already patched (both markers must be present)
    if (
        "For GitLab, load the `glab` skill" in rules
        and "Keep GitLab mutations on named, authorised paths." in rules
    ):
        print("patch_agents_md: AGENTS.md already contains glab references, skipping")
        return

    # Find the GitHub paragraph and append GitLab equivalents
    github_tool_line = "For GitHub, load the `gh` skill."
    github_fence_line = "Keep GitHub mutations on named, authorised paths."

    if github_tool_line not in rules or github_fence_line not in rules:
        print("patch_agents_md: expected GitHub rules paragraphs not found", file=sys.stderr)
        sys.exit(1)

    # Replace the tool line to mention both
    old_tool = (
        "For GitHub, load the `gh` skill. "
        "For reads, prefer the constrained CLI path when available: "
        "use a dedicated `gh` subcommand first, then `gh-api-safe` for raw REST or GraphQL reads."
    )
    new_tool = (
        "For GitHub, load the `gh` skill. For GitLab, load the `glab` skill. "
        "For reads, prefer the constrained CLI path when available: "
        "use a dedicated `gh` or `glab` subcommand first, then `gh-api-safe` or `glab-api-safe` for raw REST or GraphQL reads."
    )
    patched_tool = rules.replace(old_tool, new_tool)
    if patched_tool == rules:
        print(
            "patch_agents_md: GitHub tool paragraph drifted from expected wording; "
            "refusing to patch silently. Update old_tool in patch_agents_md.py.",
            file=sys.stderr,
        )
        sys.exit(1)
    rules = patched_tool

    # Find the end of the GitHub fence paragraph and insert GitLab fence after it
    github_fence_start = rules.find(github_fence_line)
    # Find the next double-newline after the GitHub fence paragraph
    next_section = rules.find("\n\n", github_fence_start + len(github_fence_line))
    if next_section == -1:
        next_section = len(rules)

    gitlab_fence = (
        "\n\n"
        "Keep GitLab mutations on named, authorised paths. Coding agents run fenced. "
        "Raw `glab api` stays denied. Fence permits the everyday mutations: "
        "`git push`, `glab mr comment`, `glab mr approve`, `glab mr create`, "
        "`glab issue create`, `glab issue update`, `glab ci retry`, and `glab mr merge`. "
        "Run them when the task calls for them. "
        "Fence-denied commands (`glab repo create`, `glab repo edit`, `glab config`, `glab auth`) "
        "are output for the operator to run unfenced."
    )

    rules = rules[:next_section] + gitlab_fence + rules[next_section:]

    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(agents_path.parent), prefix=".AGENTS-", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(rules)
        os.replace(tmp_name, agents_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    print("patch_agents_md: applied glab rules to AGENTS.md")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <opencode-output-dir>", file=sys.stderr)
        sys.exit(1)
    patch_agents_md(Path(sys.argv[1]))
