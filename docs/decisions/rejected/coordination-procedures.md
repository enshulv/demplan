# Rejected: Coordination Procedures

## 2026-08-28

### v1 assembles coordination procedures from a preset operator set

**Rejected** (deferred, not permanently excluded. See the revival condition at the end.)

**Proposal**: the library provides a set of operators (`excess_ratio`, `clamp`, `power_adjust`, `scale_prices`, and so on),
and the researcher composes them into a tree in Python. Calling an operator does not execute the computation, only describes it;
the whole tree is handed to Rust once at run start and interpreted there. This is the pattern behind polars' lazy expressions and
Keras' layer stacking, and it is also this project's original "polars mode" concept.

**Why it was considered**: three benefits. First, no cross-language call per round. Second, the assembled object is data, so a
content hash is naturally reliable. Third, the method is inspectable — a tree can be printed, diffed, and normalized; an arbitrary
Python script cannot. This third point serves directly the vision of researchers sharing a common language and reviewing each
other's work.

**Why rejected**: of the three benefits, only the third holds up, and the third is not a v1 goal.

The first does not hold. A coordination procedure is called once per round and runs on the order of 10² times per run; each round
touches five price vectors of length 10² to 10³ (`research/bench/repro.py:118`), tens of kilobytes. Cross-language overhead is on
the order of 0.1% of the total. The 54.8 MB figure is for the whole economy; the coordination procedure never touches that much data.

The second point is only a matter of cleanliness — arbitrary Python can also have its source hashed.

The third is real, but v1's goal is "the same numbers, much faster, much easier to use." Reproducibility is judged by whether the
same input produces the same numbers, which a numerical diff can verify without anyone having to read the method. Inspectability
serves a later vision, not v1.

In terms of effort, the operator approach costs four things before v1 can ship: designing the operator set, writing the interpreter,
defining a serialization format, and defining a canonical form. And once the operator set becomes the extension mechanism,
**a researcher missing an operator is blocked on the maintainer** — their real option is usually not to wait for a release but to
work around the library with their own script, at which point that demand signal is lost too.

**Revival condition**: once the interface layer is working and there are real users. At that point the operator set would be added
as a **convenience layer built on top of the interface**, not as the extension mechanism — composing with operators would additionally
buy inspectability and structured hashing, while writing arbitrary Python would still get everything else. The two paths sit at
different layers and do not conflict.

The cost of deferring is bounded: if the interface ships first and the operator layer is added later, existing coordination
procedures keep working unchanged, because they were already wired in through the interface, and an operator-assembled procedure
ultimately produces something that satisfies the same interface too. Under the test set in [phasing-and-granularity.md](../phasing-and-granularity.md)
(whether doing it later instead of now costs a rewrite), this does not.

**Related**: [coordination-procedures.md](../coordination-procedures.md)

---

### Split the interface into two layers, with iterative mechanisms forced to implement a narrower interface

**Rejected.**

**Proposal**: the outer `solve(economy, seed) -> Plan` stays general; iterative mechanisms are additionally required to implement
three small methods, `init` / `step` / `converged`, with the library driving the loop, so that round count, per-round trajectory,
divergence detection, and timeouts are all handled by the library.

**Why it was considered**: the convergence-rounds CI benchmark in [reproducibility.md](../reproducibility.md) needs the library to
know the round count, and that benchmark is the main safeguard against a failure mode specific to this field — "the math is right
but it does not converge in 250 rounds." A two-layer interface makes this hold for every iterative method.

**Why rejected**: forcing researchers to split their own loop into three callbacks means requiring them to rewrite an existing
script just to use this library. The library's role is infrastructure; it should not force anyone into a particular coding style.

The same benefit can be obtained for most cases through an opt-in tool — offering `iterate` gives a round count to anyone who uses
it. The cost is that the convergence benchmark does not apply to methods that skip it, and that cost has already been recorded as a
scope narrowing in [reproducibility.md](../reproducibility.md).

**Revival condition**: if it is observed that nearly all methods skip `iterate`, making the convergence benchmark meaningless in
practice.

## 2026-09-26

### Build the book's literal rule and the `pequod-plus` rule into the Hahnel module as comparable variants

**Rejected**: The maintainer decided to follow the program. Neither of these two is the program that produced the book's results, so neither is built in.

**Proposal**: Besides the original rule, build two more into `demplan.prefabs.hahnel`: the literal reading of page 181 of the book (`w = min(v, 0.25)·(1.05 − 0.5^v)`, no lag), and the `pequod-plus` reading (`1.05 − 0.5^v` times the previous round's step size). A researcher could then compare the three rules directly on the same data.

**Why it was considered**: All three have a source (the book's text, and the same author's new code from 2023 on), and "how much the result changes when the textual description and the actual program differ by a one-round lag" is itself a mechanism insight about price-update rules.

**Why rejected**:
- The book's literal reading was never run this way, and the book's numbers do not come from it
- `pequod-plus` is a different program from two years after the book was published; it does not converge on dep1ex01, and its demand aggregation is also wrong
- The library defines only the slot; a researcher who wants to compare writes a function and plugs it in, and the library does not need to implement it for them

**Revival condition**: When a researcher wants to compare price-update rules systematically and asks the library to provide these as comparison baselines.
