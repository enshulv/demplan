# License

## 2026-09-05

### MIT stays after re-evaluation; three GPL peer implementations are for reading only, never for copying

**Decision**: MIT stays; the license does not change to GPL. The three clones newly added under `upstream/` (`socialist_planning`, GPL-3.0; `EPOS`, GPL-2.0-or-later; `Economic-Planning`, GPL-3.0) are for reading and running side by side. **None of their code is merged into this repository.**

**Why**: Switching to GPL would directly conflict with an existing commitment: [spec.md](../spec.md) states that the coordination procedure's extension mechanism is an interface, and any implementation that satisfies the interface gets all of the above capabilities, **without needing to merge into this library's code**. GPL's copyleft boundary falls on derivative works, and a researcher who writes their own `Procedure` and does `import demplan` picks up a GPL obligation the moment they distribute it — hitting exactly the audience this library most wants to reach: universities whose legal counsel only clears OSI-whitelisted licenses, and researchers who need to attach code to a paper.

"Every peer project uses GPL" is a sampling bias. Those three repositories sit in the same political spectrum, where GPL is itself a statement. Against the reference class this library actually targets — Concordia uses Apache-2.0, AgentSociety uses Apache-2.0, NumPy and pandas use BSD-3, PyO3 uses Apache-2.0/MIT — infrastructure projects in this category almost never use GPL. Rust's own ecosystem is even more decisive: the crates.io convention is MIT/Apache-2.0 dual licensing, and almost nothing depends on a GPL crate. (Corrected 2026-09-26 after a citation check: this said "AgentSociety uses MIT"; the source says Apache-2.0: `tsinghua-fib-lab/AgentSociety` switched from MIT to Apache-2.0 on 2025-04-07, see commit `c56e9f8` in that repository.)

Switching to GPL also wouldn't buy the two things it was proposed for. **Citation has nothing to do with licensing** — that's an academic norm, handled through `CITATION.cff` and provenance lines. **"Switch so we can copy their code" doesn't hold either**: none of the three should be vendored (one-off scripts, Java, an incompatible data model), and re-implementing from the papers is entirely legal under MIT, because mathematical formulations and algorithmic ideas aren't covered by copyright.

**Alternatives rejected**: see [rejected/license.md](rejected/license.md) 2026-09-05.

**How to apply**: Reading any GPL repository under `upstream/` is fine. **Copying a fragment is not, and neither is copying a rewritten fragment.** Whatever mechanism is needed from them gets re-implemented from the paper, with the source cited in the prefab's docstring. Interoperability (reading their data formats) doesn't involve copying code, and is allowed.

**Related**: [research/related-implementations.md](../research/related-implementations.md)

## 2026-08-28

### Adopt MIT

**Decision**: This library uses the MIT license.

**Why**: Minimal friction to academic adoption. MIT is on the OSI list, and it clears university legal review, conda-forge, Debian, and journal reproducibility requirements without issue; other libraries can depend on it freely too.

This project's goal is to be used by as many researchers as possible, and a license is the easiest obstacle to accidentally put in that road.

**Alternatives rejected**: see [rejected/license.md](rejected/license.md)

**How to apply**: Before folding someone else's published code into this library, confirm their license permits it. Academic code often ships with no license at all, and no license legally means all rights reserved — in that case, only reimplementing from the paper is allowed, not copying the code.
