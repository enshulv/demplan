# Technology choices

## 2026-08-28

### Rust for the core, with Python bindings as the primary user interface

**Decision**: Core computation is written in Rust. Python bindings are provided through PyO3 and maturin, with documentation centered on the Python API and the Rust crate supported as an equally maintained lower layer. TS/wasm handles visualization and human-in-the-loop front ends; it does no computation.

**Why**: Three reasons.

First, the target users are economists and social scientists, not engineers. Concordia and AgentSociety both use Python, because that's where the researchers are. A Rust-only interface would push adoption close to zero.

Second, Rust suits the core: the workload is fixed-point iteration over 10⁴–10⁷ entities, needs cross-platform reproducible determinism, no GC pauses, and single-file distribution.

Third, once Rust compiles to wasm, the same core has three outlets — native, Python, and the browser. "Democratic" planning eventually lands on real councils submitting proposals, and that's a web application — a spot this project will need to occupy sooner or later.

**Alternatives rejected**:

- Rust only, no Python interface — see [rejected/technology-choices.md](rejected/technology-choices.md)
- Python only — see [rejected/technology-choices.md](rejected/technology-choices.md)

**How to apply**: When designing extension points, put the Python-reachable seam at the `Procedure` layer. `Procedure` is called once per round (order 10²); `Participant` is called once per round per agent (order 10⁷). When custom `Participant` behavior is needed, go through a vectorized callback — pass the whole population's arrays at once, not one call per agent.

---

### Research platform first; academic output lives in the outer wrapper

**Decision**: Every design decision serves "run the experiment, produce the figure, write the paper." The Rust side only produces long-format Arrow/Parquet; plotting and LaTeX table export live in the Python layer.

**Why**: The alternative path is "deployable system first," which means taking persistence, concurrent submission, identity, and authorization seriously from day one, with a different data model to match. Only one path can be chosen, and this project exists to reduce researchers' duplicated work.

Journals want editable vector PDFs, not PNGs, so plotting can't be hard-baked into the Rust side.

**How to apply**: Keep a `paper/` directory in the repository, with one command that reproduces every figure in a given published paper. That is the strongest adoption argument available.

---

## 2026-09-05

### v1's Rust surface is deliberately kept small

**Decision**: v1's Rust code holds only four things: columnar storage and schema validation for `Economy` and `Plan`, the data loader, residual computation, and Parquet output. The Cobb-Douglas closed-form solution, `iterate`, prefabs, and the reference solution all live in Python (numpy and scipy).

**Why**: The coordination procedure is arbitrary Python, and the heaviest computation sits on the researcher's side. Scenario-level parallelism has to go through multiple processes anyway, because Python callbacks can't use Rust threads. At this scale, numpy's 127 milliseconds per round is already good enough (measured locally on 2026-09-05, dep1ex01, 14 rounds in 1.77 seconds).

What Rust delivers in v1: load speed (the numpy version takes 4.5 seconds to parse dep1ex), deterministic reduction, Parquet output, and a placeholder for v2 and wasm.

**How to apply**: Before proposing to "move X into Rust," measure the Python version's bottleneck first.

---

### Repository layout and the Python-side data classes

**Decision**: One Cargo workspace, maturin's mixed layout:

| Path | Contents |
|---|---|
| `crates/demplan-core` | Data model and loaders, no Python dependency |
| `crates/demplan-py` | PyO3 bindings, module name `demplan._core` |
| `python/demplan` | Python package |
| `tests/` | pytest and hypothesis |

On the Python side, `Economy` and `Plan` are immutable dataclasses whose fields are numpy arrays. `_core` copies arrays once when returning them; Python holds that copy. Errors: Rust returns a `Result`; the binding layer converts it to a Python exception, with the exception type inheriting from `ValueError`.

The development loop uses `maturin develop` (debug build); timing runs use `--release`. Measured locally: a release build takes 58 seconds.

**Why**: A Tier-C mechanical decision. Copying once at the 50 MB scale costs milliseconds — not worth introducing lifetime constraints for zero-copy.
