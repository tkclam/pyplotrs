"""Phase 1c smoke test: imshow heatmaps + colorbars in reserved layout bands.
The colorbar gets its own band from the layout solver (never an overlay), with
its own nice-number ticks and a rotated label. Rendered to all three backends."""

import math
import os

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


# A smooth 2D field: a couple of Gaussian bumps over a sinusoidal ripple.
nx, ny = 80, 64
x0, x1, y0, y1 = -3.0, 3.0, -2.0, 2.0


def field(x, y):
    g1 = math.exp(-((x - 1.0) ** 2 + (y - 0.5) ** 2) / 0.6)
    g2 = -0.7 * math.exp(-((x + 1.2) ** 2 + (y + 0.6) ** 2) / 0.5)
    ripple = 0.25 * math.sin(3.0 * x) * math.cos(2.5 * y)
    return g1 + g2 + ripple


def grid():
    rows = []
    for j in range(ny):
        # row 0 is the top; map j -> y from y1 (top) down to y0 (bottom)
        y = y1 + (y0 - y1) * j / (ny - 1)
        rows.append([field(x0 + (x1 - x0) * i / (nx - 1), y) for i in range(nx)])
    return rows


data = grid()

fig, axes = figurs.subplots(1, 2, figsize=(612, 245))
fig.set(suptitle="figurs Phase 1c - imshow + colorbar")

im0 = axes[0].imshow(data, cmap="viridis", extent=(x0, x1, y0, y1))
axes[0].set(title="viridis", xlabel="x", ylabel="y")
fig.colorbar(im0, label="intensity")

im1 = axes[1].imshow(data, cmap="coolwarm", vmin=-1.0, vmax=1.0, extent=(x0, x1, y0, y1))
axes[1].set(title="coolwarm (diverging)", xlabel="x", ylabel="y")
fig.colorbar(im1, label="value")

fig.save(out("phase1c.pdf"))
fig.save(out("phase1c.svg"))
fig.save(out("phase1c.png"))
print("done ->", _OUT)
