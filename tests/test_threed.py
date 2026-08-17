"""The 3D projection layer.

`PLAN.md` specified a `pyplotrs-3d` crate that was never built: the camera and
the per-vertex projection lived in Python, and a 60x60 surface spent about a
quarter of its save there, growing with vertex count. The crate exists now and
`_core.project3d` maps a whole mark's vertices in one pass.

The camera math is tested in Rust (`crates/pyplotrs-3d`); these tests pin the
Python side: that the batch projection agrees with the point-by-point one it
replaced, and that the depth-sorting contract is what it claims to be.
"""

from __future__ import annotations

import math

import pyplotrs as pp
import pytest
from pyplotrs import _pyplotrs_core as _core
from pyplotrs import threed as _threed


def _helix(n=400, turns=3):
    t = [i * turns * 2 * math.pi / n for i in range(n)]
    return ([math.cos(v) for v in t],
            [math.sin(v) for v in t],
            [v / (turns * 2 * math.pi) for v in t])


# -- the batch projection agrees with the camera it replaced ------------------

def test_project3d_matches_the_python_camera():
    """`threed.Camera3D` is still the reference for the axis chrome, so the
    Rust batch path has to agree with it exactly or marks and chrome drift."""
    elev, azim = 30.0, -60.0
    cam = _threed.Camera3D(elev, azim)
    frame = dict(xmin=0.0, xspan=2.0, ymin=-1.0, yspan=4.0, zmin=0.0, zspan=1.0,
                 ccx=120.0, ccy=90.0, scx=0.05, scy=-0.1, scale=44.0)
    xs = [0.0, 1.0, 2.0, 0.5]
    ys = [-1.0, 0.0, 3.0, 1.0]
    zs = [0.0, 0.5, 1.0, 0.25]

    dxs, dys, dzs = _core.project3d(xs, ys, zs, elev, azim, *frame.values())

    for i in range(len(xs)):
        nx = (xs[i] - frame["xmin"]) / frame["xspan"] - 0.5
        ny = (ys[i] - frame["ymin"]) / frame["yspan"] - 0.5
        nz = (zs[i] - frame["zmin"]) / frame["zspan"] - 0.5
        sx, sy, depth = cam.view((nx, ny, nz))
        ex = frame["ccx"] + (sx - frame["scx"]) * frame["scale"]
        ey = frame["ccy"] - (sy - frame["scy"]) * frame["scale"]
        assert dxs[i] == pytest.approx(ex)
        assert dys[i] == pytest.approx(ey)
        assert dzs[i] == pytest.approx(depth)


def test_cube_bbox_matches_the_python_corners():
    for elev, azim in [(30.0, -60.0), (0.0, 0.0), (75.0, 120.0)]:
        cam = _threed.Camera3D(elev, azim)
        sxs = [cam.view(c)[0] for c in _threed.CUBE_CORNERS]
        sys_ = [cam.view(c)[1] for c in _threed.CUBE_CORNERS]
        got = _core.cube_screen_bbox(elev, azim)
        assert got[0] == pytest.approx(min(sxs))
        assert got[1] == pytest.approx(max(sxs))
        assert got[2] == pytest.approx(min(sys_))
        assert got[3] == pytest.approx(max(sys_))


def test_project3d_handles_an_empty_mark():
    dxs, dys, dzs = _core.project3d([], [], [], 30.0, -60.0,
                                    0.0, 1.0, 0.0, 1.0, 0.0, 1.0,
                                    0.0, 0.0, 0.0, 0.0, 1.0)
    assert list(dxs) == list(dys) == list(dzs) == []


# -- depth sorting ------------------------------------------------------------

def test_line_depthsort_defaults_on():
    import inspect
    sig = inspect.signature(pp.Axes3D.plot).parameters
    assert sig["depthsort"].default is True


def test_depthsort_off_emits_one_path_per_line(tmp_path):
    """The whole point of the escape hatch: a dense 3D line costs one stroked
    path per *segment* when sorted, and exactly one when not."""
    import re
    hx, hy, hz = _helix(300)

    def paths(depthsort):
        fig, ax = pp.subplots(figsize=(260, 200), projection="3d")
        ax.plot(hx, hy, hz, depthsort=depthsort)
        out = tmp_path / f"ds_{depthsort}.svg"
        fig.save(str(out))
        return len(re.findall(r"<path", out.read_text()))

    many, one = paths(True), paths(False)
    assert many > 250, f"sorted line should emit a path per segment, got {many}"
    assert one < many - 200, f"unsorted line should collapse to one path, got {one}"


def test_depthsort_changes_occlusion(tmp_path):
    """A line passing behind a surface must be hidden when sorted and drawn
    over it when not - that is the tradeoff the flag buys."""
    hx, hy, hz = _helix(300)
    k = 12
    X = [[-1.2 + 2.4 * j / (k - 1) for j in range(k)] for _ in range(k)]
    Y = [[-1.2 + 2.4 * i / (k - 1)] * k for i in range(k)]
    Z = [[0.5] * k for _ in range(k)]

    def render(depthsort):
        fig, ax = pp.subplots(figsize=(240, 200), projection="3d")
        ax.surface(X, Y, Z)
        ax.plot(hx, hy, hz, depthsort=depthsort, color="C3")
        out = tmp_path / f"occl_{depthsort}.png"
        fig.save(str(out))
        return out.read_bytes()

    assert render(True) != render(False)


@pytest.mark.parametrize("ext", ["png", "svg", "pdf"])
def test_unsorted_line_renders_everywhere(ext, tmp_path):
    hx, hy, hz = _helix(120)
    fig, ax = pp.subplots(figsize=(240, 200), projection="3d")
    ax.plot(hx, hy, hz, depthsort=False)
    fig.save(str(tmp_path / f"u.{ext}"))


def test_line3d_alpha_reaches_the_colour():
    """`Axes3D.plot` took an `alpha` and dropped it: the color came from
    `_next_color`, which does not fold opacity in."""
    fig, ax = pp.subplots(projection="3d")
    ax.plot([0, 1], [0, 1], [0, 1], alpha=0.4)
    assert ax._marks3[0]["color"][3] < 255


# -- every 3D mark takes alpha/label, same contract as the 2D marks -----------

@pytest.mark.parametrize("kind", [
    "bar3d", "wireframe", "contour3d", "quiver3d", "voxels",
])
def test_3d_mark_alpha_reaches_the_colour(kind):
    """`surface`/`bar3d`/`wireframe`/`contour3d`/`quiver3d`/`voxels` all used
    `_next_color`, which drops opacity - the same bug `plot` had, just never
    checked on the marks Phase 7a restored."""
    fig, ax = pp.subplots(projection="3d")
    if kind == "bar3d":
        ax.bar3d([0], [0], [0], [1], [1], [1], alpha=0.4)
    elif kind == "wireframe":
        ax.plot_wireframe([[0, 1]], [[0, 1]], [[0, 1]], alpha=0.4)
    elif kind == "contour3d":
        ax.contour3d([[0, 1], [1, 2]], [[0, 0], [1, 1]], [[0, 1], [1, 2]], alpha=0.4)
    elif kind == "quiver3d":
        ax.quiver3d([0], [0], [0], [1], [1], [1], alpha=0.4)
    elif kind == "voxels":
        ax.voxels([[[True]]], alpha=0.4)
    m = ax._marks3[0]
    color = m["colors"][0] if kind == "contour3d" else m["color"]
    assert color[3] < 255


@pytest.mark.parametrize("kind", ["surface", "trisurf"])
def test_colormapped_3d_mark_label_reaches_the_legend(kind, tmp_path):
    """`surface(..., label=...)` and `plot_trisurf(..., label=...)` followed by
    `legend()` raised `KeyError('color')`: the shared `_legend_entries` fell
    through to the branch that reads `m["color"]`, which colormapped 3D marks
    never set. They now carry a swatch color (the colormap's midpoint) for
    exactly this."""
    k = 4
    X = [[-1.0 + 2.0 * j / (k - 1) for j in range(k)] for _ in range(k)]
    Y = [[-1.0 + 2.0 * i / (k - 1)] * k for i in range(k)]
    Z = [[X[i][j] + Y[i][j] for j in range(k)] for i in range(k)]
    fig, ax = pp.subplots(figsize=(240, 200), projection="3d")
    if kind == "surface":
        ax.surface(X, Y, Z, label="surf")
    else:
        xs = [v for r in X for v in r]
        ys = [v for r in Y for v in r]
        zs = [v for r in Z for v in r]
        ax.plot_trisurf(xs, ys, zs, label="tri")
    ax.legend()
    entries = ax._legend_entries()
    assert len(entries) == 1
    assert entries[0]["color"][3] == 255  # opaque by default, not dropped
    fig.save(str(tmp_path / f"{kind}_legend.png"))  # must not raise


# -- the vertex-heavy marks still draw the same picture -----------------------

@pytest.mark.parametrize("kind", ["surface", "wireframe", "scatter", "line", "trisurf"])
def test_vertex_heavy_marks_render(kind, tmp_path):
    k = 10
    X = [[-2 + 4 * j / (k - 1) for j in range(k)] for _ in range(k)]
    Y = [[-2 + 4 * i / (k - 1)] * k for i in range(k)]
    Z = [[math.sin(X[i][j]) * math.cos(Y[i][j]) for j in range(k)] for i in range(k)]
    fig, ax = pp.subplots(figsize=(240, 200), projection="3d")
    if kind == "surface":
        ax.surface(X, Y, Z)
    elif kind == "wireframe":
        ax.plot_wireframe(X, Y, Z)
    elif kind == "scatter":
        ax.scatter([v for r in X for v in r], [v for r in Y for v in r],
                   [v for r in Z for v in r])
    elif kind == "line":
        ax.plot(*_helix(120))
    else:
        xs = [v for r in X for v in r]
        ys = [v for r in Y for v in r]
        zs = [v for r in Z for v in r]
        ax.plot_trisurf(xs[:40], ys[:40], zs[:40])
    fig.save(str(tmp_path / f"{kind}.png"))
