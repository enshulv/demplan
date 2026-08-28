"""
检验假说：已发表的「6.5 轮」是热启动（第二年）数字，不是冷启动（第一年）。

流程完全按 JIE 2023 论文与 util.cljc/augmented-reset：
  第一年：价格全部 700 起，跑到 5% 阈值
  augmented reset：扰动指数，重置轮次计数器，**价格不重置**
  第二年：从第一年的收敛价格接着跑，重新数轮数
"""
import time

import numpy as np

DATA = __import__('pathlib').Path(__file__).resolve().parent.parent / 'data'

import repro

THRESHOLD = 5.0
MAX_ITER = 400
SEED = 0


def iterate(wc, cc, n_priv, n_pub, n_goods, S, p0=None, tag=""):
    n_cc = len(cc["income"])
    p = ({k: v.copy() for k, v in p0.items()} if p0 else
         {"priv": np.full(n_priv, 700.0), "pub": np.full(n_pub, 700.0),
          "inter": np.full(n_goods, 700.0), "nature": np.full(n_goods, 700.0),
          "labor": np.full(n_goods, 700.0)})
    cat_delta = {k: 0.05 for k in p}

    a, c, s, k = wc["a"], wc["c"], wc["s"], wc["k"]
    b, mask, cat, coef = wc["b"], wc["mask"], wc["cat"], wc["coef"]
    ind, prod = wc["industry"], wc["product"]
    B = b.sum(axis=1)
    D = c - k + k * B
    log_b = np.where(mask, np.log(np.where(mask, b, 1.0)), 0.0)
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)

    for it in range(1, MAX_ITER + 1):
        p_in = np.where(cat == 0, p["inter"][coef],
                np.where(cat == 1, p["nature"][coef],
                np.where(cat == 2, p["labor"][coef], 1.0)))
        log_p = np.where(mask, np.log(np.where(mask, p_in, 1.0)), 0.0)
        lam = np.where(ind == 0, p["priv"][prod], np.where(ind == 1, p["inter"][prod], p["pub"][prod]))
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

        worst = 0.0
        for key in p:
            tot = sup[key] + dem[key]
            t = np.where(tot > 0, 100 * np.abs(2 * (sup[key] - dem[key])) / np.where(tot > 0, tot, 1), 0.0)
            worst = max(worst, float(np.nanmax(t)))
        if not np.isfinite(worst):
            return None, p, worst
        if worst < THRESHOLD:
            return it, p, worst

        for key in p:
            surplus = sup[key] - dem[key]
            tot = sup[key] + dem[key]
            raw = 1.05 - 0.5 ** np.where(tot > 0, np.abs(2 * surplus) / np.where(tot > 0, tot, 1), 0.0)
            d = np.minimum(np.maximum(np.minimum(np.abs(raw * cat_delta[key]), raw), 0.001), 0.25)
            p[key] = p[key] * np.where(surplus > 0, 1 - d, np.where(surplus < 0, 1 + d, 1.0))
            m_s, m_d = sup[key].mean(), dem[key].mean()
            cat_delta[key] = abs(surplus.mean() / ((m_s + m_d) / 2)) if (m_s + m_d) else 0.05
    return None, p, worst


def augmented_reset(wc, cc, rng):
    """按论文: WC 指数 +{0,.001,.002,.003,.004}; CC 指数 +{-.002,-.001,0,.001,.002}"""
    wc2 = dict(wc)
    bump = rng.choice([0, 0.001, 0.002, 0.003, 0.004], size=wc["b"].shape)
    wc2["b"] = np.where(wc["mask"], wc["b"] + bump, 0.0)
    cc2 = dict(cc)
    cc2["priv_exp"] = cc["priv_exp"] + rng.choice([-0.002, -0.001, 0, 0.001, 0.002], size=cc["priv_exp"].shape)
    cc2["pub_exp"] = cc["pub_exp"] + rng.choice([-0.002, -0.001, 0, 0.001, 0.002], size=cc["pub_exp"].shape)
    return wc2, cc2


if __name__ == "__main__":
    wc, cc = repro.parse(str(DATA / "dep1ex01.clj.gz"))
    n_priv, n_pub = cc["priv_exp"].shape[1], cc["pub_exp"].shape[1]
    n_goods = int(wc["coef"].max()) + 1

    print("\n禀赋 S     第一年(冷启动)   第二年(热启动)   备注")
    print("-" * 62)
    for S in (1e3, 1e4, 1e5):
        t0 = time.perf_counter()
        n1, p1, w1 = iterate(wc, cc, n_priv, n_pub, n_goods, S)
        if n1 is None:
            print(f"{S:>8.0e}   未收敛({w1:.0f}%)      --              第一年就没到阈值")
            continue
        rng = np.random.default_rng(SEED)
        wc2, cc2 = augmented_reset(wc, cc, rng)
        n2, _, w2 = iterate(wc2, cc2, n_priv, n_pub, n_goods, S, p0=p1)
        dt = time.perf_counter() - t0
        n2s = str(n2) if n2 else f"未收敛({w2:.0f}%)"
        print(f"{S:>8.0e}   {n1:>10}      {n2s:>10}       {dt:.0f}s")
