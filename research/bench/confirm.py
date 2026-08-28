"""
交叉验证：2020 幻灯片的调价规则 + 论文明写的禀赋 1000，能否重现已发表结果。

目标值（2020 幻灯片第 7 页，40 组实验的平均）：
  冷启动 5% 阈值 11.85 轮 · 冷启动 3% 阈值 19.2 轮 · 热启动 5% 阈值 6.5 轮
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
    print(f"\n规则 = {MODE}   禀赋 S = {S:,.0f}\n")
    print(f"{'实验':<10} {'冷5%':>6} {'冷3%':>6} {'热5%（三个种子）':>22}")
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
    print(f"{'均值':<10} {np.mean(cold5):>6.2f} {np.mean(cold3):>6.2f} {np.mean(warm):>10.2f}")
    print(f"{'2020 报告':<10} {11.85:>6} {19.2:>6} {6.5:>10}")

    print(f"\n=== 禀赋敏感度（dep1ex01，规则 {MODE}）===")
    wc, cc, dims = cache[FILES[0]]
    print(f"{'S':>8} {'冷5%':>6} {'冷3%':>6}")
    for s in (250, 500, 700, 1000, 1400, 2000, 4000):
        n1, _, w1 = E.run(wc, cc, dims, float(s), MODE, 5.0)
        n3, _, _ = E.run(wc, cc, dims, float(s), MODE, 3.0)
        print(f"{s:>8} {str(n1 or f'>250'):>6} {str(n3 or '>250'):>6}")

    print(f"\n=== 同一实验换调价规则（dep1ex01，S={S:,.0f}）===")
    for mode in ("paper2023", "slides_capv", "slides_capw"):
        t0 = time.perf_counter()
        n1, _, w1 = E.run(wc, cc, dims, S, mode, 5.0)
        print(f"  {mode:<14} 冷5% = {str(n1 or '>250 未收敛'):<12} "
              f"最差失衡 {w1:.1f}%   {time.perf_counter()-t0:.0f}s")
