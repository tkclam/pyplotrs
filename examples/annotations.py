"""Text and callout-arrow annotations in data coordinates."""
import math

import pyplotrs as plt

xs = [i * 0.1 for i in range(80)]
ys = [math.sin(x) for x in xs]
peak = max(range(len(xs)), key=lambda i: ys[i])
fig, ax = plt.subplots()
ax.line(xs, ys, color="C0")
ax.annotate("first maximum", (xs[peak], ys[peak]),
            xytext=(xs[peak] + 1.5, ys[peak] + 0.05))
ax.text(4.7, -0.9, r"$y=\sin t$", ha="center", color="C0")
ax.set(title="Annotations", xlabel="t", ylabel="y")
fig.save("annotations.png")
