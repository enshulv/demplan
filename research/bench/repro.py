"""
用作者公开的原始实验数据（szcz.org/depexperiments）重跑参与式计划迭代，
检验已发表的「平均 6.5 轮收敛」这一主张。

数据是 pequod-cljs 的输入经济体（30,000 WC + 30,000 CC + 100 商品）。
算法按 JIE 2023 论文的伪代码与 util.cljc 的 CLJS 路径实现。
"""
import gzip
import re
import sys
import time

import numpy as np

DATA = __import__('pathlib').Path(__file__).resolve().parent.parent / 'data'

THRESHOLD = 5.0        # 论文用的 5% 阈值
MAX_ITER = 300
INIT_PRICE = 700.0
INIT_CAT_DELTA = 0.05
SUPPLY_NATURE = 1000.0
SUPPLY_LABOR = 1000.0
DELTA_MODE = "category"   # category | pergood


def floats(s):
    return np.array(s.split(), dtype=np.float64)


def ints(s):
    return np.array(s.split(), dtype=np.int64)


def parse(path):
    t0 = time.perf_counter()
    with gzip.open(path, "rt") as f:
        text = f.read()
    cut = text.index("(def wcs")
    cc_text, wc_text = text[:cut], text[cut:]
    del text
    print(f"  解压+切分 {time.perf_counter() - t0:.1f}s", flush=True)

    # ---- CC
    t0 = time.perf_counter()
    ue = re.findall(r":utility-exponents\s*\[([^\]]*)\]", cc_text)
    pe = re.findall(r":public-good-exponents\s*\[([^\]]*)\]", cc_text)
    inc = re.findall(r":income\s+([0-9.eE+-]+)", cc_text)
    cc = {
        "priv_exp": np.array([floats(x) for x in ue]),
        "pub_exp": np.array([floats(x) for x in pe]),
        "income": np.array(inc, dtype=np.float64),
    }
    del cc_text
    print(f"  CC 解析  {time.perf_counter() - t0:.1f}s  "
          f"{cc['priv_exp'].shape=} {cc['pub_exp'].shape=} "
          f"income[0]={cc['income'][0]}", flush=True)

    # ---- WC
    t0 = time.perf_counter()
    pi = re.findall(r":production-inputs\s*\[\[([^\]]*)\]\s*\[([^\]]*)\]\s*\[([^\]]*)\]\]", wc_text)
    ie = re.findall(r":input-exponents\s*\[([^\]]*)\]", wc_text)
    ne = re.findall(r":nature-exponents\s*\[([^\]]*)\]", wc_text)
    le = re.findall(r":labor-exponents\s*\[([^\]]*)\]", wc_text)
    a = np.array(re.findall(r":a\s+([0-9.eE+-]+)", wc_text), dtype=np.float64)
    c = np.array(re.findall(r":c\s+([0-9.eE+-]+)", wc_text), dtype=np.float64)
    s = np.array(re.findall(r":s\s+([0-9.eE+-]+)", wc_text), dtype=np.float64)
    du = np.array(re.findall(r":du\s+([0-9.eE+-]+)", wc_text), dtype=np.float64)
    ind = np.array(re.findall(r":industry\s+(\d+)", wc_text), dtype=np.int64)
    prod = np.array(re.findall(r":product\s+(\d+)", wc_text), dtype=np.int64)
    del wc_text
    n_wc = len(pi)
    print(f"  WC 解析  {time.perf_counter() - t0:.1f}s  n_wc={n_wc} "
          f"a={len(a)} c={len(c)} du={len(du)} ind={len(ind)}", flush=True)

    # 变长投入 -> padding 成矩阵
    ii = [ints(x[0]) for x in pi]
    nn = [ints(x[1]) for x in pi]
    ll = [ints(x[2]) for x in pi]
    ie = [floats(x) for x in ie]
    ne = [floats(x) for x in ne]
    le = [floats(x) for x in le]

    counts = np.array([len(x) + len(y) + len(z) for x, y, z in zip(ii, nn, ll)])
    bad = [i for i in range(n_wc)
           if len(ii[i]) != len(ie[i]) or len(nn[i]) != len(ne[i]) or len(ll[i]) != len(le[i])]
    print(f"  投入品数 分布={dict(zip(*np.unique(counts, return_counts=True)))} "
          f"长度不一致记录={len(bad)}", flush=True)

    W = counts.max()
    coef = np.zeros((n_wc, W), dtype=np.int64)
    b = np.zeros((n_wc, W))
    cat = np.full((n_wc, W), -1, dtype=np.int8)   # 0=中间品 1=自然 2=劳动
    for i in range(n_wc):
        segs = [(ii[i], ie[i], 0), (nn[i], ne[i], 1), (ll[i], le[i], 2)]
        j = 0
        for ids, exps, k in segs:
            m = min(len(ids), len(exps))
            coef[i, j:j + m] = ids[:m]
            b[i, j:j + m] = exps[:m]
            cat[i, j:j + m] = k
            j += m
    mask = cat >= 0

    print(f"  product 范围=[{prod.min()},{prod.max()}]  "
          f"coef 范围=[{coef[mask].min()},{coef[mask].max()}]", flush=True)
    # 数据中商品编号从 1 开始，统一改成 0-based
    coef = np.where(mask, coef - 1, 0)
    prod = prod - 1

    wc = {"a": a, "c": c, "s": s, "k": du, "industry": ind, "product": prod,
          "coef": coef, "b": b, "cat": cat, "mask": mask}
    return wc, cc


def run(wc, cc, n_priv, n_pub, n_goods, label):
    global DELTA_MODE
    n_cc = len(cc["income"])
    p = {"priv": np.full(n_priv, INIT_PRICE),
         "pub": np.full(n_pub, INIT_PRICE),
         "inter": np.full(n_goods, INIT_PRICE),
         "nature": np.full(n_goods, INIT_PRICE),
         "labor": np.full(n_goods, INIT_PRICE)}
    cat_delta = {k: INIT_CAT_DELTA for k in p}
    pd_prev = {k: np.full_like(v, 0.25) for k, v in p.items()}

    a, c, s, k = wc["a"], wc["c"], wc["s"], wc["k"]
    b, mask, cat, coef = wc["b"], wc["mask"], wc["cat"], wc["coef"]
    ind, prod = wc["industry"], wc["product"]
    B = b.sum(axis=1)
    D = c - k + k * B
    log_b = np.where(mask, np.log(np.where(mask, b, 1.0)), 0.0)
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)

    t0 = time.perf_counter()
    for it in range(1, MAX_ITER + 1):
        # --- 投入价格：按类别取
        p_in = np.where(cat == 0, p["inter"][coef],
                np.where(cat == 1, p["nature"][coef],
                np.where(cat == 2, p["labor"][coef], 1.0)))
        p_in = np.where(mask, p_in, 1.0)
        log_p = np.where(mask, np.log(p_in), 0.0)

        lam = np.where(ind == 0, p["priv"][prod % n_priv],
              np.where(ind == 1, p["inter"][prod % n_goods],
                                 p["pub"][prod % n_pub]))
        log_lam = np.log(lam)

        # --- WC 闭式解
        num = (-k * np.log(a) - k * (b * log_b).sum(axis=1)
               - c * np.log(c) + c * np.log(k)
               + k * (b * log_p).sum(axis=1) + c * np.log(s)
               - (c + k * B) * log_lam)
        log_Q = num / D
        output = np.exp(log_Q)
        x = np.where(mask, np.exp(log_b + log_lam[:, None] - log_p + log_Q[:, None]), 0.0)

        # --- CC 需求
        d_priv = (cc["income"][:, None] * cc["priv_exp"]) / (tot_exp[:, None] * p["priv"][None, :])
        d_pub = (cc["income"][:, None] * cc["pub_exp"]) / (tot_exp[:, None] * (p["pub"] / n_cc)[None, :])

        # --- 聚合
        sup, dem = {}, {}
        for key, iid, n in (("priv", 0, n_priv), ("inter", 1, n_goods), ("pub", 2, n_pub)):
            sel = ind == iid
            sup[key] = np.bincount(prod[sel] % n, weights=output[sel], minlength=n)
        sup["nature"] = np.full(n_goods, SUPPLY_NATURE)
        sup["labor"] = np.full(n_goods, SUPPLY_LABOR)

        dem["priv"] = d_priv.sum(axis=0)
        dem["pub"] = d_pub.sum(axis=0) / n_cc
        for key, cid in (("inter", 0), ("nature", 1), ("labor", 2)):
            m = mask & (cat == cid)
            dem[key] = np.bincount(coef[m], weights=x[m],
                                   minlength=n_goods)[:n_goods]

        # --- 阈值
        worst, thr_all, worst_cat = 0.0, {}, None
        for key in p:
            tot = sup[key] + dem[key]
            t = np.where(tot > 0, 100 * np.abs(2 * (sup[key] - dem[key])) / np.where(tot > 0, tot, 1), 0.0)
            thr_all[key] = t
            if np.nanmax(t) > worst:
                worst, worst_cat = np.nanmax(t), key

        if not np.isfinite(worst):
            print(f"  [{label}] 第 {it} 轮出现非有限值，中止")
            return None, it, thr_all

        if worst < THRESHOLD:
            dt = time.perf_counter() - t0
            print(f"  [{label}] 收敛于第 {it} 轮  (最差失衡 {worst:.2f}%)  用时 {dt:.2f}s")
            return it, it, thr_all

        # --- 调价
        for key in p:
            surplus = sup[key] - dem[key]
            tot = sup[key] + dem[key]
            raw = 1.05 - 0.5 ** np.where(tot > 0, np.abs(2 * surplus) / np.where(tot > 0, tot, 1), 0.0)
            prev = cat_delta[key] if DELTA_MODE == "category" else pd_prev[key]
            d = np.maximum(np.minimum(np.abs(raw * prev), raw), 0.001)
            d = np.minimum(np.abs(d), 0.25)
            p[key] = p[key] * np.where(surplus > 0, 1 - d, np.where(surplus < 0, 1 + d, 1.0))
            pd_prev[key] = d
            m_s, m_d = sup[key].mean(), dem[key].mean()
            cat_delta[key] = abs(surplus.mean() / ((m_s + m_d) / 2)) if (m_s + m_d) else INIT_CAT_DELTA

        if it % 10 == 0 or it <= 3:
            print(f"    ...第 {it} 轮 最差失衡 {worst:.1f}% ({worst_cat})  " + " ".join(f"{kk}={np.nanmax(vv):.1f}" for kk,vv in thr_all.items()), flush=True)

    dt = time.perf_counter() - t0
    print(f"  [{label}] {MAX_ITER} 轮未收敛 (最差失衡 {worst:.2f}%)  用时 {dt:.2f}s")
    return None, MAX_ITER, thr_all


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(DATA / "dep1ex01.clj.gz")
    if len(sys.argv) > 2: DELTA_MODE = sys.argv[2]
    print(f"  price-delta 模式: {DELTA_MODE}", flush=True)
    print(f"=== 解析 {path} ===", flush=True)
    wc, cc = parse(path)
    n_priv = cc["priv_exp"].shape[1]
    n_pub = cc["pub_exp"].shape[1]
    n_goods = int(wc["coef"].max()) + 1
    print(f"  私人品={n_priv} 公共品={n_pub} 投入品编号上界={n_goods} "
          f"WC={len(wc['a'])} CC={len(cc['income'])}", flush=True)
    print(f"=== 迭代（阈值 {THRESHOLD}%）===", flush=True)
    run(wc, cc, n_priv, n_pub, n_goods, path)
