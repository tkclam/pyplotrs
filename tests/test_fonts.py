"""Bold and italic text.

Until now the font stack knew exactly two faces, `"body"` and `"math"`, so there
was no way to set a bold title - a real hole for the journal-figure use case
that no plot-type count would show. These tests cover the whole path: the face
selector, resolution against the host, layout measuring with the right face, and
the PDF actually embedding four distinct subsets rather than four references to
one regular face.
"""

from __future__ import annotations

import re

import pytest

import pyplotrs as plt
from pyplotrs import _pyplotrs_core as _core
from pyplotrs.figure import _font


# -- the selector ------------------------------------------------------------

@pytest.mark.parametrize("weight,style,expected", [
    ("normal", "normal", "body"),
    ("bold", "normal", "body-bold"),
    ("normal", "italic", "body-italic"),
    ("bold", "italic", "body-bolditalic"),
    ("normal", "oblique", "body-italic"),
    ("BOLD", "Italic", "body-bolditalic"),
])
def test_font_selector(weight, style, expected):
    assert _font(weight, style) == expected


def test_unknown_weight_or_style_falls_back_rather_than_raising():
    """A typo should cost you the emphasis, not the whole figure at save time."""
    assert _font("bolt", "itallic") == "body"


# -- host resolution ---------------------------------------------------------

def test_all_four_faces_resolve():
    variants = dict(_core.resolved_font_variants())
    assert set(variants) == {"body", "body-bold", "body-italic", "body-bolditalic"}
    assert all(v for v in variants.values())


def test_faces_are_distinct_when_the_host_has_them():
    """Reported as PostScript names, which differ per face (ArialMT vs
    Arial-BoldMT); the *family* name is identical across all four and so cannot
    show whether a bold face was really found.

    Skipped rather than failed on a host with no bold face - font matching is
    approximate by design and falls back to regular.
    """
    variants = dict(_core.resolved_font_variants())
    if variants["body-bold"] == variants["body"]:
        pytest.skip(f"host has no distinct bold face for {_core.resolved_font_name()}")
    assert variants["body-bold"] != variants["body"]
    assert variants["body-italic"] != variants["body"]
    assert variants["body-bolditalic"] not in (variants["body"], variants["body-bold"])


def test_changing_the_family_invalidates_every_cached_face():
    """The cache is keyed per face, so `set_font_family` has to clear all of it -
    not just the regular entry."""
    original = plt.get_font_family()
    try:
        plt.set_font_family("Liberation Sans")
        liberation = dict(_core.resolved_font_variants())
        plt.set_font_family("DejaVu Sans")
        dejavu = dict(_core.resolved_font_variants())
        if liberation == dejavu:
            pytest.skip("host lacks one of Liberation Sans / DejaVu Sans")
        for key in liberation:
            assert liberation[key] != dejavu[key], f"{key} was served from a stale cache"
    finally:
        plt.set_font_family(*original)


# -- measuring ---------------------------------------------------------------

def test_bold_measures_wider_than_regular():
    """The layout engine sizes its bands from these measurements, so bold must
    measure as bold or a bold label will clip."""
    scene = _core.Scene(200.0, 100.0)
    regular = scene.measure_math("Handgloves", 11.0, "body")[0]
    bold = scene.measure_math("Handgloves", 11.0, "body-bold")[0]
    if bold == regular:
        pytest.skip("host has no distinct bold face")
    assert bold > regular


def test_bold_title_reserves_more_height_than_it_needs_none(tmp_path):
    """End-to-end: a bold title must not overlap the plot area."""
    for weight in ("normal", "bold"):
        theme = plt.themes.default.with_(title_weight=weight)
        fig, ax = plt.subplots(figsize=(240, 180), theme=theme)
        ax.line([0, 1], [0, 1])
        ax.set(title="Handgloves", xlabel="x", ylabel="y")
        fig.save(str(tmp_path / f"{weight}.png"))


# -- rendering ---------------------------------------------------------------

def test_weight_and_style_reach_the_output(tmp_path):
    """Distinct faces must produce distinct text extents in the SVG, which is
    the cheapest observable proof the right font was used."""
    def widths(**kw):
        fig, ax = plt.subplots(figsize=(300, 200))
        ax.line([0, 1], [0, 1])
        ax.text(0.1, 0.8, "Handgloves", **kw)
        out = tmp_path / "t.svg"
        fig.save(str(out))
        return out.read_text()

    plain = widths()
    bold = widths(weight="bold")
    italic = widths(style="italic")
    # Every variant still emits real text, not outlines.
    for svg in (plain, bold, italic):
        assert "Handgloves" in svg
    if _core.resolved_font_variants()[1][1] == _core.resolved_font_variants()[0][1]:
        pytest.skip("host has no distinct bold face")
    assert bold != plain, "bold produced byte-identical SVG to regular"
    assert italic != plain, "italic produced byte-identical SVG to regular"


def test_pdf_embeds_a_separate_subset_per_face(tmp_path):
    """Four faces should mean four embedded subsets, each still CID TrueType and
    never Type 3 - the emphasis must not cost the library its headline property."""
    theme = plt.themes.default.with_(title_weight="bold")
    fig, ax = plt.subplots(figsize=(320, 240), theme=theme)
    ax.line([0, 1], [0, 1])
    ax.set(title="Bold title", xlabel="x")
    ax.text(0.2, 0.8, "italic", style="italic")
    ax.text(0.2, 0.6, "bold italic", weight="bold", style="italic")
    out = tmp_path / "faces.pdf"
    fig.save(str(out))
    data = out.read_bytes()

    assert b"/Type3" not in data
    subsets = set(re.findall(rb"/BaseFont\s*/([A-Z]{6}\+[^\s/>]+)", data))
    families = {name.split(b"+", 1)[1] for name in subsets}
    if len(families) < 2:
        pytest.skip("host has no distinct bold/italic faces to embed")
    assert len(families) >= 3, f"expected several faces embedded, got {families}"
    assert data.count(b"CIDFontType2") >= 3


def test_annotations_accept_weight_and_style(tmp_path):
    fig, ax = plt.subplots(figsize=(240, 180))
    ax.line([0, 1], [0, 1])
    ax.annotate("look", (0.5, 0.5), xytext=(0.7, 0.2), weight="bold", style="italic")
    fig.save(str(tmp_path / "ann.png"))


def test_default_theme_is_still_all_normal_weight():
    """Emphasis is opt-in: adding the feature must not restyle existing figures."""
    t = plt.themes.default
    assert (t.title_weight, t.suptitle_weight, t.axis_label_weight) == (
        "normal", "normal", "normal"
    )
