"""Regression tests for specific defects.

Each test here corresponds to a bug that shipped and went unnoticed because
nothing exercised the path. Keep the reproduction minimal and name the symptom,
so a future failure reads as "this exact thing broke again".
"""

from __future__ import annotations

import re

import pyplotrs as plt
import pytest
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


def test_hexbin_hexagons_tile_without_seams(tmp_path):
    """Hexagons that tile the plane were still drawn with white between them.

    Every fill is composited on its own, so along an edge two neighbors share,
    each covers only part of the boundary pixels and the background bleeds
    through the difference. It read worst on the vertical edges: those are
    exactly axis-aligned, so every pixel down the seam splits the same way and
    the leak lines up into a crisp white streak rather than dithering away.

    The stretched case also covers the lattice geometry - hexagons sized off
    the wrong cell leave real gaps, not just seams (see
    :func:`test_hexbin_cell_matches_the_binning_lattice`).

    Rendered at 100 dpi because a seam is a *pixel*-scale artifact: it thins as
    resolution rises, so a high-dpi check would pass either way.
    """
    import random

    from conftest import read_png

    for name, yscale in (("square", 1.0), ("stretched", 6.0)):
        rng = random.Random(3)
        n = 20000  # dense enough that the middle of the patch has no empty cells
        xs = [rng.uniform(0.0, 1.0) for _ in range(n)]
        ys = [yscale * rng.uniform(0.0, 1.0) for _ in range(n)]

        # One flat color for every hexagon: with the count range swamped, any
        # pixel inside the patch that is *not* that color is a gap or a seam.
        fig, ax = plt.subplots(figsize=(240, 180))
        ax.hexbin(xs, ys, gridsize=18, vmin=-1e6, vmax=1e6)
        out = tmp_path / f"hex_{name}.png"
        fig.save(str(out), dpi=100)

        w, h, buf = read_png(out)
        # A window at the canvas center, small enough to stay inside the patch.
        x0, x1 = int(w * 0.45), int(w * 0.55)
        y0, y1 = int(h * 0.45), int(h * 0.55)
        px = [tuple(buf[(y * w + x) * 4:(y * w + x) * 4 + 3])
              for y in range(y0, y1) for x in range(x0, x1)]
        face = max(set(px), key=px.count)
        assert face != (255, 255, 255), f"{name}: sampled the background, not the patch"

        worst = max(max(abs(c - f) for c, f in zip(p, face)) for p in px)
        assert worst <= 8, (
            f"{name}: hexbin interior is not solid - a pixel differs from the "
            f"face color {face} by {worst} levels, i.e. background showing "
            f"through a gap or a shared edge"
        )


def test_hexbin_draws_the_cells_nothing_landed_in(tmp_path):
    """An empty cell is a count of zero, not a hole in the patch.

    Only the occupied hexagons were emitted, so wherever the cloud thinned out
    the figure background showed through the lattice and the patch frayed into
    speckle. matplotlib bins into the whole grid and draws all of it: a cell
    nothing landed in is a zero, and takes the bottom of the colormap - viridis'
    deepest shade - so the patch reads as one continuous field.

    Dropping them also moved the color scale, which then started at the
    smallest *occupied* count: a cell holding a single point got the very bottom
    of the colormap, the color an empty cell has to have, and the scale said
    nothing about how far the data was above nothing.

    Checked through the rendered pixels rather than the mark, because the
    symptom was the background showing through: the four clumps leave the middle
    of the lattice empty, so the center of the canvas lands on cells with no
    points in them at all.
    """
    import random

    from conftest import read_png
    from pyplotrs import colormaps

    rng = random.Random(11)
    xs, ys = [], []
    # Tight clumps, with hard edges: a gaussian tail would drop the odd point in
    # the middle, and a count of one is not the color under test.
    for cx, cy in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
        for _ in range(500):
            xs.append(cx + rng.uniform(-0.05, 0.05))
            ys.append(cy + rng.uniform(-0.05, 0.05))

    gridsize = 12
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.hexbin(xs, ys, gridsize=gridsize)

    # Both interleaved lattices in full: (nx+1)x(ny+1) grid points, plus the
    # nx x ny half-offset centers between them.
    ny = int(gridsize / 3 ** 0.5)
    assert len(ax._marks[-1]["centers"]) == (gridsize + 1) * (ny + 1) + gridsize * ny

    out = tmp_path / "hexbin_empty.png"
    fig.save(str(out), dpi=100)
    w, h, buf = read_png(out)

    empty = colormaps.get_cmap("viridis")(0.0)[:3]
    px = [tuple(buf[(y * w + x) * 4:(y * w + x) * 4 + 3])
          for y in range(int(h * 0.45), int(h * 0.55))
          for x in range(int(w * 0.45), int(w * 0.55))]
    assert max(px, key=px.count) == empty, (
        "the middle of the hexbin patch, where no point fell, should be the "
        f"colormap's zero {empty}; it is mostly {max(px, key=px.count)}"
    )
    # Nothing anywhere near the background: a few levels of drift along a shared
    # edge is the seam this lattice already tolerates (see
    # :func:`test_hexbin_hexagons_tile_without_seams`), 187 levels is white.
    worst = max(max(abs(c - e) for c, e in zip(p, empty)) for p in px)
    assert worst <= 8, (
        f"a pixel in the empty middle of the patch is {worst} levels off the "
        f"colormap's zero - the background showing through an undrawn cell"
    )


def test_hexbin_cell_matches_the_binning_lattice():
    """The drawn hexagon has to be the cell the binner actually binned into.

    The binner spaces its rows on a y cell derived from the *y* range and its
    own row count, but the polygon was built from the x cell alone with a fudged
    aspect factor. The two agreed only when the data range was roughly square -
    which every example happened to be. Stretch y and the hexagons shrank to
    slivers with background between them; squash it and they grew into
    overlapping spikes.

    Checked against the emitted centers rather than a recomputed cell size, so
    the polygon is pinned to the lattice itself: the two interleaved grids put
    their centers half a cell apart, and the cell is their Voronoi region - half
    the cell wide, and a third of it from center to point.
    """
    import random

    def half_cell(values):
        """Smallest real spacing between the distinct coordinates of a lattice."""
        vals = sorted(set(values))
        span = vals[-1] - vals[0]
        return min(b - a for a, b in zip(vals, vals[1:]) if b - a > span * 1e-6)

    for yscale in (1.0, 6.0, 0.15):
        rng = random.Random(5)
        xs = [rng.uniform(0.0, 1.0) for _ in range(4000)]
        ys = [yscale * rng.uniform(0.0, 1.0) for _ in range(4000)]

        fig, ax = plt.subplots(figsize=(240, 180))
        ax.hexbin(xs, ys, gridsize=16)
        mark = ax._marks[-1]

        half_x = half_cell(cx for cx, _ in mark["centers"])
        half_y = half_cell(cy for _, cy in mark["centers"])
        wide = max(ox for ox, _ in mark["offsets"])
        tall = max(oy for _, oy in mark["offsets"])

        assert wide == pytest.approx(half_x, rel=1e-9), (
            f"yscale={yscale}: hexagon is {wide} wide from center to side, "
            f"but neighboring columns sit {half_x} apart"
        )
        assert tall == pytest.approx(2 * half_y / 3, rel=1e-9), (
            f"yscale={yscale}: hexagon reaches {tall} from center to point, "
            f"but the row cell it was binned on is {2 * half_y}"
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


def test_contour_levels_land_on_round_numbers():
    """``levels=N`` used to slice the data range into N+1 equal parts, which put
    the lines on values like 0.1426 and 0.2853 - and gave a different set (and
    count) of lines than matplotlib for the same call. A contour level is read
    as a *value*, so it belongs on a round number, chosen the way the axis
    locator chooses ticks.
    """
    import math

    gx = [-3.0 + 6.0 * i / 29 for i in range(30)]
    gy = [-2.0 + 4.0 * j / 19 for j in range(20)]
    Z = [[math.exp(-(x * x + y * y) / 4) * math.sin(1.5 * x) * math.cos(1.2 * y)
          for x in gx] for y in gy]

    fig, ax = plt.subplots()
    ax.contour(gx, gy, Z, levels=10)
    # matplotlib draws exactly these for this field and this `levels` hint.
    assert ax._marks[0]["levels"] == pytest.approx(
        [-0.75, -0.6, -0.45, -0.3, -0.15, 0.0, 0.15, 0.3, 0.45, 0.6, 0.75])


def test_contour_levels_stay_inside_the_data_range():
    """A level at (or past) an extreme draws nothing, or a single degenerate
    point, but still consumed a color and a legend slot."""
    fig, ax = plt.subplots()
    ax.contour([[0.0, 1.0], [1.0, 2.0]], levels=5)
    assert all(0.0 < lv < 2.0 for lv in ax._marks[0]["levels"])


def test_contour_levels_survive_a_field_of_tiny_magnitude():
    """The step is rounded to the decimals it needs to be written exactly, and
    the count of those decimals gave up at zero for any step under 1e-6: every
    level of a field spanning a micro-unit rounded to 0.0, fell outside the data
    range, and was dropped. A whole class of fields drew no contour at all.
    """
    Z = [[1e-6 * (c + r) / 20.0 for c in range(11)] for r in range(11)]
    fig, ax = plt.subplots()
    ax.contour(Z, levels=7)
    lvls = ax._marks[0]["levels"]
    assert len(lvls) > 3, f"a 1e-6-wide field drew {len(lvls)} contour lines"
    assert all(0.0 < lv < 1e-6 for lv in lvls)


# -- filled contours ---------------------------------------------------------

def _contourf_pixels(mark):
    """``(width, height, rgba rows)`` of a ``contourf`` mark's raster."""
    img, w, h = mark["img"], mark["uw"], mark["uh"]
    return w, h, [[tuple(img[(y * w + x) * 4:(y * w + x) * 4 + 4]) for x in range(w)]
                  for y in range(h)]


def test_contourf_fills_the_column_through_the_extreme():
    """Band edges built as ``lo + (hi - lo) * i / n`` land a whole ulp under
    ``hi``, so the pixels interpolating the field's own maximum tested as *above*
    the last edge and were left transparent - a white line straight down the
    middle of the peak.

    Auto levels no longer divide the range that way, but a caller's own can (it
    is the obvious way to write them), so the band kernel admits a hair past
    each end too. Both routes have to fill the peak.
    """
    import math

    gx = [-3.0 + 6.0 * i / 29 for i in range(30)]
    gy = [-2.0 + 4.0 * j / 19 for j in range(20)]
    Z = [[math.exp(-(x * x + y * y) / 4) * math.sin(1.5 * x) * math.cos(1.2 * y)
          for x in gx] for y in gy]
    lo, hi = min(min(r) for r in Z), max(max(r) for r in Z)
    # `lo + (hi - lo)` is not `hi`: the last edge falls an ulp short of the peak.
    by_hand = [lo + (hi - lo) * i / 12 for i in range(13)]
    assert by_hand[-1] < hi, "float arithmetic changed; pick another field"

    for levels in (12, by_hand, [lo, 0.0, hi]):
        fig, ax = plt.subplots()
        ax.contourf(gx, gy, Z, levels=levels)
        w, h, rows = _contourf_pixels(ax._marks[0])
        clear = [(x, y) for y in range(h) for x in range(w) if rows[y][x][3] == 0]
        assert not clear, (
            f"levels={levels}: {len(clear)} transparent pixels inside the data "
            f"range, at columns {sorted({x for x, _ in clear})}"
        )


def test_contourf_bands_end_where_contour_lines_run():
    """Filled bands sliced the data range into equal fractions while the lines
    were placed on round numbers, so a ``contour`` drawn over a ``contourf`` of
    the same field ran through the middle of the bands instead of along their
    boundaries. Both now read off one lattice - matplotlib's, so the numbers on
    the colorbar match a matplotlib figure too.
    """
    import math

    gx = [-3.0 + 6.0 * i / 29 for i in range(30)]
    gy = [-2.0 + 4.0 * j / 19 for j in range(20)]
    Z = [[math.exp(-(x * x + y * y) / 4) * math.sin(1.5 * x) * math.cos(1.2 * y)
          for x in gx] for y in gy]

    fig, ax = plt.subplots()
    mappable = ax.contourf(gx, gy, Z, levels=12)
    ax.contour(gx, gy, Z, levels=12)
    edges = [-0.9, -0.75, -0.6, -0.45, -0.3, -0.15, 0.0,
             0.15, 0.3, 0.45, 0.6, 0.75, 0.9]  # matplotlib's, for this field

    assert mappable.vmin == pytest.approx(edges[0])
    assert mappable.vmax == pytest.approx(edges[-1])
    for lv in ax._marks[1]["levels"]:
        assert any(lv == pytest.approx(e) for e in edges), (
            f"line at {lv} sits inside a band, not on a boundary: {edges}"
        )


def test_contourf_and_contour_default_to_the_same_levels():
    """Two hard-wired defaults (9 bands, 8 lines) meant the plainest overlay of
    all - ``contourf`` then ``contour``, neither given ``levels`` - picked two
    different steps and disagreed everywhere."""
    import math

    Z = [[math.sin(c / 4.0) * math.cos(r / 4.0) for c in range(25)] for r in range(25)]
    fig, ax = plt.subplots()
    mappable = ax.contourf(Z)
    ax.contour(Z)

    # matplotlib fills -1.0 to 1.0 in steps of 0.25 here; the two levels its
    # lattice puts outside this field draw nothing, leaving the seven lines.
    assert mappable.vmin == pytest.approx(-1.0)
    assert mappable.vmax == pytest.approx(1.0)
    assert ax._marks[1]["levels"] == pytest.approx(
        [-0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75])


# -- pie -----------------------------------------------------------------------

def _clipped_group(svg):
    """The body of the axes' clipped data group, and the clip rect's bbox."""
    grp = re.search(r'<g clip-path="url\(#(clip\d+)\)">(.*?)</g>', svg, flags=re.S)
    assert grp, "no clipped data group in the SVG"
    clip = re.search(rf'<clipPath id="{grp.group(1)}"[^>]*>(.*?)</clipPath>',
                     svg, flags=re.S)
    return grp.group(2), _path_bbox(clip.group(1))


def _path_bbox(chunk):
    """``(x0, y0, x1, y1)`` over every point of every path in ``chunk``. Paths
    are emitted as ``M``/``L``/``Z`` only, so the numbers pair up as x, y."""
    xs, ys = [], []
    for d in re.findall(r'<path[^>]*d="([^"]*)"', chunk):
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
        xs.extend(nums[0::2])
        ys.extend(nums[1::2])
    assert xs, "no path geometry found"
    return min(xs), min(ys), max(xs), max(ys)


def test_pie_slice_labels_are_not_clipped(tmp_path):
    """`gamma` rendered as `gamm`.

    Slice labels were drawn inside the axes' clip group, at a rim offset in
    *data* units, while their width is a device length the view limits know
    nothing about. `pie` padded the limits by a fixed 1.55x to cover for that -
    a guess that clipped anything wider than it allowed for, and wasted a third
    of the cell on everything narrower. The labels are now measured and drawn
    outside the clip, and the pie takes the shrink instead.
    """
    w, h = 250.0, 200.0
    fig, ax = plt.subplots(figsize=(w, h))
    ax.pie([35, 25, 22, 18], labels=["alpha", "beta", "gamma", "delta"])

    out = tmp_path / "pie_labels.svg"
    fig.save(str(out))
    svg = out.read_text()
    clipped, _ = _clipped_group(svg)
    assert "<text" not in clipped, (
        "a slice label is inside the plot clip - the clip is what ate the last "
        "glyph of the widest label"
    )

    from pyplotrs import _pyplotrs_core as _core
    from pyplotrs._draw import _tw

    size = ax._theme.tick_label_size
    scene = _core.Scene(w, h)
    texts, _ = _page_texts(fig, tmp_path, "pie_labels")
    labels = [t for t in texts if t[2] in ("alpha", "beta", "gamma", "delta")]
    assert len(labels) == 4, f"expected 4 slice labels, drew {len(labels)}"
    for x, y, s in labels:
        assert x >= 0.0 and x + _tw(scene, s, size) <= w, (
            f"label {s!r} spans x={x}..{x + _tw(scene, s, size)} on a {w}pt canvas")
        assert 0.0 <= y <= h, f"label {s!r} at y={y} is off a {h}pt-tall canvas"


def test_pie_grows_until_a_label_reaches_the_cell_edge(tmp_path):
    """Labeling a pie used to shrink it by a fixed 1.15/1.55 whatever the cell
    and the labels looked like, because the room came out of the view limits -
    which the equal aspect then squares off, spending it on all four sides at
    once. Room now comes out of the *device* radius, only as much as the
    measured labels need, so the fit is tight: something has to be touching an
    edge, or the pie was drawn smaller than it had to be.

    The labels are also held to the axes' whole cell rather than to that
    square, so a wide cell spends its horizontal slack on the labels instead of
    on the pie - which is why one of them reaches past the square here.
    """
    from pyplotrs import _pyplotrs_core as _core
    from pyplotrs._draw import _th, _tw

    w, h = 400.0, 200.0
    names = ["alpha", "beta", "gamma", "delta"]

    def draw(labels, name):
        fig, ax = plt.subplots(figsize=(w, h))
        ax.pie([35, 25, 22, 18], labels=labels)
        out = tmp_path / f"{name}.svg"
        fig.save(str(out))
        svg = out.read_text()
        clipped, square = _clipped_group(svg)
        return ax, svg, _path_bbox(clipped), square

    # With no labels the pie fills the equal-aspect square outright.
    _ax, _svg, bare, square = draw(None, "pie_bare")
    assert (bare[3] - bare[1]) == pytest.approx(square[3] - square[1], abs=2.0), (
        f"an unlabeled pie should fill its square: {bare} in {square}")

    ax, svg, pie, square = draw(names, "pie_labelled")
    size = ax._theme.tick_label_size
    scene = _core.Scene(w, h)
    texts = re.findall(
        r'<text[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*>([^<]*)</text>', svg)
    boxes = []
    for x, y, s in ((float(x), float(y), s) for x, y, s in texts):
        if s not in names:
            continue
        asc, desc = _th(scene, s, size)
        # `y` is the baseline, and the label is centered about the rim point.
        boxes.append((x, y - (asc + desc) / 2.0, x + _tw(scene, s, size),
                      y + (asc + desc) / 2.0))
    assert len(boxes) == 4, f"expected 4 slice labels, drew {len(boxes)}"

    # Tight vertically: the cell is height-bound, so its top and bottom are the
    # square's, and the label that binds has to be sitting on one of them.
    top = min(b[1] for b in boxes)
    bottom = max(b[3] for b in boxes)
    assert min(top - square[1], square[3] - bottom) <= 2.0, (
        f"labels span y={top}..{bottom} inside a cell of y={square[1]}.."
        f"{square[3]} - the pie could have been drawn larger")

    # And using the slack the square does not have: a label reaches past it.
    assert min(b[0] for b in boxes) < square[0], (
        "no label used the cell's horizontal slack, so the pie was fitted to "
        "the equal-aspect square instead of to the cell")


def test_frame_off_reserves_no_tick_band(tmp_path):
    """A pie sat in a cell with a wide blank strip down its left.

    `axis("off")` - which `pie` implies - suppresses every tick and tick label,
    but the layout still reserved the band they would have occupied: a y band
    as wide as the undrawn "-1.00" labels on the left, an x band on the bottom.
    Nothing was drawn there, so the whole plot rect just sat off-center in its
    cell. With no ticks to reserve for, the cell's only chrome is the title, so
    the pie must come out centered on the canvas.
    """
    w, h = 400.0, 300.0
    fig, ax = plt.subplots(figsize=(w, h))
    ax.pie([35, 25, 22, 18])
    ax.set(title="Pie")
    out = tmp_path / "pie_off.svg"
    fig.save(str(out))
    clipped, _square = _clipped_group(out.read_text())
    x0, _y0, x1, _y1 = _path_bbox(clipped)

    assert (x0 + x1) / 2.0 == pytest.approx(w / 2.0, abs=1.0), (
        f"the pie spans x={x0}..{x1} on a {w}pt canvas - it is off-center, so "
        "an empty tick band is still being reserved beside it")


def test_indented_mosaic_string_has_no_phantom_panel():
    """An indented `subplot_mosaic` string grew a blank panel from its margin.

    A mosaic is written inside a function, so its triple-quoted string carries
    the function's indentation - which is exactly the form the docstring shows.
    Each of those leading spaces was read as a cell, and every row shared them,
    so the spaces formed one solid rectangle: a label of their own, spanning
    every row and as many columns as the code was indented. The figure came out
    with a wide empty axes on the left and the real panels squeezed into what
    was left.
    """
    fig, axd = plt.subplot_mosaic(
        """
        AB
        AC
        """
    )

    assert set(axd) == {"A", "B", "C"}, f"phantom labels: {sorted(axd)}"
    assert len(fig.axes) == 3
    # A spans both rows of column 0; B and C are single cells in column 1.
    assert fig._spans == [(0, 0, 2, 1), (0, 1, 1, 1), (1, 1, 1, 1)]


def test_mosaic_space_marks_an_empty_cell():
    """A space reads as an empty cell, like `"."`. Both spellings appear in the
    wild, and the alternative is a panel whose label is a space."""
    fig, axd = plt.subplot_mosaic(["AB", "A "])

    assert set(axd) == {"A", "B"}
    assert fig._spans == [(0, 0, 2, 1), (0, 1, 1, 1)]


def test_pinned_ticks_outside_the_view_are_dropped():
    """`set(yticks=[...])` drew ticks that fall outside the limits anyway.

    A pinned tick has no place on the axis to sit, so it was placed by the same
    linear map as the rest and landed outside the plot rect: a stray label
    floating above the panel, on top of whatever was there. It shows up as soon
    as ticks are pinned to round numbers on data that turns out to be smaller
    than expected - a residual panel, say.
    """
    fig, ax = plt.subplots()
    ax.scatter([0, 1, 2], [0.01, -0.02, 0.015])
    ax.set(yticks=[-0.05, 0.0, 0.05])

    lo, hi = ax.get_ylim()
    assert lo > -0.05 and hi < 0.05, "the view no longer excludes the outer ticks"
    assert ax.get_yticks() == [0.0], f"ticks outside {lo}..{hi}: {ax.get_yticks()}"
    assert ax.get_yticklabels() == ["0"]


# -- spine / tick junctions ----------------------------------------------------

def _chrome_lines(fig, tmp_path, name, width):
    """The straight two-point segments stroked at ``width``, as `(x0, y0, x1, y1)`.

    That is the axes chrome - spines and tick marks - and nothing else: the data
    here is drawn at the theme's line width, which differs from the spine width.
    """
    out = tmp_path / f"{name}.svg"
    fig.save(str(out))
    found = []
    for d, w in re.findall(r'<path[^>]*d="([^"]*)"[^>]*stroke-width="([\d.]+)"',
                           out.read_text()):
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
        if len(nums) == 4 and float(w) == pytest.approx(width):
            found.append(tuple(nums))
    assert found, f"no chrome strokes at width {width} in {name}.svg"
    return found


def _spines(lines, vertical):
    """The full-length chrome segments running one way, ordered across the page.

    Those are the spines: a tick mark is a couple of points long and the axis it
    sits on is the height of the panel, so "longer than half the longest" splits
    them cleanly however the ends are finished.
    """
    def length(ln):
        return abs(ln[3] - ln[1]) if vertical else abs(ln[2] - ln[0])

    along = [ln for ln in lines if (ln[0] == ln[2] if vertical else ln[1] == ln[3])]
    longest = max(length(ln) for ln in along)
    return sorted((ln for ln in along if length(ln) > longest / 2.0),
                  key=lambda ln: ln[0] if vertical else ln[1])


def _junction_figure(theme, ylim=(0, 8)):
    fig, ax = plt.subplots(figsize=(200, 150), theme=theme)
    ax.line([0, 1, 2, 3], [0, 2, 5, 8])
    ax.set(xlim=(0, 3), ylim=ylim)
    return fig, ax


def test_spine_end_reaches_the_outer_edge_of_the_tick_that_sits_on_it(tmp_path):
    """A tick on the axis limit and the end of its spine did not join up.

    Both are strokes with width, drawn as separate paths, so each stopped on the
    other's centerline: the tick's own half-width jutted half a stroke past the
    flat end of the spine, and the outer corner between them was left blank. At
    a 1pt spine that is a 0.5pt step in the one place a reader's eye is drawn to
    - the corner of the frame. Running the spine half a width past that end
    covers exactly what a miter join between the two would have.
    """
    sw = plt.themes.default.spine_width
    fig, _ax = _junction_figure(plt.themes.default)
    lines = _chrome_lines(fig, tmp_path, "join_tick", sw)

    spine = _spines(lines, vertical=True)[0]
    spine_top = min(spine[1], spine[3])
    # The y tick on ymax: the horizontal chrome stroke highest on the page.
    tick = min((ln for ln in lines if ln[1] == ln[3]), key=lambda ln: ln[1])

    assert spine_top == pytest.approx(tick[1] - sw / 2.0), (
        f"the left spine ends at y={spine_top} but the limit tick spans "
        f"y={tick[1] - sw / 2.0}..{tick[1] + sw / 2.0} - they do not close"
    )


def test_spine_corner_is_closed_with_no_tick_to_hide_it(tmp_path):
    """The same notch between two spines, where no limit tick fills it in.

    A framed axes with its ticks inside the view is the bare case: the vertical
    spine stopped on the horizontal one's centerline and vice versa, leaving a
    half-width square missing from the outer corner of the frame. It survived
    this long because the default theme is despined and its one corner usually
    *does* carry limit ticks, which cover the hole by accident.
    """
    framed = plt.themes.default.with_(spines=("left", "right", "top", "bottom"))
    sw = framed.spine_width
    fig, _ax = _junction_figure(framed, ylim=(-0.3, 8.3))
    lines = _chrome_lines(fig, tmp_path, "join_corner", sw)

    left = _spines(lines, vertical=True)[0]
    top = _spines(lines, vertical=False)[0]
    assert min(left[1], left[3]) == pytest.approx(top[1] - sw / 2.0), (
        "the vertical spine stops short of the top spine's outer edge")
    assert min(top[0], top[2]) == pytest.approx(left[0] - sw / 2.0), (
        "the horizontal spine stops short of the left spine's outer edge")


def test_spine_join_butt_keeps_the_spine_on_the_plot_rect(tmp_path):
    """The escape hatch, for anyone who wants the ends bare: `spine_join="butt"`
    puts every spine back on exactly the plot rect it bounds."""
    framed = plt.themes.default.with_(spines=("left", "right", "top", "bottom"),
                                      spine_join="butt")
    fig, _ax = _junction_figure(framed, ylim=(-0.3, 8.3))
    lines = _chrome_lines(fig, tmp_path, "join_butt", framed.spine_width)

    left = _spines(lines, vertical=True)[0]
    top = _spines(lines, vertical=False)[0]
    assert min(left[1], left[3]) == pytest.approx(top[1]), (
        "with butt ends the spines meet on each other's centerline")
    assert min(top[0], top[2]) == pytest.approx(left[0]), (
        "with butt ends the spines meet on each other's centerline")


def test_spine_join_square_extends_an_end_nothing_meets(tmp_path):
    """`"miter"` closes a junction; `"square"` is the blunter projecting cap that
    overhangs every end, junction or not.

    The two only differ on a *free* end - here the top of the left spine, with
    the view running past the last tick - which is the whole reason both exist:
    an unclosed spine end is a statement about where the axis stops, and half a
    stroke of overhang is not always wanted there.
    """
    sw = plt.themes.default.spine_width
    tops = {}
    for join in ("miter", "square"):
        theme = plt.themes.default.with_(spine_join=join)
        fig, _ax = _junction_figure(theme, ylim=(0, 9))  # ticks 0..8, none at 9
        lines = _chrome_lines(fig, tmp_path, f"join_{join}", sw)
        spine = _spines(lines, vertical=True)[0]
        tops[join] = min(spine[1], spine[3])

    assert tops["square"] == pytest.approx(tops["miter"] - sw / 2.0), (
        f"square should overhang the free end by {sw / 2.0}, got "
        f"{tops['miter'] - tops['square']}")


def test_spine_join_rejects_an_unknown_value():
    """A typo has to fail at the theme, not silently draw a different join."""
    with pytest.raises(ValueError, match="spine_join"):
        plt.themes.default.with_(spine_join="mitre")
