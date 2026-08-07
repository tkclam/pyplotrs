"""3D scatter cloud."""
import math
import pyplotrs as plt

def rnd(seed):
    s = seed
    while True:
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        yield (s / 0x7FFFFFFF) * 2 - 1
g = rnd(7)
xs, ys, zs = [], [], []
for _ in range(220):
    t = next(g) * math.pi
    r = 0.6 + 0.4 * next(g)
    xs.append(r * math.cos(3 * t) + 0.1 * next(g))
    ys.append(r * math.sin(3 * t) + 0.1 * next(g))
    zs.append(t / math.pi)
fig, ax = plt.subplots(projection="3d", figsize=(420, 340))
ax.scatter(xs, ys, zs, color="C5", markersize=5.1)
ax.set(title="3D scatter", xlabel="x", ylabel="y", zlabel="z")
fig.save("scatter3d.png")
