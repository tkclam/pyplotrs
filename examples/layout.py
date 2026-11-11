"""Uneven layouts: mosaics, twin axes and insets."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)
rng = np.random.default_rng(4)

fig, axd = pp.subplot_mosaic("AAB;CDB", figsize=(400, 260))
t = np.linspace(0, 24, 300)
axd["A"].line(t, 20 + 5 * np.sin(t / 24 * 2 * np.pi), label="temperature")
humidity = axd["A"].twinx()
humidity.line(t, 60 + 10 * np.cos(t / 24 * 2 * np.pi), color="C1", label="humidity")
axd["A"].set(title="Twin y axes", ylabel="°C")
humidity.set(ylabel="%")
axd["A"].legend("lower left")

axd["B"].hexbin(rng.normal(size=3000), rng.normal(size=3000), gridsize=15, cmap="cividis")
axd["B"].set(title="hexbin", aspect="equal")
axd["C"].stackplot(t, np.abs(np.sin(t / 4)), np.abs(np.cos(t / 5)), labels=["a", "b"])
axd["C"].set(title="stackplot")
main = axd["D"]
main.line(t, np.sin(t))
inset = main.inset_axes((0.55, 0.55, 0.4, 0.4))
inset.line(t[:40], np.sin(t[:40]), color="C3")
main.set(title="inset")
fig.save(out / "layout.png")
