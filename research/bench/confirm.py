# Price rules: every mode this script runs is a reading of the text rather than the program:
# slides_capv ("cap v everywhere") and slides_capw read the 2020 slides, paper2023 reads the
# page-10 pseudocode of the 2023 paper ("previous delta"). The program behind the published
# tables of Hahnel (2021), pequod-cljs csvgen.clj at 71e44d3, uses none of them. Its rule is
# the mode cljs_lagged of endowment.py and, in the library, demplan.prefabs.hahnel.book_2021_rule.
# See docs/research/reproduction.md.
"""
Cross-check: does the 2020 slides' price-update rule, combined with the endowment of 1000
stated in the paper, reproduce the published results?

Target values (2020 slides, page 7, average of 40 experiments):
  cold start, 5% threshold: 11.85 rounds
  cold start, 3% threshold: 19.2 rounds
  warm start, 5% threshold: 6.5 rounds
"""
import time

import numpy as np

import repro
import endowment as E

S = 1000.0
MODE = "slides_capv"
FILES = [f"dep1ex{n:02d}.clj.gz" for n in range(1, 6)]


def load(name):
    wc, cc = repro.parse(str(repro.DATA / name))
    dims = (cc["priv_exp"].shape[1], cc["pub_exp"].shape[1], int(wc["coef"].max()) + 1)
    return wc, cc, dims


if __name__ == "__main__":
    print(f"\nrule = {MODE}   endowment S = {S:,.0f}\n")
    print(f"{'file':<10} {'cold5%':>6} {'cold3%':>6} {'warm5% (3 seeds)':>22}")
    print("-" * 50)

    cold5, cold3, warm = [], [], []
    cache = {}
    for name in FILES:
        wc, cc, dims = load(name)
        cache[name] = (wc, cc, dims)
        n1, p1, _ = E.run(wc, cc, dims, S, MODE, 5.0)
        n3, _, _ = E.run(wc, cc, dims, S, MODE, 3.0)
        ws = []
        for seed in (0, 1, 2):
            wc2, cc2 = E.augmented_reset(wc, cc, np.random.default_rng(seed))
            n2, _, _ = E.run(wc2, cc2, dims, S, MODE, 5.0, p0=p1)
            ws.append(n2)
        cold5.append(n1); cold3.append(n3); warm.extend(w for w in ws if w)
        print(f"{name[:8]:<10} {n1:>6} {n3:>6} {str(ws):>22}", flush=True)

    print("-" * 50)
    print(f"{'mean':<10} {np.mean(cold5):>6.2f} {np.mean(cold3):>6.2f} {np.mean(warm):>10.2f}")
    print(f"{'2020 report':<10} {11.85:>6} {19.2:>6} {6.5:>10}")

    print(f"\n=== endowment sensitivity (dep1ex01, rule {MODE}) ===")
    wc, cc, dims = cache[FILES[0]]
    print(f"{'S':>8} {'cold5%':>6} {'cold3%':>6}")
    for s in (250, 500, 700, 1000, 1400, 2000, 4000):
        n1, _, w1 = E.run(wc, cc, dims, float(s), MODE, 5.0)
        n3, _, _ = E.run(wc, cc, dims, float(s), MODE, 3.0)
        print(f"{s:>8} {str(n1 or f'>250'):>6} {str(n3 or '>250'):>6}")

    print(f"\n=== same experiment, different price-update rules (dep1ex01, S={S:,.0f}) ===")
    for mode in ("paper2023", "slides_capv", "slides_capw"):
        t0 = time.perf_counter()
        n1, _, w1 = E.run(wc, cc, dims, S, mode, 5.0)
        print(f"  {mode:<14} cold5% = {str(n1 or '>250 did not converge'):<12} "
              f"worst imbalance {w1:.1f}%   {time.perf_counter()-t0:.0f}s")
