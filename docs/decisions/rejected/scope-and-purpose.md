# Rejected: Scope and Purpose

## 2026-08-28

### Implement a market baseline in v1 as a control condition

**Rejected.**

**Proposal**: alongside democratic planning mechanisms, also implement a market-clearing mechanism as an experimental control.
`Economy` would gain corresponding fields for monetary balances and market-clearing residuals.

**Why it was considered**: reviewers ask "compared to what" of any mechanism-design work. With a market baseline in hand, the
pitch of "one economy, five procedures, three curves" would be complete.

**Why rejected**: once the project's positioning changed, this reason no longer holds. This library is shared research
infrastructure for democratic economic planning, not a mechanism-neutral comparison platform. Under this positioning, "compared to
what" is answered by the centralized-optimal reference solution — an upper bound computable on that same `Economy`, which is a
harder benchmark than a market baseline anyway.

A market baseline would also require committing to an extra set of behavioral assumptions. Those assumptions would become the
focus of debate, pulling discussion away from the mechanisms themselves.

The cost is real too: the implementation effort of an entire additional mechanism, plus a batch of `Economy` fields that no other
mechanism would use.

**Revival condition**: if reviewers explicitly require a market comparison and the reference solution is not accepted as a
benchmark. At that point it should be added as a mechanism-layer plugin (see [extension-boundary.md](../extension-boundary.md)),
with the market fields on `Economy` kept as an optional extension, outside the core invariants.

**Related**: [scope-and-purpose.md](../scope-and-purpose.md)
