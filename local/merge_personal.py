#!/usr/bin/env python3
"""
Merge local/personal.json into opencode/opencode.json.

The git-ignored personal file lets a user layer machine-specific settings
(such as a private MCP server) on top of the extracted output without
touching tracked files. Merge is deep: nested objects combine, and the
personal file wins on scalar/list conflicts. It is idempotent: running it
multiple times produces the same result. Keys starting with ``$`` (such as
``$comment``) are documentation and are never written to opencode.json.

Usage:
    python3 merge_personal.py <path-to-opencode-output-dir> [<personal-json>]
"""

import json
import os
import sys
import tempfile
from pathlib import Path


def deep_merge(base, override):
    """Deep-merge override into base; override wins on conflicts."""
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _strip_meta_keys(personal):
    """Drop non-schema keys (``$comment`` and other ``$``-prefixed keys).

    These document the personal file but must never reach the merged
    opencode.json, which is validated strictly against the opencode schema.
    """
    return {
        key: value
        for key, value in personal.items()
        if not key.startswith("$")
    }


def _atomic_write_text(path, text):
    """Write text to path atomically so a torn write cannot corrupt config."""
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".opencode-", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def merge_personal(opencode_dir: Path, personal_path: Path):
    settings_path = opencode_dir / "opencode.json"
    if not settings_path.exists():
        print(f"merge_personal: {settings_path} not found", file=sys.stderr)
        sys.exit(1)
    if not personal_path.exists():
        print(f"merge_personal: {personal_path} not found, skipping", file=sys.stderr)
        return

    with open(settings_path) as f:
        settings = json.load(f)
    with open(personal_path) as f:
        personal = json.load(f)

    merged = _strip_meta_keys(deep_merge(settings, personal))
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    _atomic_write_text(settings_path, text)

    print(f"merge_personal: merged {personal_path} into {settings_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <opencode-output-dir> [<personal-json>]", file=sys.stderr)
        sys.exit(1)
    opencode_dir = Path(sys.argv[1])
    personal = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path(__file__).resolve().parent / "personal.json"
    )
    merge_personal(opencode_dir, personal)
