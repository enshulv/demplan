# Rejected: License

## 2026-09-05

### Switch to GPL and explicitly credit three comparable implementations

**Rejected.**

**Proposal**: change this library's license from MIT to GPL, on the grounds that three newly surveyed economic-planning
implementations (`socialist_planning`, `EPOS`, `Economic-Planning`) all use GPL, so switching would align with them and let this
project explicitly credit their contributions.

**Why it was considered**: consistency with how peers in the field license their work. Intuitively, switching also seemed like it
would make it easier to cite and build on their work. The timing also favored it — every line in this repository currently has a
single author, so changing the license costs nothing right now; once the first outside contributor arrives, each one would need to
consent individually.

**Why rejected**:

- **This conflicts directly with rule 5.** GPL's copyleft boundary runs through derivative works. A researcher who runs
  `import demplan` to write their own `Procedure`, once they distribute it, would have to distribute it under GPL too — and the
  spec explicitly states that extension implementations "need not be merged into this library's code." The people hit hardest by
  this would be exactly this library's target users.
- **"Everyone else uses GPL" is a sampling bias.** The three samples all sit on the same point of the political spectrum, where GPL
  is a stance statement. This library is positioned in the infrastructure category, and that category almost never uses GPL.
- **Switching would not get the proposal what it wants.** Citing sources is an academic norm, not a licensing mechanism;
  reimplementing from a paper is already legal under MIT, because algorithmic ideas are not copyrightable.
- **The cost on the Rust side is disproportionately heavy**: the crates.io convention is dual MIT/Apache-2.0 licensing, and no one
  is willing to depend on a GPL crate.

**Alternatives also evaluated**: MPL-2.0 was the only option that could satisfy both "has copyleft" and "does not collide with
rule 5" (file-level copyleft, leaving a researcher's own `Procedure` files unaffected). LGPL's linking boundary is unclear for Rust
and Python extension modules, which is a liability for an academic library. Apache-2.0 differs from MIT mainly by adding a patent
grant. None of the three was adopted, because the problem the proposal wanted to solve (citation, reuse) is not something a
license can solve in the first place.

**Revival condition**: same as [the 2026-08-28 entry](#2026-08-28) — if a specific case of commercial appropriation needs to be
prevented, and there is by then a large enough user base to absorb the resulting drop in adoption. The current user count is zero,
so neither condition holds.

**Related**: [license.md](../license.md) 2026-09-05

## 2026-08-28

### Use Coopyleft (the CoopCycle license)

**Rejected.**

**Proposal**: adopt the custom Coopyleft license from CoopCycle, a French federation of delivery-rider cooperatives, restricting
use of this library to cooperatives and entities recognized as part of the EU's social and solidarity economy.

**Why it was considered**: consistency with this project's own position in the field. Building infrastructure for democratic
economic planning under a license that hands usage rights to cooperatives is a self-consistent stance.

**Why rejected**: it restricts use based on the legal form of the user, and therefore does not meet the OSI's open-source
definition. The consequences for an academic library are concrete — conda-forge and Debian cannot package a non-OSI license; many
universities' legal and IT departments only approve licenses on the OSI list; a growing number of journals' reproducibility
requirements specify an open license; and other libraries cannot depend on it.

There is also an internal tension: this project's positioning is "shared academic infrastructure," and restricting who can use it
based on institutional form runs in the opposite direction from "shared."

**Revival condition**: if this library faces a specific case of commercial appropriation that needs to be prevented, and there is
by then a large enough user base to absorb the resulting drop in adoption.

**Related**: [license.md](../license.md)
