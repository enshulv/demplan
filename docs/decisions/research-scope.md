# Research scope

## 2026-08-28

### Closing out the upstream-implementation research track

**Decision**: Reproduction and review of the pequod family ends here. The remaining thirty-five configurations won't be run, warm-start perturbation won't be calibrated, and the upstream authors won't be contacted. What's already been found is enough to support this library's design; the work returns to v1 from here.

**Why**: Research is a means; this project's end is the library.

What's already been gained has already paid for itself: the performance architecture's hard constraint (keeping the whole economy resident in memory) came from measurement; the two decisions in [reproducibility.md](reproducibility.md) came from that algorithm-drift case; and the reference-implementation requirement in [performance-architecture.md](performance-architecture.md) came from that transcription error. All of these are already captured in the decision log.

Continuing further would amount to "writing a paper about pequod" — that's a different project, and it would push v1's start date back indefinitely.

**Alternatives rejected**:

- **Run all forty configurations** — marginal benefit is low. The five configurations run so far gave 13, 13, 13, 14, and 14 rounds, with almost no variation between them; running the remaining thirty-five would only pin down the mean's decimal places more precisely, without changing a single design decision
- **Calibrate warm-start perturbation using GDP growth** — this could pull the warm-start round count from 4.00 closer to the reported 6.5, but the warm-start round count doesn't affect any design choice this library makes
- **Contact the authors** — two costs. First, it turns the project into a collaboration with the upstream authors, with progress paced by their schedule. Second, the current conclusions don't depend on their confirmation — that rule discrepancy was measured against data and material the authors themselves published, and can be independently verified

**Revival condition**: When v1 wants to use pequod as a validation benchmark and publish results from it. At that point, all forty configurations need to be run, and coordinating with the authors will likely be necessary.

**How to apply**: The scripts and data under `research/` stay; they aren't deleted. They're v1's ready-made validation target — once v1's `Procedure` extension is implemented, the first regression benchmark is getting it to converge in 13 to 14 rounds on the dep1ex data.

**Partially superseded**: The alternatives "run all forty configurations" and "calibrate warm-start perturbation using GDP growth"; see 2026-09-26.

## 2026-09-26

### Full reproduction against Hahnel (2021), chapter 9; the criterion is trends and mechanism insights

**Decision**: Before release, every table in chapter 9 of the book is reproduced: cold start for 40 experiments (Tables 9.1 and 9.2), Table 9.5, warm start (Table 9.4, including GDP) and increasing returns to scale (Table 9.6). All 40 data sets are downloaded (not tracked). **The criterion for the reproduction is whether the book's mechanism conclusions hold in this library, not digit-for-digit values.** Candidate conclusions: warm start roughly halves the round count; tightening the threshold from 5% to 3% takes about seven more rounds (diminishing returns); GDP growth is in the range of a little over 2%; increasing returns to scale do not break convergence. Cold start has no randomness, and an experiment-by-experiment numeric match serves only as a probe for implementation errors. Warm start runs 10 seeds per experiment and reports the distribution. The upstream timings are cited verbatim from the author's run log, without running the original.

**Why**: The maintainer's position is that a reproduction is certainly not an identical rerun; the core is that the mechanism is at work, since otherwise no model with randomness could ever be fully reproduced. The perturbation draws for each experiment in the book can no longer be recovered (the dep1ex data has no `augment` field), so warm start can only be compared by distribution. After the citation check found that the prefab's rule differs from the book, the reproduction comparison in the README no longer holds and must be redone before release. The book gives numbers for each of the 40 experiments, so an experiment-by-experiment comparison becomes meaningful, and it is cheap (about 2–3 minutes for 40 cold-start experiments). The `pequod-cljs` repository that note 7 of the book points to was only read, not run: it locates the cause of the one-round gap at the 5% threshold in the one-round lag of the price-update rule; see the second 2026-09-26 addendum in [research/reproduction.md](../research/reproduction.md).

**Supersedes**: Partially supersedes the alternatives "run all forty configurations" and "calibrate warm-start perturbation using GDP growth" of 2026-08-28, "Closing out the upstream-implementation research track." Its revival condition, "when v1 wants to use pequod as a validation benchmark and publish results from it," is now met: the README publishes a reproduction comparison. "Contact the authors" is still not done.

**How to apply**: When reproducing published results that involve randomness, compare distributions and conclusions, not digits; this library fixes its own randomness with seeds, so researchers who use it can reproduce each other digit for digit.
