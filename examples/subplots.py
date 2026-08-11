"""A multi-panel figure with a shared y-axis and a figure-level legend."""
import math

import pyplotrs as plt

xs = [i * 0.15 for i in range(60)]
fig, axs = plt.subplots(1, 3, figsize=(640, 240), sharey=True)
for k, ax in enumerate(axs):
    ax.line(xs, [math.sin(x + k) for x in xs], label="sin")
    ax.line(xs, [math.cos(x + k) for x in xs], label="cos", linestyle="dashed")
    ax.set(title=f"phase {k}", xlabel="t")
axs[0].set(ylabel="y")
fig.legend()
fig.set(suptitle="Shared-axis small multiples")
fig.save("subplots.png")
