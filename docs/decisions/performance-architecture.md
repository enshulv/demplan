# Performance architecture

## 2026-08-28

### The whole economy stays resident in memory; a single iteration round never touches disk

**Decision**: `Economy` is entirely resident in memory, using column-oriented f64 arrays. Disk is touched only when a run starts (read) and ends (write).

**Why**: This lesson comes from measurements of the upstream implementation, see [research/reproduction.md](../research/reproduction.md) for details.

Upstream put its data in SQLite, running an UPDATE with a correlated subquery over six million rows every iteration. In the author's run log from January to March 2026, one experiment at that scale took about 4 hours; upstream had no SQLite code at the time. The same computation done with column-oriented arrays measures 99 milliseconds per round, with the whole economy resident in memory at 54.8 MB — under 10 seconds for 100 rounds. About a 1450x difference. (Corrected 2026-09-26 after a citation check: this presented the roughly 4 hours as the SQLite implementation's running time; the source is the author's run log from January to March 2026, which predates upstream's SQLite code, first appearing on 2026-04-09, see upstream's `docs/notes.txt`.)

The reason upstream ended up on disk was a 4 GB JVM heap getting exhausted. But what exhausted it wasn't the data volume, it was the representation: nested maps with keywords carry 50 to 100x the overhead of plain arrays. This is "a memory wall caused by representation," solved by "moving the data to disk" — at the cost of being three orders of magnitude slower.

**Alternatives rejected**:

- Using a database as the computational substrate — see [rejected/performance-architecture.md](rejected/performance-architecture.md).

**How to apply**: v2 needs a memory budget. 10⁷ councils × 100 commodities × 8 bytes is 8 GB per field; adding indices, demand, and scratch arrays brings it to 30 to 40 GB. So v2 must use a sparse representation — it cannot reuse v1's dense layout.

---

### v1's performance target is multi-run throughput, not single-run speed

**Decision**: v1's performance engineering targets throughput over large numbers of small runs — zero residual state between runs, cheap setup, no per-run allocation storm, scenario-level parallelism, streaming results to disk.

**Why**: Solving a sparse (I−A)x=d once for 10³ sectors takes milliseconds, and 100 rounds of iteration still finish in under a second. v1 has no single-run performance problem.

What consumes the compute budget is the number of runs: parameter scans, Monte Carlo, sensitivity analysis. On the plots a researcher wants, every point on the x-axis is one complete run.

---

### Every optimized kernel keeps a reference implementation, with differential tests

**Decision**: For any computational kernel that's been optimized, keep a slow, obviously-correct reference implementation, and pin the two together with differential tests. The reference implementation is allowed to be a thousand times slower.

**Why**: Errors in this domain are silent. A wrongly computed number is still a plausible-looking economy — it doesn't crash, it doesn't trip an assertion, and the plot still looks fine. And the user will take the output and write a paper with it.

Upstream has one instance of this: the `solution-5` expression wrote `b3·k·log(p3)` instead of `b3·k·log(p2)`, originating from a manual transcription of a symbolic derivation result, with nothing to catch it. See [research/upstream-code-issues.md](../research/upstream-code-issues.md).

**How to apply**: Pair this with the batch of invariants in [spec.md](../spec.md) — material balance, budget identities, non-negativity, price homogeneity of degree zero. These can all be stated as a law, which is exactly the target property-based testing is built for.

---

## 2026-09-05

### The cost of divergence detection is eliminated by the prefab, not by weakening `iterate`'s check semantics

**Decision**: `HahnelSlides2020` splits consumption demand into two blocks by commodity kind, and `plan_of` hands over only the private-goods block directly. `iterate`'s check surface remains the same four arrays of the plan's physical layer, unchanged in any way.

**Why**: In the default configuration, converting the state to a `Plan` every round for the finiteness check measured 31% to 38% of a single run's time (dep1ex01: 1.32 seconds with detection, 1.00 seconds without). The cost isn't in the check itself — it's in `plan_of`'s fancy indexing on the consumption matrix: an integer index array necessarily copies, and on dep1ex that's 24 MB per round. After splitting the computation into two blocks, `plan_of` no longer indexes, and the overhead drops to 8% to 14% — what's left is the finiteness scan itself.

This copy also happens on runs where detection is off, so fixing it saves everyone regardless of configuration. The cost is that splitting into two matrices and doing two `bincount` calls has its own overhead: without detection, the new code is about 5% slower; with detection (the default), it's about 13% faster.

**Alternatives rejected**:

- Leave it as is — everyone using this prefab pays 31% to 38%, most of it an unnecessary copy.
- Add a lightweight hook to `iterate` that only checks the production side — "the plan's physical layer" would then have two meanings, and a researcher's own `plan_of` would also need to know this distinction. And "the consumption side won't diverge first" is an empirical claim generalized from one mechanism; writing it into `iterate` would make the base layer promise it on behalf of every mechanism, violating the hard constraint of theory-neutrality — see [invariants-and-metrics.md](invariants-and-metrics.md).

**How to apply**: `iterate`'s check surface is the library's promise to every mechanism, and it doesn't get cut just because one prefab finds it expensive. If a prefab's way of expressing the check is expensive, fix the prefab.
