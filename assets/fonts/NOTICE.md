# Bundled fonts

pyplotrs embeds these fonts directly into the compiled extension (via Rust
`include_bytes!`) so that rendering always works, with no dependency on any
font being installed on the host system.

| File | Family | Role | License |
|---|---|---|---|
| `LiberationSans-Regular.ttf` | Liberation Sans | body / labels / ticks / legends — **fallback** sans-serif | SIL Open Font License 1.1 — see `LiberationSans-OFL.txt` |
| `LiberationSans-Bold.ttf` | Liberation Sans | bold body text (`weight="bold"`, `Theme.title_weight`) | SIL Open Font License 1.1 — see `LiberationSans-OFL.txt` |
| `LiberationSans-Italic.ttf` | Liberation Sans | italic body text (`style="italic"`) | SIL Open Font License 1.1 — see `LiberationSans-OFL.txt` |
| `LiberationSans-BoldItalic.ttf` | Liberation Sans | bold italic body text | SIL Open Font License 1.1 — see `LiberationSans-OFL.txt` |
| `FiraMath-Regular.otf` | Fira Math | `$...$` math: the sans math font — radicals, big operators, stretchy fences, and the MATH table that positions every atom | SIL Open Font License 1.1 — see `FiraMath-OFL.txt` |
| `DejaVuSans-MathSymbols.ttf` | DejaVu Sans (subset) | `$...$` math: sans shapes for symbols neither the body family nor Fira Math carries | Bitstream Vera license — see `DejaVuSans-LICENSE.txt` |
| `STIXTwoMath-Regular.ttf` | STIX Two Math | `$...$` math: the `stix` font set outright, and the last resort under `sans` — Script and Fraktur alphabets, double-struck digits | SIL Open Font License 1.1 — see `STIXTwoMath-OFL.txt` |

The Liberation, Fira Math and STIX fonts are licensed under the SIL Open Font
License, Version 1.1, which permits bundling and redistribution (including
embedding in documents) provided the license text accompanies the font software.
All three are bundled byte-for-byte as published upstream. Two of them declare a
Reserved Font Name — Liberation declares "Liberation", STIX Two Math declares
"TM Math"; Fira Math declares none — so the RFN clause is not engaged here, but
any future subsetting or modification of those two files would require renaming
them first. (The DejaVu Sans subset *is* modified, and the Bitstream Vera
license it travels under is handled separately below.) The license texts are
included alongside the fonts here and are shipped in the source distribution.

## Why three math fonts

A `$...$` span is drawn from the body family wherever that family has the
glyphs. What it cannot have is the parts that must *grow*: a radical sized to
its content, a `\left(...\right)` fence sized to what it wraps, a `\sum` enlarged
in display style. Those need the variant and assembly chains of an OpenType MATH
table, which no text font carries.

**Fira Math** is that font, and it is a sans, so those parts match the label
around them instead of arriving Times-shaped. It was chosen over the obvious
alternative — DejaVu Sans, which matplotlib's default mathtext set is built on —
because pyplotrs drives layout *from* the MATH table rather than from hardcoded
per-font constants: DejaVu leaves ten of its twenty-four constants unset and has
no vertical construction for `√` at all, so it can supply shapes but never
metrics. (matplotlib can use it precisely because it hardcodes a
`DejaVuSansFontConstants` class instead of reading the table.) Fira Math leaves
no constant unset, gives `√` sixteen designed variants plus an assembly, and
carries 244 italic corrections. Designed sizes matter: scaling one base glyph up
— the approach that needs no MATH table — thickens its strokes as it grows, so a
tall delimiter comes out heavier than the text it wraps.

Fira Math is not complete, though: no Script or Fraktur alphabet, no
double-struck digits, and 37 of the symbols in pyplotrs' command table are
missing. So the chain continues past it — to the DejaVu symbol subset, which has
33 of those 37, and then to **STIX Two Math** for the rest and for the alphabets
nothing else has. STIX also serves the whole span under
`set_mathtext_fontset("stix")`.

Positioning constants always come from whichever font is *primary* for the
active set, so a span is laid out to one font's metrics even when several supply
its marks.

## The math symbol subset (DejaVu Sans)

A `$...$` span is drawn from the body family wherever that family has the
glyphs, and only otherwise from the math font. STIX Two Math is a *serif*, so
every fallback used to arrive as a Times-shaped mark in the middle of sans text
— and the fallbacks are neither rare nor evenly spread. Coverage of the symbol
blocks is ragged in every text family: Arial and Liberation Sans carry `→ ← ↔`
but not `⇒ ⇐ ↦`, `∩` but not `∪`, `≤ ≥ ≠ ≈` but not `≪ ≫ ∝ ∼`, `±` but not `∓`.
Glyph-by-glyph fallback therefore cannot be family-consistent on its own: a sans
`$A \cap B$` would sit beside a serif `$A \cup B$`.

`DejaVuSans-MathSymbols.ttf` closes that gap in the same sans idiom. It covers
108 of the 111 symbols the body family lacks — the three it misses (`⨿ ⨄ ⨆`) are
big operators, which come from the math font regardless. DejaVu Sans is also the
face matplotlib's default `dejavusans` mathtext set is built on, so the shapes
are the familiar ones.

It supplies **shapes only**. Layout is driven by the OpenType MATH table, and
DejaVu's is not usable for that: ten of its twenty-four constants are unset,
it carries no italic corrections or cut-in kerns, and `√` has no vertical
construction at all — which is why matplotlib hardcodes a font-constants class
rather than reading the table. STIX keeps the job of positioning every atom and
of drawing everything that has to stretch. The subset drops the MATH table
outright, so nothing can read positioning out of it by accident.

The file is produced by `tools/build_math_symbol_font.py`, which keeps the math
symbol blocks and nothing else — no letters, no digits, no MATH table — taking
742 KB down to 95 KB. No glyph outline is altered; this is the same subsetting
every PDF writer performs on the way into a file.

The Bitstream Vera license permits modification and redistribution provided the
notices travel with the font and a modified font is renamed to a name containing
neither "Bitstream" nor "Vera". "DejaVu Sans" contains neither. DejaVu's own
changes to the Vera originals are in the public domain.

## Body font resolution (Arial / Helvetica)

For body text, pyplotrs prefers the host's **Arial**, then **Helvetica**, before
falling back to the bundled Liberation Sans (matplotlib's `font.sans-serif`
behavior; configurable via `pyplotrs.set_font_family([...])`). **Arial and
Helvetica are proprietary** typefaces (Monotype / Linotype) and are *not*
bundled or redistributed by pyplotrs — they are only ever used when already
present on the user's machine.

**Liberation Sans** is metrically compatible with Arial (identical glyph
advances), so figures laid out against the bundled fallback size and line-break
identically to ones rendered with the real Arial. It is the standard permissive
Arial substitute.

All four faces (Regular, Bold, Italic, Bold Italic, all version 2.1.5) are
bundled rather than only Regular. Emphasis is otherwise resolved from the host,
which works on a desktop but silently renders upright inside a minimal container
— precisely where figures are generated in bulk — and that would break the
guarantee that a saved figure looks the same everywhere.

### Saved figures view consistently across machines

Whichever font is chosen, it is **embedded into the saved figure**: PDF and SVG
carry a subset/`@font-face` copy of the exact glyphs, PNG bakes them into
pixels, and HTML inlines the font. So a figure saved on one machine looks
identical when opened on any other, independent of what fonts the viewer has
installed — the body-font choice only affects how that one rendering looks, not
its portability.

STIX Fonts™ is a trademark of the Institute of Electrical and Electronics
Engineers, Inc.; the font is used here under the OFL and the "STIX" name is not
used to identify modified versions.
