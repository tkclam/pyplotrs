"""mathtext: LaTeX ``$...$`` typesetting for pyplotrs.

This module is a thin Python adapter. The actual typesetting lives in the Rust
``pyplotrs-math`` crate, a faithful (LaTeX/MathJax-grade) engine that lays out the
TeX ``$...$`` subset with Knuth's boxes-and-glue model driven by the math font's
**OpenType MATH table** (positioning constants, per-glyph italic corrections,
and the glyph variants/assembly used to grow radicals and ``\\left...\\right``
delimiters). It emits ordinary pyplotrs IR — real, editable glyph runs plus
filled/stroked vector paths for fraction bars, radicals, stretchy glyphs and
accents — so math output stays selectable text in PDF/SVG, like the rest of
pyplotrs.

Supported: super/subscripts (``^``/``_``, with TeX shift/italic-correction),
``{...}`` grouping, Greek and a broad operator/relation/arrow table (with TeX
inter-atom spacing and a real U+2212 minus), ``\\frac``/``\\binom``,
``\\sqrt`` / ``\\sqrt[n]`` (stretchy radical that *connects* to its rule),
auto-sized ``\\left...\\right`` fences, ``\\text``/``\\operatorname`` and
function names (upright), accents (``\\hat``, ``\\vec``, ``\\bar``, ...) and the
math alphabets (``\\mathbf``, ``\\mathbb``, ``\\mathcal``, ``\\mathfrak``,
``\\mathsf``, ``\\mathtt``, ...).

Public API (unchanged, so every call site routes through here unconditionally):
``measure(scene, s, size) -> (width, ascent, depth)`` and
``draw(scene, x, baseline, s, size, color)``. A plain string with no ``$`` is
shaped as a single body-font run.
"""

from __future__ import annotations


def measure(scene, s: str, size: float, font: str = "body") -> tuple[float, float, float]:
    """Return ``(width, ascent, depth)`` of ``s`` (math-aware), in points.

    ``font`` selects the *ambient* body face - ``"body"``, ``"body-bold"``,
    ``"body-italic"``, ``"body-bolditalic"``. It must match what ``draw``
    will use, since the layout engine sizes its bands from this measurement.
    """
    return scene.measure_math(s, size, font)


def draw(scene, x: float, baseline: float, s: str, size: float, color,
         font: str = "body") -> None:
    """Render ``s`` with its left edge at ``x`` and baseline at ``baseline``.

    ``font`` selects the *ambient* body face (see ``measure``): what the span's
    digits, upright roman and common operators are set in, and whose italic
    companion draws its variables and Greek - so a bold label's math comes out
    bold throughout. Only what a text face cannot draw is left to the math
    font; see ``pyplotrs.set_mathtext_fontset``.
    """
    scene.add_math(x, baseline, s, size, color, font)
