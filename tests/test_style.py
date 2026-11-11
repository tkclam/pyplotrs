"""Colors, colormaps, norms, text and fonts."""

import re
import warnings

import pytest

import pyplotrs as pp
from pyplotrs.colors import to_rgba


def test_color_spellings():
    assert to_rgba("red") == (255, 0, 0, 255)
    assert to_rgba("#f008") == (255, 0, 0, 136)
    assert to_rgba("k") == (0, 0, 0, 255)
    assert to_rgba((1.0, 0.5, 0.0)) == (255, 128, 0, 255)
    assert to_rgba((255, 128, 0, 10)) == (255, 128, 0, 10)
    with pytest.raises(ValueError):
        to_rgba("#12")
    assert pp.themes.default.color("C1") == pp.themes.default.palette[1]


def test_colormaps():
    vir = pp.colormaps.get("viridis")
    assert vir(0.0) == (68, 1, 84, 255)
    assert pp.colormaps.get("viridis_r")(1.0) == vir(0.0)
    assert vir.reversed()(1.0) == vir(0.0)
    assert len(vir.lut(0.5)) == 1024
    assert "magma" in pp.colormaps.names("perceptually_uniform")
    assert "Blues" in pp.colormaps.names("sequential")
    assert len(pp.colormaps.palette("tab10")) == 10
    custom = pp.Colormap.from_colors(["black", "white"])
    assert custom(0.0)[:3] == (0, 0, 0) and custom(1.0)[:3] == (255, 255, 255)
    with pytest.raises(ValueError, match="unknown colormap"):
        pp.colormaps.get("nope")


def test_norms():
    n = pp.norms.Norm().autoscale([1.0, 3.0])
    assert n.limits == (1.0, 3.0) and n(2.0) == 0.5
    log = pp.norms.LogNorm().autoscale([1, 10, 100])
    assert log(10) == pytest.approx(0.5)
    two = pp.norms.TwoSlopeNorm(0).autoscale([-1, 4])
    assert two(0) == 0.5 and two(4) == 1.0
    bounds = pp.norms.BoundaryNorm([0, 1, 2])
    assert bounds(0.5) == 0.25 and bounds(1.5) == 0.75
    assert pp.norms.get("log", 1, 10).limits == (1, 10)


@pytest.mark.parametrize(
    "norm", ["log", pp.norms.TwoSlopeNorm(0.5), pp.norms.BoundaryNorm([0, 0.5, 1])]
)
def test_colorbars_follow_the_norm(norm):
    fig, ax = pp.subplots()
    fig.colorbar(ax.imshow([[0.1, 0.5], [0.7, 1.0]], norm=norm), label="value")
    fig.to_bytes("svg")


def test_rich_text():
    s = pp.rich("a ", pp.bold("b", color="C1"), pp.mark("c"), pp.italic("d", scale=0.8))
    assert s.text == "a bcd" and pp.plain(s) == "a bcd"
    with pytest.raises(TypeError, match="style"):
        pp.rich("x", colour="red")
    fig, ax = pp.subplots()
    ax.set(title=s, xlabel=pp.underline("u"), ylabel=pp.strike("s"))
    runs = re.findall(r'preserve">([^<]*)<', fig.to_bytes("svg").decode())
    assert {"a ", "b", "c", "d", "u", "s"} <= set(runs)


def test_math_renders_and_unknown_commands_warn():
    fig, ax = pp.subplots()
    ax.set(title=r"$\alpha^2 + \sqrt{\frac{x}{y}}$", xlabel=r"$\textcolor{C1}{\mu}$m")
    fig.to_bytes("png", dpi=72)
    ax.set(ylabel=r"$\notarealcommand$")
    with pytest.warns(pp.MathTextWarning, match="notarealcommand"):
        fig.to_bytes("png", dpi=72)


def test_fonts_come_from_the_theme():
    fig, ax = pp.subplots()
    ax.set(title="x")
    canvas = fig._render()
    assert canvas.scene.font_faces()[0][0] == "Liberation Sans"
    fig, ax = pp.subplots(theme=pp.themes.default.replace(font_family=("No Such Font",)))
    assert fig._render().scene.font_faces()[0][0] == "Liberation Sans"  # bundled fallback
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        pp.subplots(theme=pp.themes.default.replace(math_fontset="stix"))[0].to_bytes("png", dpi=50)
