"""A reference strip of the built-in colormaps."""
import pyplotrs as plt
from pyplotrs import colormaps

names = ["viridis", "plasma", "inferno", "magma", "cividis", "coolwarm", "grays"]
strip = [[j / 255 for j in range(256)] for _ in range(8)]
fig, axs = plt.subplots(len(names), 1, figsize=(560, 700))
for ax, name in zip(axs, names):
    ax.imshow(strip, cmap=name, extent=(0, 1, 0, 1))
    ax.set(ylabel=name)
fig.set(suptitle="Built-in colormaps")
fig.save("colormaps.png")
