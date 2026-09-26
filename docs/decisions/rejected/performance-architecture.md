# Rejected: Performance Architecture

## 2026-08-28

### Use a database as the computation substrate

**Rejected.**

**Proposal**: store the economy in SQLite or a similar database, use SQL for demand computation and supply-demand aggregation,
and update the iteration state in place inside the database.

**Why it was considered**: this is the path two independent upstream implementations both took — `pe_ifb_compute` in 2023 and
`pequod-plus` in 2026 — so it has real appeal: when data does not fit in memory, a database is the obvious answer, and aggregation
queries are genuinely simpler to write in SQL.

**Why rejected**: measured cost is about 1450x — a single experiment at the same scale took 4 hours instead of under 10 seconds.
The bottleneck is the round-trip and serialization of 6 million rows per round to disk, not floating-point work.

And the premise that drove upstream to this choice was itself false: measurement shows that dataset is only 54.8 MB resident in
memory. What was blowing past a 4 GB heap was the representational overhead of a boxed map, not the amount of data. **When you hit
a memory wall, measure the real size of the data first, before deciding whether to spill to disk.**

**Revival condition**: if a single run's economy genuinely does not fit in memory (v2's dense council layout at 10⁷ scale is
roughly 30 to 40 GB, close to this line). At that point the right fix is a sparse representation or chunked streaming, still not
putting the iteration state into a database.

**Related**: [research/reproduction.md](../../research/reproduction.md)
