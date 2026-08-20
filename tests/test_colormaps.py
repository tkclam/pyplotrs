"""The expanded colormap/palette registry and color-science layer.

Coverage sourced from matplotlib/colorcet/cmocean (continuous) and
matplotlib/ColorBrewer/seaborn (categorical) via ``tools/extract_colormaps.py``
- see ``crates/pyplotrs-color`` for the Rust side these all delegate to.
"""

from __future__ import annotations

import pytest
from pyplotrs import color, colormaps, palettes
from pyplotrs.colormaps import Colormap

# -- registry coverage --------------------------------------------------------

def test_available_is_much_larger_than_the_original_seven():
    assert len(colormaps.available()) > 100


@pytest.mark.parametrize("name", [
    "viridis", "plasma", "inferno", "magma", "cividis",  # perceptually uniform
    "RdBu", "coolwarm", "turbo", "twilight",              # mpl families
    "grays", "gray",                                      # pre-existing back-compat names
    "cet_fire", "cet_coolwarm", "cet_bgy",                # colorcet
    "cmo_thermal", "cmo_balance", "cmo_phase",             # cmocean
])
def test_get_cmap_resolves_every_source(name):
    cm = colormaps.get_cmap(name)
    assert isinstance(cm, Colormap)
    assert len(cm._table) == 256


def test_unknown_name_raises_with_a_helpful_message():
    with pytest.raises(ValueError, match="unknown colormap"):
        colormaps.get_cmap("not_a_real_colormap")


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="unknown category"):
        colormaps.available(category="not_a_category")


def test_category_filter_is_a_nonempty_subset():
    all_names = set(colormaps.available())
    diverging = colormaps.available(category="diverging")
    assert diverging
    assert set(diverging) <= all_names
    assert len(diverging) < len(all_names)


def test_reversed_name_reverses_the_table():
    fwd = colormaps.get_cmap("viridis")
    rev = colormaps.get_cmap("viridis_r")
    assert fwd(0.0)[:3] == rev(1.0)[:3]
    assert fwd(1.0)[:3] == rev(0.0)[:3]


def test_viridis_table_is_bit_exact_at_known_endpoints():
    # Regression guard on the extraction pipeline: these are matplotlib's
    # well-known viridis endpoints, unchanged by the migration to Rust.
    cm = colormaps.get_cmap("viridis")
    assert cm(0.0) == (68, 1, 84, 255)
    assert cm(1.0) == (253, 231, 37, 255)


def test_get_cmap_caches_by_identity():
    a = colormaps.get_cmap("plasma")
    b = colormaps.get_cmap("plasma")
    assert a is b


def test_passing_a_colormap_instance_through_is_a_no_op():
    cm = colormaps.get_cmap("magma")
    assert colormaps.get_cmap(cm) is cm


# -- custom colormaps (Oklab interpolation) -----------------------------------

def test_custom_stops_interpolate_and_hit_endpoints():
    cm = Colormap("warm", [(0.0, (0, 0, 0)), (1.0, (255, 128, 0))])
    assert cm(0.0) == (0, 0, 0, 255)
    assert cm(1.0) == (255, 128, 0, 255)


def test_custom_stops_default_to_oklab_not_naive_srgb_lerp():
    black_white = Colormap("bw", [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))])
    mid = black_white(0.5)[0]
    # A naive sRGB lerp would land at 127/128; Oklab's perceptual midpoint is
    # noticeably darker (see pyplotrs-color's own interp tests).
    assert mid < 115


def test_explicit_srgb_space_matches_the_old_naive_lerp_behavior():
    cm = Colormap("bw", [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))], space="srgb")
    mid = cm(0.5)[0]
    assert 126 <= mid <= 129


def test_colormap_requires_exactly_one_of_stops_or_table():
    with pytest.raises(ValueError):
        Colormap("x")
    with pytest.raises(ValueError):
        Colormap("x", [(0.0, (0, 0, 0)), (1.0, (1, 1, 1))], table=[(0, 0, 0)] * 256)


def test_table_must_be_exactly_256_entries():
    with pytest.raises(ValueError):
        Colormap("x", table=[(0, 0, 0), (255, 255, 255)])


def test_reversed_method_reverses_a_custom_colormap():
    cm = Colormap("warm", [(0.0, (0, 0, 0)), (1.0, (255, 128, 0))])
    rev = cm.reversed()
    assert rev(0.0) == cm(1.0)
    assert rev(1.0) == cm(0.0)


# -- palettes ------------------------------------------------------------------

def test_palettes_available_covers_all_sources():
    names = palettes.available()
    assert "tab10" in names
    assert "okabe_ito" in names
    assert any(n.startswith("cet_glasbey") for n in names)
    assert any(n.startswith("sns_") for n in names)


def test_tab10_matches_matplotlib_exactly():
    tab10 = palettes.get("tab10")
    assert len(tab10) == 10
    assert tab10[0] == (31, 119, 180, 255)  # matplotlib's tab:blue


def test_unknown_palette_raises():
    with pytest.raises(ValueError, match="unknown palette"):
        palettes.get("not_a_real_palette")


def test_palette_usable_as_a_theme_cycle():
    from pyplotrs import themes

    mine = themes.default.with_(palette=palettes.get("tab10"))
    assert mine.palette[0] == palettes.get("tab10")[0]


# -- color science ---------------------------------------------------------

def test_oklab_round_trips_through_srgb():
    for rgb in [(0, 0, 0), (255, 255, 255), (255, 0, 0), (12, 200, 90)]:
        back = color.from_oklab(color.to_oklab(rgb))
        assert all(abs(a - b) <= 1 for a, b in zip(rgb, back))


def test_white_is_achromatic_in_oklab():
    l, a, b = color.to_oklab((255, 255, 255))
    assert l == pytest.approx(1.0, abs=1e-3)
    assert a == pytest.approx(0.0, abs=1e-3)
    assert b == pytest.approx(0.0, abs=1e-3)


def test_cam16ucs_distance_is_symmetric_and_zero_for_equal_colors():
    assert color.distance((10, 20, 30), (10, 20, 30)) == 0.0
    assert color.distance((10, 20, 30), (200, 50, 90)) == pytest.approx(
        color.distance((200, 50, 90), (10, 20, 30))
    )


def test_simulate_cvd_leaves_grayscale_unaffected():
    for kind in ("protanopia", "deuteranopia", "tritanopia"):
        sim = color.simulate_cvd((128, 128, 128), kind)
        assert all(abs(c - 128) <= 2 for c in sim)


def test_cvd_safe_report_has_all_three_kinds_in_range():
    report = color.cvd_safe_report("coolwarm")
    assert set(report) == {"protanopia", "deuteranopia", "tritanopia"}
    assert all(0.0 <= v <= 1.0 for v in report.values())


def test_cvd_safe_report_accepts_a_colormap_instance_too():
    cm = colormaps.get_cmap("viridis")
    assert color.cvd_safe_report(cm) == color.cvd_safe_report("viridis")


def test_red_green_diverging_map_is_cvd_unsafe():
    # The textbook colorblind-unsafe map: pure red<->green.
    unsafe = Colormap("rg", [(0.0, (220, 20, 20)), (1.0, (20, 180, 20))])
    report = color.cvd_safe_report(unsafe)
    assert report["deuteranopia"] < 0.5
    assert report["protanopia"] < 0.5


def test_perceptual_uniformity_is_nonnegative():
    assert color.perceptual_uniformity("viridis") >= 0.0
    assert color.perceptual_uniformity(colormaps.get_cmap("cet_fire")) >= 0.0


# -- the public color-space conversions --------------------------------------
#
# `pyplotrs.color` exposes twelve conversions and none of them was executed by
# the suite. They are a documented public module, they are the evidence behind
# the "defaults you can *check*" claim, and a round-trip is the cheapest
# possible test of each: any sign error, channel swap or white-point mixup
# breaks it.

_PROBE_COLORS = [
    (0, 0, 0), (255, 255, 255), (128, 128, 128),
    (255, 0, 0), (0, 255, 0), (0, 0, 255),
    (18, 52, 86), (203, 65, 84), (0, 114, 178),  # incl. the palette's C0
]

_ROUND_TRIPS = [
    ("oklab", color.to_oklab, color.from_oklab),
    ("oklch", color.to_oklch, color.from_oklch),
    ("lab", color.to_lab, color.from_lab),
    ("xyz", color.to_xyz, color.from_xyz),
    ("linear", color.to_linear, color.from_linear),
    ("cam16ucs", color.to_cam16ucs, color.from_cam16ucs),
]


@pytest.mark.parametrize("space,forward,back", _ROUND_TRIPS, ids=[s for s, _, _ in _ROUND_TRIPS])
@pytest.mark.parametrize("rgb", _PROBE_COLORS, ids=[str(c) for c in _PROBE_COLORS])
def test_color_space_round_trips(space, forward, back, rgb):
    """sRGB -> space -> sRGB must return the same 8-bit color.

    One unit of tolerance per channel: every space here is continuous and the
    endpoints are bytes, so a value can land on either side of a rounding
    boundary. Two units would hide a real bug.
    """
    out = back(forward(rgb))
    assert len(out) == 3
    for got, want, channel in zip(out, rgb, "rgb"):
        assert abs(got - want) <= 1, (
            f"{space} round trip moved {channel} from {want} to {got} for {rgb}"
        )


def test_lightness_is_ordered_the_way_a_reader_sees_it():
    """A conversion can round-trip perfectly and still have the axes swapped."""
    black = color.to_oklab((0, 0, 0))[0]
    gray = color.to_oklab((128, 128, 128))[0]
    white = color.to_oklab((255, 255, 255))[0]
    assert black < gray < white, (black, gray, white)
    assert abs(black) < 1e-6 and abs(white - 1.0) < 1e-3


def test_a_gray_has_no_chroma():
    for value in (0, 64, 128, 200, 255):
        _lightness, chroma, _hue = color.to_oklch((value, value, value))
        assert chroma < 1e-3, f"gray {value} reports chroma {chroma}"


def test_perceptual_distance_is_a_metric():
    red, blue, near_red = (255, 0, 0), (0, 0, 255), (250, 5, 5)
    assert color.distance(red, red) < 1e-6, "distance to itself must be zero"
    assert color.distance(red, blue) == pytest.approx(
        color.distance(blue, red)), "distance must be symmetric"
    assert color.distance(red, near_red) < color.distance(red, blue)


@pytest.mark.parametrize("kind", ["protanopia", "deuteranopia", "tritanopia"])
def test_cvd_simulation_moves_the_confusable_axis(kind):
    """Simulating a deficiency has to change the colors it should confuse and
    leave grays alone - otherwise `cvd_safe_report` is scoring noise."""
    gray = (128, 128, 128)
    assert max(abs(a - b) for a, b in
               zip(color.simulate_cvd(gray, kind), gray)) <= 2

    red, green = (220, 30, 30), (30, 180, 30)
    before = color.distance(red, green)
    after = color.distance(color.simulate_cvd(red, kind),
                               color.simulate_cvd(green, kind))
    if kind in ("protanopia", "deuteranopia"):
        assert after < before, (
            f"{kind} should make red and green harder to tell apart; "
            f"{before:.1f} -> {after:.1f}"
        )


def test_cvd_safe_report_ranks_colormaps_the_way_the_literature_does():
    """The report exists so the defaults can be *checked* rather than asserted,
    which only means something if it separates known-good from known-bad.

    Asserted as an ordering, not against a fixed threshold: the score is a
    worst-case ratio over every pair in the table, so its absolute level is a
    property of the metric rather than of accessibility practice. (Worth
    knowing: viridis scores 0.39 under protanopia, below the ~0.5 the
    docstring calls a concern - the ordering below is the part that is solid.)
    """
    worst = {name: min(color.cvd_safe_report(name).values())
             for name in ("cividis", "coolwarm", "viridis", "jet",
                          "gist_rainbow", "RdYlGn")}

    # A red-green diverging map is the textbook failure, and deuteranopia is
    # the deficiency it fails for.
    assert color.cvd_safe_report("RdYlGn")["deuteranopia"] < 0.05

    assert worst["cividis"] > worst["viridis"], (
        "cividis was designed for CVD viewers and must not score below viridis"
    )
    for good in ("cividis", "coolwarm"):
        for bad in ("jet", "gist_rainbow", "RdYlGn"):
            assert worst[good] > worst[bad], (good, worst[good], bad, worst[bad])

    for name, value in worst.items():
        assert 0.0 <= value <= 1.0, (name, value)


def test_cvd_safe_report_covers_all_three_deficiencies():
    report = color.cvd_safe_report("viridis")
    assert set(report) == {"protanopia", "deuteranopia", "tritanopia"}


def test_perceptual_uniformity_scores_viridis_better_than_a_rainbow():
    """The score is *roughness* - the coefficient of variation of the step
    size - so lower is better, and a perceptually-uniform map should beat a
    rainbow by a wide margin. The scoring exists so the defaults can be
    checked rather than asserted."""
    viridis = color.perceptual_uniformity(colormaps.get_cmap("viridis"))
    rainbow = color.perceptual_uniformity(colormaps.get_cmap("gist_rainbow"))
    assert viridis < rainbow, (viridis, rainbow)
    assert viridis < 0.35, f"viridis should be smooth; roughness {viridis}"
