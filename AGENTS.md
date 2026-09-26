# Instructions for AI agents

demplan is shared research infrastructure for democratic economic planning (Rust core, Python
interface). Two manuals tell an agent how to work here; read the one that fits the task in full
before starting:

| Task | Manual |
|---|---|
| Using the library for research: running, reproducing, comparing, reporting | [.claude/skills/demplan-usage/SKILL.md](.claude/skills/demplan-usage/SKILL.md) |
| Changing the library: code, tests, CI, documentation | [.claude/skills/demplan-development/SKILL.md](.claude/skills/demplan-development/SKILL.md) |

Rules that apply to every task:

- **Do not state anything about published work you have not checked against the original.** If
  you do not have the source, ask the user for it; if it cannot be provided, leave the claim out.
  The procedure is in the development manual, section "Citation check".
- **Numbers come from runs.** Quote a round count, a timing or a test result only if you ran it,
  and say how.
- **A person stays accountable.** Contributions record the decisions behind them and a "Human in
  the loop" section; AI-generated code without that context is not accepted. See
  [CONTRIBUTING.md](CONTRIBUTING.md).
- **Run `python tools/check_repo.py` before committing.** Never skip checks with `--no-verify` and
  never force-push.
- Code, comments and error messages are in English.

Claude Code loads the two manuals as skills from `.claude/skills/` and installs the project hooks
from `.claude/settings.json`. Other agents should read the files directly.
