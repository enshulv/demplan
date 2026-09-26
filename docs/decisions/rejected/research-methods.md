# Rejected: Research Methods

## 2026-08-28

### Install the JVM and Leiningen to run upstream's original code for cross-validation (⚠️ Partially revived, see research-scope.md 2026-09-26)

**Rejected.**

**Proposal**: install a JDK and Leiningen locally so that `pequod-cljs` can run upstream's already-published `dep1ex` data and
produce its own round count, to locate the source of the gap between "our reimplementation takes 155 rounds" and "the paper
reports 6.5 rounds."

**Why it was considered**: this is the only path that directly compares against upstream's own code behavior. Since the gap
cannot come from floating-point differences (both are IEEE 754 double precision, and `Math/pow` differs from libm at the 1-ulp
scale), it must be a semantic or parameter difference, and running the original code would pin down exactly which one.

**Why rejected**: that gap has already been explained by a much cheaper experiment. A cold-start-versus-warm-start comparison
(two minutes of compute time, no Java required) shows warm start at 7 to 8 rounds and cold start at 54 to 155 rounds, and
upstream's own recorded numbers fall in the same distribution. "6.5 rounds" is a warm-start number, not evidence of a semantic bug.

The only remaining question is "was the original's cold start also single-digit," and two independent implementations both answer
no (the author's own newer code takes 41 to 96 rounds, ours takes 54 to 155). The burden of proof has already shifted, and writing
to the author is faster than fighting the toolchain.

**Revival condition**: if a bit-for-bit comparison against upstream's intermediate results becomes necessary, or if the author's
reply indicates the original's cold start really is single-digit and the source of the difference needs to be located.

**Related**: [research/reproduction.md](../../research/reproduction.md)
