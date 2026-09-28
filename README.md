# demplan

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23010110.svg)](https://doi.org/10.5281/zenodo.23010110)
[![PyPI](https://img.shields.io/pypi/v/demplan)](https://pypi.org/project/demplan/)

Shared research infrastructure for democratic economic planning.

Write a coordination procedure, run it on a published economy, and get the whole plan back as
plain arrays, raw enough to recompute any metric afterwards. A mechanism is compared with a
centrally computed optimum under an objective you declare, not with a market.

## Why

Research on democratic planning has no shared tools. The participatory planning model of Hahnel
and Szczepanczyk has been implemented at least four times since 2017, in three languages, and
none of the implementations became a library someone else could build on. Other groups, such as
OLIN-EP [7], I-EPOS [8] and Economic-Planning [9], each define their own data model, so no
group's economy runs in another group's solver.

Neighbouring fields have such libraries: Mesa [13], Concordia [10] and AgentSociety [11] in
agent-based and generative social simulation. demplan aims to do the same for democratic
planning: one data model that several mechanisms run on, deterministic seeding, raw output, and a
benchmark every mechanism can be compared with. Success means less duplicated work in the field.
A fork that does better also counts.

## What reproducing the published experiments found

Chapter 9 of Hahnel (2021) [3] reports 40 simulation experiments. Their input data is public [5];
the round counts are not, so demplan ran all 40 again.

- The round counts come back. In Tables 9.1, 9.2 and 9.5, demplan matches the output of the
  program behind the book, `pequod-cljs` [14], in all 40 experiments.
- They come back only with a price rule that no published text states in full. With the rule as
  printed in the book, the first round below 5% matches the program's output in 8 of the 40
  experiments.
  [Entry 1](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations#1-no-published-text-states-the-price-update-rule-the-published-runs-used)
- Four cells of the printed tables differ from the program's output, and the book's own text
  follows the output.
  [Entry 2](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations#2-four-cells-of-the-books-tables-differ-from-the-programs-output)
- A round on the book's first experiment takes about 0.06 s. The program behind the book takes 54
  to 97 s per round on the same data, measured in a different environment.

Every statement about the book and the upstream programs can be rerun with the scripts in
[research/upstream/](research/upstream/README.md). The wiki page
[Limitations of Existing Implementations](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations)
lists all nine gaps found in the published texts and implementations.

<details>
<summary>All 40 experiments against the book's tables</summary>

Prefab `demplan.prefabs.hahnel` (`HahnelBook2021`), endowment 1000, initial price 700. Year one
runs to the 3% threshold; year two starts from year one's last prices and price-rule state, after
the book's random change to the exponents. The book's random draws cannot be recovered, so the
two-year rows are over 10 seeds per experiment and are compared as distributions.

| Table in [3] | Book: mean [min, max] | demplan: mean [min, max] | Runs |
|---|---|---|---|
| 9.1 cold start, first round with every imbalance below 5% | 11.850 [11, 13] | 11.850 [11, 13] | 40 |
| 9.2 cold start, first round with every imbalance below 3% | 19.225 [18, 22] (text: 19.2) | 19.200 [18, 22] | 40 |
| 9.5 rounds from every imbalance below 10% to below 5% | 3.775 [3, 5] | 3.775 [3, 5] | 40 |
| 9.4 year two, first round below 5% | 6.525 [5, 8] (text: 6.575) | 6.287 [5, 8] | 400 |
| 9.4 real GDP growth, % | 2.446 [2.178, 2.659] | 2.477 [2.143, 2.720] | 400 |
| 9.6 year two with increasing returns, first round below 5% | 6.275 [5, 8] | 6.197 [5, 7] | 400 |
| 9.6 real GDP growth, % | 1.860 [1.659, 2.101] | 1.852 [1.577, 2.116] | 400 |

The book's means are computed from the 40 printed entries of each table. Every run converged.

Experiment n of the book is `dep1ex{n}` on the public site and `dep1ex{60+n}` in the program's
repository.

What is not reproduced: the year-two round counts experiment by experiment, because the book's
random draws are not recoverable, and Table 9.6 experiment by experiment, because its output files
are not in the program's repository. Every intermediate number is in
[docs/research/reproduction.md](docs/research/reproduction.md).

</details>

<details>
<summary>How the speed figures were measured</summary>

Both on dep1ex01: 30,000 worker councils, 30,000 consumer councils, 500 commodities.

- `pequod-cljs` at `71e44d3`, in Docker (OpenJDK 11.0.16, Leiningen 2.9.8, a VM with 12 CPUs and
  8 GB, on a Windows laptop): 81 to 119 s to load the input and compute round 1, then 54 to 97 s
  per round, with a peak memory of 2.0 to 4.5 GiB.
- demplan's `HahnelBook2021`, natively on the same laptop while it was running other work: 12
  rounds to the 5% threshold in 0.76 s, the median of three runs.

The two ran in different environments, so the figures give an order of magnitude, not a ratio.

</details>

## Install

```sh
pip install demplan
```

Python 3.10 or newer. Prebuilt packages cover Windows, macOS and Linux; the wiki's
[Installing](https://github.com/enshulv/demplan/wiki/Tutorial-Installing) page covers other
systems and building from source.

The example below reads one of the published economies (56 MB):

```sh
curl -sSL -o dep1ex01.clj.gz https://www.szcz.org/depexperiments/dep1ex01.clj.gz
```

## Example

Run the procedure of Hahnel (2021) on the first published economy and measure the largest
imbalance left in the plan:

```python
import numpy as np
from demplan import load_dep1ex, run
from demplan.prefabs import HahnelBook2021

economy = load_dep1ex("dep1ex01.clj.gz")
result = run(HahnelBook2021(), economy, seed=0)
plan = result.plan

supply = plan.total_output(economy) + economy.endowment
demand = plan.total_input_use(economy) + plan.extra["consumer_demand"]
gap = np.abs(2 * (supply - demand)) / np.where(supply + demand > 0, supply + demand, 1.0)

print(result.summary.rounds, result.summary.converged, gap.max())
```

Nothing in that calculation is privileged. The plan holds every quantity the procedure decided,
so any measure of feasibility, cost or fairness is a few lines away from the same output. The
[tutorial](https://github.com/enshulv/demplan/wiki/Tutorial-First-Run) goes on from here.

## Documentation

The [wiki](https://github.com/enshulv/demplan/wiki) holds the guides.

| You are | Start with |
|---|---|
| A researcher who has never used Python | [Tutorial: Before you start](https://github.com/enshulv/demplan/wiki/Tutorial-Before-You-Start), then the tutorial pages in order |
| A researcher who wants a one-page overview | [For Researchers](https://github.com/enshulv/demplan/wiki/For-Researchers) |
| Looking for the exact model of a planning mechanism | [Mechanisms](https://github.com/enshulv/demplan/wiki/Mechanisms) |
| A researcher with a mechanism of your own | An [issue](https://github.com/enshulv/demplan/issues) with the paper, pseudocode or code that states it, or [Writing your own procedure](https://github.com/enshulv/demplan/wiki/Tutorial-Writing-Your-Own-Procedure) |
| Comparing with the published experiments | [Limitations of Existing Implementations](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations) |
| Looking up a function, parameter or error | [Reference index](https://github.com/enshulv/demplan/wiki/Reference-Index) |
| Asking how far to trust the results | [Quality Assurance](https://github.com/enshulv/demplan/wiki/Quality-Assurance) |
| A developer who wants to contribute | [For Contributors](https://github.com/enshulv/demplan/wiki/For-Contributors) and [CONTRIBUTING.md](CONTRIBUTING.md) |

## Status

Version 0.1.1, early. It has one published procedure, two data sources (the dep1ex archives and
the WIOD 2016 release) and a linear-programming reference solution for Leontief economies. It
does not yet have an on-disk output format, a capital stock across periods, or a second published
procedure. The full list is on the [wiki's home page](https://github.com/enshulv/demplan/wiki#status).

If any of it blocks your research, open an issue. Requests with a concrete research question move
up the list.

## Contributing

demplan is maintained by one independent developer, with no funding and no commercial purpose.
Bug reports, questions about a result, and requests for a data source or a procedure are welcome
as issues. For code and documentation, read [CONTRIBUTING.md](CONTRIBUTING.md) first.

AI-assisted work is accepted when a person stays accountable for it: a change to behaviour, the
data model or a documented rule comes with a decision record of the choices a person made. See
[CONTRIBUTING.md](CONTRIBUTING.md#ai-assisted-contributions); AI agents start from
[AGENTS.md](AGENTS.md).

## How to cite

Every release is archived on Zenodo. Cite the version you used:

> Mark, E. (2026). *demplan: shared research infrastructure for democratic economic planning*
> (Version 0.1.1) [Computer software]. Zenodo. <https://doi.org/10.5281/zenodo.23010111>

The DOI [10.5281/zenodo.23010110](https://doi.org/10.5281/zenodo.23010110) stands for all
versions and resolves to the latest. Metadata is in [CITATION.cff](CITATION.cff).

If your work depends on the reproduction results above, please also cite the original
experiments [2, 3] and the pseudocode paper [4].

## References

<details>
<summary>15 references</summary>

1. Albert, M., and Hahnel, R. (1991). *The Political Economy of Participatory Economics.*
   Princeton University Press.
2. Hahnel, R., Szczepanczyk, M., and Weisdorf, M. (2020). *Computer Simulation Experiments of
   Participatory Annual Planning.* Systems Science Noon Seminar, 4 December 2020. Slides:
   <https://thenextrecession.wordpress.com/wp-content/uploads/2021/01/computersimulationexperimentsofparti_powerpoint.pdf>
3. Hahnel, R. (2021). *Democratic Economic Planning.* Routledge.
4. Szczepanczyk, M. (2023). Pseudocode and algorithms for computer simulations of
   democratically planned economies. *Journal of Information Economics* 1(3), 15, 43–54.
   <https://doi.org/10.58567/jie01030004>. Open access under CC BY 4.0. Page numbers in this
   README refer to the author's version, <http://www.szcz.org/img/jie-paper-2023.pdf>.
5. Szczepanczyk, M. Participatory planning experiment data (`dep1ex01` to `dep1ex40`).
   <https://www.szcz.org/depexperiments/>
6. Szczepanczyk, M. `pequod-plus`: participatory planning procedure prototype (Clojure,
   GPL-3.0). <https://github.com/msszczep/pequod-plus>
7. Samothrakis, S. (2020). Open loop in natura economic planning. arXiv:2005.01539. Code
   (GPL-3.0): <https://github.com/ssamot/socialist_planning>
8. Nardelli, P. H. J., Gória Silva, P. E., Siljak, H., and Narayanan, A. (2025). Cyber-physical
   decentralized planning for communizing. *Competition & Change* 29(1).
   <https://doi.org/10.1177/10245294231213141>. I-EPOS code (GPL-2.0-or-later):
   <https://github.com/epournaras/EPOS>
9. Parellada, P. V. `Economic-Planning`: a Python package for multi-period
   linear-programming planning (GPL-3.0). <https://github.com/pablovegan/Economic-Planning>
10. Vezhnevets, A. S., et al. (2023). Generative agent-based modeling with actions grounded in
    physical, social, or digital space using Concordia. arXiv:2312.03664.
11. Piao, J., et al. (2025). AgentSociety: Large-scale simulation of LLM-driven generative
    agents advances understanding of human behaviors and society. arXiv:2502.08691.
12. Cockshott, W. P., and Cottrell, A. (1993). *Towards a New Socialism.* Spokesman.
13. Kazil, J., Masad, D., and Crooks, A. (2020). Utilizing Python for agent-based modeling: the
    Mesa framework. In *Social, Cultural, and Behavioral Modeling (SBP-BRiMS 2020)*, Lecture
    Notes in Computer Science 12268, Springer.
14. Szczepanczyk, M. `pequod-cljs`: a computerized simulation of a participatory economy
    (Clojure and ClojureScript). <https://github.com/msszczep/pequod-cljs>. The runs behind the
    tables of [3] used `src/clj/pequod_cljs/csvgen.clj` at commit `71e44d3` (2020-06-23).
15. Timmer, M. P., Dietzenbacher, E., Los, B., Stehrer, R., and de Vries, G. J. (2015). An
    illustrated user guide to the World Input–Output Database: the case of global automotive
    production. *Review of International Economics* 23, 575–605. The WIOD 2016 release (CC BY
    4.0) is at <https://doi.org/10.34894/PJ2M1C>.

demplan reads the published papers and data; it contains no code from the implementations
above. Its reference solution calls the HiGHS solver through SciPy.

</details>

## License

MIT. See [LICENSE](LICENSE).
