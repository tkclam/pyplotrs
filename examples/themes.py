"""The built-in themes, and deriving your own."""

import os
from pathlib import Path

import numpy as np

import pyplotrs as pp

out = Path(os.environ.get("PYPLOTRS_EXAMPLES_OUT", Path(__file__).parent / "output"))
out.mkdir(exist_ok=True)

x = np.linspace(0, 10, 200)
custom = pp.themes.default.replace(
    grid=True, spines=("left", "bottom", "top", "right"), tick_direction="in", title_weight="bold"
)
for name, theme in [
    ("default", "default"),
    ("dark", "dark"),
    ("grayscale", "grayscale"),
    ("custom", custom),
]:
    fig, ax = pp.subplots(theme=theme)
    for k in range(4):
        ax.line(x, np.sin(x + k / 2), label=f"phase {k}")
    ax.set(title=f"{name} theme", xlabel="x", ylabel="y")
    ax.legend("lower left", ncols=2)
    fig.save(out / f"theme_{name}.png")
