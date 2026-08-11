""":class:`Axes3D`: 3D marks projected to 2D by an orthographic camera.

The camera and the per-vertex projection live in the ``pyplotrs-3d`` crate.
This module builds primitives, sorts them back-to-front, and emits ordinary 2D
paths, so no backend ever sees anything three-dimensional.
"""

from __future__ import annotations

import math

from . import _pyplotrs_core as _core
from . import colormaps as _colormaps
from . import scales as _scales
from . import threed as _threed
from .theme import Theme

from ._const import (
    _CUBE_FILL,
    _GRID_3D,
    _PANE_EDGE,
    _PANE_FILL,
    _TITLE_GAP,
)
from ._util import (
    _as_seq,
    _auto_levels,
    _bilinear_grid,
    _darker,
    _data_range,
    _delaunay,
    _to_f64,
    _with_alpha,
)
from ._draw import (
    _dash_for,
    _draw_legend_box,
    _draw_marker,
    _font,
    _measure_legend,
    _text,
    _th,
    _tw,
)
from .axes import _AxesBase


def _grid_xyz(X, Y, Z):
    """Normalize surface inputs to 2D grids ``(gx, gy, gz, nrows, ncols)``.

    ``Z`` is a 2D ``nrows x ncols`` grid. ``X``/``Y`` may each be 2D grids of
    the same shape, or 1D (``X`` length ncols, ``Y`` length nrows), in which
    case they are broadcast.
    """
    gz = [[float(v) for v in row] for row in Z]
    nr = len(gz)
    nc = len(gz[0]) if gz else 0

    def is_2d(a) -> bool:
        return len(a) > 0 and isinstance(a[0], (list, tuple))

    if is_2d(X):
        gx = [[float(v) for v in row] for row in X]
    else:
        col = [float(v) for v in X]
        gx = [list(col) for _ in range(nr)]
    if is_2d(Y):
        gy = [[float(v) for v in row] for row in Y]
    else:
        rowv = [float(v) for v in Y]
        gy = [[rowv[i]] * nc for i in range(nr)]
    return gx, gy, gz, nr, nc


class Axes3D(_AxesBase):
    """A 3D axes. Marks (scatter/plot/surface) are projected to 2D paths by an
    orthographic camera and depth-sorted, then drawn through the normal IR."""

    # A 3D cell is filled by the projection, so there is no reliably clear
    # corner to search for; pin one instead.
    _LEGEND_DEFAULT_LOC = "upper right"
    _MARKS_ATTR = "_marks3"

    def __init__(self, theme: Theme | None = None) -> None:
        self._init_common(theme)
        self._marks3: list[dict] = []
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        self._zlabel: str | None = None
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None
        self._zlim: tuple[float, float] | None = None
        self._elev = 30.0
        self._azim = -60.0

    # -- public API ---------------------------------------------------------

    def scatter(self, xs, ys, zs, *, label: str | None = None, color=None,
                markersize: float | None = None, alpha: float = 1.0,
                marker: str = "o", edgecolor=None, size: float | None = None) -> "Axes3D":
        """Scatter 3D points at ``(xs, ys, zs)``.

        ``markersize`` is a diameter in points; ``size`` is the matplotlib-style
        area in pt² (see :meth:`Axes.scatter`)."""
        self._marks3.append({
            "kind": "scatter",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "zs": [float(z) for z in zs],
            "label": label,
            "color": self._mark_color(color, alpha),
            "markersize": self._marker_diameter(markersize, size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def plot(self, xs, ys, zs, *, label: str | None = None, color=None,
             linewidth: float = 1.5, alpha: float = 1.0,
             linestyle: str = "solid", depthsort: bool = True) -> "Axes3D":
        """Draw a 3D polyline through ``(xs, ys, zs)``.

        ``depthsort`` controls how the line takes part in the painter's-order
        pass. With it on (the default) each **segment** is sorted separately,
        so the line occludes itself and interleaves correctly with surfaces and
        points it passes through - which is what makes a knotted or spiraling
        curve read as 3D at all. That costs one stroked path per segment, and
        on a long line the rasterizer notices.

        With it off the whole polyline is one path at a single depth: much
        faster on dense lines, and what matplotlib's mplot3d always does, at
        the cost of a line that cannot pass behind anything - including itself.
        """
        self._marks3.append({
            "kind": "line",
            "xs": [float(x) for x in xs],
            "ys": [float(y) for y in ys],
            "zs": [float(z) for z in zs],
            "label": label,
            "color": self._mark_color(color, alpha),
            "linewidth": float(linewidth),
            "linestyle": linestyle,
            "depthsort": bool(depthsort),
        })
        return self

    def surface(self, X, Y, Z, *, cmap="viridis", alpha: float = 1.0,
                label: str | None = None) -> "Axes3D":
        """Draw a colormapped surface over the grid ``(X, Y, Z)``."""
        gx, gy, gz, nr, nc = _grid_xyz(X, Y, Z)
        zflat = [v for row in gz for v in row]
        cm = _colormaps.get_cmap(cmap)
        self._marks3.append({
            "kind": "surface",
            "gx": gx,
            "gy": gy,
            "gz": gz,
            "nr": nr,
            "nc": nc,
            "xflat": [v for row in gx for v in row],
            "yflat": [v for row in gy for v in row],
            "zflat": zflat,
            "zmin": min(zflat) if zflat else 0.0,
            "zmax": max(zflat) if zflat else 1.0,
            "cmap": cm,
            "alpha": float(alpha),
            "label": label,
            # Legend fallback: the colormap's midpoint stands for the surface.
            "color": _with_alpha(cm(0.5), alpha),
        })
        return self

    def bar3d(self, x, y, z, dx, dy, dz, *, color=None, alpha: float = 1.0,
              label: str | None = None) -> "Axes3D":
        """Draw 3D bars (boxes): base corners ``(x, y, z)`` with sizes
        ``(dx, dy, dz)`` (each a scalar or per-bar array)."""
        xs = [float(v) for v in x]
        n = len(xs)
        self._marks3.append({
            "kind": "bar3d", "xs": xs, "ys": [float(v) for v in y],
            "zs": [float(v) for v in z], "dx": _as_seq(dx, n), "dy": _as_seq(dy, n),
            "dz": _as_seq(dz, n), "color": self._mark_color(color, alpha), "label": label,
        })
        return self

    def plot_wireframe(self, X, Y, Z, *, color=None, linewidth: float = 0.8,
                       alpha: float = 1.0, label: str | None = None) -> "Axes3D":
        """Draw the grid ``(X, Y, Z)`` as a wireframe (row + column lines)."""
        gx, gy, gz, nr, nc = _grid_xyz(X, Y, Z)
        self._marks3.append({
            "kind": "wireframe", "gx": gx, "gy": gy, "gz": gz, "nr": nr, "nc": nc,
            "xflat": [v for row in gx for v in row],
            "yflat": [v for row in gy for v in row],
            "zflat": [v for row in gz for v in row],
            "color": self._mark_color(color, alpha), "linewidth": float(linewidth),
            "label": label,
        })
        return self

    def contour3d(self, X, Y, Z, *, levels=None, cmap="viridis",
                  linewidth: float = 1.5, alpha: float = 1.0,
                  label: str | None = None) -> "Axes3D":
        """Draw contour lines of the grid ``(X, Y, Z)`` at their z-heights
        (marching squares in Rust); each level colored from ``cmap``."""
        gx, gy, gz, nr, nc = _grid_xyz(X, Y, Z)
        flat = [v for row in gz for v in row]
        lvls = _auto_levels(flat, levels)
        lines = _core.contour_lines(flat, nc, nr, lvls)
        cm = _colormaps.get_cmap(cmap)
        lo, hi = (min(lvls), max(lvls)) if lvls else (0.0, 1.0)
        span = (hi - lo) or 1.0
        colors = [_with_alpha(cm((lv - lo) / span), alpha) for lv in lvls]
        self._marks3.append({
            "kind": "contour3d", "lines": lines, "gx": gx, "gy": gy, "levels": lvls,
            "colors": colors, "linewidth": float(linewidth), "label": label,
            # Legend fallback: the middle level's color stands for the line set.
            "color": colors[len(colors) // 2] if colors else _with_alpha((0, 0, 0, 255), alpha),
            "xflat": [v for row in gx for v in row],
            "yflat": [v for row in gy for v in row], "zflat": flat,
        })
        return self

    def plot_trisurf(self, x, y, z, *, triangles=None, cmap="viridis",
                     alpha: float = 1.0, label: str | None = None) -> "Axes3D":
        """Surface over scattered points ``(x, y, z)``: Delaunay-triangulate the
        ``(x, y)`` plane (unless ``triangles`` index-triples are given) and shade
        each facet by mean z."""
        xs = [float(v) for v in x]
        ys = [float(v) for v in y]
        zs = [float(v) for v in z]
        tris = triangles if triangles is not None else _delaunay(list(zip(xs, ys)))
        cm = _colormaps.get_cmap(cmap)
        self._marks3.append({
            "kind": "trisurf", "xs": xs, "ys": ys, "zs": zs,
            "tris": [tuple(t) for t in tris], "cmap": cm, "alpha": float(alpha),
            "zmin": min(zs) if zs else 0.0, "zmax": max(zs) if zs else 1.0,
            "xflat": xs, "yflat": ys, "zflat": zs, "label": label,
            # Legend fallback: the colormap's midpoint stands for the surface.
            "color": _with_alpha(cm(0.5), alpha),
        })
        return self

    def quiver3d(self, x, y, z, u, v, w, *, length: float = 1.0, color=None,
                 linewidth: float = 1.5, alpha: float = 1.0,
                 label: str | None = None) -> "Axes3D":
        """Draw 3D arrows ``(u, v, w)`` rooted at ``(x, y, z)``, scaled by
        ``length``."""
        self._marks3.append({
            "kind": "quiver3d", "xs": [float(v) for v in x], "ys": [float(v) for v in y],
            "zs": [float(v) for v in z], "us": [float(v) for v in u],
            "vs": [float(v) for v in v], "ws": [float(v) for v in w],
            "length": float(length), "color": self._mark_color(color, alpha),
            "linewidth": float(linewidth), "label": label,
        })
        # Autoscale should include arrow tips.
        self._marks3[-1]["xflat"] = [px + length * uu for px, uu in
                                     zip(self._marks3[-1]["xs"], self._marks3[-1]["us"])] + self._marks3[-1]["xs"]
        self._marks3[-1]["yflat"] = [py + length * vv for py, vv in
                                     zip(self._marks3[-1]["ys"], self._marks3[-1]["vs"])] + self._marks3[-1]["ys"]
        self._marks3[-1]["zflat"] = [pz + length * ww for pz, ww in
                                     zip(self._marks3[-1]["zs"], self._marks3[-1]["ws"])] + self._marks3[-1]["zs"]
        return self

    def voxels(self, filled, *, color=None, edgecolor=None, alpha: float = 1.0,
               label: str | None = None) -> "Axes3D":
        """Draw a 3D boolean occupancy grid ``filled[i][j][k]`` as unit cubes."""
        color = self._mark_color(color, alpha)
        cells = []
        for i, plane in enumerate(filled):
            for j, row in enumerate(plane):
                for k, on in enumerate(row):
                    if on:
                        cells.append((i, j, k))
        self._marks3.append({
            "kind": "voxels", "cells": cells, "color": color, "label": label,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
            "xflat": [0.0] + [c[0] + 1 for c in cells],
            "yflat": [0.0] + [c[1] + 1 for c in cells],
            "zflat": [0.0] + [c[2] + 1 for c in cells],
        })
        return self

    # matplotlib-style aliases.
    scatter3d = scatter
    plot3d = plot

    def set(self, *, title=None, xlabel=None, ylabel=None, zlabel=None,
            xlim=None, ylim=None, zlim=None, elev=None, azim=None) -> "Axes3D":
        if title is not None:
            self._title = title
        if xlabel is not None:
            self._xlabel = xlabel
        if ylabel is not None:
            self._ylabel = ylabel
        if zlabel is not None:
            self._zlabel = zlabel
        if xlim is not None:
            self._xlim = (float(xlim[0]), float(xlim[1]))
        if ylim is not None:
            self._ylim = (float(ylim[0]), float(ylim[1]))
        if zlim is not None:
            self._zlim = (float(zlim[0]), float(zlim[1]))
        if elev is not None:
            self._elev = float(elev)
        if azim is not None:
            self._azim = float(azim)
        return self

    # -- reading an axes back (mirrors Axes; see the note there) -------------

    def get_xlim(self) -> tuple[float, float]:
        """Effective x limits: explicit if set, else the data cube's extent."""
        return self._limits()[0]

    def get_ylim(self) -> tuple[float, float]:
        return self._limits()[1]

    def get_zlim(self) -> tuple[float, float]:
        return self._limits()[2]

    def get_xlabel(self) -> str | None:
        return self._xlabel

    def get_ylabel(self) -> str | None:
        return self._ylabel

    def get_zlabel(self) -> str | None:
        return self._zlabel

    def get_view(self) -> tuple[float, float]:
        """The camera as ``(elev, azim)`` in degrees."""
        return (self._elev, self._azim)

    # -- Figure protocol ----------------------------------------------------

    def _ranges(self):
        # 3D axes don't participate in 2D shared-range unification.
        return ((0.0, 1.0), (0.0, 1.0))

    def _bands(self, scene, xr, yr):
        title_h = 0.0
        if self._title:
            a, d = _th(scene, self._title, self._theme.title_size)
            title_h = a + d + _TITLE_GAP
        return (title_h, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), [], []

    def _limits(self):
        xs: list[float] = []
        ys: list[float] = []
        zs: list[float] = []
        for m in self._marks3:
            k = m["kind"]
            if k in ("scatter", "line"):
                xs += m["xs"]
                ys += m["ys"]
                zs += m["zs"]
            elif k == "bar3d":
                xs += m["xs"] + [a + b for a, b in zip(m["xs"], m["dx"])]
                ys += m["ys"] + [a + b for a, b in zip(m["ys"], m["dy"])]
                zs += m["zs"] + [a + b for a, b in zip(m["zs"], m["dz"])]
            elif k == "voxels":
                for i, j, kk in m["cells"]:
                    xs += [i, i + 1]
                    ys += [j, j + 1]
                    zs += [kk, kk + 1]
            elif "xflat" in m:
                xs += m["xflat"]
                ys += m["yflat"]
                zs += m["zflat"]
        if not xs:
            xs = ys = zs = [0.0, 1.0]
        xr = self._xlim or _data_range(xs)
        yr = self._ylim or _data_range(ys)
        zr = self._zlim or _data_range(zs)
        return xr, yr, zr

    def _draw(self, scene, layout, xr, yr, xticks, yticks) -> None:
        t = self._theme
        _TICK_LABEL_SIZE = t.tick_label_size
        _AXIS_LABEL_SIZE = t.axis_label_size
        _TITLE_SIZE = t.title_size
        _BLACK = t.text_color
        plot = layout.plot
        cam = _threed.Camera3D(self._elev, self._azim)
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = self._limits()
        xspan = (xmax - xmin) or 1.0
        yspan = (ymax - ymin) or 1.0
        zspan = (zmax - zmin) or 1.0

        def norm(x, y, z):
            return ((x - xmin) / xspan - 0.5, (y - ymin) / yspan - 0.5, (z - zmin) / zspan - 0.5)

        # Fit the projected unit cube into the plot rect, preserving aspect.
        # The bbox comes from Rust so the camera basis has exactly one
        # definition; `_threed` keeps the Python mirror only for the chrome.
        min_sx, max_sx, min_sy, max_sy = _core.cube_screen_bbox(self._elev, self._azim)
        bw = (max_sx - min_sx) or 1.0
        bh = (max_sy - min_sy) or 1.0
        scale = min(plot.w / bw, plot.h / bh) * _CUBE_FILL
        ccx = plot.x + plot.w / 2.0
        ccy = plot.y + plot.h / 2.0
        scx = (min_sx + max_sx) / 2.0
        scy = (min_sy + max_sy) / 2.0

        def to_dev(sx, sy):
            return (ccx + (sx - scx) * scale, ccy - (sy - scy) * scale)

        def projn(p):
            s = cam.view(p)
            dx, dy = to_dev(s[0], s[1])
            return (dx, dy, s[2])

        def proj(x, y, z):
            return projn(norm(x, y, z))

        # Batch projection: every vertex of a mark in one Rust pass, returning
        # device x/y plus eye-space depth. `proj` above stays for the axis
        # chrome, which is a few dozen points and not worth a round trip; the
        # marks are where the per-vertex Python cost actually lived.
        def proj_many(xs_, ys_, zs_):
            """`[(dx, dy, depth), ...]` for parallel data-space sequences."""
            dxs, dys, dzs = _core.project3d(
                _to_f64(xs_), _to_f64(ys_), _to_f64(zs_),
                self._elev, self._azim,
                xmin, xspan, ymin, yspan, zmin, zspan,
                ccx, ccy, scx, scy, scale)
            return list(zip(dxs, dys, dzs))

        def proj_grid(gx, gy, gz, nr, nc):
            """`proj_many` over a row-major grid, returned as rows."""
            flat = proj_many([v for row in gx for v in row],
                             [v for row in gy for v in row],
                             [v for row in gz for v in row])
            return [flat[r * nc:(r + 1) * nc] for r in range(nr)]

        center_dev = to_dev(0.0, 0.0)

        def depth_n(p):
            return cam.view(p)[2]

        # Back walls = the farther plane of each axis-aligned pair (smaller depth).
        z_back = -0.5 if depth_n((0.0, 0.0, -0.5)) < depth_n((0.0, 0.0, 0.5)) else 0.5
        x_back = -0.5 if depth_n((-0.5, 0.0, 0.0)) < depth_n((0.5, 0.0, 0.0)) else 0.5
        y_back = -0.5 if depth_n((0.0, -0.5, 0.0)) < depth_n((0.0, 0.5, 0.0)) else 0.5

        def axis_ticks(vmin, vmax):
            span = (vmax - vmin) or 1.0
            out = []
            for val, lab in _scales.nice_ticks(vmin, vmax, 5):
                frac = (val - vmin) / span
                if -1e-9 <= frac <= 1.0 + 1e-9:
                    out.append((frac - 0.5, lab))
            return out

        xt = axis_ticks(xmin, xmax)
        yt = axis_ticks(ymin, ymax)
        zt = axis_ticks(zmin, zmax)

        # 1. Back panes + gridlines.
        def quad(p0, p1, p2, p3, fill, stroke=None):
            pts = [projn(p0)[:2], projn(p1)[:2], projn(p2)[:2], projn(p3)[:2]]
            scene.add_path(pts, fill_color=fill, close=True, stroke_color=stroke,
                           stroke_width=0.8 if stroke else 1.0)

        def gridline(p0, p1):
            scene.add_path([projn(p0)[:2], projn(p1)[:2]], stroke_color=_GRID_3D, stroke_width=0.6)

        quad((-0.5, -0.5, z_back), (0.5, -0.5, z_back), (0.5, 0.5, z_back), (-0.5, 0.5, z_back),
             _PANE_FILL, _PANE_EDGE)
        for nx, _ in xt:
            gridline((nx, -0.5, z_back), (nx, 0.5, z_back))
        for ny, _ in yt:
            gridline((-0.5, ny, z_back), (0.5, ny, z_back))

        quad((x_back, -0.5, -0.5), (x_back, 0.5, -0.5), (x_back, 0.5, 0.5), (x_back, -0.5, 0.5),
             _PANE_FILL, _PANE_EDGE)
        for ny, _ in yt:
            gridline((x_back, ny, -0.5), (x_back, ny, 0.5))
        for nz, _ in zt:
            gridline((x_back, -0.5, nz), (x_back, 0.5, nz))

        quad((-0.5, y_back, -0.5), (0.5, y_back, -0.5), (0.5, y_back, 0.5), (-0.5, y_back, 0.5),
             _PANE_FILL, _PANE_EDGE)
        for nx, _ in xt:
            gridline((nx, y_back, -0.5), (nx, y_back, 0.5))
        for nz, _ in zt:
            gridline((-0.5, y_back, nz), (0.5, y_back, nz))

        # 2. Data marks: project every primitive to (depth, draw_fn) and paint
        #    them in one global back-to-front order so surfaces, lines, bars and
        #    points that interpenetrate occlude each other correctly (a single
        #    depth sort across all marks, not per-mark).
        # ``(depth, draw, chain)`` per primitive. ``chain`` is reserved for the
        # unsorted-polyline path below and is ``None`` for depth-sorted marks.
        prims: list[tuple] = []

        def add_poly(pts3, fill, stroke=None, sw=1.0):
            if len(pts3) < 3:
                return
            depth = sum(p[2] for p in pts3) / len(pts3)
            dev = [(p[0], p[1]) for p in pts3]
            prims.append((depth, lambda: scene.add_path(
                dev, fill_color=fill, close=True, stroke_color=stroke,
                stroke_width=sw if stroke else 1.0), None))

        def add_seg(a3, b3, color, w, dash=None):
            prims.append(((a3[2] + b3[2]) / 2.0, lambda: scene.add_path(
                [(a3[0], a3[1]), (b3[0], b3[1])], stroke_color=color,
                stroke_width=w, cap="round", join="round", dash=dash), None))

        def add_point(p3, d, marker, fc, ec):
            prims.append((p3[2], lambda: _draw_marker(
                scene, p3[0], p3[1], d, marker, facecolor=fc, edgecolor=ec), None))

        def box_faces(x0, y0, z0, x1, y1, z1, fill, edge):
            c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                 (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            cp = [proj(*v) for v in c]
            for a, b, cc, dd in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                                 (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)):
                add_poly([cp[a], cp[b], cp[cc], cp[dd]], fill, edge, 0.6)

        for m in self._marks3:
            k = m["kind"]
            if k == "surface":
                gx, gy, gz = m["gx"], m["gy"], m["gz"]
                zmin, zmax, cm = m["zmin"], m["zmax"], m["cmap"]
                a = m["alpha"]
                zspd = (zmax - zmin) or 1.0
                grid = proj_grid(gx, gy, gz, m["nr"], m["nc"])
                for r in range(m["nr"] - 1):
                    row, nxt = grid[r], grid[r + 1]
                    gzr, gzn = gz[r], gz[r + 1]
                    for cc in range(m["nc"] - 1):
                        zc = (gzr[cc] + gzr[cc + 1] + gzn[cc + 1] + gzn[cc]) / 4.0
                        fc = cm((zc - zmin) / zspd)
                        add_poly([row[cc], row[cc + 1], nxt[cc + 1], nxt[cc]],
                                 fc if a >= 1.0 else _with_alpha(fc, a), None, 1.0)
            elif k == "trisurf":
                cm, zmin, zmax = m["cmap"], m["zmin"], m["zmax"]
                a = m["alpha"]
                zspd = (zmax - zmin) or 1.0
                pv = proj_many(m["xs"], m["ys"], m["zs"])
                zs_ = m["zs"]
                for a1, b, cc in m["tris"]:
                    zc = (zs_[a1] + zs_[b] + zs_[cc]) / 3.0
                    fc = cm((zc - zmin) / zspd)
                    add_poly([pv[a1], pv[b], pv[cc]], fc if a >= 1.0 else _with_alpha(fc, a),
                             t.separator_color, 0.4)
            elif k == "line":
                pr = proj_many(m["xs"], m["ys"], m["zs"])
                dash = _dash_for(m["linestyle"])
                if m.get("depthsort", True):
                    for i in range(len(pr) - 1):
                        add_seg(pr[i], pr[i + 1], m["color"], m["linewidth"], dash)
                elif len(pr) >= 2:
                    # One path at the line's mean depth: the whole polyline
                    # sorts as a single primitive.
                    dev = [(p[0], p[1]) for p in pr]
                    mean_d = sum(p[2] for p in pr) / len(pr)
                    prims.append((mean_d, lambda dev=dev, m=m, dash=dash: scene.add_path(
                        dev, stroke_color=m["color"], stroke_width=m["linewidth"],
                        cap="round", join="round", dash=dash), None))
            elif k == "wireframe":
                gx, gy, gz = m["gx"], m["gy"], m["gz"]
                grid = proj_grid(gx, gy, gz, m["nr"], m["nc"])
                for r in range(m["nr"]):
                    for c in range(m["nc"] - 1):
                        add_seg(grid[r][c], grid[r][c + 1], m["color"], m["linewidth"])
                for c in range(m["nc"]):
                    for r in range(m["nr"] - 1):
                        add_seg(grid[r][c], grid[r + 1][c], m["color"], m["linewidth"])
            elif k == "contour3d":
                gx, gy = m["gx"], m["gy"]
                # The kernel hands back whole contour lines; the painter's-
                # algorithm sort works on segments, so walk each line pairwise
                # (a closed line wrapping from its last point back to its first).
                for li, closed, pts in m["lines"]:
                    lv = m["levels"][li]
                    col = m["colors"][li] if li < len(m["colors"]) else m["colors"][-1]
                    proj_pts = [proj(_bilinear_grid(gx, py, px),
                                     _bilinear_grid(gy, py, px), lv) for px, py in pts]
                    if closed and proj_pts:
                        proj_pts.append(proj_pts[0])
                    for a, b in zip(proj_pts, proj_pts[1:]):
                        add_seg(a, b, col, m["linewidth"])
            elif k == "bar3d":
                for i in range(len(m["xs"])):
                    box_faces(m["xs"][i], m["ys"][i], m["zs"][i],
                              m["xs"][i] + m["dx"][i], m["ys"][i] + m["dy"][i],
                              m["zs"][i] + m["dz"][i], m["color"], _darker(m["color"]))
            elif k == "voxels":
                for i, j, kk in m["cells"]:
                    box_faces(float(i), float(j), float(kk), i + 1.0, j + 1.0, kk + 1.0,
                              m["color"], m["edgecolor"] or _darker(m["color"]))
            elif k == "quiver3d":
                L = m["length"]
                for i in range(len(m["xs"])):
                    base = proj(m["xs"][i], m["ys"][i], m["zs"][i])
                    tip = proj(m["xs"][i] + L * m["us"][i], m["ys"][i] + L * m["vs"][i],
                               m["zs"][i] + L * m["ws"][i])
                    add_seg(base, tip, m["color"], m["linewidth"])
                    add_point(tip, 3.0, "o", m["color"], None)
            elif k == "scatter":
                d = m["markersize"]
                for p3 in proj_many(m["xs"], m["ys"], m["zs"]):
                    add_point(p3, d, m["marker"], m["color"], m["edgecolor"])

        prims.sort(key=lambda p: p[0])  # back (small depth) to front
        for _depth, draw, _chain in prims:
            draw()

        # 3. Tick labels + axis labels (on top, offset radially outward).
        def place(anchor, text, size, outward):
            dx, dy, _ = projn(anchor)
            vx, vy = dx - center_dev[0], dy - center_dev[1]
            vlen = math.hypot(vx, vy) or 1.0
            dx += vx / vlen * outward
            dy += vy / vlen * outward
            tw = _tw(scene, text, size)
            a, dd, _ = scene.font_vmetrics(size)
            _text(scene, dx - tw / 2.0, dy + (a - dd) / 2.0, text, size, _BLACK)

        # x/y tick labels along the bottom-front edges; z along the leftmost edge.
        x_edge_y = max((-0.5, 0.5), key=lambda yy: projn((0.0, yy, z_back))[1])
        y_edge_x = max((-0.5, 0.5), key=lambda xx: projn((xx, 0.0, z_back))[1])
        z_edge = min(((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)),
                     key=lambda c: projn((c[0], c[1], 0.0))[0])

        for nx, lab in xt:
            place((nx, x_edge_y, z_back), lab, _TICK_LABEL_SIZE, 9.0)
        for ny, lab in yt:
            place((y_edge_x, ny, z_back), lab, _TICK_LABEL_SIZE, 9.0)
        for nz, lab in zt:
            place((z_edge[0], z_edge[1], nz), lab, _TICK_LABEL_SIZE, 9.0)

        if self._xlabel:
            place((0.0, x_edge_y, z_back), self._xlabel, _AXIS_LABEL_SIZE, 26.0)
        if self._ylabel:
            place((y_edge_x, 0.0, z_back), self._ylabel, _AXIS_LABEL_SIZE, 26.0)
        if self._zlabel:
            place((z_edge[0], z_edge[1], 0.0), self._zlabel, _AXIS_LABEL_SIZE, 30.0)

        # Title in its reserved band.
        title_font = _font(t.title_weight)
        label_font = _font(t.axis_label_weight)
        if self._title:
            a, _d = _th(scene, self._title, _TITLE_SIZE, title_font)
            tw = _tw(scene, self._title, _TITLE_SIZE, title_font)
            _text(scene, plot.x + (plot.w - tw) / 2.0, layout.title.y + a, self._title,
                  _TITLE_SIZE, _BLACK, title_font)

        # Auto-legend for labeled line/scatter marks, inset in the plot rect.
        if self._legend is not None:
            entries = self._legend_entries()
            if entries:
                box_w, box_h, mt = _measure_legend(scene, entries, self._theme, self._legend)
                inset = 6.0
                px, py, pw, ph = plot.x, plot.y, plot.w, plot.h
                corners = {
                    "upper right": (px + pw - inset - box_w, py + inset),
                    "upper left": (px + inset, py + inset),
                    "lower right": (px + pw - inset - box_w, py + ph - inset - box_h),
                    "lower left": (px + inset, py + ph - inset - box_h),
                }
                bx, by = corners.get(self._legend["loc"], corners["upper right"])
                _draw_legend_box(scene, entries, bx, by, mt)

    def _draw_surface(self, scene, m: dict, proj) -> None:
        gx, gy, gz = m["gx"], m["gy"], m["gz"]
        nr, nc = m["nr"], m["nc"]
        cm = m["cmap"]
        zmin, zspan = m["zmin"], (m["zmax"] - m["zmin"]) or 1.0
        faces = []
        for i in range(nr - 1):
            for j in range(nc - 1):
                p00 = proj(gx[i][j], gy[i][j], gz[i][j])
                p01 = proj(gx[i][j + 1], gy[i][j + 1], gz[i][j + 1])
                p11 = proj(gx[i + 1][j + 1], gy[i + 1][j + 1], gz[i + 1][j + 1])
                p10 = proj(gx[i + 1][j], gy[i + 1][j], gz[i + 1][j])
                depth = (p00[2] + p01[2] + p11[2] + p10[2]) / 4.0
                zc = (gz[i][j] + gz[i][j + 1] + gz[i + 1][j + 1] + gz[i + 1][j]) / 4.0
                color = cm((zc - zmin) / zspan)
                faces.append((depth, [p00[:2], p01[:2], p11[:2], p10[:2]], color))
        faces.sort(key=lambda f: f[0])  # back to front
        for _, pts, color in faces:
            scene.add_path(pts, fill_color=color, close=True, stroke_color=color, stroke_width=0.4)

    def _interactive_payload(self) -> dict:
        """Serialize this 3D axes into a JSON-able dict for the in-browser
        renderer (``_html3d``). Coordinates are pre-normalized into the
        ``[-0.5, 0.5]^3`` cube (same as :meth:`_draw`'s ``norm``) so the camera
        is all the JS has to apply; surface face colors are pre-sampled from the
        colormap (depth/order are recomputed per frame). Ticks and theme colors
        come along so the page reproduces the static look."""
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = self._limits()
        xspan, yspan, zspan = (xmax - xmin) or 1.0, (ymax - ymin) or 1.0, (zmax - zmin) or 1.0

        def nrm(x, y, z):
            return [(x - xmin) / xspan - 0.5, (y - ymin) / yspan - 0.5, (z - zmin) / zspan - 0.5]

        def ticks(vmin, vmax):
            span = (vmax - vmin) or 1.0
            out = []
            for val, lab in _scales.nice_ticks(vmin, vmax, 5):
                frac = (val - vmin) / span
                if -1e-9 <= frac <= 1.0 + 1e-9:
                    out.append([frac - 0.5, lab])
            return out

        marks: list[dict] = []
        for m in self._marks3:
            if m["kind"] == "scatter":
                marks.append({
                    "kind": "scatter",
                    "pts": [nrm(x, y, z) for x, y, z in zip(m["xs"], m["ys"], m["zs"])],
                    "color": list(m["color"]),
                    "edgecolor": list(m["edgecolor"]) if m["edgecolor"] else None,
                    "d": m["markersize"],
                    "marker": m["marker"],
                })
            elif m["kind"] == "line":
                marks.append({
                    "kind": "line",
                    "pts": [nrm(x, y, z) for x, y, z in zip(m["xs"], m["ys"], m["zs"])],
                    "color": list(m["color"]),
                    "linewidth": m["linewidth"],
                    "dash": _dash_for(m["linestyle"]),
                })
            elif m["kind"] == "surface":
                gx, gy, gz, nr, nc = m["gx"], m["gy"], m["gz"], m["nr"], m["nc"]
                cm = m["cmap"]
                zmn, zsp = m["zmin"], (m["zmax"] - m["zmin"]) or 1.0
                verts = [nrm(gx[i][j], gy[i][j], gz[i][j]) for i in range(nr) for j in range(nc)]
                facecolors = []
                for i in range(nr - 1):
                    for j in range(nc - 1):
                        zc = (gz[i][j] + gz[i][j + 1] + gz[i + 1][j + 1] + gz[i + 1][j]) / 4.0
                        r, g, b, _a = cm((zc - zmn) / zsp)
                        facecolors.append([r, g, b])
                marks.append({"kind": "surface", "nr": nr, "nc": nc,
                              "verts": verts, "facecolors": facecolors})

        legend = None
        if self._legend is not None:
            entries = self._legend_entries()
            if entries:
                legend = {
                    "loc": self._legend.get("loc", "upper right"),
                    "entries": [{
                        "kind": e["kind"], "label": e["label"], "color": list(e["color"]),
                        "marker": e.get("marker"),
                        "dash": _dash_for(e.get("linestyle", "solid")),
                    } for e in entries],
                }

        t = self._theme
        return {
            "title": self._title, "xlabel": self._xlabel,
            "ylabel": self._ylabel, "zlabel": self._zlabel,
            "elev": self._elev, "azim": self._azim,
            "xticks": ticks(xmin, xmax), "yticks": ticks(ymin, ymax), "zticks": ticks(zmin, zmax),
            "marks": marks, "legend": legend,
            "theme": {
                "grid": list(_GRID_3D), "pane_fill": list(_PANE_FILL), "pane_edge": list(_PANE_EDGE),
                "text": list(t.text_color), "tick_size": t.tick_label_size,
                "axis_size": t.axis_label_size, "title_size": t.title_size, "cube_fill": _CUBE_FILL,
            },
        }
