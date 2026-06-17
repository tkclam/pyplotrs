"""Phase 1d smoke test: basic 3D via the projection layer - a colormapped
surface, a 3D parametric line, and a depth-sorted 3D scatter. All three are
projected to ordinary 2D paths and flow through the same PDF/SVG/raster
backends (so the axis tick/label text stays real, editable text)."""

import math
import os
import random

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


rng = random.Random(1)

# --- surface: a "sombrero" sinc-like bump ----------------------------------
n = 40
xs1d = [-3.0 + 6.0 * i / (n - 1) for i in range(n)]
ys1d = [-3.0 + 6.0 * j / (n - 1) for j in range(n)]


def surf_z(x, y):
    r = math.sqrt(x * x + y * y)
    return math.sin(r * 1.6) / (1.0 + r)


Z = [[surf_z(x, y) for x in xs1d] for y in ys1d]

# --- 3D line: a helix ------------------------------------------------------
tt = [i * 0.1 for i in range(160)]
hx = [math.cos(t) for t in tt]
hy = [math.sin(t) for t in tt]
hz = [t / 16.0 for t in tt]

# --- 3D scatter: a noisy cloud ---------------------------------------------
sx = [rng.gauss(0, 1) for _ in range(120)]
sy = [rng.gauss(0, 1) for _ in range(120)]
sz = [rng.gauss(0, 1) for _ in range(120)]

fig, axes = figurs.subplots(1, 2, figsize=(648, 302), projection="3d")
fig.set(suptitle="figurs Phase 1d - basic 3D")

axes[0].surface(xs1d, ys1d, Z, cmap="viridis")
axes[0].plot(hx, hy, [z - 0.5 for z in hz], color="C7", width=1.5)
axes[0].set(title="surface + helix", xlabel="x", ylabel="y", zlabel="z")

axes[1].scatter(sx, sy, sz, color="C3", marker="o", size=26.0)
axes[1].set(title="3D scatter", xlabel="x", ylabel="y", zlabel="z", elev=24.0, azim=-50.0)

fig.save(out("phase1d.pdf"))
fig.save(out("phase1d.svg"))
fig.save(out("phase1d.png"))
print("done ->", _OUT)
