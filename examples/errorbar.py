"""Error bars with caps."""
import math
import pyplotrs as plt

xs = list(range(1, 9))
ys = [math.log(x) for x in xs]
yerr = [0.08 + 0.02 * x for x in xs]
fig, ax = plt.subplots()
ax.errorbar(xs, ys, yerr=yerr, marker="o", capsize=4, color="C5", label="measured")
ax.set(title="Error bars", xlabel="x", ylabel="log(x)")
ax.legend()
fig.save("errorbar.png")
