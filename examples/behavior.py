"""A behavior figure: a walking path colored by time, voltage traces with
scale bars, group comparisons with significance brackets, and a broken axis."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)
rng = np.random.default_rng(7)

fig, axd = pp.subplot_mosaic("AB;CD", figsize=(400, 300))

# a: a fly's walking path, colored by time
t = np.linspace(0, 30, 3000)
heading = np.cumsum(rng.normal(0.004, 0.05, t.size))
x, y = np.cumsum(np.cos(heading)) * 0.02, np.cumsum(np.sin(heading)) * 0.02
path = axd["A"].line(x, y, c=t, cmap="viridis", linewidth=1.2)
fig.colorbar(path, label="time (s)")
axd["A"].set(title=pp.bold("a"), title_loc="left", aspect="equal", xlabel="x (mm)", ylabel="y (mm)")

# b: membrane potential traces, with scale bars in place of axes
tt = np.linspace(0, 1, 2000)
for i in range(3):
    v = -60 + 4 * np.sin(2 * np.pi * (3 + i) * tt) + rng.normal(0, 0.4, tt.size)
    axd["B"].line(tt, v + 15 * i, linewidth=0.8)
axd["B"].scalebar(x=0.2, y=5, xlabel="200 ms", ylabel="5 mV")
axd["B"].set(title=pp.bold("b"), title_loc="left", frame=False, ylim=(-80, None))

# c: walking speed by condition, with significance brackets
groups = ["ctrl", "dark", "odor"]
speed = [rng.normal(m, 1.2, 20) for m in (8, 6, 11)]
axd["C"].boxplot(speed, positions=[0, 1, 2])
axd["C"].set(xticks=[0, 1, 2], xticklabels=groups)
axd["C"].bracket(0, 1, 0.003)
axd["C"].bracket(1, 2, 2e-5)
axd["C"].bracket(0, 2, 0.2)
axd["C"].set(title=pp.bold("c"), title_loc="left", ylabel="speed (mm/s)")

# d: bout counts where one behavior dwarfs the rest, on a broken axis
behaviors = ["walk", "groom", "rest", "turn"]
axd["D"].bar(behaviors, [412, 23, 31, 17])
axd["D"].set(ybreak=(40, 390), title=pp.bold("d"), title_loc="left", ylabel="bouts")

fig.save(out / "behavior.png")
