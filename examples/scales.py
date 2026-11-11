"""Axis scales: log, symlog, dates and categories."""

import datetime as dt
import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

fig, ((a, b), (c, d)) = pp.subplots(2, 2, figsize=(380, 280))
f = np.geomspace(1, 1e4, 100)
a.line(f, 1 / np.sqrt(1 + (f / 100) ** 2))
a.set(xscale="log", yscale="log", title="log-log", grid=True)

v = np.linspace(-1000, 1000, 400)
b.line(v, v)
b.set(xscale=pp.scales.Symlog(linthresh=10), title="symlog")

days = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(120)]
c.line(days, np.cumsum(np.random.default_rng(0).normal(size=120)))
c.set(title="dates")

d.barh(["mouse", "fly", "zebrafish", "worm"], [22, 14, 9, 5], color="C2")
d.set(title="categories", xlabel="papers")
fig.save(out / "scales.png")
