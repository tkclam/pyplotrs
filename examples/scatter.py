"""Scatter plot with marker styling."""
import math
import pyplotrs as plt

n = 80
xs = [i / n * 6 for i in range(n)]
ys = [math.sin(x) + 0.15 * math.cos(7 * x) for x in xs]
fig, ax = plt.subplots()
ax.scatter(xs, ys, markersize=6.3, marker="o", color="C0",
           edgecolor=(255, 255, 255, 255), edgewidth=0.8)
ax.set(title="Scatter plot", xlabel="x", ylabel="y")
fig.save("scatter.png")
