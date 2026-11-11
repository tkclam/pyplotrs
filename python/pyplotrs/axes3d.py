"""3D axes: marks projected to 2D by an orthographic camera.

    fig, ax = pp.subplots(projection="3d")
    ax.surface(X, Y, Z, cmap="viridis")
    ax.set(xlabel="x", ylabel="y", zlabel="z", elev=25, azim=-50)
    fig.save("surface.html")   # interactive: drag to rotate

Everything is depth-sorted and drawn as ordinary 2D vector shapes, so PDF and
SVG output stays editable.
"""

from __future__ import annotations

import itertools
import math
from array import array
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from . import _core, _legend
from . import _data as data
from . import colormaps as _colormaps
from ._canvas import Canvas, check_linestyle, check_marker, dash
from ._frame import TITLE_GAP, Margins
from .artists import Artist, Key, View
from .axes import AxesBase, Cmap, Color
from .colors import RGBA, with_alpha
from .scales import nice_ticks
from .text import Label, as_label

__all__ = ["Axes3D"]

Vec3 = tuple[float, float, float]
PANE_FILL: RGBA = (242, 242, 242, 255)
PANE_EDGE: RGBA = (170, 170, 170, 255)
GRID: RGBA = (214, 214, 214, 255)
CUBE_FILL = 0.86  # fraction of the plot area the projected cube fills


class Camera:
    """Orthographic camera looking at the origin from ``(elev, azim)`` degrees
    (matplotlib's convention). ``view`` gives screen x, y and depth (larger is
    nearer)."""

    def __init__(self, elev: float, azim: float) -> None:
        e, a = math.radians(elev), math.radians(azim)
        d = (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))
        right = (-d[1], d[0], 0.0)  # (0, 0, 1) x d
        n = math.hypot(*right)
        right = (right[0] / n, right[1] / n, 0.0) if n > 1e-12 else (1.0, 0.0, 0.0)
        up = (
            d[1] * right[2] - d[2] * right[1],
            d[2] * right[0] - d[0] * right[2],
            d[0] * right[1] - d[1] * right[0],
        )
        self.dir, self.right, self.up = d, right, up

    def view(self, p: Vec3) -> Vec3:
        return (
            sum(a * b for a, b in zip(p, self.right, strict=True)),
            sum(a * b for a, b in zip(p, self.up, strict=True)),
            sum(a * b for a, b in zip(p, self.dir, strict=True)),
        )


@dataclass(eq=False)
class Mark3D(Artist):
    """A 3D mark: points in data space and how to draw them."""

    kind: str = "scatter"
    xs: Any = field(default=None, repr=False)
    ys: Any = field(default=None, repr=False)
    zs: Any = field(default=None, repr=False)
    color: RGBA = (0, 0, 0, 255)
    size: float = 5.0
    marker: str | None = "o"
    edgecolor: RGBA | None = None
    linewidth: float = 1.2
    linestyle: str = "solid"
    shape: tuple[int, int] = (0, 0)  # grid rows, cols for surfaces/wireframes
    cmap: _colormaps.Colormap | None = None
    alpha: float = 1.0
    extra: Any = field(default=None, repr=False)  # bar sizes / arrow vectors

    def legend_key(self) -> Key:
        if self.kind == "scatter":
            return Key(
                "marker",
                self.color,
                marker=self.marker,
                markersize=self.size,
                edgecolor=self.edgecolor,
            )
        if self.kind in ("surface", "bar"):
            return Key("patch", self.color)
        return Key("line", self.color, self.linewidth, self.linestyle)

    def draw(self, canvas: Canvas, view: View) -> None:  # drawn by Axes3D
        pass


@dataclass
class _Plan:
    margins: Margins


def _grid3(X: Any, Y: Any, Z: Any) -> tuple[Any, Any, Any, int, int]:
    """Surface inputs as flat row-major x, y, z and the grid shape. ``X``/``Y``
    may be 2D grids or 1D coordinates (``len(X) == cols``, ``len(Y) == rows``)."""
    zs, nc, nr = data.grid(Z)
    if data.is_2d(X):
        xs, *_ = data.grid(X)
    else:
        col = data.f64(X)
        xs = array("d", list(col) * nr)
    if data.is_2d(Y):
        ys, *_ = data.grid(Y)
    else:
        row = data.f64(Y)
        ys = array("d", [row[r] for r in range(nr) for _ in range(nc)])
    if not (len(xs) == len(ys) == len(zs) == nr * nc):
        raise ValueError("X, Y and Z must describe the same grid")
    return xs, ys, zs, nr, nc


class _Batcher:
    """Draws depth-sorted primitives, merging runs with the same style into one
    engine call."""

    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas
        self.key: Any = None
        self.buf: list[Any] = []

    def add(self, key: tuple, item: Any) -> None:
        if key != self.key:
            self.flush()
            self.key = key
        self.buf.append(item)

    def flush(self) -> None:
        if not self.buf:
            return
        kind, *style = self.key
        c, buf = self.canvas, self.buf
        if kind == "poly":
            edge, width = style
            xs = [v for item in buf for v in item[0]]
            ys = [v for item in buf for v in item[1]]
            fills = b"".join(bytes(item[2]) for item in buf)
            c.polygons(
                xs, ys, [len(item[0]) for item in buf], fills=fills, stroke=edge, width=width
            )
        elif kind == "seg":
            color, width, ls = style
            x0, y0, x1, y1 = (list(col) for col in zip(*buf, strict=True))
            c.segments(x0, y0, x1, y1, color=color, width=width, dash=dash(ls), cap="round")
        else:
            marker, size, fill, edge = style
            c.markers(
                [p[0] for p in buf],
                [p[1] for p in buf],
                marker=marker,
                size=size,
                fill=fill,
                edge=edge,
            )
        self.buf = []


def _darker(c: RGBA, k: float = 0.65) -> RGBA:
    return (round(c[0] * k), round(c[1] * k), round(c[2] * k), c[3])


class Axes3D(AxesBase):
    """A 3D axes."""

    is_3d = True

    def __init__(self, theme: Any, figure: Any = None) -> None:
        super().__init__(theme, figure)
        self.xlabel: Label | None = None
        self.ylabel: Label | None = None
        self.zlabel: Label | None = None
        self._lims: list[tuple[float, float] | None] = [None, None, None]
        self.elev, self.azim = 30.0, -60.0

    def _mark(self, label: Any, zorder: float, **kw: Any) -> Mark3D:
        for k in ("xs", "ys", "zs"):
            kw[k] = data.f64(kw[k])
        data.same_length(kw["kind"], x=kw["xs"], y=kw["ys"], z=kw["zs"])
        return self._add(Mark3D(**kw), label, zorder)

    def scatter(
        self,
        x: Any,
        y: Any,
        z: Any,
        *,
        color: Color = None,
        size: float | None = None,
        marker: str = "o",
        edgecolor: Color = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Mark3D:
        """Markers at 3D points."""
        return self._mark(
            label,
            zorder,
            kind="scatter",
            xs=x,
            ys=y,
            zs=z,
            color=self._color(color, alpha),
            size=self.theme.marker_size if size is None else float(size),
            marker=check_marker(marker) or "o",
            edgecolor=None if edgecolor is None else self.theme.color(edgecolor),
        )

    def line(
        self,
        x: Any,
        y: Any,
        z: Any,
        *,
        color: Color = None,
        linewidth: float | None = None,
        linestyle: str = "solid",
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Mark3D:
        """A line through 3D points. Each segment is depth-sorted, so the line
        can pass behind other marks and itself."""
        return self._mark(
            label,
            zorder,
            kind="line",
            xs=x,
            ys=y,
            zs=z,
            color=self._color(color, alpha),
            linewidth=self.theme.line_width if linewidth is None else float(linewidth),
            linestyle=check_linestyle(linestyle),
        )

    def surface(
        self,
        X: Any,
        Y: Any,
        Z: Any,
        *,
        cmap: Cmap = "viridis",
        color: Color = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Mark3D:
        """A surface over a grid, colored by height through ``cmap`` (or one ``color``)."""
        xs, ys, zs, nr, nc = _grid3(X, Y, Z)
        cm = None if color is not None else _colormaps.get(cmap)
        col = self.theme.color(color) if color is not None else cm(0.5)  # type: ignore[misc]
        return self._add(
            Mark3D(
                kind="surface",
                xs=xs,
                ys=ys,
                zs=zs,
                color=with_alpha(col, alpha),
                shape=(nr, nc),
                cmap=cm,
                alpha=alpha,
            ),
            label,
            zorder,
        )

    def wireframe(
        self,
        X: Any,
        Y: Any,
        Z: Any,
        *,
        color: Color = None,
        linewidth: float = 0.8,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Mark3D:
        """A grid drawn as lines along its rows and columns."""
        xs, ys, zs, nr, nc = _grid3(X, Y, Z)
        return self._add(
            Mark3D(
                kind="wireframe",
                xs=xs,
                ys=ys,
                zs=zs,
                color=self._color(color, alpha),
                linewidth=float(linewidth),
                shape=(nr, nc),
            ),
            label,
            zorder,
        )

    def bar3d(
        self,
        x: Any,
        y: Any,
        z: Any,
        dx: Any,
        dy: Any,
        dz: Any,
        *,
        color: Color = None,
        alpha: float = 1.0,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Mark3D:
        """Boxes with a corner at ``(x, y, z)`` and size ``(dx, dy, dz)``."""
        xs = data.f64(x)
        n = len(xs)
        sizes = (data.full(dx, n), data.full(dy, n), data.full(dz, n))
        return self._mark(
            label,
            zorder,
            kind="bar",
            xs=xs,
            ys=y,
            zs=z,
            color=self._color(color, alpha),
            extra=sizes,
        )

    def quiver(
        self,
        x: Any,
        y: Any,
        z: Any,
        u: Any,
        v: Any,
        w: Any,
        *,
        length: float = 1.0,
        color: Color = None,
        linewidth: float = 1.2,
        label: Label | None = None,
        zorder: float = 0.0,
    ) -> Mark3D:
        """Arrows from each point along ``(u, v, w) * length``."""
        xs = data.f64(x)
        n = len(xs)
        vec = tuple(data.f64([length * s for s in data.full(c, n)]) for c in (u, v, w))
        return self._mark(
            label,
            zorder,
            kind="quiver",
            xs=xs,
            ys=y,
            zs=z,
            color=self._color(color),
            linewidth=float(linewidth),
            extra=vec,
        )

    def set(
        self,
        *,
        title: Label | None = None,
        xlabel: Label | None = None,
        ylabel: Label | None = None,
        zlabel: Label | None = None,
        xlim: tuple[float, float] | None = None,
        ylim: tuple[float, float] | None = None,
        zlim: tuple[float, float] | None = None,
        elev: float | None = None,
        azim: float | None = None,
    ) -> Axes3D:
        """Labels, limits and the camera angle (``elev``/``azim`` in degrees)."""
        if title is not None:
            self.title = as_label(title)
        for attr, value in (("xlabel", xlabel), ("ylabel", ylabel), ("zlabel", zlabel)):
            if value is not None:
                setattr(self, attr, as_label(value))
        for i, lim in enumerate((xlim, ylim, zlim)):
            if lim is not None:
                self._lims[i] = (float(lim[0]), float(lim[1]))
        if elev is not None:
            self.elev = float(elev)
        if azim is not None:
            self.azim = float(azim)
        return self

    def limits(self) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        """The ``(x, y, z)`` ranges shown."""
        spans: list[tuple[float, float] | None] = [None, None, None]
        for m in self._artists:
            assert isinstance(m, Mark3D)
            cols = [m.xs, m.ys, m.zs]
            if m.extra is not None:
                cols = [
                    data.f64([a + b for a, b in zip(c, e, strict=True)])
                    for c, e in zip(cols, m.extra, strict=True)
                ] + cols
            for i in range(3):
                for c in cols[i::3]:
                    spans[i] = data.union(spans[i], _core.finite_range(c))
        out = []
        for i in range(3):
            if self._lims[i] is not None:
                out.append(self._lims[i])
                continue
            lo, hi = spans[i] or (0.0, 1.0)
            if lo == hi:
                lo, hi = lo - 0.5, hi + 0.5
            pad = (hi - lo) * 0.05
            out.append((lo - pad, hi + pad))
        return tuple(out)  # type: ignore[return-value]

    def get_xlim(self) -> tuple[float, float]:
        return self.limits()[0]

    def get_ylim(self) -> tuple[float, float]:
        return self.limits()[1]

    def get_zlim(self) -> tuple[float, float]:
        return self.limits()[2]

    # -- rendering --------------------------------------------------------------

    def _measure(self, canvas: Canvas) -> _Plan:
        m = Margins()
        if self.title:
            m.top = (
                canvas.measure(self.title, self.theme.title_size, self.theme.title_weight).height
                + TITLE_GAP
            )
        return _Plan(m)

    def _ticks(self, lo: float, hi: float) -> list[tuple[float, str]]:
        span = (hi - lo) or 1.0
        return [
            ((v - lo) / span - 0.5, s)
            for v, s in nice_ticks(lo, hi, 5, self.theme.unicode_minus)
            if -1e-9 <= (v - lo) / span <= 1 + 1e-9
        ]

    def _draw(self, canvas: Canvas, plan: _Plan, rect: tuple[float, float, float, float]) -> None:
        th = canvas.theme
        x, y, w, h = rect
        cam = Camera(self.elev, self.azim)
        (x0, x1), (y0, y1), (z0, z1) = self.limits()
        bx0, bx1, by0, by1 = _core.cube_bounds(self.elev, self.azim)
        scale = min(w / ((bx1 - bx0) or 1), h / ((by1 - by0) or 1)) * CUBE_FILL
        ccx, ccy, scx, scy = x + w / 2, y + h / 2, (bx0 + bx1) / 2, (by0 + by1) / 2
        frame = (
            x0,
            (x1 - x0) or 1.0,
            y0,
            (y1 - y0) or 1.0,
            z0,
            (z1 - z0) or 1.0,
            ccx,
            ccy,
            scx,
            scy,
            scale,
        )

        def unit(p: Vec3) -> tuple[float, float, float]:
            sx, sy, d = cam.view(p)
            return ccx + (sx - scx) * scale, ccy - (sy - scy) * scale, d

        def project(xs: Any, ys: Any, zs: Any) -> list[tuple[float, float, float]]:
            px, py, pd = _core.project3d(xs, ys, zs, self.elev, self.azim, frame)
            return list(zip(px, py, pd, strict=True))

        def back(axis: int) -> float:
            lo, hi = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            lo[axis], hi[axis] = -0.5, 0.5
            return -0.5 if cam.view(tuple(lo))[2] < cam.view(tuple(hi))[2] else 0.5  # type: ignore[arg-type]

        xb, yb, zb = back(0), back(1), back(2)
        xt, yt, zt = self._ticks(x0, x1), self._ticks(y0, y1), self._ticks(z0, z1)

        def pane(corners: list[Vec3], lines: list[tuple[Vec3, Vec3]]) -> None:
            pts = [unit(p) for p in corners]
            canvas.path(
                [p[0] for p in pts],
                [p[1] for p in pts],
                fill=PANE_FILL,
                close=True,
                stroke=PANE_EDGE,
                width=0.8,
            )
            if lines:
                ends = [(unit(a), unit(b)) for a, b in lines]
                canvas.segments(
                    [a[0] for a, _ in ends],
                    [a[1] for a, _ in ends],
                    [b[0] for _, b in ends],
                    [b[1] for _, b in ends],
                    color=GRID,
                    width=0.6,
                )

        pane(
            [(-0.5, -0.5, zb), (0.5, -0.5, zb), (0.5, 0.5, zb), (-0.5, 0.5, zb)],
            [((t, -0.5, zb), (t, 0.5, zb)) for t, _ in xt]
            + [((-0.5, t, zb), (0.5, t, zb)) for t, _ in yt],
        )
        pane(
            [(xb, -0.5, -0.5), (xb, 0.5, -0.5), (xb, 0.5, 0.5), (xb, -0.5, 0.5)],
            [((xb, t, -0.5), (xb, t, 0.5)) for t, _ in yt]
            + [((xb, -0.5, t), (xb, 0.5, t)) for t, _ in zt],
        )
        pane(
            [(-0.5, yb, -0.5), (0.5, yb, -0.5), (0.5, yb, 0.5), (-0.5, yb, 0.5)],
            [((t, yb, -0.5), (t, yb, 0.5)) for t, _ in xt]
            + [((-0.5, yb, t), (0.5, yb, t)) for t, _ in zt],
        )

        prims: list[tuple[float, tuple, Any]] = []
        for m in sorted(self._artists, key=lambda a: a.zorder):
            assert isinstance(m, Mark3D)
            if m.kind == "scatter":
                key = ("pt", m.marker, m.size, m.color, m.edgecolor)
                prims += [(p[2], key, p) for p in project(m.xs, m.ys, m.zs)]
            elif m.kind == "line":
                key = ("seg", m.color, m.linewidth, m.linestyle)
                pts = project(m.xs, m.ys, m.zs)
                prims += [
                    ((a[2] + b[2]) / 2, key, (a[0], a[1], b[0], b[1]))
                    for a, b in itertools.pairwise(pts)
                    if all(math.isfinite(v) for v in (*a, *b))
                ]
            elif m.kind in ("surface", "wireframe"):
                nr, nc = m.shape
                pts = project(m.xs, m.ys, m.zs)
                if m.kind == "wireframe":
                    key = ("seg", m.color, m.linewidth, "solid")
                    for r in range(nr):
                        for c in range(nc):
                            a = pts[r * nc + c]
                            for b in ([pts[r * nc + c + 1]] if c + 1 < nc else []) + (
                                [pts[(r + 1) * nc + c]] if r + 1 < nr else []
                            ):
                                prims.append(((a[2] + b[2]) / 2, key, (a[0], a[1], b[0], b[1])))
                    continue
                zs = m.zs
                zlo, zhi = _core.finite_range(zs) or (0.0, 1.0)
                key = ("poly", None, 0.0)
                for r in range(nr - 1):
                    for c in range(nc - 1):
                        idx = (r * nc + c, r * nc + c + 1, (r + 1) * nc + c + 1, (r + 1) * nc + c)
                        q = [pts[i] for i in idx]
                        if not all(math.isfinite(v) for p in q for v in p):
                            continue
                        if m.cmap is not None:
                            zc = sum(zs[i] for i in idx) / 4
                            col = with_alpha(m.cmap((zc - zlo) / ((zhi - zlo) or 1.0)), m.alpha)
                        else:
                            col = m.color
                        prims.append(
                            (
                                sum(p[2] for p in q) / 4,
                                key,
                                ([p[0] for p in q], [p[1] for p in q], col),
                            )
                        )
            elif m.kind == "bar":
                dxs, dys, dzs = m.extra
                edge = _darker(m.color)
                key = ("poly", edge, 0.6)
                for i in range(len(m.xs)):
                    a, b = (
                        (m.xs[i], m.ys[i], m.zs[i]),
                        (m.xs[i] + dxs[i], m.ys[i] + dys[i], m.zs[i] + dzs[i]),
                    )
                    cx = [a[0], b[0], b[0], a[0], a[0], b[0], b[0], a[0]]
                    cy = [a[1], a[1], b[1], b[1], a[1], a[1], b[1], b[1]]
                    cz = [a[2]] * 4 + [b[2]] * 4
                    cp = project(cx, cy, cz)
                    for face in (
                        (0, 1, 2, 3),
                        (4, 5, 6, 7),
                        (0, 1, 5, 4),
                        (2, 3, 7, 6),
                        (1, 2, 6, 5),
                        (0, 3, 7, 4),
                    ):
                        q = [cp[f] for f in face]
                        prims.append(
                            (
                                sum(p[2] for p in q) / 4,
                                key,
                                ([p[0] for p in q], [p[1] for p in q], m.color),
                            )
                        )
            elif m.kind == "quiver":
                us, vs, ws = m.extra
                base = project(m.xs, m.ys, m.zs)
                tips = project(
                    data.f64([a + b for a, b in zip(m.xs, us, strict=True)]),
                    data.f64([a + b for a, b in zip(m.ys, vs, strict=True)]),
                    data.f64([a + b for a, b in zip(m.zs, ws, strict=True)]),
                )
                seg, pt = ("seg", m.color, m.linewidth, "solid"), ("pt", "o", 3.0, m.color, None)
                for a, b in zip(base, tips, strict=True):
                    prims.append(((a[2] + b[2]) / 2, seg, (a[0], a[1], b[0], b[1])))
                    prims.append((b[2], pt, b))
        prims.sort(key=lambda p: p[0])
        batch = _Batcher(canvas)
        for _, key, item in prims:
            batch.add(key, item)
        batch.flush()

        center = unit((0.0, 0.0, 0.0))

        def place(
            anchor: Vec3, text: Label, size: float, outward: float, weight: str = "normal"
        ) -> None:
            px, py, _ = unit(anchor)
            vx, vy = px - center[0], py - center[1]
            n = math.hypot(vx, vy) or 1.0
            canvas.text(
                px + vx / n * outward,
                py + vy / n * outward,
                text,
                size,
                weight=weight,
                ha="center",
                va="center",
            )

        x_edge = max((-0.5, 0.5), key=lambda v: unit((0.0, v, zb))[1])
        y_edge = max((-0.5, 0.5), key=lambda v: unit((v, 0.0, zb))[1])
        z_edge = min(
            ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)),
            key=lambda c: unit((c[0], c[1], 0.0))[0],
        )
        ts, ls, lw = th.tick_label_size, th.axis_label_size, th.axis_label_weight
        for t, s in xt:
            place((t, x_edge, zb), s, ts, 9.0)
        for t, s in yt:
            place((y_edge, t, zb), s, ts, 9.0)
        for t, s in zt:
            place((z_edge[0], z_edge[1], t), s, ts, 9.0)
        if self.xlabel:
            place((0.0, x_edge, zb), self.xlabel, ls, 26.0, lw)
        if self.ylabel:
            place((y_edge, 0.0, zb), self.ylabel, ls, 26.0, lw)
        if self.zlabel:
            place((z_edge[0], z_edge[1], 0.0), self.zlabel, ls, 30.0, lw)
        if self.title:
            e = canvas.measure(self.title, th.title_size, th.title_weight)
            canvas.text(
                x + w / 2,
                y - TITLE_GAP - e.depth,
                self.title,
                th.title_size,
                weight=th.title_weight,
                ha="center",
            )
        if self._legend is not None:
            items = _legend.entries(self._artists)
            if items:
                box = _legend.measure(canvas, items, self._legend)
                loc = "upper right" if self._legend.loc == "best" else self._legend.loc
                _legend.draw(
                    canvas,
                    box,
                    *_legend.place(
                        box, loc, View(_core.Transform(), x, y, w, h, (0, 1), (0, 1)), []
                    ),
                )

    # -- interactive export -------------------------------------------------------

    def _payload(self) -> dict[str, Any]:
        """This axes as JSON for the browser viewer, in unit-cube coordinates."""
        (x0, x1), (y0, y1), (z0, z1) = self.limits()
        sx, sy, sz = (x1 - x0) or 1.0, (y1 - y0) or 1.0, (z1 - z0) or 1.0

        def unit(
            xs: Sequence[float], ys: Sequence[float], zs: Sequence[float]
        ) -> list[list[float]]:
            return [
                [(a - x0) / sx - 0.5, (b - y0) / sy - 0.5, (c - z0) / sz - 0.5]
                for a, b, c in zip(xs, ys, zs, strict=True)
            ]

        marks: list[dict[str, Any]] = []
        for m in self._artists:
            assert isinstance(m, Mark3D)
            if m.kind == "scatter":
                marks.append(
                    {
                        "kind": "scatter",
                        "pts": unit(m.xs, m.ys, m.zs),
                        "color": list(m.color),
                        "edgecolor": list(m.edgecolor) if m.edgecolor else None,
                        "d": m.size,
                        "marker": m.marker,
                    }
                )
            elif m.kind in ("line", "wireframe"):
                nr, nc = m.shape if m.kind == "wireframe" else (1, len(m.xs))
                pts = unit(m.xs, m.ys, m.zs)
                rows = [pts[r * nc : (r + 1) * nc] for r in range(nr)]
                if m.kind == "wireframe":
                    rows += [[pts[r * nc + c] for r in range(nr)] for c in range(nc)]
                for row in rows:
                    marks.append(
                        {
                            "kind": "line",
                            "pts": row,
                            "color": list(m.color),
                            "linewidth": m.linewidth,
                            "dash": dash(m.linestyle),
                        }
                    )
            elif m.kind == "surface":
                nr, nc = m.shape
                zlo, zhi = _core.finite_range(m.zs) or (0.0, 1.0)
                colors = []
                for r in range(nr - 1):
                    for c in range(nc - 1):
                        zc = (
                            m.zs[r * nc + c]
                            + m.zs[r * nc + c + 1]
                            + m.zs[(r + 1) * nc + c]
                            + m.zs[(r + 1) * nc + c + 1]
                        ) / 4
                        col = m.cmap((zc - zlo) / ((zhi - zlo) or 1.0)) if m.cmap else m.color
                        colors.append(list(col[:3]))
                marks.append(
                    {
                        "kind": "surface",
                        "nr": nr,
                        "nc": nc,
                        "verts": unit(m.xs, m.ys, m.zs),
                        "facecolors": colors,
                    }
                )
        th = self.theme
        legend = None
        if self._legend is not None:
            items = _legend.entries(self._artists)
            legend = {
                "loc": "upper right" if self._legend.loc == "best" else self._legend.loc,
                "entries": [
                    {
                        "kind": "scatter" if k.kind == "marker" else "line",
                        "label": str(lbl),
                        "color": list(k.color),
                        "marker": k.marker,
                        "dash": dash(k.linestyle) if k.linestyle not in ("none",) else None,
                    }
                    for lbl, k in items
                ],
            }
        return {
            "title": str(self.title) if self.title else None,
            "xlabel": str(self.xlabel) if self.xlabel else None,
            "ylabel": str(self.ylabel) if self.ylabel else None,
            "zlabel": str(self.zlabel) if self.zlabel else None,
            "elev": self.elev,
            "azim": self.azim,
            "xticks": [[t, s] for t, s in self._ticks(x0, x1)],
            "yticks": [[t, s] for t, s in self._ticks(y0, y1)],
            "zticks": [[t, s] for t, s in self._ticks(z0, z1)],
            "marks": marks,
            "legend": legend,
            "theme": {
                "grid": list(GRID),
                "pane_fill": list(PANE_FILL),
                "pane_edge": list(PANE_EDGE),
                "text": list(th.text_color),
                "tick_size": th.tick_label_size,
                "axis_size": th.axis_label_size,
                "title_size": th.title_size,
                "cube_fill": CUBE_FILL,
                "bg": list(th.figure_facecolor or (255, 255, 255, 255)),
            },
        }
