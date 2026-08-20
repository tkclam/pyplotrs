"""Structural assertions on the PDF backend - the project's headline claim.

pyplotrs exists to emit PDFs whose text stays *real text*: embedded, subset,
CID-keyed TrueType with a ToUnicode map, never Type 3 and never converted to
outlines. matplotlib's default PDF writer emits Type 3 fonts, which IEEE, ACM
and several publisher preflight checkers reject outright - so this is the
difference that justifies the library, and until now it was only ever verified
by opening a file in Illustrator by hand.

The checks read the raw PDF bytes. Font descriptors and the cross-reference
objects are not inside the compressed content streams, so no PDF parser (and no
test dependency) is needed.
"""

from __future__ import annotations

import pyplotrs as pp
import pytest


@pytest.fixture
def pdf_bytes(tmp_path):
    """Render a figure exercising body text *and* math, return its PDF bytes."""

    def render(**save_kwargs) -> bytes:
        fig, ax = pp.subplots(figsize=(320, 240))
        ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="series one")
        ax.set(title=r"Energy $E = mc^2$", xlabel="time (s)", ylabel="amplitude")
        ax.legend()
        out = tmp_path / "structure.pdf"
        fig.save(str(out), **save_kwargs)
        return out.read_bytes()

    return render


def test_pdf_is_wellformed(pdf_bytes):
    data = pdf_bytes()
    assert data.startswith(b"%PDF-"), "missing PDF header"
    assert data.rstrip().endswith(b"%%EOF"), "missing EOF marker"


def test_pdf_never_uses_type3_fonts(pdf_bytes):
    """The single most important assertion in the suite.

    Type 3 fonts are glyph-procedure fonts. They are what matplotlib emits by
    default, they are rejected by journal preflight, and they are the failure
    mode this library was built to avoid. If this ever fires, the core promise
    is broken.
    """
    data = pdf_bytes()
    assert b"/Type3" not in data, "PDF contains a Type 3 font"
    assert b"/CharProcs" not in data, "PDF contains Type 3 glyph procedures"


def test_pdf_embeds_subset_cid_truetype(pdf_bytes):
    data = pdf_bytes()
    assert b"CIDFontType2" in data, "text is not CID-keyed TrueType"
    assert b"/FontFile2" in data, "the font is not embedded"
    assert b"/Identity-H" in data, "expected Identity-H encoding"


def test_pdf_text_is_extractable(pdf_bytes):
    """A ToUnicode CMap is what makes the text copyable and screen-readable."""
    data = pdf_bytes()
    assert b"/ToUnicode" in data, "no ToUnicode map: text would not be extractable"


def test_pdf_subsets_rather_than_embedding_whole_fonts(pdf_bytes):
    """Subset fonts carry a six-letter tag prefix (PDF 9.6.4), e.g. ``ABCDEF+ArialMT``.

    Without subsetting a figure would carry the entire ~340 KB face.
    """
    import re

    data = pdf_bytes()
    assert re.search(rb"/BaseFont\s*/[A-Z]{6}\+", data), (
        "no subset-tagged BaseFont found; the full font may be embedded"
    )


def test_math_embeds_the_math_font_as_real_text(tmp_path):
    """A glyph only a math font can supply pulls one in as a further embedded
    face — still subset, still CID-keyed, still real text, never outlines.

    Fira Math is OpenType/**CFF**, so it embeds as ``CIDFontType0`` with a
    ``/FontFile3`` beside the body family's ``CIDFontType2``/``/FontFile2``.
    That mixture is the thing worth pinning: a CFF math font must not push the
    writer onto a Type 3 or outline-conversion path.
    """
    fig, ax = pp.subplots(figsize=(320, 240))
    ax.line([0, 1, 2], [0, 1, 4])
    ax.set(title=r"Total $\sqrt{\sum_i x_i}$")
    out = tmp_path / "math.pdf"
    fig.save(str(out))
    data = out.read_bytes()
    assert b"FiraMath" in data, "the sans math font was not embedded"
    assert b"/Type3" not in data and b"/CharProcs" not in data
    assert b"CIDFontType0" in data, "the CFF math font is not CID-keyed"
    assert b"/FontFile3" in data, "the CFF math font is not embedded"
    assert b"/FontFile2" in data, "the body font is not embedded"


def test_tagged_pdf_adds_structure(pdf_bytes):
    """``save(..., tagged=True)`` should produce accessibility structure."""
    plain = pdf_bytes()
    tagged = pdf_bytes(tagged=True, title="A figure", alt="A line rising to nine")
    assert b"/StructTreeRoot" in tagged, "tagged PDF lacks a structure tree"
    assert b"/StructTreeRoot" not in plain, "untagged PDF should not carry structure"
    assert len(tagged) > len(plain)


def test_markers_are_emitted_once_as_a_form_xobject(tmp_path):
    """Scatter marks are instanced: one glyph definition, N placements.

    This is the invariant that keeps a large scatter export small; losing it
    would silently multiply file size by the point count.
    """
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.scatter(list(range(500)), list(range(500)))
    out = tmp_path / "markers.pdf"
    fig.save(str(out))
    data = out.read_bytes()
    assert data.count(b"/Subtype /Form") <= 2, "marker outline was not deduplicated"
    assert out.stat().st_size < 200_000, (
        f"500-point scatter produced {out.stat().st_size} bytes; instancing may be broken"
    )


def test_svg_embeds_the_font_and_keeps_text(tmp_path):
    """The SVG backend's parallel promise: real ``<text>``, self-contained font."""
    fig, ax = pp.subplots(figsize=(240, 180))
    ax.line([0, 1], [0, 1])
    ax.set(title="Selectable")
    out = tmp_path / "t.svg"
    fig.save(str(out))
    svg = out.read_text(encoding="utf-8")
    assert "<text" in svg, "no text elements: labels may have been outlined"
    assert "Selectable" in svg, "title text is not present as characters"
    assert "@font-face" in svg, "font is not embedded, output is not portable"
