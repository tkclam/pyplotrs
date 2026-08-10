"""Vector-field and matrix plot types: quiver, streamplot, stackplot, spy."""

import pyplotrs as plt

N = 21
xc = [-3 + 6 * j / (N - 1) for j in range(N)]
yc = [-3 + 6 * i / (N - 1) for i in range(N)]
# Solid-body rotation: u = -y, v = x.
U = [[-yc[i] for _ in range(N)] for i in range(N)]
V = [[xc[j] for j in range(N)] for _ in range(N)]

fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(720, 560))
(ax_stream, ax_quiver), (ax_stack, ax_spy) = axes

ax_stream.streamplot(xc, yc, U, V, density=1.1)
ax_stream.set(title="streamplot", xlabel="x", ylabel="y")

step = 3
ax_quiver.quiver(
    [xc[::step] for _ in yc[::step]],
    [[y] * len(xc[::step]) for y in yc[::step]],
    [[-yc[i] for j in range(0, N, step)] for i in range(0, N, step)],
    [[xc[j] for j in range(0, N, step)] for i in range(0, N, step)],
    scale=0.25,
)
ax_quiver.set(title="quiver", xlabel="x")

months = list(range(12))
ax_stack.stackplot(
    months,
    [3 + i % 4 for i in months],
    [2 + (i * 2) % 5 for i in months],
    [4 + (i * 3) % 3 for i in months],
    labels=["solar", "wind", "hydro"],
    alpha=0.85,
)
ax_stack.set(title="stackplot", xlabel="month", ylabel="TWh")
ax_stack.legend()

sparse = [[1 if (i * j) % 4 == 0 or i == j else 0 for j in range(24)] for i in range(24)]
ax_spy.spy(sparse, markersize=3.5)
ax_spy.set(title="spy")

fig.save("fields.png")
