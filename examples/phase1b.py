"""Phase 1b smoke test: the full core 2D mark vocabulary - line+marker,
scatter, bar, hist, fill_between, errorbar - plus auto-legends whose glyphs
mirror the actual mark styles. Rendered to all three backends."""

import math
import os
import random

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


rng = random.Random(0)

xs = [i * 0.25 for i in range(41)]  # 0 .. 10
sin = [math.sin(x) for x in xs]
cos = [math.cos(x) for x in xs]
band_lo = [s - 0.25 for s in sin]
band_hi = [s + 0.25 for s in sin]

fig, axes = figurs.subplots(2, 2, figsize=(576, 432))
fig.set(suptitle="figurs Phase 1b - core 2D marks")

# (0,0) line + marker + scatter + legend
ax = axes[0][0]
ax.line(xs, sin, color="C0", label="sin(x)", marker="o", markersize=3.5)
ax.line(xs, cos, color="C1", label="cos(x)", linestyle="dashed")
ax.scatter([1, 3, 5, 7, 9], [0.5, -0.3, 0.9, -0.6, 0.2], color="C3",
           marker="^", size=48.0, label="samples")
ax.set(title="Lines & scatter", xlabel="x", ylabel="y")
ax.legend(loc="lower left")

# (0,1) fill_between + center line + legend
ax = axes[0][1]
ax.fill_between(xs, band_lo, band_hi, color="C2", alpha=0.3, label="±0.25 band")
ax.line(xs, sin, color="C2", width=1.75, label="sin(x)")
ax.set(title="Uncertainty band", xlabel="x", ylabel="amplitude")
ax.legend(loc="upper right")

# (1,0) bar chart + legend
ax = axes[1][0]
groups = [1, 2, 3, 4, 5]
ax.bar(groups, [3.0, 7.0, 4.0, 8.0, 5.0], width=0.7, color="C4", label="trial A")
ax.set(title="Bar chart", xlabel="group", ylabel="count")
ax.legend(loc="upper left")

# (1,1) histogram + errorbar overlay + legend
ax = axes[1][1]
data = [rng.gauss(0.0, 1.0) for _ in range(2000)]
ax.hist(data, bins=24, color="C5", label="samples", density=True)
ex = [-2.0, -1.0, 0.0, 1.0, 2.0]
ey = [0.05, 0.24, 0.40, 0.24, 0.05]
ax.errorbar(ex, ey, yerr=[0.02, 0.03, 0.03, 0.03, 0.02], color="C7",
            marker="s", markersize=4.0, capsize=3.0, label="model ± σ")
ax.set(title="Histogram + errorbar", xlabel="value", ylabel="density")
ax.legend(loc="upper right")

fig.save(out("phase1b.pdf"))
fig.save(out("phase1b.svg"))
fig.save(out("phase1b.png"))
print("done ->", _OUT)
