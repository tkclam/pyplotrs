"""Lines, markers and a legend: the basics."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

t = np.linspace(0, 4 * np.pi, 400)
fig, ax = pp.subplots()
ax.line(t, np.exp(-t / 8) * np.cos(t), label="damped")
ax.line(t, np.exp(-t / 8), linestyle="--", label="envelope")
ax.scatter(t[::25], np.exp(-t[::25] / 8) * np.cos(t[::25]), size=4)
ax.set(title="Damped oscillation", xlabel="time (s)", ylabel="amplitude")
ax.legend()

fig.save(out / "quickstart.png")
fig.save(out / "quickstart.pdf")  # vector, with selectable text
