# Rejected: Technology Choices

## 2026-08-28

### Pure Rust, no Python interface

**Rejected.**

**Proposal**: publish only a Rust crate; users write their own experiments in Rust.

**Why it was considered**: a single-language stack, no cross-language boundary, and a type system that makes illegal plugin
combinations unrepresentable, with no need for an extra schema-validation layer. The maintenance surface is also half the size.

**Why rejected**: the target users are economists and social scientists. What they want is to `pip install` the library and change
parameters in a notebook. Concordia and AgentSociety are both Python, and that is not a coincidence.
With only a Rust interface, this library would be unusable for its declared target users, and "letting researchers spend less time
on this" is the whole reason this project exists.

**Revival condition**: if the target users change from "researchers" to "engineers deploying a system."

---

### Pure Python, no Rust

**Rejected.**

**Proposal**: implement everything in Python plus numpy.

**Why it was considered**: fast to develop, zero installation friction for users, and numpy measures at 99 milliseconds per round,
already fast enough.

**Why rejected**: three reasons. v2's 10⁷-entity scale needs GC-pause-free execution and SIMD; bit-identical reproducibility across
platforms is hard to guarantee in the Python ecosystem; and a wasm build would be out of reach, meaning the browser-based
human-in-the-loop frontend would need a separate reimplementation of the core, and the two would inevitably drift apart.

**Revival condition**: if v2 is dropped and running in the browser is also abandoned.
