"""
Two benchmarks:
A. Compares pe_ifb_compute's SQLite loading path (commit per row) against a batched commit.
B. A numpy implementation equivalent to one pequod-plus iteration round, timing its real
   arithmetic cost.

Order-of-magnitude only, not precision.
"""
import os
import sqlite3
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = 20_000  # the commit-per-row path is slow; measure a rate on 20k rows and extrapolate


# ---------------------------------------------------------------- Experiment A

def make_rows(path, n):
    rng = np.random.default_rng(0)
    with open(path, "w") as f:
        for i in range(n):
            f.write(f"{i % 500 + 1},{i % 100 + 1},{rng.integers(1, 11)}\n")


def load_per_row_commit(db, txt):
    """Verbatim copy of load_data_to_sqlite_db from pe_ifb_compute/src/core.py."""
    product_file = open(txt, "r")
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("CREATE TABLE wc_products(council_id, product_id, quantity)")
    cur.execute("CREATE INDEX wc_product_id_index on wc_products(product_id)")
    while True:
        L = product_file.readline()
        if not L:
            break
        d = L.strip().split(",")
        cur.execute("INSERT INTO wc_products VALUES(?, ?, ?)", [d[0], d[1], d[2]])
        con.commit()          # <- this is where the original code puts it, inside the loop
    product_file.close()
    con.close()


def load_batched(db, txt):
    """The only change: commit moved outside the loop, using executemany."""
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("CREATE TABLE wc_products(council_id, product_id, quantity)")
    cur.execute("CREATE INDEX wc_product_id_index on wc_products(product_id)")
    with open(txt) as f:
        rows = [l.strip().split(",") for l in f if l.strip()]
    cur.executemany("INSERT INTO wc_products VALUES(?, ?, ?)", rows)
    con.commit()
    con.close()


def run_a():
    print("=" * 70)
    print(f"Experiment A: SQLite loading path comparison ({ROWS:,} rows)")
    print("=" * 70)

    txt = os.path.join(HERE, "rows.txt")
    make_rows(txt, ROWS)

    results = {}
    for name, fn in (("per-row commit (original code)", load_per_row_commit),
                     ("batch commit", load_batched)):
        db = os.path.join(HERE, f"a_{'per' if '(original code)' in name else 'batch'}.db")
        if os.path.exists(db):
            os.remove(db)
        t0 = time.perf_counter()
        fn(db, txt)
        dt = time.perf_counter() - t0
        results[name] = dt
        print(f"  {name:<24} {dt:8.3f} s   ({ROWS / dt:>12,.0f} rows/s)")

    slow, fast = results["per-row commit (original code)"], results["batch commit"]
    print(f"\n  Ratio: {slow / fast:.0f}x")

    # Extrapolated to pe_ifb_compute's own exp=6 target scale:
    # population 1e6, ~76 members per council -> ~13,158 councils; 1e6 product rows per council
    target = 13_158 * 1_000_000
    print(f"\n  Extrapolated to the repo's stated target scale (1M products / 1M people = {target:,} rows/table):")
    print(f"    per-row commit : {target / (ROWS / slow) / 86400:>12,.0f} days")
    print(f"    batch commit   : {target / (ROWS / fast) / 86400:>12,.1f} days")
    print("    (note: this scale itself is unrealistic; it's only here to show the order-of-magnitude gap between the two paths)")


# ---------------------------------------------------------------- Experiment B

N_WC = 30_000
N_CC = 30_000
N_GOODS = 100
MAX_IN = 10


def build_economy(seed=0):
    rng = np.random.default_rng(seed)

    # --- Consumer councils: each has exponents over 100 private goods + 100 public goods
    cc = {
        "income": np.full(N_CC, 5000.0),
        "priv_exp": rng.uniform(0.005, 0.010, (N_CC, N_GOODS)),
        "pub_exp": rng.uniform(0.005, 0.010, (N_CC, N_GOODS)),
    }

    # --- Worker councils: each has 3-10 inputs, padded to 10 columns with a mask
    n_inputs = rng.integers(3, MAX_IN + 1, N_WC)
    mask = np.arange(MAX_IN)[None, :] < n_inputs[:, None]
    b = np.zeros((N_WC, MAX_IN))
    # exponents follow populate.clj: U(0.75/n, 0.85/n)
    lo = (0.75 / n_inputs)[:, None]
    hi = (0.85 / n_inputs)[:, None]
    b[mask] = (lo + (hi - lo) * rng.random((N_WC, MAX_IN)))[mask]

    wc = {
        "a": rng.uniform(4, 6, N_WC),            # total factor productivity
        "c": rng.uniform(0.05, 0.10, N_WC),      # effort elasticity
        "k": rng.uniform(3, 4, N_WC),            # effort disutility exponent
        "s": np.ones(N_WC),                      # effort disutility coefficient
        "b": b,
        "mask": mask,
        "coef": rng.integers(0, N_GOODS, (N_WC, MAX_IN)),   # which good each input is
        "industry": rng.integers(0, 3, N_WC),
        "product": rng.integers(0, N_GOODS, N_WC),
    }
    return wc, cc


def one_iteration(wc, cc, prices):
    """One round: WC proposals -> CC proposals -> aggregate supply and demand -> update prices."""
    p_priv, p_pub, p_inter = prices["priv"], prices["pub"], prices["inter"]

    # ---- WC side: closed-form solution (general n-input form, equivalent to the expanded one)
    lam = np.where(wc["industry"] == 0, p_priv[wc["product"]],
          np.where(wc["industry"] == 1, p_inter[wc["product"]],
                                        p_pub[wc["product"]]))
    a, c, k, s = wc["a"], wc["c"], wc["k"], wc["s"]
    b, mask = wc["b"], wc["mask"]
    p_in = np.where(mask, p_inter[wc["coef"]], 1.0)

    log_b = np.where(mask, np.log(np.where(mask, b, 1.0)), 0.0)
    log_p = np.where(mask, np.log(p_in), 0.0)
    B = b.sum(axis=1)
    D = c - k + k * B

    num = (-k * np.log(a)
           - k * (b * log_b).sum(axis=1)
           - c * np.log(c) + c * np.log(k)
           + k * (b * log_p).sum(axis=1)
           + c * np.log(s)
           - (c + k * B) * np.log(lam))
    log_Q = num / D
    log_x = log_b + np.log(lam)[:, None] - log_p + log_Q[:, None]
    output = np.exp(log_Q)
    x = np.where(mask, np.exp(log_x), 0.0)

    # ---- CC side: Cobb-Douglas demand
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)
    d_priv = (cc["income"][:, None] * cc["priv_exp"]) / (tot_exp[:, None] * p_priv[None, :])
    d_pub = (cc["income"][:, None] * cc["pub_exp"]) / (tot_exp[:, None] * p_pub[None, :])

    # ---- Aggregation
    supply_priv = np.bincount(wc["product"][wc["industry"] == 0],
                              weights=output[wc["industry"] == 0], minlength=N_GOODS)
    supply_inter = np.bincount(wc["product"][wc["industry"] == 1],
                               weights=output[wc["industry"] == 1], minlength=N_GOODS)
    supply_pub = np.bincount(wc["product"][wc["industry"] == 2],
                             weights=output[wc["industry"] == 2], minlength=N_GOODS)
    demand_inter = np.bincount(wc["coef"][mask], weights=x[mask], minlength=N_GOODS)
    demand_priv = d_priv.sum(axis=0)
    demand_pub = d_pub.sum(axis=0) / N_CC

    # ---- Price update
    out = {}
    for key, sup, dem in (("priv", supply_priv, demand_priv),
                          ("pub", supply_pub, demand_pub),
                          ("inter", supply_inter, demand_inter)):
        surplus = sup - dem
        denom = np.where(sup + dem == 0, 1.0, sup + dem)
        delta = np.clip(1.05 - 0.5 ** (np.abs(2 * surplus) / denom), 0.001, 0.25)
        out[key] = prices[key] * np.where(surplus > 0, 1 - delta, 1 + delta)
    return out


def run_b():
    print()
    print("=" * 70)
    print(f"Experiment B: numpy reference implementation, {N_WC:,} WC x {N_CC:,} CC x {N_GOODS} goods")
    print("=" * 70)

    t0 = time.perf_counter()
    wc, cc = build_economy()
    print(f"  build economy       {time.perf_counter() - t0:8.3f} s")

    nbytes = sum(v.nbytes for v in cc.values() if isinstance(v, np.ndarray))
    nbytes += sum(v.nbytes for v in wc.values() if isinstance(v, np.ndarray))
    print(f"  full economy in RAM {nbytes / 1e6:8.1f} MB")

    prices = {"priv": np.full(N_GOODS, 700.0),
              "pub": np.full(N_GOODS, 700.0),
              "inter": np.full(N_GOODS, 700.0)}

    one_iteration(wc, cc, prices)          # warm-up

    reps = 10
    t0 = time.perf_counter()
    for _ in range(reps):
        prices = one_iteration(wc, cc, prices)
    dt = (time.perf_counter() - t0) / reps
    print(f"  one round           {dt * 1000:8.1f} ms   (single-threaded numpy)")
    print(f"  100 rounds total    {dt * 100:8.2f} s")


if __name__ == "__main__":
    run_a()
    run_b()
    print("\nDone.")
