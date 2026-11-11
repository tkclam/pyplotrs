"""A grid of panels with shared axes and panel labels."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)
rng = np.random.default_rng(1)

fig, ((a, b), (c, d)) = pp.subplots(2, 2, figsize=(360, 280))
x = np.linspace(0, 10, 200)
a.line(x, np.sin(x), label="sin")
a.line(x, np.cos(x), label="cos")
a.legend(ncols=2)
b.bar(["WT", "KO", "Rescue"], [3.1, 1.4, 2.7], color="C5")
c.fill_between(x, np.sin(x) - 0.3, np.sin(x) + 0.3, color="C2")
c.line(x, np.sin(x), color="C2")
d.scatter(rng.normal(size=200), rng.normal(size=200), color="C1", size=3, alpha=0.6)

for ax, letter in zip((a, b, c, d), "abcd", strict=True):
    ax.set(title=pp.bold(letter), title_loc="left")  # panel letters
c.set(xlabel="time (s)")
d.set(xlabel="z-score")
fig.set(suptitle="Four panels, aligned automatically")
fig.save(out / "subplots.png")
