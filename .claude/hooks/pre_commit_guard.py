"""Claude Code PreToolUse hook for Bash: hard checks before commits and pushes.

- `git commit` runs tools/check_repo.py first and is blocked if any check fails.
- `git commit --no-verify` is blocked: the checks exist so that nobody skips them.
- `git push --force` (or `-f`, `--force-with-lease`) is blocked: history on the shared branches
  is not rewritten by an agent.

Exit status 2 blocks the tool call and shows the message to the agent. Standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    command = (payload.get("tool_input") or {}).get("command") or ""
    segments = re.split(r"&&|\|\||;|\|", command)
    commits = [seg for seg in segments if re.search(r"\bgit\b.*\bcommit\b", seg)]
    pushes = [seg for seg in segments if re.search(r"\bgit\b.*\bpush\b", seg)]

    if any(re.search(r"\s(--force|--force-with-lease|-f)\b", seg) for seg in pushes):
        block("demplan: force-pushing is not allowed for agents. Ask the maintainer instead.")
    if not commits:
        return
    if any(re.search(r"\s(--no-verify|-n)\b", seg) for seg in commits):
        block("demplan: `git commit --no-verify` skips the repository checks and is not allowed.")

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_repo.py")],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        block(
            "demplan: the commit is blocked because tools/check_repo.py failed.\n"
            f"{result.stderr.strip()}\n"
            "Fix these problems, then commit again. Do not work around the check."
        )


if __name__ == "__main__":
    main()
