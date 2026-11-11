"""A spike raster with a peri-stimulus time histogram."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)
rng = np.random.default_rng(3)

trials = []
for _ in range(40):
    base = rng.uniform(-0.5, 1.5, rng.poisson(15))
    evoked = rng.normal(0.15, 0.05, rng.poisson(8))
    trials.append(np.sort(np.concatenate([base, evoked])))

fig, (raster, psth) = pp.subplots(2, 1, figsize=(250, 220), sharex=True, height_ratios=[2, 1])
raster.eventplot(trials, linewidth=0.8)
raster.axvspan(0, 0.3, color="C1", alpha=0.15)
raster.set(ylabel="trial", title="Evoked response", margin=0.01)
psth.hist(np.concatenate(trials), bins=np.arange(-0.5, 1.51, 0.05), color="C5")
psth.axvline(0, linestyle=":")
psth.set(xlabel="time from stimulus (s)", ylabel="spikes")
fig.save(out / "neuroscience.png")
