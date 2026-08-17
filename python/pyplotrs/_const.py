"""Shared spacing, color and unit constants for the figure layer.

One definition each, imported by every module that draws. Phase 5 deleted a
second copy of these that shadowed `theme.py`; keeping them in one module
makes that class of drift a `NameError` rather than a silent divergence.
"""

from __future__ import annotations

# Gaps (points) framing a figure-level legend within its reserved right column:
# space between the axes grid and the box, and between the box and figure edge.
_LEGEND_COL_GAP_L = 10.0
_LEGEND_COL_GAP_R = 2.0

# Type scale (points), calibrated for journal figure sizes.
#: Points sampled per mark when `legend(loc="best")` looks for a clear corner.
#: Capped so the search stays a fixed small cost rather than scaling with data.
_LEGEND_PROBE_POINTS = 60

#: Default canvas size (points) for every figure entry point: `subplots`,
#: `subplot_mosaic`, `figure` and `Figure` itself. 250 pt is a single journal
#: column (~3.5 in), so the default lands at publication size rather than
#: needing to be shrunk down to one. Defined here, once, because four separate
#: copies of a default is the drift this module exists to prevent.
DEFAULT_FIGSIZE = (250.0, 200.0)

# Spacing (points).
_TICK_LENGTH = 2.5
_TICK_LABEL_GAP = 2.5

_AXIS_LABEL_GAP = 3.0
_TITLE_GAP = 4.0

_OUTER_MARGIN = 6.0
_INLINE_DPI = 150.0  # raster resolution for Jupyter `_repr_png_` inline display
#: Raster resolution for an inline `Animation`. Lower than a still figure's,
#: because an animation multiplies the resolution by its frame count and the
#: result is stored base64-encoded inside the `.ipynb`: the guide's 60-frame
#: 360x220pt wave is 297 KB here against 469 KB at 150.
_INLINE_ANIM_DPI = 100.0

_WSPACE = 26.0
_HSPACE = 24.0

# Colorbar geometry (points).
_CBAR_GAP = 8.0  # between the plot's right edge and the color strip
_CBAR_WIDTH = 11.0  # width of the color strip

_CBAR_TICK_LEN = 2.5
_CBAR_TICK_GAP = 2.5

# 3D chrome.
_PANE_FILL = (242, 242, 242, 255)  # back-wall panes
_PANE_EDGE = (170, 170, 170, 255)  # pane borders (the 3 axis frames)

_GRID_3D = (214, 214, 214, 255)  # 3D gridlines
_CUBE_FILL = 0.86  # fraction of the plot rect the projected cube fills

_DATA_PAD = 0.05  # fraction of range added as margin around data

#: Expansion applied to a *degenerate* (zero-span) range, before `_DATA_PAD`.
#: `_DEGENERATE_REL` is a fraction of the value's own magnitude, so a constant
#: series lands on a scale that means something at any size; `_DEGENERATE_ABS`
#: is the floor for a value that has no magnitude to scale from (zero, or a
#: subnormal where the relative term underflows). See `_util._expand_degenerate`.
_DEGENERATE_REL = 0.05
_DEGENERATE_ABS = 0.5

#: Half-width of the category slot a boxplot reserves per position, in data
#: units. The value axis is sized from this rather than from `widths`, so
#: narrowing the boxes thins the glyphs instead of zooming the axis in on them.
#: 0.5 matches matplotlib and puts adjacent integer positions exactly edge to
#: edge.
_BOX_SLOT = 0.5

#: Pie slice labels. `_PIE_LABEL_R` is where a label's anchor sits, in wedge
#: radii, so the text clears the rim. A label's *width* is a device length the
#: data limits know nothing about, so the pie is sized in device space instead
#: (see `Axes._pie_geometry`): it shrinks until every label fits the plot rect.
#: `_PIE_MIN_RADIUS` floors that shrink - a label wider than the rect would
#: otherwise drive the radius to nothing, and a legible pie with one overhanging
#: label beats a dot with a tidy one. It is a fraction of the radius the pie
#: would have with no labels at all.
_PIE_LABEL_R = 1.12
_PIE_MIN_RADIUS = 0.5
_PIE_WEDGE_STROKE = 1.0  # separator stroke straddling each wedge edge

#: Width (points) of the face-colored outline drawn on tiled cells - hexbin's
#: hexagons - so their shared edges don't show a seam. Two cells that abut
#: exactly still split the pixels along that edge, and compositing them in turn
#: leaves the background partly uncovered; the outline straddles the edge and
#: covers the sliver. It has to be at least one device pixel wide to do that, so
#: this is sized for the coarsest resolution we render at: 1 pt spans a pixel
#: down to 72 dpi, and inline notebook figures (`_INLINE_DPI`) get two. The cost
#: is that a cell grows by half this, which is invisible next to a cell but is
#: why the outline is not made wider "to be safe".
_SEAM_STROKE = 1.0

# Figure size units. pyplotrs sizes figures in *points* by default, so a plot can
# be reasoned about directly against its font scale (e.g. a 480x360 pt figure
# with a 10 pt font). These factors convert a length in the named unit to points
# (1 pt = 1/72 in).
_UNIT_TO_PT = {"pt": 1.0, "in": 72.0, "cm": 72.0 / 2.54, "mm": 72.0 / 25.4}

#: Cache of colormap -> 1024-byte RGBA LUT. `Colormap` has no `__eq__`, so this
#: keys on object identity while holding the colormap alive - unlike an `id()`
#: key, which a later allocation at the same address could impersonate.
#: Bounded so a program minting many ad-hoc colormaps cannot grow it without end.
_LUT_CACHE: dict = {}

_LUT_CACHE_MAX = 64

_DASH_PATTERNS: dict = {
    "solid": None,
    "-": None,
    "dashed": [4.0, 3.0],
    "--": [4.0, 3.0],
    "dotted": [1.0, 2.5],
    ":": [1.0, 2.5],
    "dashdot": [5.0, 2.0, 1.0, 2.0],
    "-.": [5.0, 2.0, 1.0, 2.0],
    "none": None,
    None: None,
}

_HATCH_SPACING = 6.0  # device-point gap between hatch lines
_ELLIPSE_N = 72  # polygon segments approximating an ellipse/circle patch

#: Legend kinds drawn as a filled swatch rather than a line or marker. The
#: colormapped and area kinds join the bar family here: none of them is a
#: stroke, so a rule would misrepresent them. Each carries a single "color"
#: chosen at construction (the colormap midpoint for the mapped kinds).
_LEGEND_SWATCH_KINDS = ("bar", "barh", "hist", "fill", "broken_barh",
                        "boxplot", "violin", "image", "hexbin", "quadmesh",
                        "contourf", "pie")
