from pathlib import Path
import html
import json
import os
import re
import shutil

from json_schema_for_humans.generate import generate_from_filename
from json_schema_for_humans.generation_configuration import GenerationConfiguration
import markdown


ACTION_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = ACTION_DIR / "templates"
SOURCE_ROOT = Path("to_docs")
OUTPUT_ROOT = Path("to_docs_site")
PACKAGE_METADATA_PATH = Path("docs_metadata/packages.json")
ASSETS_DIR = OUTPUT_ROOT / "assets"


def read_title(markdown_text: str, fallback: str) -> str:
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def relative_back(path: Path) -> str:
    depth = len(path.relative_to(OUTPUT_ROOT).parts) - 1
    return "/".join([".."] * depth) or "."


def normalize_repo_path(url: str) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@github.com:"):
        return url[len("git@github.com:") :]
    for prefix in ("https://github.com/", "http://github.com/"):
        if url.startswith(prefix):
            return url[len(prefix) :]
    return None


def load_repo_revisions() -> dict[str, str]:
    repo_revisions: dict[str, str] = {}

    current_repo = os.environ.get("GITHUB_REPOSITORY")
    current_sha = os.environ.get("GITHUB_SHA")
    if current_repo and current_sha:
        repo_revisions[current_repo] = current_sha

    if PACKAGE_METADATA_PATH.is_file():
        for entry in json.loads(PACKAGE_METADATA_PATH.read_text(encoding="utf-8")):
            repo_path = normalize_repo_path(entry.get("url", ""))
            sha = entry.get("sha")
            if repo_path and sha:
                repo_revisions[repo_path] = sha

    return repo_revisions


GITHUB_LINK_PATTERN = re.compile(
    r"https://github\.com/(?P<repo>[^/\s]+/[^/\s]+)/(?P<kind>blob|tree)/(?P<ref>main|release/[^/\s]+)/(?P<path>[^\s)]+)"
)


def pin_github_links(markdown_text: str, repo_revisions: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        repo_path = match.group("repo")
        sha = repo_revisions.get(repo_path)
        if not sha:
            return match.group(0)
        return f'https://github.com/{repo_path}/{match.group("kind")}/{sha}/{match.group("path")}'

    return GITHUB_LINK_PATTERN.sub(replace, markdown_text)


def render_template(name: str, replacements: dict[str, str]) -> str:
    content = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"__{key}__", value)
    return content


def stylesheet_href(html_path: Path) -> str:
    return f"{relative_back(html_path)}/assets/docs.css"


def ensure_output_dirs() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATES_DIR / "docs.css", ASSETS_DIR / "docs.css")


def build_package_docs(package_dir: Path, repo_revisions: dict[str, str]) -> tuple[str, str] | None:
    docs_dir = package_dir / "docs"
    schemas_dir = package_dir / "schemas"
    if not docs_dir.is_dir() and not schemas_dir.is_dir():
        return None

    package_out = OUTPUT_ROOT / package_dir.name
    package_out.mkdir(parents=True, exist_ok=True)
    page_entries: list[tuple[str, str]] = []

    if docs_dir.is_dir():
        for src in sorted(docs_dir.rglob("*")):
            rel = src.relative_to(docs_dir)
            dst = package_out / rel
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel.parts and rel.parts[0] == "doxygen":
                shutil.copy2(src, dst)
                continue

            if src.suffix.lower() == ".md":
                markdown_text = src.read_text(encoding="utf-8")
                markdown_text = pin_github_links(markdown_text, repo_revisions)
                title = read_title(markdown_text, src.stem.replace("-", " ").title())
                html_body = markdown.markdown(markdown_text, extensions=["extra", "tables", "toc"])
                html_path = dst.with_suffix(".html")
                html_path.write_text(
                    render_template(
                        "docs_page.html",
                        {
                            "TITLE": html.escape(title),
                            "STYLESHEET_HREF": stylesheet_href(html_path),
                            "BACK_HREF": f"{relative_back(html_path)}/index.html",
                            "BODY": html_body,
                        },
                    ),
                    encoding="utf-8",
                )
                page_entries.append((title, html_path.relative_to(package_out).as_posix()))
            else:
                shutil.copy2(src, dst)

    doxygen_index = package_out / "doxygen" / "index.html"
    if doxygen_index.is_file():
        page_entries.append(("API", "doxygen/index.html"))

    if schemas_dir.is_dir():
        schemas_out = package_out / "schemas"
        schemas_out.mkdir(parents=True, exist_ok=True)
        generate_from_filename(
            str(schemas_dir),
            str(schemas_out),
            config=GenerationConfiguration(template_name="js"),
        )
        page_entries.append(("Schemas", "schemas/index.html"))

    package_links = "".join(
        f'    <li><a href="{href}">{html.escape(title)}</a></li>\n'
        for title, href in page_entries
    )
    package_index = package_out / "index.html"
    package_index.write_text(
        render_template(
            "package_index.html",
            {
                "TITLE": html.escape(f"{package_dir.name} docs"),
                "STYLESHEET_HREF": stylesheet_href(package_index),
                "BACK_HREF": "../index.html",
                "PACKAGE_NAME": html.escape(package_dir.name),
                "LINKS": package_links,
            },
        ),
        encoding="utf-8",
    )
    return package_dir.name, f"{package_dir.name}/index.html"


def build_bundle_index(package_entries: list[tuple[str, str]]) -> None:
    index_links = "".join(
        f'    <li><a href="{href}">{html.escape(name)}</a></li>\n'
        for name, href in package_entries
    )
    bundle_index = OUTPUT_ROOT / "index.html"
    bundle_index.write_text(
        render_template(
            "bundle_index.html",
            {
                "STYLESHEET_HREF": stylesheet_href(bundle_index),
                "LINKS": index_links,
            },
        ),
        encoding="utf-8",
    )


def main() -> None:
    ensure_output_dirs()
    repo_revisions = load_repo_revisions()
    package_entries: list[tuple[str, str]] = []

    for package_dir in sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir()):
        package_entry = build_package_docs(package_dir, repo_revisions)
        if package_entry:
            package_entries.append(package_entry)

    build_bundle_index(package_entries)


if __name__ == "__main__":
    main()
