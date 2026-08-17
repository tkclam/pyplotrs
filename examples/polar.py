"""Polar plot: line + scatter on a polar projection, with a legend."""
import math

import pyplotrs as pp

theta = [i * math.pi / 180 for i in range(0, 361)]
fig, ax = pp.subplots(projection="polar", figsize=(360, 360))
ax.plot(theta, [abs(math.cos(2 * t)) for t in theta], label="rose  r=|cos 2θ|")
ax.plot(theta, [t / (2 * math.pi) for t in theta], label="spiral", linestyle="dashed")
ax.scatter([0, math.pi / 2, math.pi, 3 * math.pi / 2], [0.9, 0.7, 0.9, 0.7],
           color="C7", label="markers")
ax.set(title="Polar plot")
ax.legend(loc="upper right")
fig.save("polar.png")
