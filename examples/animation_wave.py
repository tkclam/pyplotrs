"""An animated GIF: a traveling wave."""
import math

import pyplotrs as pp

xs = [i * 0.1 for i in range(120)]

def frame(i):
    fig, ax = pp.subplots(figsize=(360, 220))
    ax.line(xs, [math.sin(x - i * 0.3) for x in xs], color="C0")
    ax.set(title="Traveling wave", xlabel="x", ylabel="y", ylim=(-1.2, 1.2))
    return fig

pp.animate(frame, frames=40, fps=20).save("animation_wave.gif")
