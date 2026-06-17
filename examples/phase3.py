"""Phase 3 feature gallery: multi-frame / animated export.

figurs animations are stateless - a render callback returns a fully-built
``figurs.Figure`` per frame, and the sequence is encoded to an animated GIF
(broadly viewable) or APNG (full colour). Run with the project venv:
``.venv/bin/python examples/phase3.py``. Writes a few files into
``examples/output/``.
"""

import math
import os

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


def traveling_wave() -> None:
    """A sine wave sweeping in phase -> looping GIF."""
    xs = [i * 0.08 for i in range(160)]

    def frame(i):
        ph = i * 2.0 * math.pi / 48.0
        fig, ax = figurs.subplots(figsize=(360, 202))
        ax.line(xs, [math.sin(x + ph) for x in xs], color="C0", label="sin(x + φ)")
        ax.line(xs, [math.cos(x + ph) * 0.6 for x in xs], color="C1",
                linestyle="dashed", label="0.6 cos(x + φ)")
        ax.set(ylim=(-1.15, 1.15), xlabel="x", ylabel="amplitude",
               title="traveling wave")
        ax.legend(loc="upper right")
        return fig

    figurs.animate(frame, frames=48, fps=24).save(out("phase3_wave.gif"))


def growing_scatter() -> None:
    """Points accumulating over time -> a 'data arriving' GIF."""
    import random
    random.seed(7)
    pts = [(random.gauss(0, 1), random.gauss(0, 1)) for _ in range(300)]

    def frame(i):
        k = (i + 1) * len(pts) // 30
        fig, ax = figurs.subplots(figsize=(259, 259), theme="nature")
        ax.scatter([x for x, _ in pts[:k]], [y for _, y in pts[:k]],
                   color="C2", size=18.0)
        ax.set(xlim=(-3.5, 3.5), ylim=(-3.5, 3.5),
               title=f"n = {k}", xlabel="x", ylabel="y")
        return fig

    figurs.animate(frame, frames=30, fps=15).save(out("phase3_scatter.gif"))


def rotating_surface() -> None:
    """A 3D surface spun through azimuth -> full-colour APNG (the colormap is
    why APNG, not 256-colour GIF, is the right format here)."""
    n = 28
    xs = [-3.0 + 6.0 * i / (n - 1) for i in range(n)]
    ys = [-3.0 + 6.0 * j / (n - 1) for j in range(n)]
    zz = [[math.sin(math.hypot(x, y)) for x in xs] for y in ys]

    def frame(i):
        fig, ax = figurs.subplots(projection="3d", figsize=(302, 259))
        ax.surface(xs, ys, zz, cmap="viridis")
        ax.set(title="rotating surface", xlabel="x", ylabel="y", zlabel="z",
               elev=28.0, azim=float(i * 15))
        return fig

    figurs.animate(frame, frames=24, fps=18).save(out("phase3_surface.apng"), dpi=110)


def interactive_surface() -> None:
    """The same 3D surface saved as .html: because the figure is 3D, the HTML is
    a dependency-free Canvas2D viewer you can orbit/zoom/pan live in a browser."""
    n = 40
    xs = [-3.0 + 6.0 * i / (n - 1) for i in range(n)]
    ys = [-3.0 + 6.0 * j / (n - 1) for j in range(n)]
    zz = [[math.sin(math.hypot(x, y)) for x in xs] for y in ys]
    fig, ax = figurs.subplots(projection="3d", figsize=(432, 360))
    ax.surface(xs, ys, zz, cmap="viridis")
    ax.set(title="drag to rotate", xlabel="x", ylabel="y", zlabel="z", elev=30.0, azim=-60.0)
    fig.save(out("phase3_surface_interactive.html"))


def main() -> None:
    traveling_wave()
    growing_scatter()
    rotating_surface()
    interactive_surface()
    print("Phase 3 gallery written to", _OUT)
    print("  phase3_wave.gif, phase3_scatter.gif, "
          "phase3_surface.apng, phase3_surface_interactive.html")


if __name__ == "__main__":
    main()
