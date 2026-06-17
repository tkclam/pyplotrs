"""Built-in themes: one figure per preset, shown together.

A theme is passed to ``subplots`` and flows to its axes (there is no global
'current theme'). Here we render the same line in each preset.
"""
import math
import pyplotrs as plt

xs = [i * 0.2 for i in range(40)]
ys = [math.sin(x) for x in xs]
for name in ["default", "nature", "grayscale", "presentation"]:
    fig, ax = plt.subplots(figsize=(300, 200), theme=name)
    ax.line(xs, ys, label="sin")
    ax.line(xs, [y * 0.6 for y in ys], label="0.6·sin", linestyle="dashed")
    ax.set(title=f"theme = {name}", xlabel="t", ylabel="y")
    ax.legend()
    fig.save(f"theme_{name}.png")
