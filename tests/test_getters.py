"""Reading a figure back.

Every property was write-only: `set(...)` went in, and nothing came out. There
was no `get_xlim`, no `get_title`, no way to ask what ticks an axes would draw.
That blocks anything built *on top* of a figure - a layout tool, a test that
asserts a computed limit, a caption generator - and it is the one gap where
matplotlib's surface is genuinely richer rather than just larger.

The design here is deliberately asymmetric: **writing is `set(**kwargs)`,
reading is `get_*`**. There are no `set_x` partners for these, because a second
way to write is what the vocabulary work spent two phases removing.

The property that matters is not that the getters exist but that they report
the *effective* value - what will be drawn, after autoscaling, tick location
and shared-axis unification - since what was explicitly set is already visible
in the calling code.
"""

from __future__ import annotations

import re

import pytest

import pyplotrs as plt
from pyplotrs.axes import Axes
from pyplotrs.axes3d import Axes3D
from pyplotrs.polar import PolarAxes


def test_getters_report_autoscaled_limits_not_none():
    fig, ax = plt.subplots()
    ax.line([0, 1, 2], [0, 10, 20])
    lo, hi = ax.get_ylim()
    assert lo < 0 and hi > 20, "should report the padded autoscaled range"


def test_getters_report_explicit_limits():
    fig, ax = plt.subplots()
    ax.line([0, 1, 2], [0, 10, 20])
    ax.set(ylim=(-5, 25))
    assert ax.get_ylim() == (-5.0, 25.0)


def test_title_and_labels_round_trip():
    fig, ax = plt.subplots()
    ax.set(title="T", xlabel="X", ylabel="Y")
    assert (ax.get_title(), ax.get_xlabel(), ax.get_ylabel()) == ("T", "X", "Y")


def test_scale_and_aspect_round_trip():
    fig, ax = plt.subplots()
    ax.line([1, 10], [1, 10])
    ax.set(xscale="log", aspect="equal")
    assert ax.get_xscale() == "log"
    assert ax.get_yscale() == "linear"
    assert ax.get_aspect() == "equal"


def test_aspect_defaults_to_auto():
    fig, ax = plt.subplots()
    assert ax.get_aspect() == "auto"


def test_ticks_are_the_located_ones_not_only_manual_ones():
    fig, ax = plt.subplots()
    ax.line([0, 1, 2], [0, 1, 2])
    assert ax.get_xticks(), "an axes with no manual ticks still draws ticks"
    assert len(ax.get_xticks()) == len(ax.get_xticklabels())


def test_manual_ticks_and_labels_come_back():
    fig, ax = plt.subplots()
    ax.line([0, 1, 2], [0, 1, 2])
    ax.set(xticks=[0, 1, 2], xticklabels=["a", "b", "c"])
    assert ax.get_xticks() == [0.0, 1.0, 2.0]
    assert ax.get_xticklabels() == ["a", "b", "c"]


def test_get_xticklabels_matches_the_rendered_svg(tmp_path):
    """The getter and the renderer must resolve ticks through the same path;
    two locators that drift apart would make the getter quietly wrong."""
    fig, ax = plt.subplots(figsize=(320, 240))
    ax.line([0, 1, 2, 3], [0, 5, 3, 9])
    out = tmp_path / "ticks.svg"
    fig.save(str(out))
    drawn = re.findall(r"<text[^>]*>([^<]+)</text>", out.read_text())
    for label in ax.get_xticklabels():
        assert label in drawn, f"getter reported tick {label!r}, not in the SVG"


def test_shared_axes_report_the_unified_range():
    """`sharex`/`sharey` unify ranges inside `_build_scene`, so an axes asked
    in isolation would otherwise report a range it will never be drawn with."""
    fig, (a, b) = plt.subplots(ncols=2, sharey=True)
    a.line([0, 1], [0, 1])
    b.line([0, 1], [0, 100])
    assert a.get_ylim() == b.get_ylim()
    assert a.get_ylim()[1] > 100


def test_unshared_axes_keep_their_own_range():
    fig, (a, b) = plt.subplots(ncols=2)
    a.line([0, 1], [0, 1])
    b.line([0, 1], [0, 100])
    assert a.get_ylim() != b.get_ylim()


def test_legend_handles_and_labels():
    fig, ax = plt.subplots()
    ax.line([0, 1], [0, 1], label="one")
    ax.scatter([0], [0], label="two")
    ax.line([0, 1], [1, 0])  # unlabelled, must not appear
    handles, labels = ax.get_legend_handles_labels()
    assert labels == ["one", "two"]
    assert [h["kind"] for h in handles] == ["line", "scatter"]


def test_legend_handles_expand_pie_wedges():
    fig, ax = plt.subplots()
    ax.pie([1, 2], labels=["a", "b"])
    assert ax.get_legend_handles_labels()[1] == ["a", "b"]


# -- the idiom is uniform across the three axes kinds -------------------------

@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_every_axes_kind_can_be_read_back(cls):
    assert callable(getattr(cls, "get_title"))
    assert callable(getattr(cls, "get_legend_handles_labels"))


@pytest.mark.parametrize("cls", [Axes, Axes3D, PolarAxes])
def test_no_getter_has_a_setter_partner(cls):
    """Reading is `get_*`; writing stays `set(**kwargs)`. A `set_x` partner
    would reintroduce the second write idiom Phase 6 removed."""
    getters = {n[4:] for n in dir(cls) if n.startswith("get_")}
    setters = {n[4:] for n in dir(cls) if n.startswith("set_")}
    assert not (getters & setters), f"{cls.__name__} grew set_/get_ pairs"


def test_3d_getters():
    fig, ax = plt.subplots(projection="3d")
    ax.scatter([0, 1], [0, 2], [0, 3])
    ax.set(title="T", zlabel="z", elev=20, azim=40)
    assert ax.get_title() == "T"
    assert ax.get_zlabel() == "z"
    assert ax.get_view() == (20.0, 40.0)
    assert ax.get_zlim()[1] > 3.0


def test_polar_getters():
    fig, ax = plt.subplots(projection="polar")
    ax.plot([0, 1, 2], [1, 2, 3])
    ax.set(title="P", rmax=5, rticks=[1, 2], thetagrids=[0, 90], theta_direction=-1)
    assert ax.get_title() == "P"
    assert ax.get_rlim() == (0.0, 5.0)
    assert ax.get_rticks() == [1.0, 2.0]
    assert ax.get_thetagrids() == [0.0, 90.0]
    assert ax.get_theta_direction() == -1
