---
name: demplan-development
description: How to change the demplan library itself. Use when implementing a feature, fixing a bug, refactoring, adding a loader, prefab or tool, changing tests, CI or documentation in this repository; writing or editing a wiki page; preparing a release; before committing or opening a pull request; and whenever a document or message states something about published work, data or another implementation.
---

# Developing demplan

This is the working manual for changing the library. For using it, see `demplan-usage`. The
rules for contributors are in `CONTRIBUTING.md`; this skill adds how to work so that the result
holds up to academic scrutiny.

**Why the bar is high.** In this field a wrong result does not announce itself. A coordination
procedure with a bug converges to a plausible plan, passes every structural check, and ends up in
a paper. Most of what follows exists to catch that kind of error before it leaves the repository.

## Design constraints

These are settled; each has a decision record in `docs/decisions/`.

1. **The base layer is theory-neutral.** Before adding anything to `Economy`, `Plan` or the loop,
   ask which school of economic thought would disagree with it. If one would, it belongs in an
   optional tool or a prefab. Prices are not part of `Economy`; material balance is a difference
   that is reported, not a constraint that is enforced. `Economy` has no classes of commodity or
   groups of units: a label a loader or prefab needs goes into an `extra` bag under a key it owns,
   and the library's own tools never read an `extra` key of `Economy`. A tool that needs to know which commodities are labour, resources, shared or bads
   takes that as a declaration argument (a one-dimensional int64 array of commodity indices), and
   a prefab offers helpers that build it. Reports state numbers: N/A is `None` with a reason, and
   nothing carries a tolerance or a pass/fail field.
2. **Only two things are fixed**: the `Economy` data model and deterministic seeding.
3. **The extension point is an interface.** A procedure is any object with
   `solve(economy, seed) -> Plan`; the library does not break procedures into operators.
4. **Comparability comes from raw output**, not from shared metrics.
5. **The whole economy stays in memory**; one round never touches the disk.

If a change seems to need one of these to bend, stop and ask the maintainer. Do not decide it.

## Setup and commands

```sh
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install maturin pytest pytest-xdist hypothesis numpy scipy pyarrow psutil
maturin develop                                         # debug build
maturin develop --release                               # for anything you time
export DEMPLAN_DATA_DIR=/path/to/dep1ex/archives        # enables the data-dependent tests
pytest
cargo test -p demplan-core
python tools/check_repo.py                              # the checks CI and the commit hook run
```

Without `DEMPLAN_DATA_DIR`, about 75 tests skip. **A skip is not a pass**: with the data present
exactly one test skips (a timing test that needs `DEMPLAN_RELEASE=1` and a release build).

| Path | Contents |
|---|---|
| `crates/demplan-core/` | Rust data model, validation, dep1ex loader |
| `crates/demplan-py/` | PyO3 bindings, built as `demplan._core` |
| `python/demplan/` | the Python package |
| `tests/` | pytest and Hypothesis; `tests/reference/` holds independent numpy reference implementations |
| `research/bench/` | reproduction and timing scripts, including `golden_dep1ex.py` |
| `tools/check_repo.py` | repository checks |
| `docs/` | `spec.md` (current rules), `decisions/` (why), `research/`, `reviews/` (evidence) |

## How to make a change

### 1. Settle the design before writing code

Write down every design choice the change involves, with the options and the reason for the one
chosen. A plan that still says "decide during implementation" is not ready. Choices that are the
maintainer's or the user's to make (anything touching the constraints above, the data model, or a
theoretical commitment) are asked, not assumed. Record decisions in `docs/decisions/` (format
below).

### 2. Write the contract, then the tests, before the implementation

List the behaviour as a contract: inputs, behaviour, outputs, boundary values, failure paths, and
where each input comes from. Write the tests from that list before the implementation exists.
Cover units, multi-step flows, the Rust–Python seam, and out-of-range input.

**Never edit a test to make it agree with the implementation.** If a test turns out to be wrong,
change it deliberately, record why in the commit message, and review it again.

### 3. Implement

Follow the surrounding code. Comments describe the code as it is now; the history of a change
belongs in the commit message.

### 4. Show that the key tests can fail

A passing test proves nothing until it has been seen to fail. For every assertion that protects
something important, break the implementation in the way the assertion should catch, run the
tests, confirm they fail, and restore the code exactly. A change that survives is a gap: either
the test does not test what it claims, or coverage is missing. Fix it before merging. Tests whose
expected value was copied from the implementation's own output, and assertions that only check
that two things differ, are the usual ways a test ends up proving nothing.

### 5. Keep results fixed when they are meant to be fixed

A change that is not meant to alter results must leave them bit-identical. With the dep1ex data
available, run `python research/bench/golden_dep1ex.py before.json` before the change and
`... after.json` after it; the two files must be identical byte for byte. If results are meant to
change, say by how much and why, in the pull request and the decision record.

### 6. Independent adversarial review before the pull request

Once the change is complete, have it reviewed by someone who did not write it and has no access to
how it was reasoned out: another person, or a separate agent session given only the contract, the
diff and this skill. The reviewer:

- assumes the implementation is wrong and the tests are hollow, and looks for where;
- reviews the tests first and the code second, because code checked against untrustworthy tests
  proves nothing;
- mutation-tests the key assertions again, not only reads them;
- backs every finding with a run: the input, the command, the output;
- reports "no problems found" only together with the list of attacks tried and why each failed.

Every confirmed defect gets a regression test that fails before the fix. Then run both full test
suites yourself on the final state and record the numbers you measured, not numbers from memory.

### 7. Document and commit

- `docs/spec.md` changes in the same pull request as any rule it describes.
- A change to behaviour, a data model field or a rule in `spec.md` gets a decision record.
- `docs/progress.md` gets a line for a finished piece of work.
- Commit messages use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `perf:`,
  `refactor:`, `build:`, `chore:`), an imperative subject of at most 72 characters, and a body that
  says what changed and why.
- Never use `git commit --no-verify` or force-push; the project hooks block both.

## Decision records

Topic files in `docs/decisions/`, newest entry at the bottom of its date section, one line per
entry in `docs/decisions/index.md`:

```markdown
## YYYY-MM-DD

### One sentence saying what was decided

**Decision**: What changes, concretely.

**Why**: Background, constraint, evidence. The most important field.

**Alternatives rejected**:
- Option X — the specific reason it lost

**How to apply**: What someone facing a similar choice should do.

**Human in the loop**:
- Decided by: GitHub handle
- AI assistance: none, or which tool helped with which parts
- Verified by me: tests run and their results, outputs inspected, cases checked by hand
- Not verified: anything not checked
```

A proposal turned down goes to `docs/decisions/rejected/` with **Rejected**, **Proposal**, **Why it
was considered**, **Why rejected**, **Revival condition**. A record is never rewritten to say the
opposite: a new record supersedes it with **Supersedes**, and the old one gets
"(⚠️ Superseded, see DATE)". A factual error in an old record is corrected in place with a dated
correction note. `tools/check_repo.py` checks this format.

## Project hooks

`.claude/settings.json` installs two hooks for Claude Code sessions in this repository:

- **Before a commit**, `tools/check_repo.py` runs and blocks the commit if a check fails:
  documentation format, broken links, missing required files, committed data or build artefacts.
  `--no-verify` and force-pushing are blocked.
- **After an edit to a Markdown file or `CITATION.cff`** that adds something citation-like, the
  agent is reminded of the citation check below.

The same repository checks run in CI, together with rustfmt, Clippy and both test suites on Linux,
Windows and macOS.

## Citation check (before finishing any task)

Run this check on every document, docstring, commit message and reply you produced in the task.

**Scope.** Every citation, and every claim attributed to a source: a number from a paper, a page, a
quotation, what another implementation does, a licence, a date, a statement about the history of
the field.

**Procedure.**

0. **Check the evidence ledger first**, if the project keeps one. A claim whose meaning and source match a
   ledger entry reuses that entry's evidence; only new claims and claims whose meaning changed are
   checked against the original. Record every newly verified claim in the ledger.
1. **Ask the user for the source.** For each claim, the original document must be available: a
   paper, a book chapter, a dataset page, a repository at a stated commit. If the user has not
   provided it and you cannot open it yourself, ask the user to provide it. Do not reconstruct what
   a source says from its title, an abstract, a secondary source or memory; a citation written that
   way reads exactly like a real one.
2. **Locate the claim in the original.** Record where it is (page, table, line or commit) and a
   short verbatim quotation.
3. **Give each claim a verdict**: verified (the quotation supports it), mismatch (the source says
   something else), overstated (the source says less), or not found.
4. **Act on the verdict.** Verified claims stay. Mismatched and overstated claims are corrected to
   what the source says. Claims not found are removed unless the user supplies the source. In a
   decision record, correct the fact in place and add a dated correction note.
5. **Leave evidence.** Put the location and quotation for each citation in the pull request
   description or the decision record, so a reviewer can check it without redoing the search.

Before a release, the whole public documentation gets this check from a reviewer who did not write
it, with the same verdicts. This project's own documents have been through it; the corrections are
visible as correction notes in `docs/decisions/`.

## Wiki pages

- **Every command output on a page comes from a run**, pasted verbatim, with the command or script
  that produced it. Version numbers in outputs change with each release; rerun them rather than
  editing the numbers by hand.
- **Mechanism pages** (the Mechanisms section) state one mechanism that ships with the library:
  participants, the model each solves, the solution and its derivation, the rules between rounds,
  the stopping rule, a table from symbols to `Economy` and `Plan` fields, the parameters of a
  published data set with the script that measures them, the properties that follow from the
  functional forms, and the sources. They state; they do not argue. A sentence that rebuts a view
  ("X is not really a kind of Y") or answers a question the reader never asked assumes a
  discussion the reader has not seen: state the property directly instead. Real-world
  counterexamples and inferences the sources do not make belong elsewhere.
- **Formulas.** GitHub renders LaTeX, but Markdown processes the text first and silently changes it:
  - Display formulas go in a fenced block that starts with ```` ```math ````, not between `$$`.
    Markdown strips the backslash from `\,` `\;` `\!` `\%` between `$$`, and a bare `%` then turns
    the rest of the formula into a TeX comment.
  - Inline formulas use `` $`...`$ ``, which Markdown leaves alone. Plain `$...$` loses the same
    escapes, and a `<` inside it is escaped twice and shows as the text `&lt;`.
  - Write comparisons as `\lt` and `\gt`.
  - In a multi-line block, put the row break `\\` at the start of the next row, not at the end of
    a line: a backslash at the end of a line is read as a Markdown hard line break.
  - After publishing, compare the page's `math-renderer` elements with the source, formula by
    formula; the rendered page looks plausible even when a formula has lost a character.

## Releasing

For the maintainer. Version numbers on PyPI can never be reused, even after deletion, so every
step before the upload is there to catch a problem while it is still free to fix.

1. **Update the README before tagging.** The description on the PyPI page is the README packed into
   that release and cannot be changed afterwards.
2. **Bump the version** in `pyproject.toml`, `Cargo.toml` (then `cargo metadata` to update
   `Cargo.lock`) and `CITATION.cff` (`version`, `date-released`).
3. **Dry run.** Run `release.yml` by hand on the branch (`gh workflow run release.yml --ref v1`). It
   builds the five wheels and the sdist, checks that the sdist contains every licence file it
   declares (`tools/check_sdist.py`) and builds and imports the library from the sdist, without
   uploading. All jobs must pass.
4. **Publish a GitHub release** on `master` with tag `vX.Y.Z`. The release event runs `release.yml`,
   which uploads to PyPI through trusted publishing, and notifies Zenodo. If no run for the
   `release` event appears under Actions within a minute, run `release.yml` by hand on the tag with
   `publish` ticked; a manual run uploads only on a `v*` tag.
5. **Check PyPI**: five wheels and one sdist listed in the simple index, and `pip install demplan`
   in a fresh virtual environment imports and reports the new version. `gh run watch` can return
   before a run ends; confirm with `gh run view --json status`.
6. **DOI.** Zenodo archives the release and mints a version DOI; the concept DOI in the README and
   `CITATION.cff` resolves to the latest version by itself. Before writing a DOI anywhere, read the
   record through `https://zenodo.org/api/records/<id>` and check title, version and linked tag.
   A new DOI can take hours to resolve at doi.org after the record appears. A release stuck in
   "Received" on Zenodo's GitHub page is on Zenodo's side; its support can rerun it.

If pushes or releases stop starting workflow runs although the workflows are active, turn the
repository's Actions off and on again (`gh api -X PUT repos/enshulv/demplan/actions/permissions -F
enabled=false`, then `-F enabled=true -f allowed_actions=all`) and disable and re-enable the
workflow.

## Finishing checklist

- [ ] Design choices recorded; none decided that belonged to the maintainer or the user
- [ ] Tests written from the contract; key assertions shown to fail when the behaviour breaks
- [ ] dep1ex fingerprints unchanged, or the change in results explained
- [ ] Independent adversarial review done; every confirmed defect has a regression test
- [ ] `pytest`, `cargo test -p demplan-core` and `python tools/check_repo.py` pass, with the skip
      count you expect
- [ ] `spec.md`, decision records and `progress.md` updated
- [ ] Citation check done; the user asked for every source you did not have
- [ ] What was not verified is stated in the pull request
