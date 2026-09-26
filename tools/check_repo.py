"""Repository checks that must pass before a commit is accepted.

Runs in CI and from the Claude Code pre-commit hook in `.claude/settings.json`, and can be run by
hand: `python tools/check_repo.py`. Standard library only. Exit status 1 means at least one check
failed; every problem is printed.

Checks:
1. Relative links in tracked Markdown files point at files that exist.
2. Decision records in `docs/decisions/` keep their format: every entry has **Decision** and
   **Why**; every entry in `rejected/` opens with **Rejected**; an entry marked
   "(⚠️ Superseded, see DATE)" has a matching **Supersedes** under that date; the index links only
   to files that exist and links every decision file.
3. No data archives, build artefacts or files over 5 MB are tracked.
4. The files every contributor and agent relies on exist, and CITATION.cff has its required fields.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
MAX_TRACKED_BYTES = 5 * 1024 * 1024
FORBIDDEN_SUFFIXES = (".clj.gz", ".pyd", ".so", ".pdb", ".dll", ".dylib", ".whl")
REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CITATION.cff",
    "AGENTS.md",
    ".github/pull_request_template.md",
    ".claude/settings.json",
    ".claude/skills/demplan-usage/SKILL.md",
    ".claude/skills/demplan-development/SKILL.md",
    "docs/README.md",
    "docs/spec.md",
    "docs/glossary.md",
    "docs/progress.md",
    "docs/decisions/index.md",
)
CITATION_FIELDS = ("cff-version:", "title:", "authors:", "license:", "repository-code:")

LINK = re.compile(r"\]\(([^)\s]+)\)")
SUPERSEDED = re.compile(r"\(⚠️ Superseded, see (\d{4}-\d{2}-\d{2})\)")
DATE_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})", re.M)
FIRST_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return [ROOT / name for name in out.split("\0") if name]


def check_links(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        if path.suffix != ".md" or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = (path.parent / target.split("#", 1)[0]).resolve()
            if not target_path.exists():
                problems.append(f"{path.relative_to(ROOT)}: broken link to {target}")
    return problems


def entries(text: str) -> list[tuple[str, str]]:
    """Each `### ` entry of a decision file as (title, body up to the next heading)."""
    parts = re.split(r"^### ", text, flags=re.M)[1:]
    result = []
    for part in parts:
        title, _, body = part.partition("\n")
        body = re.split(r"^#{2,3} ", body, flags=re.M)[0]
        result.append((title.strip(), body))
    return result


def sections_by_date(text: str) -> dict[str, str]:
    spans = [(m.group(1), m.start()) for m in DATE_HEADING.finditer(text)]
    sections = {}
    for i, (date, start) in enumerate(spans):
        end = spans[i + 1][1] if i + 1 < len(spans) else len(text)
        sections[date] = sections.get(date, "") + text[start:end]
    return sections


def check_decisions() -> list[str]:
    problems = []
    if not DECISIONS.exists():
        return problems
    for path in sorted(DECISIONS.rglob("*.md")):
        if path.name == "index.md":
            continue
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        rejected = path.parent.name == "rejected"
        for title, body in entries(text):
            if rejected:
                first = FIRST_BOLD.search(body)
                if not first or not first.group(1).startswith("Rejected"):
                    problems.append(f"{rel}: rejected entry '{title}' must open with **Rejected**")
            else:
                for field in ("**Decision**", "**Why**"):
                    if field not in body:
                        problems.append(f"{rel}: entry '{title}' has no {field}")
            marker = SUPERSEDED.search(title)
            if marker:
                section = sections_by_date(text).get(marker.group(1), "")
                if "**Supersedes**" not in section:
                    problems.append(
                        f"{rel}: '{title}' is marked superseded by {marker.group(1)}, "
                        "but that date has no **Supersedes**"
                    )
    index = DECISIONS / "index.md"
    if index.exists():
        text = index.read_text(encoding="utf-8")
        linked = set()
        for match in LINK.finditer(text):
            target = match.group(1).split("#", 1)[0]
            if target.startswith(("http://", "https://")):
                continue
            target_path = (DECISIONS / target).resolve()
            linked.add(target_path)
            if not target_path.exists():
                problems.append(f"docs/decisions/index.md: links to missing {target}")
        for path in DECISIONS.rglob("*.md"):
            if path.name != "index.md" and path.resolve() not in linked:
                problems.append(f"docs/decisions/index.md: {path.relative_to(DECISIONS)} is never linked")
    return problems


def check_tracked(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith(FORBIDDEN_SUFFIXES):
            problems.append(f"{rel}: data archives and build artefacts are not committed")
        elif path.exists() and path.stat().st_size > MAX_TRACKED_BYTES:
            problems.append(f"{rel}: {path.stat().st_size / 1e6:.1f} MB is over the 5 MB limit")
    return problems


def check_required() -> list[str]:
    problems = [f"{name}: required file is missing" for name in REQUIRED_FILES if not (ROOT / name).exists()]
    citation = ROOT / "CITATION.cff"
    if citation.exists():
        text = citation.read_text(encoding="utf-8")
        problems += [f"CITATION.cff: missing {field}" for field in CITATION_FIELDS if field not in text]
    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    files = tracked_files()
    found = check_required() + check_links(files) + check_decisions() + check_tracked(files)
    problems = list(dict.fromkeys(found))
    for problem in problems:
        print(f"check_repo: {problem}", file=sys.stderr)
    if problems:
        print(f"check_repo: {len(problems)} problem(s); fix them before committing.", file=sys.stderr)
        return 1
    print("check_repo: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
