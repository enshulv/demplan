"""Claude Code PostToolUse hook for Edit, Write and MultiEdit: remind the agent of the citation rule.

When an edit to a Markdown file or CITATION.cff adds text that looks like a citation, or like a
claim attributed to a source, the agent is told to check it against the original before keeping
it. The hook cannot tell whether a source was checked; it makes sure the question is asked every
time. Exit status 2 shows the message to the agent. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys

CITATION_LIKE = [
    (r"\bet al\.", "et al."),
    (r"doi\.org/|\bdoi:\s*10\.", "a DOI"),
    (r"\barXiv:\s*\d{4}\.\d{4,5}", "an arXiv identifier"),
    (r"\b[A-Z][a-z]+(?:,? (?:and|&) [A-Z][a-z]+)? \((?:19|20)\d{2}[a-z]?(?:, p{1,2}\. ?\d+)?\)", "an author-year reference"),
    (r"\[\d{1,3}(?:, ?\d{1,3})*(?:, ?p{1,2}\. ?\d+(?:[-–]\d+)?)?\]", "a numbered reference"),
    (r"\bpp?\. ?\d+(?:[-–]\d+)?\b", "a page reference"),
]


def added_text(tool_input: dict) -> str:
    parts = [tool_input.get("content") or "", tool_input.get("new_string") or ""]
    for edit in tool_input.get("edits") or []:
        parts.append(edit.get("new_string") or "")
    return "\n".join(parts)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    tool_input = payload.get("tool_input") or {}
    path = (tool_input.get("file_path") or "").replace("\\", "/")
    if not (path.endswith(".md") or path.endswith("CITATION.cff")):
        return
    text = added_text(tool_input)
    found = [label for pattern, label in CITATION_LIKE if re.search(pattern, text)]
    if not found:
        return
    print(
        f"demplan citation rule: this edit to {path} adds {', '.join(found)}.\n"
        "Every citation, and every claim attributed to a source (a page, a number, a quotation, a "
        "licence), must be checked against the original before it stays:\n"
        "1. Find the original and note where the claim is (page or line) with a short quotation.\n"
        "2. If you do not have the original, ask the user to provide it. Do not reconstruct it from "
        "the title, an abstract, a secondary source or memory.\n"
        "3. If the user cannot provide it, remove the citation or the claim.\n"
        "See .claude/skills/demplan-development/SKILL.md, section 'Citation check'.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
