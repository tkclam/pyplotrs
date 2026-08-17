"""3D surface (the classic 'sombrero')."""
import math

import pyplotrs as pp

n = 40
xs = [-4 + 8 * i / (n - 1) for i in range(n)]
ys = [-4 + 8 * j / (n - 1) for j in range(n)]
X = [[x for x in xs] for _ in ys]
Y = [[y for _ in xs] for y in ys]
def f(x, y):
    r = math.sqrt(x * x + y * y) + 1e-6
    return math.sin(r) / r
Z = [[f(x, y) for x in xs] for y in ys]
fig, ax = pp.subplots(projection="3d", figsize=(420, 340))
ax.surface(X, Y, Z, cmap="viridis")
ax.set(title="3D surface", xlabel="x", ylabel="y", zlabel="z", elev=35, azim=-50)
fig.save("surface3d.png")
