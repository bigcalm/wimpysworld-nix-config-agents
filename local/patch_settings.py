#!/usr/bin/env python3
"""
Patch opencode/settings.json with local rules additions.

This script merges the glab skill references and GitLab fence policy into
the rules field of the extracted settings.json. It is idempotent: running
it multiple times produces the same result.

Usage:
    python3 patch_settings.py <path-to-opencode-output-dir>
"""

import json
import sys
from pathlib import Path


def patch_settings(opencode_dir: Path):
    settings_path = opencode_dir / "settings.json"
    if not settings_path.exists():
        print(f"patch_settings: {settings_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(settings_path) as f:
        settings = json.load(f)

    rules = settings.get("rules", "")

    # Check if already patched (both markers must be present)
    if (
        "For GitLab, load the `glab` skill" in rules
        and "Keep GitLab mutations on named, authorised paths." in rules
    ):
        print("patch_settings: rules already contain glab references, skipping")
        return

    # Find the GitHub paragraph and append GitLab equivalents
    github_tool_line = "For GitHub, load the `gh` skill."
    github_fence_line = "Keep GitHub mutations on named, authorised paths."

    if github_tool_line not in rules or github_fence_line not in rules:
        print("patch_settings: expected GitHub rules paragraphs not found", file=sys.stderr)
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
            "patch_settings: GitHub tool paragraph drifted from expected wording; "
            "refusing to patch silently. Update old_tool in patch_settings.py.",
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

    settings["rules"] = rules

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("patch_settings: applied glab rules to settings.json")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <opencode-output-dir>", file=sys.stderr)
        sys.exit(1)
    patch_settings(Path(sys.argv[1]))
