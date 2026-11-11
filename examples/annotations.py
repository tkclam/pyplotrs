"""Text, arrows, rich text and math."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

x = np.linspace(0, 2, 200)
y = x**2 * np.exp(-2 * x)
fig, ax = pp.subplots(figsize=(280, 200))
ax.line(x, y)
peak = x[np.argmax(y)]
ax.annotate("maximum", (peak, y.max()), (1.5, 0.12))
ax.axvline(peak, linestyle=":", color="C3")
ax.text(
    0.45,
    0.1,
    pp.rich("growth ", pp.bold("+42%", color="C3"), " ", pp.mark("highlighted")),
    coords="axes",
)
ax.set(title=r"$f(x) = x^2 e^{-2x}$", xlabel=r"$x$ ($\mu$m)", ylabel=r"$\frac{\Delta F}{F_0}$")
fig.save(out / "annotations.png")
fig.save(out / "annotations.svg")
