# Rejected: Data Model

## 2026-08-30

### Split commodities into multiple tables by kind

**Rejected.**

**Proposal**: separate tables for private consumer goods, public goods, intermediate goods, natural resources, and labor.

**Why it was considered**: safer typing — labor could not be mistaken for an intermediate good.

**Why rejected**: adding a sixth kind would require a structural change, and this project's v1 already ships an emissions
extension and will later add money stocks. Also, the three-way `np.where` in `research/bench/repro.py:137` that selects prices by
kind shows that real computations often need to handle all kinds uniformly; splitting into tables would turn that into a five-way
branch.

**Revival condition**: if the number of kinds stays stable long-term, and misused kinds become an actual source of bugs.

---

### Give `Plan`'s valuation layer a closed enum

**Rejected.**

**Proposal**: define `Plan`'s valuation portion as a closed enum — indicative price, labor value, shadow price, none — for type
safety, mirroring `Technology`.

**Why it was considered**: a free-form key-value bag has no type protection; a misspelled key silently returns nothing.

**Why rejected**: a closed enum means that when a researcher wants to add a valuation kind the library did not anticipate, they
have to modify the library's code and wait for a release. That directly conflicts with the principle in
[coordination-procedures.md](../coordination-procedures.md) that "the extension mechanism is an interface, not a list the library
maintains," and it reproduces the same "missing one item blocks you on the maintainer" problem seen in the operator-set proposal.

The eventual compromise: the library predefines the common cases (with type protection), while also keeping a free-form bag for
the rare cases.

**Revival condition**: none. The compromise already covers the benefits of both sides.

---

### `Economy` is immutable for the whole run

**Rejected.**

**Proposal**: `Economy` is a fixed problem statement; coordination procedures only read it. A multi-period run is just solving the
same problem T times.

**Why it was considered**: conceptually clean — the problem and the answer are separate, `Economy` is the input and `Plan` is the
output, the boundary of a single run is clear, and determinism is easy to guarantee.

**Why rejected**: **it welds a theoretical assumption into the data model — that technology and input ratios never change.**
The moment anyone wants to study technological progress, resource depletion, or population change, that assumption breaks, and
long-run sustainability is one of the central battlegrounds in debates over democratic economic planning.

A theoretical presupposition written into the data model is more hidden than one written into a check: no check will ever flag
its existence, and readers will simply assume "this is just how the library is designed."

**Revival condition**: none. This conflicts directly with the theory-neutrality constraint.

**Related**: [data-model.md](../data-model.md)
