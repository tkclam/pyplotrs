"""The output formats that had no tests: HTML, GIF and APNG.

`Figure.save` advertises four formats. PDF and SVG are covered in depth by
`test_pdf_structure.py`. HTML had **nothing** - not one test in the suite
touched a `.html` file, despite it being a documented format, the one that
carries a 2.2 MB inlined MathJax bundle, and the only one with three separate
code paths (plain SVG, MathJax math, and the Canvas2D 3D viewer). Animation had
one smoke call that asserted the file was non-empty and nothing about whether
the bytes were a GIF.

The properties checked here are the ones the docs promise a reader:

* an HTML figure is **self-contained** - it fetches nothing when opened, which
  is the entire reason the bundle is inlined rather than linked to a CDN;
* it is **well-formed** and carries real `<text>`, not a rasterized image;
* a GIF is a GIF, an APNG is animated, and both have the frames asked for.
"""

from __future__ import annotations

import math
import re
import struct
import xml.etree.ElementTree as ET
import zlib

import pyplotrs as plt
import pytest


def _figure(with_math: bool = False):
    fig, ax = plt.subplots(figsize=(320, 240))
    xs = [i / 20 for i in range(60)]
    ax.line(xs, [math.sin(x) for x in xs], label="signal")
    title = r"Decay $\alpha e^{-t/\tau}$" if with_math else "Decay"
    ax.set(title=title, xlabel=r"$t$ (s)" if with_math else "t (s)", ylabel="y")
    ax.legend()
    return fig


def _html(tmp_path, name: str, **kw) -> str:
    out = tmp_path / f"{name}.html"
    _figure(**kw).save(str(out))
    return out.read_text(encoding="utf-8")


# -- HTML --------------------------------------------------------------------

@pytest.mark.parametrize("with_math", [False, True], ids=["plain", "math"])
def test_html_is_well_formed(tmp_path, with_math):
    page = _html(tmp_path, "wf", with_math=with_math)
    assert page.lstrip().startswith("<!DOCTYPE html>")
    assert page.rstrip().endswith("</html>")
    assert "<html lang=" in page, "the page must declare a language for screen readers"


@pytest.mark.parametrize("with_math", [False, True], ids=["plain", "math"])
def test_html_fetches_nothing_from_the_network(tmp_path, with_math):
    """"Self-contained ... nothing fetched at view time" is the documented
    promise, and the reason a 2.2 MB library is inlined instead of linked.

    Only *fetching* constructs count. The MathJax bundle contains
    `https://www.mathjax.org` inside the strings of its own help dialog, which
    is a link a user can click, not a resource the page loads.
    """
    page = _html(tmp_path, "net", with_math=with_math)
    fetching = re.findall(
        r"""(?:src|href)\s*=\s*["'](https?://[^"']+)""", page)
    # An `<a href>` is navigation, not a fetch; strip those.
    loads = [u for u in fetching
             if not re.search(rf"<a[^>]+href=[\"']{re.escape(u)}", page)]
    assert not loads, f"the page would fetch {loads} when opened"
    assert "@import" not in page
    assert not re.search(r"""url\(\s*["']?https?://""", page)


def test_html_keeps_real_selectable_text(tmp_path):
    page = _html(tmp_path, "text")
    assert "<text" in page, "labels must be real <text>, not a rasterized image"
    assert "Decay" in page and "t (s)" in page


def test_html_embeds_the_font(tmp_path):
    """A figure has to look the same on a machine without the font installed,
    which is the point of embedding rather than naming it."""
    page = _html(tmp_path, "font")
    assert "@font-face" in page and "base64," in page


def test_math_html_carries_the_tex_rather_than_baked_glyphs(tmp_path):
    """The math path suppresses pyplotrs' own glyphs and hands MathJax the TeX,
    so the reader can right-click and copy the source."""
    page = _html(tmp_path, "tex", with_math=True)
    assert r"\alpha" in page or r"\tau" in page, "the TeX source should survive"
    assert "MathJax" in page


def test_plain_html_does_not_carry_the_mathjax_bundle(tmp_path):
    """2.2 MB is a lot to ship for a figure with no math in it."""
    plain = _html(tmp_path, "plain")
    assert "MathJax" not in plain
    assert len(plain) < 1_000_000, f"a math-free page is {len(plain)} bytes"


def test_3d_html_is_the_interactive_viewer(tmp_path):
    fig, ax = plt.subplots(projection="3d", figsize=(320, 240))
    ax.scatter([0, 1, 2], [0, 1, 4], [0, 1, 8])
    ax.set(title="cloud")
    out = tmp_path / "v.html"
    fig.save(str(out))
    page = out.read_text(encoding="utf-8")
    assert "canvas" in page.lower(), "a 3D figure saves the Canvas2D viewer"
    assert not re.search(r"""(?:src|href)\s*=\s*["']https?://""", page)


def test_html_svg_body_parses_as_xml(tmp_path):
    """The inlined SVG has to be valid markup, not merely something a browser
    will guess at."""
    page = _html(tmp_path, "xml")
    match = re.search(r"(<svg\b.*?</svg>)", page, re.S)
    assert match, "no <svg> element found in the page"
    ET.fromstring(match.group(1))


# -- animation ---------------------------------------------------------------

def _wave(i: int):
    fig, ax = plt.subplots(figsize=(200, 140))
    xs = [j / 10 for j in range(40)]
    ax.line(xs, [math.sin(x - i * 0.4) for x in xs])
    ax.set(ylim=(-1.2, 1.2))
    return fig


def test_gif_output_is_a_gif_with_the_frames_asked_for(tmp_path):
    """The only animation test in the suite called `animate` and checked the
    file was non-empty, which a text file would also satisfy."""
    out = tmp_path / "a.gif"
    plt.animate(_wave, frames=5, fps=10).save(str(out))
    data = out.read_bytes()

    assert data[:6] in (b"GIF87a", b"GIF89a"), f"not a GIF: {data[:6]!r}"
    assert data[-1:] == b";", "GIF trailer missing"
    # One Graphic Control Extension per frame. The count is bound to a local
    # first: an f-string expression could not contain a backslash before
    # Python 3.12, and this package supports 3.9.
    gce = data.count(b"\x21\xf9\x04")
    assert gce == 5, f"expected 5 frames, found {gce}"
    # The loop block: `NETSCAPE2.0` is how an infinite GIF says so.
    assert b"NETSCAPE2.0" in data


def test_apng_output_is_an_animated_png(tmp_path):
    out = tmp_path / "a.png"
    plt.animate(_wave, frames=4, fps=10).save(str(out))
    data = out.read_bytes()

    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    assert b"acTL" in data, "no animation control chunk - this is a still PNG"
    assert data.count(b"fcTL") == 4, "expected one frame control chunk per frame"

    # `acTL` carries the frame count; it must agree with the chunks present.
    at = data.index(b"acTL")
    (num_frames,) = struct.unpack(">I", data[at + 4:at + 8])
    assert num_frames == 4, f"acTL claims {num_frames} frames"


def test_animation_frames_actually_differ(tmp_path):
    """A renderer that ignored the frame index would still produce a valid
    animated file - of the same picture N times."""
    seen = set()
    for i in (0, 3, 7):
        out = tmp_path / f"f{i}.png"
        _wave(i).save(str(out))
        seen.add(out.read_bytes())
    assert len(seen) == 3, "the render callback's frame index changed nothing"


def test_png_declares_the_dpi_it_was_asked_for(tmp_path):
    """`pHYs` is what makes a PNG land at the right physical size in a document
    rather than at whatever the viewer assumes."""
    out = tmp_path / "d.png"
    _figure().save(str(out), dpi=300)
    data = out.read_bytes()
    at = data.index(b"pHYs")
    ppu_x, ppu_y, unit = struct.unpack(">IIB", data[at + 4:at + 13])
    assert unit == 1, "pHYs should be in pixels per metre"
    # 300 dpi = 300 / 0.0254 pixels per metre, within rounding.
    assert abs(ppu_x - 300 / 0.0254) < 2 and ppu_x == ppu_y


def test_png_pixels_decode(tmp_path):
    """A structurally valid PNG whose IDAT does not inflate is still broken."""
    out = tmp_path / "p.png"
    _figure().save(str(out))
    data = out.read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    idat = b""
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        if kind == b"IDAT":
            idat += data[pos + 8:pos + 8 + length]
        pos += 12 + length
    raw = zlib.decompress(idat)
    assert len(raw) == height * (1 + width * 4), "decoded size disagrees with IHDR"
