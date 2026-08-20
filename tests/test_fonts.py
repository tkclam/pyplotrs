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
from pathlib import Path

import pyplotrs as pp
import pytest
from pyplotrs import _pyplotrs_core as _core
from pyplotrs._draw import _font

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


def test_faces_are_always_distinct():
    """Reported as PostScript names, which differ per face (ArialMT vs
    Arial-BoldMT); the *family* name is identical across all four and so cannot
    show whether a bold face was really found.

    This is an unconditional assertion because all four faces are bundled - it
    must hold even on a host with no fonts installed at all.
    """
    variants = dict(_core.resolved_font_variants())
    assert variants["body-bold"] != variants["body"]
    assert variants["body-italic"] != variants["body"]
    assert variants["body-bolditalic"] not in (variants["body"], variants["body-bold"])


def test_every_face_falls_back_to_a_bundled_one():
    """With no matching family, all four faces must come from the bundle.

    This is the property that makes emphasis portable: a container with no fonts
    installed still gets real bold and italic rather than four copies of regular.
    """
    original = pp.get_font_family()
    try:
        pp.set_font_family("No Such Family Exists")
        assert set(dict(_core.resolved_font_variants()).values()) == {
            "LiberationSans-Regular",
            "LiberationSans-Bold",
            "LiberationSans-Italic",
            "LiberationSans-BoldItalic",
        }
    finally:
        pp.set_font_family(*original)


def test_changing_the_family_invalidates_every_cached_face():
    """The cache is keyed per face, so `set_font_family` has to clear all of it,
    not just the regular entry - otherwise bold keeps serving the old family."""
    original = pp.get_font_family()
    try:
        pp.set_font_family("DejaVu Sans")
        before = dict(_core.resolved_font_variants())
        pp.set_font_family("No Such Family Exists")
        after = dict(_core.resolved_font_variants())
        if before == after:
            pytest.skip("host lacks DejaVu Sans, so there is no change to observe")
        for key in before:
            assert before[key] != after[key], f"{key} was served from a stale cache"
    finally:
        pp.set_font_family(*original)


# -- measuring ---------------------------------------------------------------

def test_bold_measures_wider_than_regular():
    """The layout engine sizes its bands from these measurements, so bold must
    measure as bold or a bold label will clip."""
    scene = _core.Scene(200.0, 100.0)
    regular = scene.measure_math("Handgloves", 11.0, "body")[0]
    bold = scene.measure_math("Handgloves", 11.0, "body-bold")[0]
    assert bold > regular


def test_bold_title_reserves_more_height_than_it_needs_none(tmp_path):
    """End-to-end: a bold title must not overlap the plot area."""
    for weight in ("normal", "bold"):
        theme = pp.themes.default.with_(title_weight=weight)
        fig, ax = pp.subplots(figsize=(240, 180), theme=theme)
        ax.line([0, 1], [0, 1])
        ax.set(title="Handgloves", xlabel="x", ylabel="y")
        fig.save(str(tmp_path / f"{weight}.png"))


# -- rendering ---------------------------------------------------------------

def test_weight_and_style_reach_the_output(tmp_path):
    """Distinct faces must produce distinct text extents in the SVG, which is
    the cheapest observable proof the right font was used."""
    def widths(**kw):
        fig, ax = pp.subplots(figsize=(300, 200))
        ax.line([0, 1], [0, 1])
        ax.text(0.1, 0.8, "Handgloves", **kw)
        out = tmp_path / "t.svg"
        fig.save(str(out))
        return out.read_text(encoding="utf-8")

    plain = widths()
    bold = widths(weight="bold")
    italic = widths(style="italic")
    # Every variant still emits real text, not outlines.
    for svg in (plain, bold, italic):
        assert "Handgloves" in svg
    assert bold != plain, "bold produced byte-identical SVG to regular"
    assert italic != plain, "italic produced byte-identical SVG to regular"


def test_pdf_embeds_a_separate_subset_per_face(tmp_path):
    """Four faces should mean four embedded subsets, each still CID TrueType and
    never Type 3 - the emphasis must not cost the library its headline property."""
    theme = pp.themes.default.with_(title_weight="bold")
    fig, ax = pp.subplots(figsize=(320, 240), theme=theme)
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
    assert len(families) >= 3, f"expected several faces embedded, got {families}"
    assert data.count(b"CIDFontType2") >= 3


def test_annotations_accept_weight_and_style(tmp_path):
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.line([0, 1], [0, 1])
    ax.annotate("look", (0.5, 0.5), xytext=(0.7, 0.2), weight="bold", style="italic")
    fig.save(str(tmp_path / "ann.png"))


def test_default_theme_is_still_all_normal_weight():
    """Emphasis is opt-in: adding the feature must not restyle existing figures."""
    t = pp.themes.default
    assert (t.title_weight, t.suptitle_weight, t.axis_label_weight) == (
        "normal", "normal", "normal"
    )


# -- which face math takes its glyphs from -----------------------------------

def _embedded_families(fig, path):
    """The font families a saved PDF actually embeds, subset tag stripped.

    A CID-keyed font names itself twice - once on the Type 0 parent, as
    ``Name-Identity-H``, and once on the descendant as plain ``Name``. Both name
    the same face, so the encoding suffix is dropped; otherwise a CFF math font
    would look like two.
    """
    fig.save(str(path))
    subsets = re.findall(rb"/BaseFont\s*/([A-Z]{6}\+[^\s/>]+)", path.read_bytes())
    names = (name.split(b"+", 1)[1].decode() for name in subsets)
    return {n.removesuffix("-Identity-H") for n in names}


def test_math_digits_come_from_the_body_face(tmp_path):
    """A log axis must not change typeface halfway round the figure.

    `LogFormatter` labels decades as `$10^{k}$`, so every one of those digits
    goes through the math engine - and the bundled math font is STIX Two Math, a
    serif. Drawn from it, a tick reading `10^3` came out Times-like beside y
    ticks reading `50` and `100` in the sans body face. Upright text-like atoms
    now come from the body font, so a figure whose only math is its tick labels
    embeds one family and reads as one figure.
    """
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([1, 10, 100, 1000], [1, 2, 3, 4])
    ax.set(xscale="log")
    assert _embedded_families(fig, tmp_path / "log.pdf") == {"LiberationSans"}


def test_variables_and_greek_come_from_the_body_italic(tmp_path):
    """The same rule carried through the rest of the span.

    Digits alone were never the whole problem: `$\\alpha + \\sqrt{\\beta}$` set
    its Greek in STIX and its `+` in the body face, so one expression mixed a
    serif with a sans. Liberation Sans (and Arial, and Helvetica) carry the
    whole Greek range in all four faces, so the variables come from the body
    italic and the span is set in one family. The radical is still STIX's - it
    is drawn as a vector outline, which embeds no face at all.
    """
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([0, 1], [0, 1])
    ax.set(xlabel=r"$\alpha + \sqrt{\beta}$")
    assert _embedded_families(fig, tmp_path / "greek.pdf") == {
        "LiberationSans", "LiberationSans-Italic",
    }


def test_symbols_the_body_family_lacks_come_from_the_sans_symbol_face(tmp_path):
    """A text family's coverage of the symbol blocks is ragged - Liberation Sans
    has `→` but not `⇒`, `∩` but not `∪`, `±` but not `∓` - so falling straight
    to a serif math font split symbol families down the middle. The bundled
    DejaVu Sans subset closes the gap in the same sans idiom, and the math font
    is not needed at all here."""
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([0, 1], [0, 1])
    ax.set(xlabel=r"$\nabla^2\psi = \hbar\omega,\ A \cup B,\ x \in S$")
    assert _embedded_families(fig, tmp_path / "symbols.pdf") == {
        "LiberationSans", "LiberationSans-Italic", "DejaVuSans",
    }


def test_structural_glyphs_come_from_the_sans_math_font(tmp_path):
    """`√`, `∑` and auto-sized fences cannot come from a text face: growing them
    needs the MATH table's variant and assembly chains. Fira Math is a *sans*
    font that has them, so they match the label around them instead of arriving
    Times-shaped from STIX."""
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([0, 1], [0, 1])
    ax.set(xlabel=r"$\sqrt{\sum_i x_i} \left(\frac{a}{b}\right)$")
    assert _embedded_families(fig, tmp_path / "struct.pdf") == {
        "LiberationSans", "LiberationSans-Italic", "FiraMath-Regular",
    }


def test_the_math_font_still_serves_the_glyphs_only_it_has(tmp_path):
    """The end of the chain. No sans math font is complete - Fira Math has no
    Script and no Fraktur alphabet - so STIX stays bundled for the letterforms
    nothing else carries. A change that dropped it would pass every test above
    and render boxes here."""
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([0, 1], [0, 1])
    ax.set(xlabel=r"$\mathcal{L}, \mathfrak{g}$")
    assert "STIXTwoMath-Regular" in _embedded_families(fig, tmp_path / "cal.pdf")


def test_the_bundled_symbol_font_is_symbols_only():
    """The subset is a *shape* source, and the invariants that keep it one.

    It carries no MATH table, so nothing can read positioning constants out of
    it by accident - DejaVu's are unusable for that, with ten of twenty-four
    unset and no vertical construction for `√`. And it carries no letters or
    digits, so it can never win a lookup that the body family or the math
    font's own alphabets should have answered.
    """
    ttLib = pytest.importorskip("fontTools.ttLib")
    TTFont = ttLib.TTFont

    path = Path(__file__).parent.parent / "assets" / "fonts" / "DejaVuSans-MathSymbols.ttf"
    font = TTFont(path, fontNumber=0)
    assert "MATH" not in font, "the symbol subset must not carry a MATH table"
    covered = {cp for table in font["cmap"].tables for cp in table.cmap}
    letters_and_digits = set(range(0x30, 0x3A)) | set(range(0x41, 0x5B)) | set(range(0x61, 0x7B))
    greek = set(range(0x370, 0x400))
    alphanumerics = set(range(0x1D400, 0x1D800))
    for name, block in [("ASCII letters/digits", letters_and_digits),
                        ("Greek", greek), ("Mathematical Alphanumerics", alphanumerics)]:
        assert not covered & block, f"the symbol subset should carry no {name}"
    assert len(covered) > 500, f"suspiciously few symbols: {len(covered)}"


def test_the_symbol_font_stays_far_smaller_than_the_font_it_is_cut_from():
    """The subset is the reason this tier costs 95 KB rather than 742 KB. If a
    regeneration ever drops the range list, the wheel grows eightfold and this
    is the only thing that would notice."""
    path = Path(__file__).parent.parent / "assets" / "fonts" / "DejaVuSans-MathSymbols.ttf"
    assert path.stat().st_size < 200 * 1024, (
        f"{path.name} is {path.stat().st_size // 1024} KB; regenerate it with "
        "tools/build_math_symbol_font.py"
    )


def test_a_bold_label_sets_its_math_bold_throughout(tmp_path):
    """Before the four body faces were plumbed through, a bold label's digits
    and operators picked up the weight and its variables did not, so
    `$E = mc^2$` in a bold title came out half-bold."""
    fig, ax = pp.subplots(figsize=(300, 220))
    ax.line([0, 1], [0, 1])
    ax.text(0.2, 0.5, r"$E = mc^2$", weight="bold")
    assert _embedded_families(fig, tmp_path / "bold.pdf") == {
        "LiberationSans", "LiberationSans-Bold", "LiberationSans-BoldItalic",
    }


def test_the_stix_fontset_sets_every_atom_in_the_math_font(tmp_path):
    """`set_mathtext_fontset("stix")` is the opposite promise to the default:
    uniformly serif math rather than math that matches a sans body."""
    try:
        pp.set_mathtext_fontset("stix")
        assert pp.get_mathtext_fontset() == "stix"
        fig, ax = pp.subplots(figsize=(300, 220))
        ax.line([0, 1], [0, 1])
        ax.set(xlabel=r"$E = mc^2$")
        assert _embedded_families(fig, tmp_path / "stix.pdf") == {
            "LiberationSans", "STIXTwoMath-Regular",
        }
    finally:
        pp.set_mathtext_fontset()
    assert pp.get_mathtext_fontset() == "sans"


def test_an_unknown_fontset_name_is_rejected():
    with pytest.raises(ValueError, match="unknown mathtext fontset"):
        pp.set_mathtext_fontset("comic-sans-math")
    assert pp.get_mathtext_fontset() == "sans"


def test_a_digit_measures_the_same_inside_and_outside_math():
    """The tightest statement of the rule: `10` is `10` either way. Widths are
    what the layout engine reserves bands from, so equal widths mean the same
    face drew both."""
    scene = _core.Scene(200.0, 100.0)
    assert scene.measure_math("10", 11.0, "body")[0] == pytest.approx(
        scene.measure_math("$10$", 11.0, "body")[0]
    )
