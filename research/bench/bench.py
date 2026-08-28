"""
两个基准：
A. 复现 pe_ifb_compute 的 SQLite 加载路径（每行 commit）与批量提交的对照。
B. 用 numpy 实现 pequod-plus 一轮迭代的等价计算，测其真实算术成本。

只测量级，不追求精确。
"""
import os
import sqlite3
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS = 20_000  # 每行 commit 的路径很慢，用两万行取速率后外推


# ---------------------------------------------------------------- 实验 A

def make_rows(path, n):
    rng = np.random.default_rng(0)
    with open(path, "w") as f:
        for i in range(n):
            f.write(f"{i % 500 + 1},{i % 100 + 1},{rng.integers(1, 11)}\n")


def load_per_row_commit(db, txt):
    """逐字照搬 pe_ifb_compute/src/core.py 的 load_data_to_sqlite_db。"""
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
        con.commit()          # <- 原代码就在循环里
    product_file.close()
    con.close()


def load_batched(db, txt):
    """唯一的改动：commit 移出循环，并用 executemany。"""
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
    print(f"实验 A: SQLite 加载路径对照（{ROWS:,} 行）")
    print("=" * 70)

    txt = os.path.join(HERE, "rows.txt")
    make_rows(txt, ROWS)

    results = {}
    for name, fn in (("每行 commit（原代码）", load_per_row_commit),
                     ("批量 commit", load_batched)):
        db = os.path.join(HERE, f"a_{'per' if 'commit（' in name else 'batch'}.db")
        if os.path.exists(db):
            os.remove(db)
        t0 = time.perf_counter()
        fn(db, txt)
        dt = time.perf_counter() - t0
        results[name] = dt
        print(f"  {name:<24} {dt:8.3f} s   ({ROWS / dt:>12,.0f} 行/秒)")

    slow, fast = results["每行 commit（原代码）"], results["批量 commit"]
    print(f"\n  倍数差: {slow / fast:.0f}x")

    # 按 pe_ifb_compute 自己的 exp=6 目标规模外推
    # population 1e6，议会均 ~76 人 -> ~13,158 个议会；每议会 1e6 个产品行
    target = 13_158 * 1_000_000
    print(f"\n  外推到该仓库自述的目标规模（100 万产品 / 100 万人 = {target:,} 行/表）：")
    print(f"    每行 commit : {target / (ROWS / slow) / 86400:>12,.0f} 天")
    print(f"    批量 commit : {target / (ROWS / fast) / 86400:>12,.1f} 天")
    print("    (注：该规模本身就不现实，此处只为显示两条路径的量级差)")


# ---------------------------------------------------------------- 实验 B

N_WC = 30_000
N_CC = 30_000
N_GOODS = 100
MAX_IN = 10


def build_economy(seed=0):
    rng = np.random.default_rng(seed)

    # --- 消费议会：每个议会对 100 种私人品 + 100 种公共品有指数
    cc = {
        "income": np.full(N_CC, 5000.0),
        "priv_exp": rng.uniform(0.005, 0.010, (N_CC, N_GOODS)),
        "pub_exp": rng.uniform(0.005, 0.010, (N_CC, N_GOODS)),
    }

    # --- 工人议会：每个 3~10 个投入品，用掩码补齐到 10 列
    n_inputs = rng.integers(3, MAX_IN + 1, N_WC)
    mask = np.arange(MAX_IN)[None, :] < n_inputs[:, None]
    b = np.zeros((N_WC, MAX_IN))
    # 指数按 populate.clj: U(0.75/n, 0.85/n)
    lo = (0.75 / n_inputs)[:, None]
    hi = (0.85 / n_inputs)[:, None]
    b[mask] = (lo + (hi - lo) * rng.random((N_WC, MAX_IN)))[mask]

    wc = {
        "a": rng.uniform(4, 6, N_WC),            # 全要素生产率
        "c": rng.uniform(0.05, 0.10, N_WC),      # 努力弹性
        "k": rng.uniform(3, 4, N_WC),            # 努力负效用指数
        "s": np.ones(N_WC),                      # 努力负效用系数
        "b": b,
        "mask": mask,
        "coef": rng.integers(0, N_GOODS, (N_WC, MAX_IN)),   # 投入品是哪一种
        "industry": rng.integers(0, 3, N_WC),
        "product": rng.integers(0, N_GOODS, N_WC),
    }
    return wc, cc


def one_iteration(wc, cc, prices):
    """一轮：WC 出提案 -> CC 出提案 -> 聚合供需 -> 调价。"""
    p_priv, p_pub, p_inter = prices["priv"], prices["pub"], prices["inter"]

    # ---- WC 侧：闭式解（通用 n 元形式，与展开式等价）
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

    # ---- CC 侧：柯布-道格拉斯需求
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)
    d_priv = (cc["income"][:, None] * cc["priv_exp"]) / (tot_exp[:, None] * p_priv[None, :])
    d_pub = (cc["income"][:, None] * cc["pub_exp"]) / (tot_exp[:, None] * p_pub[None, :])

    # ---- 聚合
    supply_priv = np.bincount(wc["product"][wc["industry"] == 0],
                              weights=output[wc["industry"] == 0], minlength=N_GOODS)
    supply_inter = np.bincount(wc["product"][wc["industry"] == 1],
                               weights=output[wc["industry"] == 1], minlength=N_GOODS)
    supply_pub = np.bincount(wc["product"][wc["industry"] == 2],
                             weights=output[wc["industry"] == 2], minlength=N_GOODS)
    demand_inter = np.bincount(wc["coef"][mask], weights=x[mask], minlength=N_GOODS)
    demand_priv = d_priv.sum(axis=0)
    demand_pub = d_pub.sum(axis=0) / N_CC

    # ---- 调价
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
    print(f"实验 B: numpy 参考实现，{N_WC:,} WC × {N_CC:,} CC × {N_GOODS} 商品")
    print("=" * 70)

    t0 = time.perf_counter()
    wc, cc = build_economy()
    print(f"  构造经济体          {time.perf_counter() - t0:8.3f} s")

    nbytes = sum(v.nbytes for v in cc.values() if isinstance(v, np.ndarray))
    nbytes += sum(v.nbytes for v in wc.values() if isinstance(v, np.ndarray))
    print(f"  全经济体常驻内存    {nbytes / 1e6:8.1f} MB")

    prices = {"priv": np.full(N_GOODS, 700.0),
              "pub": np.full(N_GOODS, 700.0),
              "inter": np.full(N_GOODS, 700.0)}

    one_iteration(wc, cc, prices)          # 预热

    reps = 10
    t0 = time.perf_counter()
    for _ in range(reps):
        prices = one_iteration(wc, cc, prices)
    dt = (time.perf_counter() - t0) / reps
    print(f"  单轮迭代            {dt * 1000:8.1f} ms   (单线程 numpy)")
    print(f"  100 轮合计          {dt * 100:8.2f} s")


if __name__ == "__main__":
    run_a()
    run_b()
    print("\n完成。")
