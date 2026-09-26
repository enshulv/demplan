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

The five above are successive implementations of the same model. There are also three **unrelated** economic-planning implementations, with different formalizations and data models, cloned under `upstream/` — see [related-implementations.md](related-implementations.md): `ssamot/socialist_planning`, `epournaras/EPOS`, `pablovegan/Economic-Planning`. All three are GPL-licensed; **read-only, not copied from**.

The same model has been rewritten five times over seven years, across four languages, without ever settling into a reusable library. That is this project's reason to exist.

## Key literature

Sources and download locations for the original texts are in [literature/](literature/README.md).

- Szczepanczyk, M. (2023). Pseudocode and algorithms for computer simulations of
  democratically planned economies. *Journal of Information Economics* 1(3), 15
- Hahnel, Szczepanczyk, Weisdorf (2020-12-04). Computer Simulation Experiments of
  Participatory Annual Planning. Systems Science Noon Seminar. **Cold-start and warm-start
  iteration counts are listed separately here**; this is currently the only public material
  that makes this distinction
- Hahnel, R. (2021). *Democratic Economic Planning*. Routledge. Chapter 9. Not obtained
- Project page: <https://participatoryeconomy.org/project/computer-simulations-of-participatory-planning/>

The 2023 paper lists seven future directions at its end, each of which maps to a capability
of this library: other production functions, improved price-adjustment algorithms,
environmental impact, robustness testing, human-in-the-loop intervention, inter-council
interaction, and integration with interactive planning software.

The second one is worth noting on its own: the authors state that the price-adjustment rule
"was arrived at with little concerted effort," and that they intended to search the rule
space systematically. That search would require hundreds or thousands of runs, while
upstream's own experiment takes four hours to run once. The 2020 slides already say
"there's room for improvement here"; six years later, that search still hasn't been done.
