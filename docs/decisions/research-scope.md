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
