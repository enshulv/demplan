# Quality assurance

## 2026-09-29

### A claim about a problem in an existing implementation comes with a check that runs, with the evidence taken first from that implementation's own artefacts

**Decision**: Every entry of the wiki page "Limitations of Existing Implementations" has a check
script in `research/upstream/`, and the page states for each entry how to rerun it and what it
prints. The rules:

- Whatever can be shown from upstream's own artefacts (the output files they committed, their program, their functions) is not shown with demplan; demplan appears only in conclusions that are about demplan, such as "demplan agrees with their output"
- Every check runs one control that should agree and one that should not, and prints the numbers of both sides with their sources, not only a verdict
- Upstream files are pinned by commit and checked by sha256 after download; Docker base images are pinned by digest; upstream programs are built with their own `project.clj`
- No upstream code enters this repository: a changed rule or term is an edit stated as line number, sha256 of the line before the edit, and replacement, checked and applied at run time, with the actual diff printed in the output
- The tests of the check scripts live in `tests/upstream/`, run offline without Docker, and run in CI on all three platforms

**Why**: The maintainer's standard is that the upstream authors themselves, running the scripts,
would agree that the problem is there. Entries 4 to 6 had been reached by reading code only, and
the comparison scripts behind entries 1 to 3 were in an untracked directory that no one else could
run. A conclusion from reading code had already been wrong once: "the paper's pseudocode on p. 10
does not reach the published results" was a misreading, corrected on 2026-09-27. Redone under
these rules, entries 1 to 6 all ran on upstream's artefacts; one sentence about the effect in
entry 5 was corrected as a result, and a new problem turned up (the sign of the effort in
`solution-8`/`solution-10`, see [research/upstream-code-issues.md](../research/upstream-code-issues.md),
"Checks that run").

**Alternatives rejected**:
- Give only line numbers and commits and let readers read the code — the library has itself been wrong from reading code, and line numbers do not show what happens at run time
- Show upstream's problems by reproducing them in demplan — the authors could fairly answer that demplan differs; demplan serves only as corroboration
- Commit the rule changes as unified-diff patches — the context and removed lines of a diff are upstream code verbatim, against [license.md](license.md) 2026-09-05 "for reading only, never for copying"; `pequod-cljs` has no licence and `pequod-plus` is GPL-3.0
- Run `pequod-cljs` to convergence in Docker — about 20 minutes or more per experiment; showing that the program runs this rule needs only the first rounds byte for byte, plus the steps recomputed from the committed output

**How to apply**: To add an entry to that page, write the check first, run it, then write the
entry, pasting its numbers from the script's output. When upstream gains new commits, rerun
`docker/pequod-plus/run_all.py` to see whether the problems are still there.

**Human in the loop**:
- Decided by: enshulv (the standard, and running their programs in Docker as an order-of-magnitude probe)
- AI assistance: Claude Code wrote the scripts, ran the checks and wrote the documents
- Verified by me: not checked item by item (the maintainer was away; an independent review without context attacked it instead, see the progress record)
- Not verified: the per-round time of `pequod-plus` on full-size data; year two of `pequod-cljs`

### Every upstream check has a step-by-step wiki guide, indexed at the top of the limitations page

**Decision**: The wiki page "Limitations of Existing Implementations" opens with an index table
(guide, entries covered, what it needs, how long it runs), and has seven child pages
`Reproducing-Limitations-*`: one Setup page (installing git, cloning, a virtual environment,
`pip install demplan`, downloading the data, installing Docker), then one page per check
script. Every page has the same structure:

- what the script does and which upstream artefact it uses
- the command to type, how long it takes, and what it downloads the first time
- how to read the output part by part, pointing out which lines are the control that should agree and which the control that should not
- "what would show the entry wrong", asking the reader to open an issue with the output
- common errors and what to do about them

Every output on these pages comes from a run, pasted verbatim and compared line by line with the
actual output. No upstream code is shown: the source lines, line listings and edit diffs the
scripts print are referred to by line number, with a link to GitHub.
`research/upstream/README.md` stays the quick reference for options and run times, and points
to the guides.

**Why**: The maintainer's words: without guides, a pile of Python scripts is something nobody
will use. The previous decision made every claim rerunnable, but there were only the scripts
and a reference README, which assume a reader who uses the command line and can read several
hundred lines of output. This library's readers are social scientists; a check has to be run by
someone before "the authors themselves would agree" can mean anything. Running the scripts to
write the guides also turned up a problem a reader can hit: with Windows line endings in the
working tree, the pequod-cljs container fails after 13 seconds (`set: pipefail: invalid option
name`). It is covered in the troubleshooting section.

**Alternatives rejected**:
- Expand `research/upstream/README.md` instead — it is a quick reference for those who already know how; a part-by-part walkthrough would bury the table of options, and readers arrive from the wiki's limitations page, not from the repository's directory tree
- One page per entry — nine entries share six scripts (`check_outputs.py` covers entries 1 and 2, `run_all.py` covers 4 to 7), so pages per entry would repeat the same setup and run instructions several times; the pages are per script, and the index table looks them up by entry
- Put the guides in the public repository's `docs/` — readers read the limitations page on the wiki, and the guides belong next to it; `docs/` holds design documents

**How to apply**: When a check script's output format changes, rerun the corresponding guide
and replace the pasted output verbatim; extracting every `text` block of the page and looking
for each line in the new output finds what has to change. When an entry is added to the
limitations page, add a section to the corresponding guide, or a new page with a row in the
index table and the sidebar.

**Human in the loop**:
- Decided by: enshulv (that there be guides, as child pages of the limitations page, with an index at its top)
- AI assistance: Claude Code wrote the guides, ran the seven scripts and checked the pasted outputs
- Verified by me: not checked page by page
- Not verified: the Setup page followed from scratch on macOS and Linux; the time to build the Docker images from scratch (10 to 15 minutes is estimated from the log of an earlier build)

## 2026-09-26

### Publish the quality assurance practices, and commit to formal proof where it is needed

**Decision**: How the library makes its results trustworthy is published as the wiki's "Quality
Assurance" page:

- Design decisions are settled and recorded first; a specification leaves nothing to "decide
  during implementation"
- Tests are laid down from the behavioural contract first, and are never edited to fit the
  implementation
- Key assertions are mutation-tested to show they can fail; a surviving mutant blocks the merge;
  mutation tables and results are archived as evidence
- Before merging, an independent adversarial review: the reviewer has no access to the
  implementation's reasoning, assumes the implementation is wrong and the tests hollow, and
  reviews the tests before the code; a report of "no problems found" must list every attack tried
  and why each failed
- Every confirmed defect gets a regression test that fails before the fix
- Results are anchored by: round counts from this library's own reproduction as regression
  targets, independent numpy reference implementations, bit-level fingerprints, Hypothesis
  property tests, byte-exact determinism checks, and README examples executed by the test suite.
  (Corrected 2026-09-26 after a citation check: this said "published round counts as regression
  targets"; the prefab follows the published procedure and gives 14, 13, 13, 14 and 13 rounds on
  dep1ex01 through 05, which are this library's reproduction results, while the only published
  figures are means over 40 experiments; see page 7 of the 2020 slides and
  [research/reproduction.md](../research/reproduction.md).)
  (Corrected 2026-09-27: two points of the correction above no longer hold. First, "the only
  published figures are means over 40 experiments" is wrong: chapter 9 of Hahnel (2021) lists all
  40 experiments individually in Tables 9.1, 9.2, 9.4, 9.5 and 9.6, pages 178–185. Second, the
  regression targets have changed: the current prefab, `HahnelBook2021`, uses the one-round-lag rule
  of the original program that produced the book's tables, and gives 12, 12, 12, 12 and 12 rounds
  at the 5% threshold on dep1ex01 through 05, the same as Table 9.1 and the original's output
  experiment by experiment, and 19, 20, 19, 19 and 19 at 3%, the original's output. The 14, 13, 13,
  14 and 13 came from the earlier prefab, which capped v in both places. Sources: Table 9.1 on page
  178 of the book; `ROUNDS_AT_5_PERCENT` and `ROUNDS_AT_3_PERCENT` in
  `tests/test_hahnel_book_2021.py`.)
- On the design side: theory-neutrality reviews, limitations stated prominently, periodic reviews
  (not yet run for the first time)
- Much of the implementation and review work is done with AI under the maintainer's direction:
  the maintainer sets the specification and makes the decisions; implementation and independent
  review run separately and do not share their reasoning; and the maintainer checks the results
  before merging, including by replaying the reported mutants
- Critical review in the academic sense is welcome; problems should be reported as issues as soon
  as they are found, and are fixed with priority

Mathematical properties (two closed forms are equivalent, an update rule preserves an invariant, a
procedure converges under stated conditions) can be refuted by tests but not established by
them. Where a result of the library depends on such a property and testing is not enough, the
maintainer will prove it formally, using Lean where the effort is justified. There are no Lean
proofs in the repository yet; they will be listed on the wiki page as they are added.

**Why**: This is an academic library, and in this field a wrong result does not reveal itself.
Publishing the quality assurance practices lets readers judge how far the results can be
trusted, and lets them look for errors by the same standard.

The page states only what is actually done, and says plainly what is not: the periodic reviews
have not run yet and there are no Lean proofs yet. Neither is described as already under way.

**How to apply**: The numbers the wiki page quotes (one review round found nine blocking defects;
the implementation's own 72 mutants, 71 killed; 17 of the reviewer's 61 mutants survived) come
from `docs/reviews/evidence/` and the progress record; check the original records when changing
them. Add a line to the wiki page when a formal proof is added.
