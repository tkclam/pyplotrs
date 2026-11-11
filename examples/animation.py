"""An animated GIF: one figure per frame."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)
x = np.linspace(0, 4 * np.pi, 300)


def frame(i: int) -> pp.Figure:
    fig, ax = pp.subplots(figsize=(250, 150))
    ax.line(x, np.sin(x - i / 5) * np.exp(-x / 10))
    ax.set(ylim=(-1.1, 1.1), title=f"t = {i / 20:.2f} s")
    return fig


pp.animate(frame, frames=30, fps=20).save(out / "animation.gif")
