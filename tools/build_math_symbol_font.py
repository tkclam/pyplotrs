#!/usr/bin/env python3
"""Subset DejaVu Sans down to the math symbols pyplotrs falls back to.

A dev tool, not part of the package. Run from the repo root::

    .venv/bin/python tools/build_math_symbol_font.py

It writes ``assets/fonts/DejaVuSans-MathSymbols.ttf``, which the extension
embeds via ``include_bytes!``.

Why this font exists
--------------------

A ``$...$`` span is drawn from the body family wherever that family has the
glyphs, and from STIX Two Math otherwise. STIX is a *serif*, so every fallback
used to arrive as a Times-shaped mark in the middle of sans text — and the
fallbacks are not rare or evenly spread. Every symbol family is *split*: Arial
and Liberation Sans carry ``→ ← ↔`` but not ``⇒ ⇐ ↦``, ``∩`` but not ``∪``,
``≤ ≥ ≠ ≈`` but not ``≪ ≫ ∝ ∼``, ``±`` but not ``∓``. Glyph-by-glyph fallback
therefore cannot be family-consistent on its own: `$A \\cap B$` would come out
sans beside a serif `$A \\cup B$`.

DejaVu Sans closes that gap — it covers 108 of the 111 symbols the body family
lacks (the three it misses, ``⨿ ⨄ ⨆``, are big operators, which always come from
the math font anyway). It is also the font matplotlib's default `dejavusans`
mathtext set is built on, so the shapes are the familiar ones.

Why a subset, and why only symbols
----------------------------------

This face supplies *shapes*, never metrics. Layout is driven by the OpenType
MATH table, and DejaVu's is not usable for that: ten of its twenty-four
constants are unset (``SuperscriptShiftUp``, ``SubscriptShiftDown``, both
fraction shifts and all four limit constants are zero), it carries no italic
corrections and no cut-in kerns, and ``√`` has no vertical construction at all,
so it could not grow a radical. That is why matplotlib hardcodes a
``DejaVuSansFontConstants`` class rather than reading the table. pyplotrs reads
the table, so STIX keeps the job of positioning everything and of drawing what
has to stretch — big operators, radicals, fences — and DejaVu is asked only for
fixed-size marks.

So the subset keeps the math symbol blocks and nothing else: no letters, no
digits, no MATH table (dropped explicitly, so it cannot be mistaken for a
layout source). 742 KB becomes 95 KB.

Licensing
---------

DejaVu Sans is under the Bitstream Vera license, which permits modification and
redistribution provided the notices travel with the font and a modified font is
renamed to a name containing neither "Bitstream" nor "Vera". "DejaVu Sans"
contains neither, and no glyph outline is altered here — this is a subset, the
same operation every PDF writer performs on the way into a file. The license
text ships as ``assets/fonts/DejaVuSans-LICENSE.txt``.
"""
from __future__ import annotations

import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

#: Unicode blocks a math fallback can be asked for. Deliberately no Latin, no
#: Greek and no digits: those come from the body family, and if the body family
#: does not have them the math font's own alphabets are the right answer, not a
#: third sans.
RANGES = [
    (0x00AC, 0x00AC),  # ¬
    (0x00B0, 0x00B1),  # ° ±
    (0x00B7, 0x00B7),  # ·
    (0x00D7, 0x00D7),  # ×
    (0x00F7, 0x00F7),  # ÷
    (0x2000, 0x206F),  # General Punctuation (′ ″ … ‰ ⁄)
    (0x2100, 0x214F),  # Letterlike Symbols (ℏ ℓ ℜ ℑ ℵ ℘)
    (0x2190, 0x21FF),  # Arrows
    (0x2200, 0x22FF),  # Mathematical Operators
    (0x2300, 0x23FF),  # Miscellaneous Technical (⌈ ⌉ ⌊ ⌋)
    (0x25A0, 0x25FF),  # Geometric Shapes (□ △ ▽ ◁ ▷)
    (0x2660, 0x266F),  # Miscellaneous Symbols (♠ ♣ ♭ ♮ ♯)
    (0x27C0, 0x27EF),  # Miscellaneous Mathematical Symbols-A (⟨ ⟩)
    (0x27F0, 0x27FF),  # Supplemental Arrows-A (⟶ ⟵ ⟹)
    (0x2900, 0x297F),  # Supplemental Arrows-B
    (0x2A00, 0x2AFF),  # Supplemental Mathematical Operators (⪯ ⪰ ⨿)
]

#: Where the upstream font is looked for. It is a *source* dependency of this
#: tool, not of the package: the committed subset is what ships.
CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/local/share/fonts/DejaVuSans.ttf",
    os.path.expanduser("~/.fonts/DejaVuSans.ttf"),
    "/Library/Fonts/DejaVuSans.ttf",
]

OUT = os.path.join(
    os.path.dirname(__file__), "..", "assets", "fonts", "DejaVuSans-MathSymbols.ttf"
)


def find_source() -> str:
    for p in CANDIDATES:
        if os.path.isfile(p):
            return p
    sys.exit(
        "DejaVuSans.ttf not found. Install it (Debian/Ubuntu: `apt install "
        "fonts-dejavu-core`) or pass a path as the first argument.\n"
        "Looked in:\n  " + "\n  ".join(CANDIDATES)
    )


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else find_source()
    font = TTFont(src, fontNumber=0)

    present = set()
    for table in font["cmap"].tables:
        present |= set(table.cmap)
    wanted = sorted({c for lo, hi in RANGES for c in range(lo, hi + 1)} & present)

    opts = subset.Options()
    # This face draws shapes only. Dropping MATH makes that structural rather
    # than a matter of the caller remembering: nothing can read positioning
    # constants out of it by accident.
    opts.drop_tables += ["MATH"]
    opts.layout_features = []
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.glyph_names = False

    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(unicodes=wanted)
    subsetter.subset(font)
    font.save(OUT)

    out = os.path.normpath(OUT)
    print(f"source: {src} ({os.path.getsize(src) / 1024:.0f} KB)")
    print(f"wrote:  {out} ({os.path.getsize(out) / 1024:.0f} KB)")
    print(f"        {len(wanted)} codepoints, MATH table dropped")


if __name__ == "__main__":
    main()
