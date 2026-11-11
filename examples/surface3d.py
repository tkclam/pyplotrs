"""A 3D surface; the HTML version can be rotated in a browser."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

x = np.linspace(-2, 2, 40)
X, Y = np.meshgrid(x, x)
Z = np.exp(-(X**2 + Y**2)) * np.cos(2 * X)
fig, ax = pp.subplots(projection="3d", figsize=(280, 240))
ax.surface(X, Y, Z, cmap="viridis")
t = np.linspace(0, 4 * np.pi, 200)
ax.line(1.5 * np.cos(t), 1.5 * np.sin(t), t / 12 - 0.5, color="C6", label="helix")
ax.set(title="Surface", xlabel="x", ylabel="y", zlabel="z", elev=25)
ax.legend()
fig.save(out / "surface3d.png")
fig.save(out / "surface3d.html")
