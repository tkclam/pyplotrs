"""Layout tools: a mosaic of spanning panels, a twin y-axis, and an inset."""
import math

import pyplotrs as pp

fig, axd = pp.subplot_mosaic(
    """
    AB
    AC
    """,
    figsize=(560, 320),
)

xs = [i * 0.1 for i in range(200)]

# A spans both rows: a decaying signal with a second series in other units.
signal = [math.exp(-x / 6) * math.sin(2 * x) for x in xs]
axd["A"].line(xs, signal, label="signal (V)")
axd["A"].set(title="spanning panel", xlabel="t (s)", ylabel="volts")

power = axd["A"].twinx()
power.line(xs, [s * s for s in signal], color="C1", label="power (W)")
power.set(ylabel="watts")

# An inset zooms the first oscillation of the same trace.
zoom = axd["A"].inset_axes((0.55, 0.62, 0.4, 0.33))
zoom.line(xs[:40], signal[:40], linewidth=1.0)
zoom.set(xlim=(0, 4))

axd["B"].scatter([math.sin(x) for x in xs], [math.cos(3 * x) for x in xs], markersize=2)
axd["B"].set(title="B")

axd["C"].hist([math.sin(x) * 2 for x in xs], bins=14, color="C3")
axd["C"].set(title="C")

fig.set(suptitle="subplot_mosaic + twinx + inset_axes")
fig.save("layout.png")
