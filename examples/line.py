"""Line plot: multiple series with a legend."""
import math
import pyplotrs as plt

xs = [i * 0.1 for i in range(80)]
fig, ax = plt.subplots()
ax.line(xs, [math.sin(x) for x in xs], label="sin")
ax.line(xs, [math.sin(x) * math.exp(-0.1 * x) for x in xs],
        label="damped", linestyle="dashed")
ax.set(title="Line plot", xlabel="t", ylabel="amplitude")
ax.legend()
fig.save("line.png")
