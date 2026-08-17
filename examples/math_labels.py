"""LaTeX math in titles, axis labels and the legend."""
import math

import pyplotrs as pp

xs = [i * 0.05 for i in range(1, 120)]
fig, ax = pp.subplots()
ax.line(xs, [math.exp(-x) * math.cos(6 * x) for x in xs],
        label=r"$e^{-x}\cos(6x)$")
ax.set(title=r"Damped oscillation $\frac{d^2y}{dt^2}+2\zeta\omega\,\dot y+\omega^2 y=0$",
       xlabel=r"$t\ \mathrm{(s)}$", ylabel=r"$y(t)$")
ax.legend()
fig.save("math_labels.png")
