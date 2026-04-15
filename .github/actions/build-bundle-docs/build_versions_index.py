#!/usr/bin/env python3

from __future__ import annotations

import html
import os
import sys
from pathlib import Path


def version_sort_key(name: str) -> tuple[int, list[object]]:
    if name == "main":
        return (0, [])
    if name.startswith("release-"):
        parts = []
        for item in name.removeprefix("release-").split("."):
            parts.append(int(item) if item.isdigit() else item)
        return (1, parts)
    return (2, [name])


def display_name(name: str) -> str:
    if name == "main":
        return "main"
    if name.startswith("release-"):
        return f"release/{name.removeprefix('release-')}"
    return name


def build_index(root: Path, current: str | None) -> None:
    versions = sorted(
        [p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")],
        key=version_sort_key,
        reverse=True,
    )

    lines = []
    for version in versions:
        label = display_name(version)
        suffix = " (latest update)" if current and version == current else ""
        lines.append(
            f'<li><a href="{html.escape(version)}/">{html.escape(label)}</a>{html.escape(suffix)}</li>'
        )

    body = "\n".join(lines) if lines else "<li>No published versions yet.</li>"
    page = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Documentation Versions</title>
    <style>
      body {{
        font-family: sans-serif;
        margin: 2rem auto;
        max-width: 48rem;
        padding: 0 1rem;
        line-height: 1.5;
      }}
      h1 {{
        margin-bottom: 0.5rem;
      }}
      ul {{
        padding-left: 1.25rem;
      }}
      li {{
        margin: 0.4rem 0;
      }}
    </style>
  </head>
  <body>
    <h1>Documentation Versions</h1>
    <p>Select a published documentation version.</p>
    <ul>
      {body}
    </ul>
  </body>
</html>
"""
    (root / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: build_versions_index.py <pages-root> [current-version]", file=sys.stderr)
        return 1
    root = Path(sys.argv[1]).resolve()
    current = sys.argv[2] if len(sys.argv) > 2 else None
    os.makedirs(root, exist_ok=True)
    build_index(root, current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
