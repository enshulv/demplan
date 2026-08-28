import sys, time
import numpy as np

DATA = __import__('pathlib').Path(__file__).resolve().parent.parent / 'data'
import repro

repro.MAX_ITER = 120
wc, cc = repro.parse(str(DATA / "dep1ex01.clj.gz"))
n_priv = cc["priv_exp"].shape[1]; n_pub = cc["pub_exp"].shape[1]
n_goods = int(wc["coef"].max()) + 1

print("\n禀赋 S      模式        收敛轮数")
print("-" * 42)
for S in (1e3, 1e4, 1e5, 1e6, 1e7, 1e8):
    for mode in ("category", "pergood"):
        repro.SUPPLY_NATURE = S; repro.SUPPLY_LABOR = S; repro.DELTA_MODE = mode
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            it, used, thr = repro.run(wc, cc, n_priv, n_pub, n_goods, "x")
        worst = max(np.nanmax(v) for v in thr.values())
        print(f"{S:>9.0e}  {mode:<10}  {('第 '+str(it)+' 轮') if it else f'>120 轮 (最差{worst:.1f}%)'}")
