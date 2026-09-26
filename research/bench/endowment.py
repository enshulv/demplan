"""
Works backward to the authors' endowment parameter and price-update rule.

Goal: find a configuration that reproduces the results reported in the 2020 slides --
cold start (arbitrary initial prices) 11.85 rounds at the 5% threshold, 19.2 rounds at the
3% threshold, and 6.5 rounds for warm start.

Searches two dimensions:
  endowment S          the per-category supply of nature and labor, not published
  price-update rule    the 2020 slides and the 2023 paper's pseudocode give different
                        formulas; see MODES
"""
import sys
import time

import numpy as np

import repro

MAX_ITER = 250


# ---------------------------------------------------------------- Price-update rules

def delta_paper2023(v, prev, _):
    """(1.05 - 0.5^v) times the previous round's increment, floored at 0.001, capped at 0.25."""
    raw = 1.05 - 0.5 ** v
    d = np.maximum(np.minimum(np.abs(raw * prev), raw), 0.001)
    return np.minimum(d, 0.25)


def delta_slides_capv(v, _prev, _):
    """2020 slides: v is first capped at 0.25, then w = v(1.05 - 0.5^v)."""
    vc = np.minimum(v, 0.25)
    return vc * (1.05 - 0.5 ** vc)


def delta_slides_capw(v, _prev, _):
    """The other reading of the 2020 slides: w = v(1.05 - 0.5^v), then cap the result at 0.25."""
    return np.minimum(v * (1.05 - 0.5 ** v), 0.25)


MODES = {"paper2023": delta_paper2023,
         "slides_capv": delta_slides_capv,
         "slides_capw": delta_slides_capw}


# ---------------------------------------------------------------- Iteration

def proposals(wc, cc, p, n_cc, tot_exp, precomp):
    a, c, s, k, b, mask, cat, coef, ind, prod, B, D, log_b = precomp
    p_in = np.where(cat == 0, p["inter"][coef],
            np.where(cat == 1, p["nature"][coef],
            np.where(cat == 2, p["labor"][coef], 1.0)))
    log_p = np.where(mask, np.log(np.where(mask, p_in, 1.0)), 0.0)
    lam = np.where(ind == 0, p["priv"][prod],
          np.where(ind == 1, p["inter"][prod], p["pub"][prod]))
    log_lam = np.log(lam)
    num = (-k * np.log(a) - k * (b * log_b).sum(axis=1)
           - c * np.log(c) + c * np.log(k)
           + k * (b * log_p).sum(axis=1) + c * np.log(s)
           - (c + k * B) * log_lam)
    log_Q = num / D
    output = np.exp(log_Q)
    x = np.where(mask, np.exp(log_b + log_lam[:, None] - log_p + log_Q[:, None]), 0.0)
    d_priv = (cc["income"][:, None] * cc["priv_exp"]) / (tot_exp[:, None] * p["priv"][None, :])
    d_pub = (cc["income"][:, None] * cc["pub_exp"]) / (tot_exp[:, None] * (p["pub"] / n_cc)[None, :])
    return output, x, d_priv, d_pub


def aggregate(wc, output, x, d_priv, d_pub, n_priv, n_pub, n_goods, n_cc, S):
    mask, cat, coef, ind, prod = wc["mask"], wc["cat"], wc["coef"], wc["industry"], wc["product"]
    sup, dem = {}, {}
    for key, iid, n in (("priv", 0, n_priv), ("inter", 1, n_goods), ("pub", 2, n_pub)):
        sel = ind == iid
        sup[key] = np.bincount(prod[sel], weights=output[sel], minlength=n)
    sup["nature"] = np.full(n_goods, S)
    sup["labor"] = np.full(n_goods, S)
    dem["priv"] = d_priv.sum(axis=0)
    dem["pub"] = d_pub.sum(axis=0) / n_cc
    for key, cid in (("inter", 0), ("nature", 1), ("labor", 2)):
        m = mask & (cat == cid)
        dem[key] = np.bincount(coef[m], weights=x[m], minlength=n_goods)[:n_goods]
    return sup, dem


def run(wc, cc, dims, S, mode, threshold, p0=None):
    n_priv, n_pub, n_goods = dims
    n_cc = len(cc["income"])
    p = ({k: v.copy() for k, v in p0.items()} if p0 else
         {k: np.full(n, 700.0) for k, n in
          (("priv", n_priv), ("pub", n_pub), ("inter", n_goods),
           ("nature", n_goods), ("labor", n_goods))})
    prev = {k: np.full_like(v, 0.05) for k, v in p.items()}
    fn = MODES[mode]

    b, mask, cat, coef = wc["b"], wc["mask"], wc["cat"], wc["coef"]
    B = b.sum(axis=1)
    precomp = (wc["a"], wc["c"], wc["s"], wc["k"], b, mask, cat, coef,
               wc["industry"], wc["product"], B, wc["c"] - wc["k"] + wc["k"] * B,
               np.where(mask, np.log(np.where(mask, b, 1.0)), 0.0))
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)

    for it in range(1, MAX_ITER + 1):
        output, x, d_priv, d_pub = proposals(wc, cc, p, n_cc, tot_exp, precomp)
        sup, dem = aggregate(wc, output, x, d_priv, d_pub, n_priv, n_pub, n_goods, n_cc, S)

        worst = 0.0
        for key in p:
            tot = sup[key] + dem[key]
            t = np.where(tot > 0, np.abs(2 * (sup[key] - dem[key])) / np.where(tot > 0, tot, 1), 0.0)
            worst = max(worst, float(np.nanmax(t)))
        if not np.isfinite(worst):
            return None, p, float("inf")
        if worst * 100 < threshold:
            return it, p, worst * 100

        for key in p:
            surplus = sup[key] - dem[key]
            tot = sup[key] + dem[key]
            v = np.where(tot > 0, np.abs(2 * surplus) / np.where(tot > 0, tot, 1), 0.0)
            d = fn(v, prev[key], None)
            p[key] = p[key] * np.where(surplus > 0, 1 - d, np.where(surplus < 0, 1 + d, 1.0))
            prev[key] = d
    return None, p, worst * 100


def augmented_reset(wc, cc, rng):
    wc2 = dict(wc)
    wc2["b"] = np.where(wc["mask"],
                        wc["b"] + rng.choice([0, .001, .002, .003, .004], size=wc["b"].shape), 0.0)
    cc2 = dict(cc)
    cc2["priv_exp"] = cc["priv_exp"] + rng.choice([-.002, -.001, 0, .001, .002], size=cc["priv_exp"].shape)
    cc2["pub_exp"] = cc["pub_exp"] + rng.choice([-.002, -.001, 0, .001, .002], size=cc["pub_exp"].shape)
    return wc2, cc2


if __name__ == "__main__":
    wc, cc = repro.parse(str(repro.DATA / "dep1ex01.clj.gz"))
    n_priv, n_pub = cc["priv_exp"].shape[1], cc["pub_exp"].shape[1]
    n_goods = int(wc["coef"].max()) + 1
    dims = (n_priv, n_pub, n_goods)
    n_cc = len(cc["income"])

    # ---- Diagnostic: labor and nature demand at the initial price of 700
    b, mask = wc["b"], wc["mask"]
    B = b.sum(axis=1)
    precomp = (wc["a"], wc["c"], wc["s"], wc["k"], b, mask, wc["cat"], wc["coef"],
               wc["industry"], wc["product"], B, wc["c"] - wc["k"] + wc["k"] * B,
               np.where(mask, np.log(np.where(mask, b, 1.0)), 0.0))
    p0 = {k: np.full(n, 700.0) for k, n in
          (("priv", n_priv), ("pub", n_pub), ("inter", n_goods),
           ("nature", n_goods), ("labor", n_goods))}
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)
    output, x, d_priv, d_pub = proposals(wc, cc, p0, n_cc, tot_exp, precomp)
    _, dem0 = aggregate(wc, output, x, d_priv, d_pub, n_priv, n_pub, n_goods, n_cc, 0.0)

    print("\n=== First-round demand at the initial price of 700 ===")
    for key in ("labor", "nature", "inter", "priv", "pub"):
        d = dem0[key]
        print(f"  {key:<7} mean={d.mean():>14,.1f}  median={np.median(d):>14,.1f}  "
              f"min={d.min():>12,.1f}  max={d.max():>14,.1f}")
    balanced = float(np.median(np.concatenate([dem0["labor"], dem0["nature"]])))
    print(f"\n  S that balances labor and nature at the initial price ~ {balanced:,.0f}")

    # ---- Search
    cands = sorted({1e3, 3e3, 1e4, 3e4,
                    balanced / 10, balanced / 3, balanced, balanced * 3, balanced * 10})
    print(f"\n=== Search: {len(cands)} endowments x {len(MODES)} price-update rules ===")
    print(f"{'endowment S':>14}  {'rule':<12} {'cold5%':>7} {'cold3%':>7} {'warm5%':>7}")
    print("-" * 56)
    best = []
    for S in cands:
        for mode in MODES:
            t0 = time.perf_counter()
            n1, p1, w1 = run(wc, cc, dims, S, mode, 5.0)
            if n1 is None:
                print(f"{S:>14,.0f}  {mode:<12} {'>250':>7} {'-':>7} {'-':>7}   (worst {w1:.0f}%)", flush=True)
                continue
            n3, _, _ = run(wc, cc, dims, S, mode, 3.0)
            rng = np.random.default_rng(0)
            wc2, cc2 = augmented_reset(wc, cc, rng)
            n2, _, w2 = run(wc2, cc2, dims, S, mode, 5.0, p0=p1)
            print(f"{S:>14,.0f}  {mode:<12} {n1:>7} {str(n3 or '>250'):>7} "
                  f"{str(n2 or '>250'):>7}   ({time.perf_counter()-t0:.0f}s)", flush=True)
            best.append((abs(n1 - 11.85), S, mode, n1, n3, n2))

    print("\n=== Configurations closest to the 2020 reported values (cold 11.85 / cold3% 19.2 / warm 6.5) ===")
    for _, S, mode, n1, n3, n2 in sorted(best)[:5]:
        print(f"  S={S:>12,.0f}  {mode:<12} cold5%={n1:<4} cold3%={str(n3 or '>250'):<5} warm5%={str(n2 or '>250')}")
