# Contributing and AI

## 2026-09-26

### AI assistance is accepted, but a person is accountable for every change and shows the decision process

**Decision**: The library does not reject AI-assisted contributions; the maintainer uses AI
tools too. What it requires is that one person is accountable for every change and shows how
they exercised that responsibility.

- A pull request that changes behaviour, changes a data model field or changes a rule in
  `docs/spec.md` must include a decision record in the same format as the records in
  `docs/decisions/` (Decision, Why, Alternatives rejected, How to apply), plus a "Human in the
  loop" section: who decided, which parts had AI help and from what, what the contributor
  verified, and what they did not verify
- A small change that needs no decision record fills in the same "Human in the loop" section in
  the pull request description
- Contributors must understand every line they submit. "The model wrote it" is not an answer to a
  review question
- Tests must be able to fail: each key assertion is shown to turn red when the behaviour it
  protects is broken, with mutation testing as the expected method
- Numbers must be run, with the command
- Concealing AI use in the "AI assistance" field is the one thing that gets a contribution
  rejected outright
- These rules apply to the maintainer's own changes as well

The rules are in `CONTRIBUTING.md`, the pull request template and the wiki's contributor guide.

**Why**: The reason is a failure mode specific to this field. A wrong coordination procedure does
not crash. It converges to a plan that looks reasonable, passes every structural check and ends
up in a paper. The library's own reproduction work ran into this: a published price-update rule
that does not converge. Page 7 of the 2023 paper gives the formula used in the experiments,
`w = v(1.05 − 0.5ᵛ)`, noting that `v` is taken as 0.25 when `v > 0.25`; page 10 gives pseudocode
it calls an adaptation, which multiplies by the previous round's delta. The published round
counts can only be reproduced with the former; current upstream code implements the latter.
(Corrected 2026-09-26 after a citation check: this said "two careful prose descriptions could not
distinguish [it] from the one that does"; the source says the 2023 paper writes out both versions
and marks the page-10 one as an adaptation, see Szczepanczyk (2023), pages 7 and 10.)
(Corrected 2026-09-27: "a published price-update rule that does not converge" and "the published
round counts can only be reproduced with the former; current upstream code implements the latter"
have both been overturned. The page-10 pseudocode says to multiply by the corresponding quantity of
the previous round without saying what that quantity is; this library read it as the previous
round's step, and "does not converge" came from that misreading. The original program that produced
the published results (`csvgen.clj` of `pequod-cljs` at `71e44d3`) multiplies by the previous
round's imbalance capped at 0.25; read that way, the pseudocode agrees with the program, and with
that rule dep1ex01 through 05 give 12, 12, 12, 12 and 12 rounds at the 5% threshold from a cold
start, the same as Table 9.1 of the book experiment by experiment. Neither reading of the cap in the
page-7 formula reproduces them (14, 13, 13, 14, 13 and 11, 11, 10, 11, 11). Current upstream
`pequod-plus` multiplies by an imbalance aggregated per category, which differs from the original
program as well. The failure mode this paragraph describes still holds; a more accurate example is
that the rule behind the published results differs from the rule printed on page 181 of the book in
two details (the multiplier is the previous round's imbalance, and the step has a floor of 0.001),
and that this library itself once misread the pseudocode as a rule that does not converge. See
[research/reproduction.md](../research/reproduction.md), second addendum of 2026-09-26, and the
correction box at the top of
[research/upstream-code-issues.md](../research/upstream-code-issues.md).)

AI makes plausible code cheap to write; it does not make review cheap. A decision record puts the
reasoning in the open, so a reviewer checks it instead of reconstructing it. This format was
chosen because every decision in this repository is already recorded that way, so contributors
can follow the existing records in `docs/decisions/`.

**Alternatives rejected**:
- Forbid AI-assisted contributions — unenforceable and not honest (the maintainer uses AI), and it
  would only encourage concealment
- Require nothing — in this field, plausible code that nobody checked is exactly the most
  dangerous kind

**How to apply**: When reviewing a pull request, read the "Human in the loop" section first:
whether "Verified by me" lists commands that were run and their results, and whether "Not
verified" is honest. A bare "tested" does not count.

---

### Two manuals for agents, project hooks, repository checks and CI

**Decision**: The public repository prepares four things for AI agents.

- **Two manuals**, written as Claude Code skills and readable by any agent:
  `.claude/skills/demplan-usage/` (using the library: reproducing, changing a rule, writing a new
  mechanism, comparing with the reference solution, reproducibility, reporting) and
  `.claude/skills/demplan-development/` (changing it: design constraints, commands, workflow,
  decision records, hooks, the citation check, a finishing checklist). `AGENTS.md` at the root
  lists the rules for every task and points to both manuals.
- **The development workflow** is taken from the maintainer's own way of working, keeping only
  what can be public: settle the design first; write the contract and the tests first; never edit
  a test to fit the implementation; show that key assertions can fail (mutation testing); keep
  results bit-identical when they are meant to be; before merging, an adversarial review by someone
  who did not write the code or by an agent without its context; a regression test that fails
  before the fix for every defect; numbers come from runs.
- **Project hooks** (`.claude/settings.json`): before a commit, `tools/check_repo.py` runs and
  blocks the commit on failure; `--no-verify` and force-pushing are blocked. When an edit adds
  citation-like text to a Markdown file or `CITATION.cff`, the agent is told to check it against
  the original, to ask the user for the source if it does not have it, and to remove it if the
  source cannot be provided.
- **Repository checks**, `tools/check_repo.py` (standard library only): relative links in
  Markdown; decision record format (Decision and Why, Rejected first, Superseded paired with
  Supersedes, index and files matching); required files present and `CITATION.cff` complete; no
  committed data archives or build artefacts. CI runs it with rustfmt and Clippy first, then both
  test suites on three operating systems.
- The fingerprint script `research/bench/golden_dep1ex.py` joins the repository so contributors
  can compare results across a refactor themselves.

The AI policy is also stated more firmly: AI-generated code submitted without its decision context
is not accepted. This is in `CONTRIBUTING.md`, the README, and a new wiki page, "AI Development
Guide".

**Why**: The maintainer expects many researchers to use and change the library with AI help. An
agent does not have the maintainer's context; writing a citation from its title, editing a test to
fit the implementation and skipping checks are the mistakes it makes most easily and that are
hardest to see in the result. The manuals state what matters; the hooks and checks turn what can
be judged mechanically into hard stops, and make sure the part that cannot (whether a citation is
true) is at least asked every time.

The citation check closes the development manual because the check before this release found 44
claims that did not match their sources, including claims about this library's own reproduction.

**Alternatives rejected**:
- Only `CONTRIBUTING.md`, no manuals for agents — agents need operational guidance (commands, API,
  pitfalls); `CONTRIBUTING.md` states the rules
- Publish the maintainer's private workflow as it is — it is full of private terms and tools that
  only exist in the maintainer's environment, and outside readers could not use it
- A git pre-commit hook instead of a Claude Code hook — git hooks are not distributed with a clone;
  CI runs the same script as the backstop

**How to apply**: When the development workflow changes, change the development manual with it;
when a file becomes required, add it to the list in `check_repo.py`. After changing a hook script,
test it with sample input for both the allowed and the blocked case.
