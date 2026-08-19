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

import warnings


class MathTextWarning(UserWarning):
    """A ``$...$`` string used a TeX command the engine does not implement.

    The command is still typeset - as its own letters - so nothing errors and
    nothing looks broken: ``$\\sfrac{1}{2}$`` comes out reading "sfrac12", and
    ``$a \\over b$`` reads "aoverb". A reader takes those for content. This
    warning is the only thing standing between a mistyped macro and a wrong
    quantity in a published axis label, so it is a warning rather than a debug
    log - and a distinct class, so it can be turned into an error with
    ``warnings.simplefilter("error", pp.mathtext.MathTextWarning)`` or silenced
    on its own.
    """


#: Macros already reported, so a label measured on every layout pass warns
#: once rather than once per pass. Python's own duplicate filter keys on the
#: warning's source line, which is the same line for every macro.
_WARNED: set[str] = set()


def _warn_unknown(scene, s: str, size: float, font: str) -> None:
    """Warn once per unimplemented command seen in ``s``."""
    if "$" not in s or "\\" not in s:
        return
    for name in scene.math_unknown_commands(s, size, font):
        if name in _WARNED:
            continue
        _WARNED.add(name)
        warnings.warn(
            f"unknown TeX command \\{name} in {s!r}: pyplotrs does not "
            f"implement it, so it is typeset as the literal letters "
            f"{name!r}. Check the label.",
            MathTextWarning,
            stacklevel=4,
        )


def _warn_missing_glyphs(scene, s: str, font: str) -> None:
    """Warn once per character no available face can draw.

    Such a character is drawn as an empty `.notdef` box. Nothing else reports
    it: the figure renders, the layout is sized from the box, and in the PDF
    every missing character collapses onto one `ToUnicode` entry so copying the
    label back out loses them. A degree-Celsius sign or a pair of angle
    brackets in a physics label is exactly the case.
    """
    if not isinstance(s, str) or s.isascii():
        return
    for ch in scene.missing_glyphs(s, font):
        key = f"glyph:{ch}"
        if key in _WARNED:
            continue
        _WARNED.add(key)
        warnings.warn(
            f"no available font can draw {ch!r} (U+{ord(ch):04X}), used in "
            f"{s!r}; it is drawn as an empty box. Install a font covering it, "
            f"or choose one with pyplotrs.set_font_family().",
            MathTextWarning,
            stacklevel=4,
        )


def measure(scene, s: str, size: float, font: str = "body") -> tuple[float, float, float]:
    """Return ``(width, ascent, depth)`` of ``s`` (math-aware), in points.

    ``font`` selects the *ambient* body face - ``"body"``, ``"body-bold"``,
    ``"body-italic"``, ``"body-bolditalic"``. It must match what ``draw``
    will use, since the layout engine sizes its bands from this measurement.

    Every label is measured before it is drawn, which makes this the one place
    every ``$...$`` string in a figure passes through - so it is where an
    unimplemented command gets reported.
    """
    _warn_unknown(scene, s, size, font)
    _warn_missing_glyphs(scene, s, font)
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
