"""A reference strip across the built-in colormap families (a curated sample
- see ``colormaps.available()`` for the full set of ~125)."""
import pyplotrs as plt

# perceptually uniform, sequential, diverging, cyclic, miscellaneous, then one
# representative pull from each third-party source (colorcet `cet_`, cmocean `cmo_`).
names = [
    "viridis", "plasma", "inferno", "magma", "cividis",
    "Blues", "YlOrRd", "grays",
    "RdBu", "coolwarm", "cet_coolwarm",
    "twilight", "cet_colorwheel", "cmo_phase",
    "turbo", "cet_rainbow",
    "cet_fire", "cet_bgy",
    "cmo_thermal", "cmo_balance",
]
strip = [[j / 255 for j in range(256)] for _ in range(8)]
fig, axs = plt.subplots(len(names), 1, figsize=(560, 100 * len(names)))
for ax, name in zip(axs, names):
    ax.imshow(strip, cmap=name, extent=(0, 1, 0, 1))
    ax.set(ylabel=name)
fig.set(suptitle="Built-in colormaps (curated sample)")
fig.save("colormaps.png")
