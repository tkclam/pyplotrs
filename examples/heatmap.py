"""Image / heatmap with a colorbar."""
import math

import pyplotrs as plt

n = 100
data = [[math.sin(i / 8) * math.cos(j / 10) for j in range(n)] for i in range(n)]
fig, ax = plt.subplots()
m = ax.imshow(data, cmap="viridis", extent=(-3, 3, -3, 3))
fig.colorbar(m, label="intensity")
ax.set(title="Heatmap", xlabel="x", ylabel="y")
fig.save("heatmap.png")
