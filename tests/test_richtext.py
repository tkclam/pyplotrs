"""Styling a substring of a label.

Everything a figure writes - titles, axis labels, tick labels, legend entries,
annotations - is one string drawn by one call, which meant emphasis was
all-or-nothing: a whole title could be bold, one word in it could not. These
tests cover the span model that fixes that, from the tree the helpers build
down to the glyphs, rules and panels that come out, and the two things a
partial style must not break: the measurement the layout engine reserves bands
from, and the text a PDF still hands back to `pdftotext`.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pyplotrs as pp
import pytest
from pyplotrs._draw import _text, _th, _tw

# -- the span tree -----------------------------------------------------------


def test_helpers_carry_their_own_style():
    assert pp.bold("x").style["weight"] == "bold"
    assert pp.italic("x").style["style"] == "italic"
    assert pp.underline("x").style["underline"] is True
    assert pp.strike("x").style["strike"] is True
    assert pp.mark("x").style["bgcolor"]


def test_an_inner_style_overrides_the_outer_one():
    """The rule that makes nesting usable: an exception inside a bold run has to
    be able to opt back out, not just add more style."""
    leaves = pp.text.flatten(pp.bold("all ", pp.rich("but this", weight="normal")))
    assert [t for t, _ in leaves] == ["all ", "but this"]
    assert leaves[0][1]["weight"] == "bold"
    assert leaves[1][1]["weight"] == "normal"


def test_an_inner_style_inherits_what_it_does_not_override():
    (_t, style), = pp.text.flatten(pp.bold(pp.italic("x"), color="teal"))
    assert style == {"weight": "bold", "style": "italic", "color": "teal"}


def test_adjacent_runs_of_one_style_merge():
    """Not cosmetic: each run is shaped separately, so an unnecessary split
    would silently drop the kern pair straddling it."""
    assert pp.text.flatten(pp.rich("a", "b", pp.rich("c"))) == [("ab" + "c", {})]


def test_a_style_boundary_that_is_real_does_not_merge():
    leaves = pp.text.flatten(pp.rich("a", pp.bold("b")))
    assert [t for t, _ in leaves] == ["a", "b"]


def test_an_unknown_style_is_rejected_at_construction():
    """A misspelled style that quietly did nothing would be found only by
    staring at the finished figure."""
    with pytest.raises(TypeError, match="colour"):
        pp.rich("x", colour="red")


def test_size_and_scale_are_mutually_exclusive():
    with pytest.raises(TypeError, match="not both"):
        pp.rich("x", size=12, scale=1.5)


def test_plain_text_survives_the_styling():
    """What a screen reader, a tagged PDF and `get_title` all need back."""
    s = pp.rich("Growth ", pp.bold("+42%"), " over ", pp.italic("6 months"))
    assert s.text == "Growth +42% over 6 months"
    assert pp.plain(s) == s.text
    assert pp.plain("already a string") == "already a string"
    assert str(s) == s.text


def test_repr_round_trips_through_the_constructor():
    s = pp.rich("a", pp.bold("b"), color="teal")
    assert eval(repr(s), {"rich": pp.rich}) == s


# -- measurement -------------------------------------------------------------


def _scene():
    return pp.subplots()[0]._build_scene()


def test_an_unstyled_span_measures_exactly_like_the_bare_string():
    """The span machinery must be a no-op when it is not asked for anything -
    otherwise every label in every figure shifts the day this lands."""
    sc = _scene()
    assert _tw(sc, pp.rich("Hello"), 10.0) == _tw(sc, "Hello", 10.0)
    assert _th(sc, pp.rich("Hello"), 10.0) == _th(sc, "Hello", 10.0)


def test_widths_add_across_runs():
    sc = _scene()
    parts = _tw(sc, "Hello ", 10.0) + _tw(sc, "world", 10.0)
    assert _tw(sc, pp.rich("Hello ", pp.bold("world")), 10.0) != pytest.approx(parts)
    assert _tw(sc, pp.rich("Hello ", pp.rich("world")), 10.0) == pytest.approx(
        _tw(sc, "Hello world", 10.0))


def test_a_bold_run_is_wider_than_the_same_run_unstyled():
    sc = _scene()
    assert _tw(sc, pp.bold("Emphasis"), 10.0) > _tw(sc, "Emphasis", 10.0)


def test_the_band_fits_the_tallest_run_not_the_first():
    """The layout engine reserves label bands from this number, so a big word
    at the end of a title has to be accounted for at the start of it."""
    sc = _scene()
    small = _th(sc, "x", 10.0)
    mixed = _th(sc, pp.rich("x", pp.rich("X", scale=3.0)), 10.0)
    assert mixed[0] > small[0]
    assert mixed[0] == pytest.approx(_th(sc, "X", 30.0)[0])


def test_a_highlight_claims_room_for_its_panel():
    """A panel that the band did not account for bleeds into the plot area."""
    sc = _scene()
    assert _th(sc, pp.mark("x"), 10.0)[0] > _th(sc, "x", 10.0)[0]


# -- what gets drawn ---------------------------------------------------------


def _svg(**kwargs) -> str:
    fig, ax = pp.subplots(figsize=(360, 240))
    ax.line([0, 1, 2], [0, 1, 4])
    ax.set(**kwargs)
    return fig._build_scene().to_svg()


def _fills(svg: str) -> list[str]:
    return re.findall(r'fill="(#[0-9a-fA-F]{6})"', svg)


def test_a_colored_run_paints_only_itself():
    svg = _svg(title=pp.rich("plain ", pp.rich("teal", color="#008080")))
    assert "#008080" in _fills(svg)
    assert svg.count("#008080") == 1, "the color leaked past its own run"


def test_a_color_resolves_against_the_theme_palette():
    """`"C1"` in a label has to mean what `"C1"` means everywhere else."""
    fig, ax = pp.subplots()
    ax.set(title=pp.rich("x", color="C1"))
    r, g, b, _a = fig.theme.palette[1]
    assert f"#{r:02x}{g:02x}{b:02x}" in _fills(fig._build_scene().to_svg())


def test_a_highlight_draws_a_panel_and_the_text_over_it():
    svg = _svg(title=pp.mark("lit"))
    panel = svg.index("#ffe89a")
    assert panel < svg.index("lit"), "the panel must be drawn under the glyphs"


def test_a_highlight_panel_stays_inside_the_band_reserved_for_it():
    """The panel's padding is counted once, by the measurement the layout
    engine reserves bands from. Counted again at draw time it put the panel a
    padding's worth into the plot area, which is the whole failure the
    measurement exists to prevent."""
    sc = _scene()
    size = 20.0
    label = pp.mark("lit")
    ascent, depth = _th(sc, label, size)
    before = sc.to_svg()
    _text(sc, 0.0, 0.0, label, size, (0, 0, 0, 255))
    panel = re.search(r'<path d="M(-?[\d.]+) (-?[\d.]+) L[^"]*L(-?[\d.]+) (-?[\d.]+) Z"'
                      r' fill="#ffe89a"', sc.to_svg()[len(before) - 12:])
    assert panel, "no highlight panel was drawn"
    top, bottom = float(panel.group(2)), float(panel.group(4))
    assert top >= -ascent - 1e-6, f"panel top {top} above the reserved {-ascent}"
    assert bottom <= depth + 1e-6, f"panel bottom {bottom} below the reserved {depth}"


def test_underline_and_strike_land_on_opposite_sides_of_the_baseline():
    """Taken from the face's own `post`/`OS-2` metrics, not guessed from the
    type size, so the rules move correctly between faces."""
    sc = _scene()
    uo, ut, so, st = sc.text_decorations(10.0, "body")
    assert uo > 0 and so < 0
    assert ut > 0 and st > 0


def test_rules_are_drawn_for_the_runs_that_ask_for_them():
    plain = _svg(title=pp.rich("abc"))
    ruled = _svg(title=pp.rich(pp.underline("a"), pp.strike("b"), "c"))
    assert ruled.count("<path") == plain.count("<path") + 2


def test_text_stays_real_text_rather_than_outlines():
    """The whole promise of the library: styling a substring must not be the
    thing that finally bakes a label into paths."""
    svg = _svg(title=pp.rich("a ", pp.bold("b"), " ", pp.mark("c")))
    assert svg.count("<text") >= 3


# -- every label slot accepts it --------------------------------------------


def test_rich_text_works_in_every_label_slot(tmp_path):
    fig, ax = pp.subplots(figsize=(420, 300))
    ax.line([0, 1, 2], [0, 1, 4], label=pp.rich("series ", pp.bold("A")))
    ax.set(
        title=pp.rich("t ", pp.bold("b")),
        xlabel=pp.rich("x ", pp.italic("i")),
        ylabel=pp.rich("y ", pp.mark("m")),
        xticks=[0, 1, 2],
        xticklabels=[pp.bold("zero"), "one", pp.rich("two", color="C2")],
    )
    ax.text(0.5, 2.0, pp.underline("annotated"))
    ax.annotate(pp.strike("callout"), (1, 1), xytext=(1.4, 3.0))
    ax.legend()
    fig.set(suptitle=pp.rich("sup ", pp.bold("title")))
    for ext in ("png", "svg", "pdf"):
        fig.save(str(tmp_path / f"all.{ext}"))
    assert (tmp_path / "all.pdf").stat().st_size > 0


def test_a_rotated_rich_label_still_rotates_as_one_piece():
    """The y label is drawn inside a rotation group; its runs, panels and rules
    all have to live in *that* group or they scatter across the figure - the
    panel painted upright behind a label that is on its side."""
    svg = _svg(ylabel=pp.rich("y ", pp.mark("units")))
    group = next(
        svg[m.start():svg.index("</g>", m.start())]
        for m in re.finditer(r'<g transform="matrix\([^"]*\)"[^>]*>', svg)
        if "units" in svg[m.start():svg.index("</g>", m.start())]
    )
    assert "#ffe89a" in group, "the highlight panel escaped the rotation group"
    assert group.count("<text") == 2, "the runs escaped the rotation group"


# -- math --------------------------------------------------------------------


def test_a_bold_span_sets_its_math_bold_throughout():
    """The span's weight becomes the math's *ambient* face, so the variables
    come with it rather than leaving `$E = mc^2$` half-bold."""
    sc = _scene()
    assert _tw(sc, pp.bold(r"$E = mc^2$"), 12.0) > _tw(sc, r"$E = mc^2$", 12.0)


def test_textcolor_tints_one_term_of_an_equation():
    svg = _svg(xlabel=r"$\textcolor{#c0392b}{\sigma} / \sqrt{N}$")
    assert "#c0392b" in svg


def test_textcolor_accepts_a_palette_index_like_any_other_color():
    fig, ax = pp.subplots()
    ax.set(xlabel=r"$\textcolor{C3}{x}$")
    r, g, b, _a = fig.theme.palette[3]
    assert f"#{r:02x}{g:02x}{b:02x}" in fig._build_scene().to_svg()


def _drawn_text(svg: str) -> str:
    return "".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))


def test_a_bad_color_costs_the_color_not_the_term():
    """Dropping the sub-expression a typo'd color wraps would lose a term of an
    equation - far worse than getting its color wrong."""
    bad = _svg(xlabel=r"$\textcolor{nosuchcolor}{x} + y$")
    good = _svg(xlabel=r"$\textcolor{#c0392b}{x} + y$")
    assert _drawn_text(bad) == _drawn_text(good)
    assert "#c0392b" not in bad


def test_a_math_span_inside_rich_text_reaches_the_mathjax_html(tmp_path):
    """The HTML backend captures math per `add_math` call; composing spans as
    separate calls is what keeps that working for a partly-styled label."""
    fig, ax = pp.subplots(figsize=(360, 240))
    ax.line([0, 1], [0, 1])
    ax.set(title=pp.rich("rate ", pp.bold(r"$\alpha$")))
    out = tmp_path / "m.html"
    fig.save(str(out))
    assert out.read_text().count('class="fxmath"') >= 1


# -- the promises a partial style must not break ----------------------------


def test_a_pdf_still_extracts_the_whole_label_in_order(tmp_path):
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext not available")
    fig, ax = pp.subplots(figsize=(400, 260))
    ax.line([0, 1, 2], [0, 1, 4])
    ax.set(title=pp.rich("Growth ", pp.bold("+42%"), " over ", pp.italic("6 months")))
    out = tmp_path / "t.pdf"
    fig.save(str(out))
    text = subprocess.run(["pdftotext", str(out), "-"],
                          capture_output=True, text=True).stdout
    assert "Growth +42% over 6 months" in " ".join(text.split())


def test_the_accessible_description_uses_the_plain_text(tmp_path):
    fig, ax = pp.subplots()
    ax.line([0, 1], [0, 1])
    ax.set(title=pp.rich("A ", pp.bold("B")), xlabel=pp.bold("x"), ylabel="y")
    title, alt = fig._accessible_text()
    assert "A B" in alt and "rich(" not in alt
    assert "rich(" not in title


def test_measuring_and_drawing_agree_on_where_a_label_ends():
    """They are separate calls with separate resolution passes; if they ever
    disagree, centered labels drift off their anchor by half the error."""
    sc = _scene()
    s = pp.rich("a ", pp.bold("b", scale=1.4), " ", pp.mark("c"))
    before = len(sc.to_svg())
    _text(sc, 0.0, 0.0, s, 10.0, (0, 0, 0, 255))
    assert len(sc.to_svg()) > before
    assert _tw(sc, s, 10.0) == pytest.approx(
        sum(_tw(sc, t, 10.0 * st.get("scale", 1.0),
                "body-bold" if st.get("weight") == "bold" else "body")
            for t, st in pp.text.flatten(s)))
