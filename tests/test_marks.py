"""Every plotting method renders to every format."""

import datetime as dt
import math

import pytest

import pyplotrs as pp

X = [i / 10 for i in range(60)]
Y = [math.sin(v) for v in X]
GRID = [[math.sin(c / 5) * math.cos(r / 4) for c in range(20)] for r in range(15)]

MARKS = {
    "line": lambda ax: ax.line(X, Y, marker="o", linestyle="--"),
    "line_y_only": lambda ax: ax.line(Y),
    "scatter": lambda ax: ax.scatter(X, Y, size=4, marker="s", edgecolor="k"),
    "scatter_c": lambda ax: ax.scatter(X, Y, c=X, cmap="magma", norm="log", vmin=0.1),
    "step": lambda ax: ax.step(X, Y, where="mid"),
    "stairs": lambda ax: ax.stairs([1, 3, 2], [0, 1, 2, 3], fill=True),
    "stem": lambda ax: ax.stem([1, 2, 3], [1, -1, 2]),
    "errorbar": lambda ax: ax.errorbar(
        [1, 2, 3], [1, 2, 1], yerr=([0.1, 0.2, 0.1], [0.3, 0.2, 0.1]), xerr=0.1
    ),
    "bar": lambda ax: ax.bar(["a", "b", "c"], [1, 2, 3], hatch="/"),
    "barh": lambda ax: ax.barh([1, 2], [3, 4], left=[0, 1]),
    "hist": lambda ax: ax.hist(Y, bins=8, density=True, cumulative=True),
    "hist_edges_step": lambda ax: ax.hist(Y, bins=[-1, 0, 0.5, 1], histtype="step"),
    "fill_between": lambda ax: ax.fill_between(X, Y, 0),
    "fill_betweenx": lambda ax: ax.fill_betweenx(X, Y),
    "stackplot": lambda ax: ax.stackplot(X, [abs(v) for v in Y], [1] * len(X), labels=["a", "b"]),
    "boxplot": lambda ax: ax.boxplot([Y, [v * 2 for v in Y]], vertical=False),
    "violinplot": lambda ax: ax.violinplot([Y, [v + 1 for v in Y]]),
    "pie": lambda ax: ax.pie([1, 2, 3], labels=["x", "y", "z"], autopct="{:.0f}%"),
    "imshow": lambda ax: ax.imshow(GRID, origin="lower"),
    "imshow_rgb": lambda ax: ax.imshow([[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (9, 9, 9)]]),
    "pcolormesh": lambda ax: ax.pcolormesh(GRID, edgecolor="w"),
    "contour": lambda ax: ax.contour(GRID, levels=[-0.5, 0, 0.5], colors=["C1", "C2"]),
    "contourf": lambda ax: ax.contourf(list(range(20)), list(range(15)), GRID, levels=5),
    "hist2d": lambda ax: ax.hist2d(X, Y, bins=(5, 4)),
    "hexbin": lambda ax: ax.hexbin(X, Y, gridsize=5),
    "quiver": lambda ax: ax.quiver([0, 1], [0, 1], [1, 0], [0, 1]),
    "streamplot": lambda ax: ax.streamplot(
        list(range(10)), list(range(10)), [[1.0] * 10] * 10, [[0.5] * 10] * 10
    ),
    "hlines": lambda ax: ax.hlines([1, 2], 0, 1, linestyle=":"),
    "vlines": lambda ax: ax.vlines([1, 2], [0, 0], [1, 2]),
    "eventplot": lambda ax: ax.eventplot([[1, 2, 3], [2, 4]], orientation="vertical"),
    "guides": lambda ax: (
        ax.axhline(1),
        ax.axvline(1),
        ax.axhspan(0, 1),
        ax.axvspan(0, 1),
        ax.axline((0, 0), (1, 2)),
    ),
    "shapes": lambda ax: (
        ax.rectangle((0, 0), 1, 1, angle=30),
        ax.circle((2, 2), 1),
        ax.ellipse((0, 2), 2, 1),
        ax.polygon([(0, 0), (1, 0), (0, 1)]),
        ax.arrow(0, 0, 1, 1),
    ),
    "text": lambda ax: (
        ax.text(0.5, 0.5, "hi", rotation=30, ha="center"),
        ax.annotate("there", (0, 0), (1, 1)),
    ),
    "dates": lambda ax: ax.line(
        [dt.datetime(2024, 1, 1) + dt.timedelta(hours=6 * i) for i in range(10)], list(range(10))
    ),
}


@pytest.mark.parametrize("name", MARKS)
@pytest.mark.parametrize("fmt", ["png", "pdf", "svg"])
def test_mark_renders(name, fmt):
    fig, ax = pp.subplots()
    MARKS[name](ax)
    data = fig.to_bytes(fmt, dpi=72)
    assert data[:4] in (b"\x89PNG", b"%PDF", b"<svg", b"<?xm")


def test_marks_return_their_artist():
    fig, ax = pp.subplots()
    line = ax.line(X, Y, label="a")
    assert isinstance(line, pp.artists.Line)
    assert ax.artists == [line]
    line.color = (255, 0, 0, 255)  # artists can be restyled after the fact
    fig.to_bytes("png", dpi=50)


def test_polar_marks():
    fig, ax = pp.subplots(projection="polar")
    t = [i / 10 for i in range(63)]
    ax.line(t, [1 + 0.3 * math.sin(3 * v) for v in t], label="r")
    ax.scatter(t[::10], [1] * 7)
    ax.fill(t, [0.5] * len(t))
    ax.set(theta_zero="N", theta_direction=-1, rmax=2, title="polar")
    ax.legend()
    assert ax.get_rlim() == (0.0, 2.0)
    for fmt in ("png", "pdf", "svg"):
        fig.to_bytes(fmt, dpi=72)


def test_3d_marks_and_interactive_html():
    fig, ax = pp.subplots(projection="3d")
    xs = [i / 5 for i in range(10)]
    ax.surface(xs, xs, [[a * b for a in xs] for b in xs])
    ax.wireframe(xs, xs, [[a + b for a in xs] for b in xs])
    ax.scatter(xs, xs, xs, label="pts")
    ax.line(xs, xs, xs)
    ax.bar3d([0], [0], [0], 1, 1, 1)
    ax.quiver([0], [0], [0], [1], [1], [1])
    ax.set(xlabel="x", elev=20, azim=30, zlim=(0, 5))
    ax.legend()
    assert ax.get_zlim() == (0.0, 5.0)
    for fmt in ("png", "pdf", "svg"):
        fig.to_bytes(fmt, dpi=72)
    page = fig.to_bytes("html").decode()
    assert "<canvas" in page and "const FIG" in page and "@font-face" in page


def test_animation(tmp_path):
    def frame(i):
        fig, ax = pp.subplots(figsize=(100, 80))
        ax.line([0, 1], [0, i])
        return fig

    anim = pp.animate(frame, 3, fps=10)
    assert len(anim) == 3
    assert anim.to_bytes("gif")[:3] == b"GIF"
    anim.save(tmp_path / "a.apng")
    assert (tmp_path / "a.apng").read_bytes()[:4] == b"\x89PNG"
    with pytest.raises(ValueError, match="same size"):
        pp.animate(lambda i: pp.subplots(figsize=(100 + i, 80))[0], 2).to_bytes()
