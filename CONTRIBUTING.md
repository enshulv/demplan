# Contributing to demplan

Thank you for considering a contribution. demplan exists so that people working on democratic
economic planning stop rewriting the same infrastructure, so contributions that save the next
researcher time are the most valuable kind.

## Ways to contribute

- **Report a problem with a result.** If a number from demplan disagrees with a paper, with
  another implementation, or with your own hand calculation, open an issue with the economy,
  the seed and the code you ran. These reports are the most useful thing an outside reader can
  send.
- **Ask for a data source or a procedure.** Say what research question it would unblock.
- **Fix documentation.** The design records under `docs/` were translated from Chinese, and
  wording errors are likely.
- **Contribute code.** Read the rest of this file first. For anything larger than a bug fix,
  open an issue to discuss the design before writing code; the data model in particular is
  shared by every mechanism and changes to it need agreement first.

## Development setup

You need Python 3.10 or newer and a Rust toolchain (<https://rustup.rs>).

```sh
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install maturin pytest hypothesis numpy scipy pyarrow psutil
maturin develop                      # debug build, for the edit-test loop
maturin develop --release            # release build, for anything you time
```

Tests that need the published dep1ex data skip themselves when it is absent. To run them,
download the archives and point `DEMPLAN_DATA_DIR` at the directory:

```sh
mkdir -p research/data
for i in 01 02 03 04 05; do
  curl -sSL -o research/data/dep1ex$i.clj.gz https://www.szcz.org/depexperiments/dep1ex$i.clj.gz
done
export DEMPLAN_DATA_DIR="$PWD/research/data"
```

Run both test suites:

```sh
pytest
cargo test --workspace
```

A skipped test is not a passing test. If you expected the data-dependent tests to run, check
that the skip count is 1, not about 40.

## Repository layout

| Path | Contents |
|---|---|
| `crates/demplan-core/` | Rust data model and loaders; no Python dependency |
| `crates/demplan-py/` | PyO3 bindings, built as `demplan._core` |
| `python/demplan/` | The Python package, the primary user interface |
| `tests/` | pytest and Hypothesis tests, plus numpy reference implementations in `tests/reference/` |
| `research/bench/` | Scripts that reproduce the upstream experiments and time them |
| `docs/` | Specification, design decisions, research notes, review evidence |

`docs/README.md` explains how the documentation is organised. The short version:
`docs/spec.md` is the current rules, `docs/decisions/` is why they are what they are, and
`docs/decisions/rejected/` is what was considered and not done.

## Conventions

- **Code, comments, error messages and test names are in English.**
- **Comments describe the code as it is now.** Why something changed belongs in the commit
  message or the decision record, not in the code.
- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `perf:`, `refactor:`, `build:`, `chore:`. Imperative
  subject line of at most 72 characters; the body says what changed and why.
- **A behaviour change comes with a test that fails without it.** Check that it fails before
  you make it pass.
- **A change that is not meant to alter results has to show that it does not.** Round counts
  and plan arrays on dep1ex01 to 05 are expected to stay bit-identical across refactors.
- **Theory stays out of the base layer.** Before adding something to `Economy`, `Plan` or the
  loop, ask which school of thought would disagree with it. If you can name one, it belongs in
  an optional tool or a prefab. See `docs/decisions/scope-and-purpose.md`.

## Decision records

A pull request that changes behaviour, adds or changes a data model field, or changes a rule in
`docs/spec.md` needs a decision record. Add it to the matching topic file in `docs/decisions/`
(newest entry at the top of its date section) and add one line to `docs/decisions/index.md`.

```markdown
## YYYY-MM-DD

### One sentence saying what was decided

**Decision**: What changes, concretely.

**Why**: The background, the constraint, the evidence. This is the most important field.

**Alternatives rejected**:
- Option X — the specific reason it lost
- Option Y — the specific reason it lost

**How to apply**: What someone facing a similar choice later should do.

**Human in the loop**:
- Decided by: your GitHub handle
- AI assistance: none, or which tool helped with which parts (code, tests, analysis, text)
- Verified by me: the tests I ran and their results, outputs I inspected, cases I checked by hand
- Not verified: anything you did not check yourself
```

A proposal that was considered and turned down goes to `docs/decisions/rejected/` with the
fields **Rejected**, **Proposal**, **Why it was considered**, **Why rejected** and
**Revival condition**. Records are never rewritten to say the opposite of what they said; a
new decision that overrides an old one says so with **Supersedes**, and the old one gets a
"Superseded" note. The existing records in `docs/decisions/` are working examples.

## AI-assisted contributions

demplan does not reject AI-assisted work. The maintainer uses AI tools, and pretending
otherwise would help nobody. What the project requires is that **a person remains accountable
for every change and shows how they exercised that responsibility.**

The reason is specific to this field. A wrong coordination procedure does not crash. It produces
a plan that looks reasonable, passes every structural check, and ends up in a paper. The
reproduction work behind this library found how easily such a difference slips through: a
published pseudocode, presented as an adaptation of a price-update rule that works, does not
converge, and the two differ by a single factor in one formula. AI tools make plausible code cheap to produce; they do not make it cheap to review. The
decision record moves the reasoning into the open, so a reviewer checks it instead of
reconstructing it.

So, for AI-assisted contributions:

1. **Fill in "Human in the loop" honestly**, in the decision record or, for changes that need
   no record, in the pull request description. "AI assistance: none" when there was some is the
   one thing that will get a contribution rejected outright.
2. **You must understand every line you submit.** "The model wrote it" is not an answer to a
   review question.
3. **Tests must be able to fail.** A generated test that passes whether or not the code is
   correct is worse than no test. Show that each key assertion fails when the behaviour it
   protects is broken; changing the implementation by hand and watching the test go red
   (mutation testing) is the expected way to show it.
4. **Numbers must be run, not described.** Round counts, timings and results quoted in a pull
   request or a document must come from a run you did, with the command.

These rules apply to the maintainer's own changes as well.

## Pull requests

- Keep one concern per pull request.
- Fill in the pull request template, including the "Human in the loop" section.
- Both test suites pass locally, and the skip count is what you expect.
- If the change alters a rule, `docs/spec.md` is updated in the same pull request.

## Code of conduct

Be civil, argue with evidence, and assume good faith. Disagreement about economic theory is
expected in this field and is welcome in issues; the library itself stays theory-neutral.
