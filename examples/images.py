"""Fields: images with colorbars, contours and meshes."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

x = np.linspace(-3, 3, 120)
y = np.linspace(-2, 2, 80)
X, Y = np.meshgrid(x, y)
Z = np.sin(X) * np.cos(Y) + 0.3 * X

fig, (a, b) = pp.subplots(1, 2, figsize=(420, 170))
im = a.imshow(
    Z, cmap="RdBu_r", norm=pp.norms.TwoSlopeNorm(0), extent=(-3, 3, -2, 2), origin="lower"
)
fig.colorbar(im, label="anomaly")
a.set(title="imshow + diverging norm")

filled = b.contourf(x, y, Z, levels=10, cmap="viridis")
b.contour(x, y, Z, levels=10, colors="k", linewidth=0.5)
fig.colorbar(filled, label="z")
b.set(title="contourf + contour", aspect="equal")
fig.save(out / "images.png")
