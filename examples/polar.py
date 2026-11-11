"""Polar axes."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

theta = np.linspace(0, 2 * np.pi, 360)
fig, ax = pp.subplots(projection="polar")
ax.line(theta, 1 + 0.4 * np.cos(4 * theta), label="rose")
ax.fill(theta, 0.6 + 0.2 * np.sin(theta), color="C2")
ax.scatter(theta[::30], np.full(12, 1.3), color="C1")
ax.set(title="Preferred direction", theta_zero="N", theta_direction=-1, rmax=1.5)
ax.legend()
fig.save(out / "polar.png")
