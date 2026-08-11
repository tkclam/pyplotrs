"""An animated GIF: a traveling wave (one frame shown in the gallery)."""
import math
import pyplotrs as plt

xs = [i * 0.1 for i in range(120)]

def frame(i):
    fig, ax = plt.subplots(figsize=(360, 220))
    ax.line(xs, [math.sin(x - i * 0.3) for x in xs], color="C0")
    ax.set(title="Traveling wave", xlabel="x", ylabel="y", ylim=(-1.2, 1.2))
    return fig

plt.animate(frame, frames=40, fps=20).save("animation_wave.gif")
# Also render a single still frame for a static thumbnail.
frame(0).save("animation_wave.png")
