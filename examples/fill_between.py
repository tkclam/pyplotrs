"""Fill between curves: a line with a confidence band."""
import math
import pyplotrs as plt

xs = [i * 0.1 for i in range(80)]
mid = [math.sin(x) for x in xs]
lo = [m - 0.2 - 0.05 * x for m, x in zip(mid, xs)]
hi = [m + 0.2 + 0.05 * x for m, x in zip(mid, xs)]
fig, ax = plt.subplots()
ax.fill_between(xs, lo, hi, color="C0", alpha=0.25, label="±1σ")
ax.line(xs, mid, color="C0", label="mean")
ax.set(title="Confidence band", xlabel="t", ylabel="y")
ax.legend()
fig.save("fill_between.png")
