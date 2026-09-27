# Quality assurance

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
