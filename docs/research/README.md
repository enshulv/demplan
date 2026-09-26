# Research

Reproduction and review of existing implementations. These results inform this library's design decisions and serve as v1's validation targets.

| File | Contents |
|---|---|
| [reproduction.md](reproduction.md) | Rerunning upstream's published experiments: cold-start and warm-start iteration counts, performance measurements |
| [upstream-code-issues.md](upstream-code-issues.md) | Correctness, performance, and engineering-state issues in `pequod-plus` and `pe_ifb_compute` |
| [literature/](literature/README.md) | Sources and download locations for upstream's original research materials |
| [wiod-field-mapping.md](wiod-field-mapping.md) | What's missing to load WIOD into `Economy`; input for defining residuals in Stage 2 |
| [related-implementations.md](related-implementations.md) | Three public economic-planning implementations: formalization, data model, license boundaries, and the first cross-mechanism comparison on dep1ex |

## Subjects

| Repository | Description |
|---|---|
| `msszczep/pequod-plus` | Current implementation, Clojure + SQLite. Cloned at `upstream/pequod-plus/` |
| `msszczep/pequod-cljs` | The implementation that produced the published results, ClojureScript. 1 GB repository, not cloned |
| `msszczep/pe_ifb_compute` | Repository studying computational requirements, Python |
| `msszczep/pequod-clj`, `pequod2` | Earlier implementations, Clojure and NetLogo |

Apart from `pe_ifb_compute`, the four above are successive implementations of the same model; `pe_ifb_compute` does not implement the model, it only studies its computational requirements. There are also three **unrelated** economic-planning implementations, with different formalizations and data models, cloned under `upstream/` — see [related-implementations.md](related-implementations.md): `ssamot/socialist_planning`, `epournaras/EPOS`, `pablovegan/Economic-Planning`. All three are GPL-licensed; **read-only, not copied from**.

Since 2017 the same model has been implemented at least four times (`pequod2` in NetLogo, `pequod-clj`, `pequod-cljs`, `pequod-plus`), across three languages, without ever settling into a reusable library. That is this project's reason to exist.

## Key literature

Sources and download locations for the original texts are in [literature/](literature/README.md).

- Szczepanczyk, M. (2023). Pseudocode and algorithms for computer simulations of
  democratically planned economies. *Journal of Information Economics* 1(3), 15
- Hahnel, Szczepanczyk, Weisdorf (2020-12-04). Computer Simulation Experiments of
  Participatory Annual Planning. Systems Science Noon Seminar. **Cold-start and warm-start
  iteration counts are listed separately here**. Hahnel (2021), chapter 9, makes the same
  distinction and gives per-experiment data
- Hahnel, R. (2021). *Democratic Economic Planning*. Routledge. Chapter 9, pp. 178–184: round
  counts for each of the 40 experiments at the 5% and 3% thresholds (Tables 9.1, 9.2); the cap in
  the price-update rule applies to v where it first appears, not in the exponent (p. 181); the
  warm-start perturbation of the exponents and its per-experiment results (pp. 182–183,
  Table 9.4, average 6.575 rounds). The maintainer holds a private copy; it is not distributed
  with the repository
- Project page: <https://participatoryeconomy.org/project/computer-simulations-of-participatory-planning/>

The 2023 paper lists seven future directions at its end, each of which maps to a capability
of this library: other production functions, improved price-adjustment algorithms,
environmental impact, robustness testing, human-in-the-loop intervention, inter-council
interaction, and integration with interactive planning software.

The second one is worth noting on its own: the authors state that the price-adjustment rule
"was arrived at with little concerted effort," and that they intended to search the rule
space systematically. That search would require hundreds or thousands of runs, while in the
author's January 2026 run log one complete experiment took four hours. The 2020 slides already
say "there's room for improvement here".
