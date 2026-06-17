"""Phase 1a smoke test: multi-axes grid, real ticks, rotated y-label,
dashed lines, shared y-axis, suptitle - rendered to all three backends."""

import math
import os

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


xs = [i * 0.1 for i in range(101)]  # 0 .. 10
sin = [math.sin(x) for x in xs]
cos = [math.cos(x) for x in xs]
damp = [math.exp(-0.25 * x) * math.sin(2 * x) for x in xs]
growth = [1.05**(10 * x) for x in xs]

fig, axes = figurs.subplots(1, 2, figsize=(504, 216), sharey=True)
fig.set(suptitle="figurs Phase 1a")

axes[0].line(xs, sin, color="C0", label="sin(x)")
axes[0].line(xs, cos, color="C1", label="cos(x)", linestyle="dashed")
axes[0].set(title="Trigonometric", xlabel="x", ylabel="amplitude")

axes[1].line(xs, damp, color="C2", label="damped")
axes[1].set(title="Damped oscillation", xlabel="time (s)", ylabel="amplitude")

fig.save(out("phase1a.pdf"))
fig.save(out("phase1a.svg"))
fig.save(out("phase1a.png"))

# A second figure with a non-trivial data range to exercise the tick locator.
fig2, ax = figurs.subplots(figsize=(324, 230))
ax.line([2015, 2016, 2017, 2018, 2019, 2020], [3.1, 17.4, 52.9, 88.0, 143.2, 201.7],
        color="C5")
ax.set(title="Adoption", xlabel="year", ylabel="thousands of users")
fig2.save(out("phase1a_locator.pdf"))
fig2.save(out("phase1a_locator.png"))

print("done ->", _OUT)
