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
    <link rel="stylesheet" href="docs.css">
  </head>
  <body>
    <main class="docs-page">
      <header class="docs-header">
        <a class="docs-back-link" href="main/">Open Main Docs</a>
        <h1>Documentation Versions</h1>
        <p>Select a published documentation version.</p>
      </header>
      <section class="docs-content">
        <ul>
          {body}
        </ul>
      </section>
    </main>
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
    css_path = Path(__file__).resolve().parent / "templates" / "docs.css"
    if css_path.exists():
        (root / "docs.css").write_text(css_path.read_text(encoding="utf-8"), encoding="utf-8")
    build_index(root, current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
