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
