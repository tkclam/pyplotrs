"""Regression tests for specific defects.

Each test here corresponds to a bug that shipped and went unnoticed because
nothing exercised the path. Keep the reproduction minimal and name the symptom,
so a future failure reads as "this exact thing broke again".
"""

from __future__ import annotations

import re

import pytest

import pyplotrs as plt
from pyplotrs.theme import parse_color


# -- color parsing ----------------------------------------------------------

def test_float_rgb_is_not_truncated_to_black():
    """``(0.2, 0.4, 0.6)`` is matplotlib's color convention: floats in 0-1.

    pyplotrs took byte tuples and ran them through ``int()``, so every float
    color silently collapsed to black with no error - the worst kind of bug for
    someone porting a script over.
    """
    palette = plt.themes.default.palette
    assert parse_color((0.2, 0.4, 0.6), palette) == (51, 102, 153, 255)
    assert parse_color((1.0, 0.0, 0.0), palette) == (255, 0, 0, 255)
    assert parse_color((0.5, 0.5, 0.5), palette) == (128, 128, 128, 255)
    assert parse_color((1.0, 1.0, 1.0), palette) == (255, 255, 255, 255)


def test_byte_rgb_still_works():
    """Byte tuples must keep their meaning; the two conventions have to coexist."""
    palette = plt.themes.default.palette
    assert parse_color((255, 0, 0), palette) == (255, 0, 0, 255)
    assert parse_color((0, 114, 178, 255), palette) == (0, 114, 178, 255)
    assert parse_color((12, 34, 56), palette) == (12, 34, 56, 255)


def test_hex_and_named_colors_are_accepted():
    palette = plt.themes.default.palette
    assert parse_color("#ff0000", palette) == (255, 0, 0, 255)
    assert parse_color("#f00", palette) == (255, 0, 0, 255)
    assert parse_color("#0072b280", palette) == (0, 114, 178, 128)
    assert parse_color("red", palette) == (255, 0, 0, 255)
    assert parse_color("steelblue", palette) == (70, 130, 180, 255)


def test_palette_indices_still_resolve_against_the_theme():
    assert parse_color("C0", plt.themes.default.palette) == (0, 114, 178, 255)
    assert parse_color("C0", plt.themes.grayscale.palette) == (0, 0, 0, 255)


def test_unknown_color_string_still_raises():
    with pytest.raises(ValueError):
        parse_color("not-a-color", plt.themes.default.palette)


# -- legend ------------------------------------------------------------------

def test_barh_with_label_and_legend(tmp_path):
    """``ax.barh(label=...)`` + ``ax.legend()`` raised ``KeyError: 'linestyle'``.

    The legend glyph dispatcher fell through to its line branch, which reads a
    key the barh mark never sets.
    """
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.barh([0, 1, 2], [3, 5, 2], label="values")
    ax.legend()
    fig.save(str(tmp_path / "barh.png"))


@pytest.mark.parametrize("theme", ["default", "nature", "grayscale", "presentation"])
def test_legend_swatch_matches_the_theme_type_size(theme, tmp_path):
    """The legend box was *measured* at ``theme.legend_size`` but its swatches
    were *drawn* at a hardcoded 9.0 pt, so any theme with a different legend
    size mismatched."""
    fig, ax = plt.subplots(figsize=(240, 180), theme=theme)
    ax.line([0, 1], [0, 1], label="a")
    ax.legend()
    fig.save(str(tmp_path / f"{theme}.png"))


# -- scales at draw time -----------------------------------------------------

def test_errorbar_draws_line_and_markers_on_a_log_axis(tmp_path):
    """On a log axis ``errorbar`` silently dropped its connecting line *and* its
    markers, leaving bare whiskers.

    Two causes: the affine coefficients were recovered by sampling the transform
    at 0.0, which is ``-inf`` under a log scale; and the draw call never passed
    the scale codes, so Rust applied a linear transform. Compared against the
    equivalent ``line`` call, which always worked.
    """
    def count_marks(scale):
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.errorbar([1, 10, 100], [10, 100, 1000], yerr=[1, 10, 100])
        ax.set(yscale=scale, xscale=scale)
        out = tmp_path / f"err_{scale}.svg"
        fig.save(str(out))
        svg = out.read_text()
        return svg.count("<path"), svg.count("<use")

    lin_paths, lin_uses = count_marks("linear")
    log_paths, log_uses = count_marks("log")

    assert log_uses == lin_uses, (
        f"markers vanished on a log axis: {log_uses} vs {lin_uses} on linear"
    )
    assert log_paths >= lin_paths - 1, (
        f"geometry vanished on a log axis: {log_paths} paths vs {lin_paths} on linear"
    )


def test_errorbar_respects_log_positions(tmp_path):
    """The connecting line must be drawn through log-transformed positions, not
    linear ones. On a log axis with decade-spaced data the polyline is straight,
    so its midpoint sits at the vertical center of the plot area."""
    fig, ax = plt.subplots(figsize=(300, 300))
    ax.errorbar([1, 10, 100], [1, 10, 100], yerr=[0.1, 1, 10])
    ax.set(xscale="log", yscale="log")
    out = tmp_path / "logpos.svg"
    fig.save(str(out))
    assert "<path" in out.read_text()


# -- theming leaks -----------------------------------------------------------

def test_hist_bar_edges_follow_the_theme(tmp_path):
    """``hist`` hardcoded white bar separators, which disappear against any
    theme with a light plot background of its own - and look wrong on dark."""
    dark = plt.themes.default.with_(axes_facecolor=(30, 30, 30, 255))
    fig, ax = plt.subplots(figsize=(240, 180), theme=dark)
    ax.hist([1, 2, 2, 3, 3, 3, 4], bins=4)
    out = tmp_path / "hist_dark.svg"
    fig.save(str(out))
    svg = out.read_text()
    assert "#ffffff" not in svg.lower(), (
        "hist still emits hardcoded white edges under a dark theme"
    )


# -- 3D methods that never worked -------------------------------------------

@pytest.mark.parametrize("method", ["bar3d", "voxels", "contour3d"])
def test_3d_methods_that_referenced_undefined_helpers(method, tmp_path):
    """``bar3d`` and ``voxels`` called ``_darker``; ``contour3d`` called
    ``_bilinear_grid``. Neither helper was ever defined in any commit, so all
    three raised ``NameError`` on every call since they were written."""
    fig, ax = plt.subplots(figsize=(240, 180), projection="3d")
    xs = [-1.0, 0.0, 1.0]
    if method == "bar3d":
        ax.bar3d([0, 1], [0, 1], [0, 0], 0.5, 0.5, [1, 2])
    elif method == "voxels":
        ax.voxels([[[True, False], [False, True]], [[False, True], [True, False]]])
    else:
        X = [xs[:] for _ in xs]
        Y = [[v] * 3 for v in xs]
        Z = [[x * x + y * y for x in xs] for y in xs]
        ax.contour3d(X, Y, Z)
    fig.save(str(tmp_path / f"{method}.png"))


# -- FFI boundary hardening --------------------------------------------------

def test_degenerate_figure_size_raises_valueerror(tmp_path):
    """A zero-size figure used to unwind out of Rust as ``PanicException``.

    That derives from ``BaseException``, so ``except Exception`` did not catch
    it and the user got a Rust panic dump instead of a diagnosis.
    """
    fig, ax = plt.subplots(figsize=(0, 0))
    ax.line([0, 1], [0, 1])
    with pytest.raises(ValueError, match="must be positive"):
        fig.save(str(tmp_path / "zero.pdf"))


def test_absurd_raster_size_raises_instead_of_aborting(tmp_path):
    """A units or dpi slip can ask for a terabyte-scale raster.

    Rust's allocator *aborts the process* on OOM rather than returning, so the
    size has to be rejected before allocation - ``Pixmap::new`` returning
    ``None`` is not a defense that can be relied on.
    """
    fig, ax = plt.subplots(figsize=(4000, 3000), units="in")
    ax.line([0, 1], [0, 1])
    with pytest.raises(ValueError, match="reduce the figure size"):
        fig.save(str(tmp_path / "huge.png"), dpi=2400)


def test_empty_animation_raises():
    """Caught in Python before it reaches Rust; the Rust-side empty-frames check
    is defense in depth for any other caller of the encoder."""
    with pytest.raises(ValueError, match="positive int"):
        plt.animate(lambda i: plt.subplots()[0], 0)


def _marker_xy(fig, tmp_path, name):
    """Device coordinates of each scatter marker, read back out of the SVG."""
    out = tmp_path / f"{name}.svg"
    fig.save(str(out))
    return [(float(x), float(y)) for x, y in
            re.findall(r'<use[^>]*x="([-\d.]+)"\s+y="([-\d.]+)"', out.read_text())]


def test_equal_aspect_does_not_mirror_an_inverted_axis(tmp_path):
    """`aspect="equal"` computed its scale from *signed* spans, so a descending
    limit - which is how an inverted axis is spelled - made the unit negative
    and `new_pw` a negative width, mirroring the *other* axis. Nothing combined
    the two until `spy`, which needs both (row 0 on top, square cells).

    Checked through the real draw path: the aspect adjustment lives in `_draw`,
    not in `_proj_for`, so it only shows up in rendered geometry.
    """
    fig, ax = plt.subplots(figsize=(240, 240))
    ax.scatter([0, 3], [1, 1], marker="s")
    ax.set(xlim=(-0.5, 3.5), ylim=(3.5, -0.5), aspect="equal")
    left, right = _marker_xy(fig, tmp_path, "aspect")[:2]
    assert left[0] < right[0], (
        f"ascending x was mirrored under equal aspect: {left[0]} !< {right[0]}"
    )


def test_equal_aspect_still_squares_the_cells(tmp_path):
    """The fix must not cost the property aspect="equal" exists for: one data
    unit spans the same device length on both axes."""
    fig, ax = plt.subplots(figsize=(300, 300))
    ax.scatter([0, 2, 0], [0, 0, 2], marker="s")
    ax.set(xlim=(-0.5, 2.5), ylim=(2.5, -0.5), aspect="equal")
    pts = _marker_xy(fig, tmp_path, "square")
    origin, dx2, dy2 = pts[0], pts[1], pts[2]
    assert abs((dx2[0] - origin[0]) - abs(dy2[1] - origin[1])) < 1.0


def test_spy_orientation_is_matrix_order(tmp_path):
    """Row 0 at the top, column 0 at the left."""
    fig, ax = plt.subplots(figsize=(240, 240))
    ax.spy([[1, 0], [0, 1]])
    (x0, x1), (y0, y1) = ax._ranges()
    assert x0 < x1, "columns must run left to right"
    assert y0 > y1, "rows must run top to bottom"
    fig.save(str(tmp_path / "spy.png"))


# -- the band fast path -------------------------------------------------------

def test_fill_between_matches_its_bounds(tmp_path):
    """`fill_between` moved from a Python per-point polygon build to the Rust
    affine path (`add_band_xform`), the same one `line`/`scatter` already used.
    A 50k band went 24.7 ms -> 6.6 ms; this pins that it still draws the right
    polygon."""
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([0, 1, 2], [1, 3, 2], 0.0)
    (x0, x1), (y0, y1) = ax._ranges()
    assert x0 <= 0.0 and x1 >= 2.0
    assert y0 <= 0.0 and y1 >= 3.0
    fig.save(str(tmp_path / "band.png"))


def test_fill_betweenx_is_the_transpose(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_betweenx([0, 1, 2], [1, 3, 2], 0.0)
    (x0, x1), (y0, y1) = ax._ranges()
    assert y0 <= 0.0 and y1 >= 2.0
    assert x0 <= 0.0 and x1 >= 3.0
    fig.save(str(tmp_path / "bandx.png"))


def test_fill_between_on_a_log_axis(tmp_path):
    """The scale transform runs inside the Rust band builder, so a non-linear
    axis must stay on the fast path rather than silently mis-mapping."""
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([1, 10, 100], [1, 10, 100], 1.0)
    ax.set(xscale="log", yscale="log")
    fig.save(str(tmp_path / "logband.png"))


def test_fill_between_survives_non_finite_points(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([0, 1, 2, 3], [1, float("nan"), 2, 1], 0.0)
    fig.save(str(tmp_path / "nanband.png"))


def test_degenerate_band_draws_nothing(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.fill_between([0.0], [1.0], 0.0)
    fig.save(str(tmp_path / "tiny.png"))


def test_hexbin_output_is_reproducible(tmp_path):
    """`hexbin` binned into two `HashMap`s and emitted them in iteration order,
    which Rust randomizes per process. The same data therefore drew its
    hexagons in a different order on every run, and since neighbors share an
    edge, the pixels on that edge changed too - so a figure was not
    reproducible and could not be golden-tested.

    Checked across *processes*, since the randomization is per-process: a
    single-process loop would have passed the whole time.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent("""
        import hashlib, random, sys
        import pyplotrs as plt
        random.seed(7)
        xs = [random.uniform(0, 10) for _ in range(2000)]
        ys = [random.uniform(0, 10) for _ in range(2000)]
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.hexbin(xs, ys, gridsize=14)
        out = sys.argv[1]
        fig.save(out)
        print(hashlib.sha256(open(out, "rb").read()).hexdigest())
    """)
    digests = set()
    for i in range(3):
        r = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / f"h{i}.png")],
            capture_output=True, text=True, check=True,
        )
        digests.add(r.stdout.strip())
    assert len(digests) == 1, f"hexbin differed across processes: {digests}"


def test_data_extent_defaults_are_pinned():
    """`bar(width=)`, `barh(height=)` and `boxplot(widths=)` are *data extents*
    in axis units, not stroke widths.

    Phase 6 renamed 36 internal `"width"` keys to `"linewidth"` to break exactly
    that collision, and in the sweep these three signature defaults drifted down
    with the stroke ones - 0.8/0.8/0.5 became 0.6/0.6/0.35. Nothing caught it:
    the values are legal, every plot still rendered, and the golden reference
    was regenerated over the top. Hence this test: whatever the chosen value is,
    it is chosen, and a rename cannot move it.

    The values themselves split two ways, and the split is the point - a
    divergence from matplotlib should be a decision on the record, not a drift
    nobody noticed.
    """
    import inspect

    from pyplotrs.axes import Axes

    # Deliberate pyplotrs defaults, differing from matplotlib's.
    chosen = {
        # matplotlib uses 0.8. pyplotrs leaves more air between bars: at the
        # default 250 pt (single-column) canvas, 0.8 runs the bars together
        # into a solid block, and the gap is what makes them read as discrete.
        ("bar", "width"): 0.5,
    }
    # Matching matplotlib, so a ported script looks the same.
    like_matplotlib = {
        ("barh", "height"): 0.8,
        ("boxplot", "widths"): 0.5,
        ("violinplot", "widths"): 0.5,
    }
    for (method, arg), want in {**chosen, **like_matplotlib}.items():
        got = inspect.signature(getattr(Axes, method)).parameters[arg].default
        assert got == want, f"Axes.{method}({arg}=) is {got}, expected {want}"


def test_bar_leaves_a_gap_between_category_slots():
    """The default above, checked where it is visible rather than in a
    signature: three categories one unit apart, so a bar spans half the gap
    between neighbors and half the slot stays empty."""
    fig, ax = plt.subplots(figsize=(300, 200))
    ax.bar(["a", "b", "c"], [1.0, 2.0, 3.0])
    mark = ax._marks[0]
    assert mark["width"] == 0.5
    assert list(mark["xs"]) == [0.0, 1.0, 2.0]


# -- secondary axes ----------------------------------------------------------

_SEC_FN = (lambda v: v * 100.0, lambda v: v / 100.0)

#: `(method, location)` for every place a secondary axis can be attached.
_SEC_SIDES = [("secondary_xaxis", "top"), ("secondary_xaxis", "bottom"),
              ("secondary_yaxis", "left"), ("secondary_yaxis", "right")]


def _page_texts(fig, tmp_path, name):
    """Every `<text>` in the rendered SVG as `(x, y, string)`.

    Coordinates are page coordinates *except* inside a `<g transform=...>`
    group, where they are group-local - which is how rotated axis labels are
    drawn - so callers checking bounds must skip the grouped ones.
    """
    out = tmp_path / f"{name}.svg"
    fig.save(str(out))
    svg = out.read_text()
    body = re.sub(r"<g transform[^>]*>.*?</g>", "", svg, flags=re.S)
    found = re.findall(
        r'<text[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*>([^<]*)</text>', body)
    return [(float(x), float(y), s) for x, y, s in found], svg


@pytest.mark.parametrize("method,loc", _SEC_SIDES)
def test_secondary_axis_ticks_stay_on_the_canvas(method, loc, tmp_path):
    """A secondary axis drew at the plot's own edge with no space reserved for
    it, so its ticks ran off whatever was beyond that edge.

    On `right` the plot edge *was* the canvas edge, so the tick labels were
    emitted at x == the figure width and simply never appeared - the notebook
    verify pass read that as "draws a bare spine, no ticks at all". On `top`
    they landed under the title instead. `_bands` now reserves a band on the
    side the axis sits on, the same way a twinx and a colorbar already do.
    """
    from pyplotrs import _pyplotrs_core as _core
    from pyplotrs._draw import _tw

    w, h = 400.0, 300.0
    fig, ax = plt.subplots(figsize=(w, h))
    ax.line([0, 1, 2, 3], [0, 1, 4, 9])
    getattr(ax, method)(loc, functions=_SEC_FN)

    texts, _ = _page_texts(fig, tmp_path, f"sec_{loc}")
    # The secondary reads 100x the primary, so its labels are the round
    # hundreds - values no primary tick on this data produces.
    secondary = [t for t in texts if t[2] in ("100", "200", "300", "400",
                                              "600", "800", "900")]
    assert secondary, f"no secondary tick labels drawn on {loc!r}"

    # The whole glyph run has to fit, not just its origin: the `right` bug put
    # the origin at exactly x == the figure width, so an origin-only bounds
    # check passed while nothing was visible.
    size = ax._theme.tick_label_size
    scene = _core.Scene(w, h)
    for x, y, s in secondary:
        assert x >= 0.0 and x + _tw(scene, s, size) <= w, (
            f"tick {s!r} spans x={x}..{x + _tw(scene, s, size)} "
            f"on a {w}pt-wide canvas"
        )
        assert 0.0 <= y <= h, f"tick {s!r} at y={y} is off a {h}pt-tall canvas"


@pytest.mark.parametrize("method,loc", _SEC_SIDES)
def test_secondary_axis_label_is_drawn(method, loc, tmp_path):
    """`label=` was accepted, stored in the spec dict, and then never read by
    `_draw_secondary` - so it rendered nothing at all, on any of the four
    locations. The same class as `Axes3D.plot(alpha=)`: a kwarg taken and
    dropped, which a signature check cannot see."""
    fig, ax = plt.subplots(figsize=(400, 300))
    ax.line([0, 1, 2, 3], [0, 1, 4, 9])
    getattr(ax, method)(loc, functions=_SEC_FN, label="SENTINEL")

    _, svg = _page_texts(fig, tmp_path, f"seclbl_{loc}")
    drawn = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
    assert "SENTINEL" in drawn, f"label= never rendered on {loc!r}"


@pytest.mark.parametrize("method,loc", _SEC_SIDES)
def test_secondary_axis_reserves_a_band(method, loc, tmp_path):
    """The band is real: adding a secondary axis has to grow the reserved band
    on the side it sits on, which is what costs it plot area. Without this,
    "the ticks are on the canvas" could be satisfied by an axis that draws over
    its neighbors and still renders.

    `loc` maps to the band it shares: top -> title, bottom -> x ticks,
    left -> y ticks, right -> the colorbar/twin column.
    """
    from pyplotrs import _pyplotrs_core as _core

    band_index = {"top": 0, "bottom": 3, "left": 4, "right": 5}[loc]

    def band(with_secondary):
        fig, ax = plt.subplots(figsize=(400, 300))
        ax.line([0, 1, 2, 3], [0, 1, 4, 9])
        if with_secondary:
            getattr(ax, method)(loc, functions=_SEC_FN, label="lbl")
        bands, _, _ = ax._bands(_core.Scene(400, 300), (0.0, 3.0), (0.0, 9.0))
        return bands[band_index]

    bare, with_sec = band(False), band(True)
    assert with_sec > bare, (
        f"{loc!r} secondary reserved nothing: band {band_index} is "
        f"{with_sec} with it and {bare} without"
    )


def test_secondary_axis_rejects_a_location_for_the_wrong_axis():
    """`secondary_xaxis("left")` used to be accepted and then silently drawn as
    if it said "bottom" - `_draw_secondary` only ever tested for the one
    location and treated everything else as the other."""
    fig, ax = plt.subplots(figsize=(200, 150))
    with pytest.raises(ValueError, match="top.*bottom"):
        ax.secondary_xaxis("left")
    with pytest.raises(ValueError, match="left.*right"):
        ax.secondary_yaxis("top")


def test_two_secondary_axes_on_one_side_stack(tmp_path):
    """Each secondary is placed outside everything already reserved on its
    side, so a second one on the same side sits beyond the first rather than
    drawing over it."""
    fig, ax = plt.subplots(figsize=(400, 300))
    ax.line([0, 1, 2, 3], [0, 1, 4, 9])
    ax.secondary_yaxis("right", functions=_SEC_FN)
    ax.secondary_yaxis("right", functions=(lambda v: v * 3.0, lambda v: v / 3.0))
    fig._build_scene()
    offsets = [s["_offset"] for s in ax._secondary]
    assert offsets[0] < offsets[1], f"second axis did not stack outside: {offsets}"


def test_secondary_y_does_not_displace_a_colorbar_label(tmp_path):
    """A secondary y on the right takes its space out of the same band the
    colorbar uses. Inflating that band pushed the colorbar's own label out to
    the band's *new* outer edge - beyond the secondary axis and on top of the
    secondary's own label - so the colorbar now measures against its own share
    of the band instead of the whole of it.
    """
    fig, ax = plt.subplots(figsize=(320, 240))
    m = ax.scatter([0, 1, 2, 3], [0, 1, 4, 9], c=[1, 2, 3, 4], cmap="viridis")
    fig.colorbar(m, label="c")
    ax.secondary_yaxis("right", functions=_SEC_FN, label="percent")
    out = tmp_path / "cbar_secondary.svg"
    fig.save(str(out))
    svg = out.read_text()

    # The rotated colorbar label: the group whose text is exactly "c". Its
    # x translation is the 5th matrix component.
    grp = re.search(r'<g transform="matrix\((?:[-\d.]+[,\s]+){4}([-\d.]+)[,\s]'
                    r'+[-\d.]+\)">\s*<text[^>]*>c</text>', svg)
    assert grp, "colorbar label 'c' not found in the SVG"
    cbar_label_x = float(grp.group(1))

    # The secondary's tick labels are the round hundreds, drawn ungrouped.
    body = re.sub(r"<g transform[^>]*>.*?</g>", "", svg, flags=re.S)
    ticks = [float(x) for x, _, s in
             re.findall(r'<text[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*>([^<]*)</text>',
                        body)
             if s in ("200", "400", "600", "800")]
    assert ticks, "secondary tick labels not drawn"

    assert cbar_label_x < min(ticks), (
        f"colorbar label at x={cbar_label_x} was pushed past the secondary "
        f"axis (tick labels start at x={min(ticks)})"
    )


# -- contour lines -----------------------------------------------------------

def test_contour_emits_one_path_per_line_not_one_per_cell():
    """Marching squares was handed to the renderer as loose two-point segments.

    Each cell's piece became its own stroked path, so neighboring pieces met
    butt cap to butt cap and left a wedge of background showing at every turn -
    a contour that looked finely dashed under any zoom. The kernel now stitches
    the pieces into whole lines, which is what lets a single path with round
    joins close those wedges.
    """
    import math

    # A cone, so each level is one ring; the levels stay clear of the border, so
    # every ring closes rather than running off the edge of the grid.
    n, mid = 21, 10.0
    Z = [[-math.hypot(c - mid, r - mid) for c in range(n)] for r in range(n)]
    rings = [-2.0, -4.0, -6.0, -8.0]

    fig, ax = plt.subplots()
    ax.contour(Z, levels=rings)
    lines = ax._marks[0]["lines"]

    assert len(lines) == len(rings), (
        f"{len(rings)} concentric rings came back as {len(lines)} paths; "
        f"one closed ring per level is the whole point of stitching"
    )
    for li, closed, pts in lines:
        assert closed, f"level {rings[li]} is a ring around the peak but came back open"
        assert len(pts) > 4, f"level {rings[li]} is only {len(pts)} points - not stitched"


def test_stitched_contour_never_joins_points_from_different_cells():
    """The stitch has to follow the grid, not just pair up nearby points.

    Consecutive points on a contour line are the crossings on two edges of one
    cell, so they can never be more than a cell apart in either axis. A stitch
    that matched on coordinates (rather than on edge identity) would jump
    between unrelated parts of the same level and draw a chord across the field.
    """
    import math

    n = 24
    Z = [[math.sin(c / 3.0) * math.cos(r / 3.0) for c in range(n)] for r in range(n)]
    fig, ax = plt.subplots()
    ax.contour(Z, levels=6)

    for li, closed, pts in ax._marks[0]["lines"]:
        ring = pts + [pts[0]] if closed else pts
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            assert max(abs(x1 - x0), abs(y1 - y0)) <= 1.0 + 1e-9, (
                f"level {li} jumps from ({x0}, {y0}) to ({x1}, {y1}) - further "
                f"than one grid cell, so these two points are not one segment"
            )
