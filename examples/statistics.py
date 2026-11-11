"""Distributions: histograms, box and violin plots, error bars."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)
rng = np.random.default_rng(2)
groups = [rng.normal(m, s, 200) for m, s in ((0, 1), (1.5, 0.6), (0.5, 1.4))]

fig, (h, bx, er) = pp.subplots(1, 3, figsize=(480, 170))
for i, g in enumerate(groups):
    h.hist(g, bins=25, alpha=0.6, label=f"group {i + 1}")
h.legend()
h.set(title="Histogram", ylabel="count")

bx.boxplot(groups, color="C5")
bx.violinplot(groups, positions=[1, 2, 3], color="C1", alpha=0.25)
bx.set(title="Box + violin", xticks=[1, 2, 3], xticklabels=["A", "B", "C"])

doses = np.array([1, 2, 5, 10, 20])
er.errorbar(doses, np.log(doses) + 1, yerr=0.2 + 0.05 * doses, linestyle="-", capsize=3)
er.set(title="Dose response", xscale="log", xlabel="dose (µM)")
fig.save(out / "statistics.png")
