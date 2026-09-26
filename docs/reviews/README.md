# Reviews

The three earlier axes — current state, history, status — are accurate at the moment they're written. Over time they drift: entry-point files stay pinned to an old architecture, a decision gets made but never lands in practice, an index points at a file that has since moved. Recording triggers tied to task completion can't catch this — those triggers fire on "something changed," and drift happens exactly where nobody looks back.

This document records only where this project stands and what its status is; the review method and checklist are maintained separately.

## Two tracks

| Track | Cadence | Scope |
|---|---|---|
| Context review | Weekly | Whether entry-point files are accurate, whether decisions have landed in practice, whether the index has orphaned links |
| Architecture review | Monthly | Whether the architecture has drifted, whether the test suite is hollow |

Evidence behind each score lives in [evidence/](evidence/).

## Four rules

- A fixed ten-point scale, the same one every time. Changing the scale invalidates the entire time series
- Every score is tied to a number measured this round. When no number is available, it's marked "not measured" — never an impression-based score
- Measurement commands are turned into runnable scripts, not left in a chat transcript
- The clock advances only when a review actually runs to completion

A review only evaluates; it doesn't fix. The context track is the exception — it fixes problems it finds on the spot. Findings are numbered and traceable, with status updated item by item at the next review; anything decided against doing is recorded under rejected proposals, never silently dropped.

## Status of this project

Architecture track: v1 has had runnable code since 2026-09-05, so the first architecture review can be scheduled. A usability evaluation has been done once, see [evidence/usability-2026-09-05.md](evidence/usability-2026-09-05.md).

Context track: ready to start. The current documentation skeleton was built 2026-08-28; the next review checks whether decisions still match reality.
