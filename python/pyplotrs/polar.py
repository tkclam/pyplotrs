"""``PolarAxes``: theta/r marks on a circular frame."""

from __future__ import annotations

import math

from . import scales as _scales
from . import ticker as _ticker
from ._const import _TITLE_GAP
from ._draw import (
    _check_marker,
    _dash_for,
    _draw_legend_box,
    _draw_marker,
    _draws_line,
    _measure_legend,
    _text,
    _th,
    _tw,
)
from .axes import _AxesBase
from .theme import Theme


def _theta_zero(loc) -> float:
    """Resolve a ``theta_zero_location`` to the angle (radians) drawn at
    ``theta == 0``. Accepts a number (radians) or ``"E"``/``"N"``/``"W"``/``"S"``."""
    if isinstance(loc, (int, float)):
        return float(loc)
    return {"E": 0.0, "N": math.pi / 2.0, "W": math.pi, "S": -math.pi / 2.0}.get(
        str(loc).upper(), 0.0)


class PolarAxes(_AxesBase):
    """A polar axes: ``plot(theta, r)`` and ``scatter(theta, r)``.

    Angles are in **radians**, measured counter-clockwise from the positive
    x-axis (East), matching matplotlib's default; change this with
    ``set(theta_zero_location=...)`` / ``set(theta_direction=...)``. Create one
    with ``subplots(projection="polar")`` or ``add_subplot(spec,
    projection="polar")``.
    """

    # A polar plot fills its cell; no corner search is meaningful.
    _LEGEND_DEFAULT_LOC = "upper right"

    def __init__(self, theme: Theme | None = None) -> None:
        self._init_common(theme)
        self._marks: list[dict] = []
        self._xlabel: str | None = None  # kept for _accessible_text() compatibility
        self._ylabel: str | None = None
        self._rmin = 0.0
        self._rmax: float | None = None
        self._rticks: list[float] | None = None
        self._thetagrids_deg: list[float] | None = None  # spoke angles, degrees
        self._theta_offset = 0.0  # angle (rad) drawn at theta == 0
        self._theta_dir = 1  # +1 counter-clockwise (default), -1 clockwise
        self._rlabel_deg = 22.5  # angle (deg) along which radial labels sit

    # -- public API ---------------------------------------------------------

    def plot(self, theta, r, *, label: str | None = None, color=None,
             linewidth: float | None = None, alpha: float = 1.0,
             linestyle: str = "solid",
             marker: str | None = None, markersize: float = 5.0,
             zorder: float = 0.0) -> "PolarAxes":
        """Line through polar points ``(theta, r)`` (``theta`` in radians)."""
        _check_marker(marker)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "line",
            "theta": [float(t) for t in theta],
            "r": [float(v) for v in r],
            "label": label,
            "color": self._mark_color(color, alpha),
            "linewidth": self._theme.line_width if linewidth is None else float(linewidth),
            "linestyle": linestyle,
            "marker": marker,
            "markersize": float(markersize),
        })
        return self

    def scatter(self, theta, r, *, label: str | None = None, color=None,
                markersize: float | None = None, alpha: float = 1.0,
                marker: str = "o", edgecolor=None,
                size: float | None = None, zorder: float = 0.0) -> "PolarAxes":
        """Scatter polar points ``(theta, r)`` (``theta`` in radians).

        ``markersize`` is a diameter in points; ``size`` is the matplotlib-style
        area in pt² (see ``Axes.scatter``)."""
        _check_marker(marker)
        self._marks.append({
            "zorder": float(zorder),
            "kind": "scatter",
            "theta": [float(t) for t in theta],
            "r": [float(v) for v in r],
            "label": label,
            "color": self._mark_color(color, alpha),
            "markersize": self._marker_diameter(markersize, size),
            "marker": marker,
            "edgecolor": None if edgecolor is None else self._theme.resolve(edgecolor),
        })
        return self

    def set(self, *, title=None, rmin=None, rmax=None, rticks=None, thetagrids=None,
            theta_zero_location=None, theta_direction=None,
            rlabel_position=None) -> "PolarAxes":
        """Set polar options: ``title``; radial limits ``rmin``/``rmax``; explicit
        ``rticks`` (radii) and ``thetagrids`` (spoke angles, degrees); the zero
        location (``"E"``/``"N"``/``"W"``/``"S"`` or radians); the ``theta_direction``
        (``1`` counter-clockwise or ``-1`` clockwise); and ``rlabel_position`` (the
        angle in degrees along which radial tick labels are placed)."""
        if title is not None:
            self._title = title
        if rmin is not None:
            self._rmin = float(rmin)
        if rmax is not None:
            self._rmax = float(rmax)
        if rticks is not None:
            self._rticks = [float(v) for v in rticks]
        if thetagrids is not None:
            self._thetagrids_deg = [float(v) for v in thetagrids]
        if theta_zero_location is not None:
            self._theta_offset = _theta_zero(theta_zero_location)
        if theta_direction is not None:
            self._theta_dir = -1 if theta_direction in (-1, "clockwise", "cw") else 1
        if rlabel_position is not None:
            self._rlabel_deg = float(rlabel_position)
        return self

    # No `set_rmax`/`set_title`/... wrappers here. They were the only
    # matplotlib-style individual setters in the library - `Axes` and `Axes3D`
    # have never had any - so polar code read differently from every other
    # panel while doing strictly less than `set()` already does. Nothing in the
    # tree used them. Writing is one idiom now: bulk `set(**kwargs)`. Reading
    # is the `get_*` accessors, which is a separate concern and stays separate.

    def get_rlim(self) -> tuple[float, float]:
        """Effective radial limits: explicit if set, else out to the data."""
        return self._rlimits()

    def get_rticks(self) -> list[float]:
        return list(self._rticks) if self._rticks else []

    def get_thetagrids(self) -> list[float]:
        """Spoke angles in degrees."""
        return list(self._thetagrids_deg) if self._thetagrids_deg else []

    def get_theta_direction(self) -> int:
        return self._theta_dir

    # -- drawing contract (mirrors Axes / Axes3D) ---------------------------

    def _rlimits(self) -> tuple[float, float]:
        rs = [v for m in self._marks for v in m["r"]]
        rmax = self._rmax if self._rmax is not None else (max(rs) if rs else 1.0)
        rmin = self._rmin
        if rmax <= rmin:
            rmax = rmin + 1.0
        return rmin, rmax

    def _ranges(self):
        # Polar opts out of 2D shared-range unification.
        return ((0.0, 1.0), (0.0, 1.0))

    def _bands(self, scene, xr, yr):
        title_h = 0.0
        if self._title:
            a, d = _th(scene, self._title, self._theme.title_size)
            title_h = a + d + _TITLE_GAP
        return (title_h, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), [], []

    def _draw(self, scene, layout, xr, yr, xticks, yticks) -> None:
        t = self._theme
        plot = layout.plot
        cx = plot.x + plot.w / 2.0
        cy = plot.y + plot.h / 2.0
        spokes = (self._thetagrids_deg if self._thetagrids_deg is not None
                  else [i * 45.0 for i in range(8)])

        # Theta tick labels hang off the rim, so measure them before sizing the
        # dial. A label centered a fixed distance outside `R` still crosses the
        # circle whenever it is wider than that distance, so each one is pushed
        # out by its own half-box along its spoke: for a box with half-extents
        # (hw, hh) the support distance along direction `a` is
        # hw*|cos a| + hh*|sin a|, which puts the *near* edge - not the center -
        # `gap` clear of the rim, whatever the label says or which way it leans.
        gap = t.tick_label_size * 0.5
        labels = []
        for deg in spokes:
            a = self._theta_offset + self._theta_dir * math.radians(deg)
            lab = _ticker.fix_minus(f"{deg:g}°")
            asc, desc = _th(scene, lab, t.tick_label_size)
            labels.append((a, lab, _tw(scene, lab, t.tick_label_size) / 2.0,
                           (asc + desc) / 2.0, (asc - desc) / 2.0))

        # The ring those labels need varies by direction, so solve for the
        # largest radius whose labels still land inside the cell rather than
        # reserving one worst-case pad all the way round.
        half_w, half_h = plot.w / 2.0, plot.h / 2.0
        R = min(half_w, half_h)
        for a, _lab, hw, hh, _base in labels:
            ca, sa = abs(math.cos(a)), abs(math.sin(a))
            off = gap + hw * ca + hh * sa  # center sits at R + off along the spoke
            if ca > 1e-9:  # (R + off)*ca + hw <= half_w
                R = min(R, (half_w - hw - off * ca) / ca)
            if sa > 1e-9:
                R = min(R, (half_h - hh - off * sa) / sa)
        R = max(1.0, R)
        rmin, rmax = self._rlimits()
        rspan = (rmax - rmin) or 1.0

        def to_dev(theta, r):
            a = self._theta_offset + self._theta_dir * theta
            rr = (r - rmin) / rspan * R
            # Screen y grows downward, so negate sin to keep angles counter-clockwise.
            return (cx + rr * math.cos(a), cy - rr * math.sin(a))

        if self._rticks is not None:
            rgrid = [(v, _ticker.fix_minus(f"{v:g}")) for v in self._rticks]
        else:
            rgrid = list(_scales.nice_ticks(rmin, rmax, 5))
        rgrid = [(v, lab) for (v, lab) in rgrid if rmin < v <= rmax + 1e-9]

        # 1. Radial spokes (theta gridlines) from the center to the rim.
        for deg in spokes:
            x1, y1 = to_dev(math.radians(deg), rmax)
            scene.add_path([(cx, cy), (x1, y1)], stroke_color=t.grid_color,
                           stroke_width=t.grid_width)
        # 2. Concentric r-circles at each radial tick.
        for rv, _lab in rgrid:
            pts = [to_dev(2.0 * math.pi * k / 96.0, rv) for k in range(97)]
            scene.add_path(pts, stroke_color=t.grid_color, stroke_width=t.grid_width)
        # 3. Outer spine circle at rmax.
        rim = [to_dev(2.0 * math.pi * k / 128.0, rmax) for k in range(129)]
        scene.add_path(rim, stroke_color=t.spine_color, stroke_width=t.spine_width)

        # 4. Theta tick labels, each clear of the rim along its own spoke.
        for a, lab, hw, hh, base in labels:
            out = R + gap + hw * abs(math.cos(a)) + hh * abs(math.sin(a))
            lx = cx + out * math.cos(a)
            ly = cy - out * math.sin(a)
            _text(scene, lx - hw, ly + base, lab, t.tick_label_size, t.text_color)
        # 5. Radial tick labels along the rlabel spoke.
        ra = self._theta_offset + self._theta_dir * math.radians(self._rlabel_deg)
        for rv, lab in rgrid:
            rr = (rv - rmin) / rspan * R
            lx = cx + rr * math.cos(ra) + 2.0
            ly = cy - rr * math.sin(ra)
            _text(scene, lx, ly, lab, t.tick_label_size, t.text_color)

        # 6. Data marks, projected through the polar map.
        for m in self._ordered_marks():
            dev = [to_dev(th, rv) for th, rv in zip(m["theta"], m["r"])]
            if m["kind"] == "line":
                if _draws_line(m["linestyle"]) and len(dev) >= 2:
                    scene.add_path(dev, stroke_color=m["color"], stroke_width=m["linewidth"],
                                   dash=_dash_for(m["linestyle"]), cap="round", join="round")
                if m.get("marker"):
                    for x, y in dev:
                        _draw_marker(scene, x, y, m["markersize"], m["marker"], m["color"])
            else:  # scatter
                d = m["markersize"]
                for x, y in dev:
                    _draw_marker(scene, x, y, d, m["marker"], m["color"],
                                 edgecolor=m["edgecolor"])

        # 7. Title in its reserved band.
        if self._title:
            a, _d = _th(scene, self._title, t.title_size)
            tw = _tw(scene, self._title, t.title_size)
            _text(scene, plot.x + (plot.w - tw) / 2.0, layout.title.y + a, self._title,
                  t.title_size, t.text_color)

        # 8. Auto-legend for labeled marks, inset in the plot rect.
        if self._legend is not None:
            entries = self._legend_entries()
            if entries:
                box_w, box_h, mt = _measure_legend(scene, entries, t, self._legend)
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
