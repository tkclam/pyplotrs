"""A 3D parametric curve (helix)."""
import math

import pyplotrs as pp

t = [i * 0.1 for i in range(220)]
xs = [math.cos(v) for v in t]
ys = [math.sin(v) for v in t]
zs = [v / (22.0) for v in t]
fig, ax = pp.subplots(projection="3d", figsize=(420, 340))
ax.plot(xs, ys, zs, color="C0", linewidth=2.0, label="helix")
ax.set(title="3D line", xlabel="x", ylabel="y", zlabel="z")
ax.legend()
fig.save("line3d.png")
