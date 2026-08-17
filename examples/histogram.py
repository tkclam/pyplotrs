"""Histogram of a synthetic distribution."""
import math

import pyplotrs as pp


# Box-Muller normal samples (no numpy dependency).
def normals(n, seed=1):
    s = seed
    out = []
    for _ in range(n):
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        u1 = (s + 1) / 0x80000000
        s = (1103515245 * s + 12345) & 0x7FFFFFFF
        u2 = (s + 1) / 0x80000000
        out.append(math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2))
    return out

fig, ax = pp.subplots()
ax.hist(normals(2000), bins=30, color="C2", density=True)
ax.set(title="Histogram", xlabel="value", ylabel="density")
fig.save("histogram.png")
