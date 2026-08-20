"""Margins, inversion, minor ticks and tick styling.

matplotlib spreads these across `margins()`, `autoscale()`, `invert_xaxis()`,
`minorticks_on()` and `tick_params()` - five more ways to write to an axes. They
arrive here as `set(**kwargs)` options instead, because a second write idiom is
exactly what Phase 6 spent its time removing (see `test_api.py`).

The autoscale margin in particular was a module constant with no way to reach
it, so "tight limits around my data" was not expressible at all.
"""

from __future__ import annotations

import re

import pyplotrs as pp
import pytest


def _axes(**kw):
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 10])
    ax.set(**kw)
    return fig, ax


# -- margins ------------------------------------------------------------------

def test_default_margin_is_five_percent():
    _, ax = _axes()
    assert ax.get_ylim() == (-0.5, 10.5)


def test_zero_margin_is_tight_to_the_data():
    _, ax = _axes(margin=0)
    assert ax.get_ylim() == (0.0, 10.0)


def test_margin_widens_the_view():
    _, ax = _axes(margin=0.3)
    assert ax.get_ylim() == (-3.0, 13.0)


def test_margins_are_per_axis():
    _, ax = _axes(ymargin=0.0)
    assert ax.get_ylim() == (0.0, 10.0)
    assert ax.get_xlim() != (0.0, 1.0), "x should keep the default margin"


def test_explicit_limits_still_beat_margins():
    _, ax = _axes(margin=0.5, ylim=(0, 20))
    assert ax.get_ylim() == (0.0, 20.0)


# -- returning to autoscale ---------------------------------------------------

def test_lim_auto_clears_a_pinned_limit():
    """`None` means "leave alone", so it cannot double as a reset - hence the
    explicit "auto"."""
    _, ax = _axes(ylim=(0, 5))
    assert ax.get_ylim() == (0.0, 5.0)
    ax.set(ylim="auto")
    assert ax.get_ylim() == (-0.5, 10.5)


# -- inversion ----------------------------------------------------------------

def test_inverted_axis_descends():
    _, ax = _axes(yinverted=True)
    lo, hi = ax.get_ylim()
    assert lo > hi


def test_inversion_composes_with_autoscaling():
    """The point of `yinverted` over `ylim=(hi, lo)`: you do not have to know
    the data range to flip the axis."""
    _, ax = _axes(yinverted=True)
    assert ax.get_ylim() == (10.5, -0.5)


def test_inversion_is_reversible():
    _, ax = _axes(yinverted=True)
    ax.set(yinverted=False)
    assert ax.get_ylim() == (-0.5, 10.5)


def test_explicit_descending_limits_still_work():
    _, ax = _axes(ylim=(10, 0))
    assert ax.get_ylim() == (10.0, 0.0)


def test_inverted_axis_changes_the_rendering(tmp_path):
    def render(name, **kw):
        fig, ax = pp.subplots(figsize=(200, 150))
        ax.line([0, 1], [0, 10])
        ax.set(**kw)
        out = tmp_path / f"{name}.png"
        fig.save(str(out))
        return out.read_bytes()

    assert render("up") != render("down", yinverted=True)


# -- minor ticks --------------------------------------------------------------

def test_linear_axes_have_no_minor_ticks_by_default(tmp_path):
    """Untouched linear output must stay byte-identical, so minor ticks on a
    linear scale are opt-in."""
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.line([0, 1, 2, 3], [0, 5, 3, 9])
    out = tmp_path / "plain.svg"
    fig.save(str(out))
    plain = len(re.findall(r"<path", out.read_text(encoding="utf-8")))

    fig2, ax2 = pp.subplots(figsize=(240, 180))
    ax2.line([0, 1, 2, 3], [0, 5, 3, 9])
    ax2.set(minor=4)
    out2 = tmp_path / "minor.svg"
    fig2.save(str(out2))
    assert len(re.findall(r"<path", out2.read_text(encoding="utf-8"))) > plain


def test_minor_subdivision_lands_between_majors():
    from pyplotrs._util import _subdivide
    minors = _subdivide([0.0, 1.0, 2.0], 4, -0.1, 2.1)
    assert 0.25 in minors and 0.5 in minors and 0.75 in minors
    assert 1.0 not in minors, "a major must not be repeated as a minor"


def test_minor_count_of_one_means_no_subdivision():
    from pyplotrs._util import _subdivide
    assert _subdivide([0.0, 1.0], 1, 0.0, 1.0) == []


def test_log_scale_keeps_its_own_minor_ticks():
    """A non-linear scale subdivides itself; the linear fallback must not
    override the 2..9 x 10^k decade subdivision."""
    fig, ax = pp.subplots()
    ax.line([1, 1000], [1, 1000])
    ax.set(xscale="log", xminor=4)
    lo, hi = ax.get_xlim()
    assert ax._xscale.minor_ticks(lo, hi), "log scale should supply its own"


# -- tick styling -------------------------------------------------------------

def test_tick_direction_changes_the_rendering(tmp_path):
    def render(name, **kw):
        fig, ax = pp.subplots(figsize=(200, 150))
        ax.line([0, 1], [0, 10])
        ax.set(**kw)
        out = tmp_path / f"{name}.svg"
        fig.save(str(out))
        return out.read_text(encoding="utf-8")

    assert render("out") != render("in", tick_direction="in")


def test_tick_length_changes_the_rendering(tmp_path):
    def render(name, **kw):
        fig, ax = pp.subplots(figsize=(200, 150))
        ax.line([0, 1], [0, 10])
        ax.set(**kw)
        out = tmp_path / f"{name}.svg"
        fig.save(str(out))
        return out.read_text(encoding="utf-8")

    assert render("short") != render("long", tick_length=9.0)


def test_tick_labels_stay_put_when_ticks_turn_inward(tmp_path):
    """The label band is measured against the default tick length, so pointing
    the ticks inward must not drag the labels onto the axis."""
    def label_xs(name, **kw):
        fig, ax = pp.subplots(figsize=(240, 180))
        ax.line([0, 1], [0, 10])
        ax.set(**kw)
        out = tmp_path / f"{name}.svg"
        fig.save(str(out))
        return re.findall(r'<text[^>]*x="([-\d.]+)"', out.read_text(encoding="utf-8"))

    assert label_xs("o") == label_xs("i", tick_direction="in")


def test_bad_tick_direction_is_rejected():
    fig, ax = pp.subplots()
    with pytest.raises(ValueError, match="tick_direction"):
        ax.set(tick_direction="sideways")
