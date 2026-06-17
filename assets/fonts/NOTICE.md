# Bundled fonts

pyplotrs embeds these fonts directly into the compiled extension (via Rust
`include_bytes!`) so that rendering always works, with no dependency on any
font being installed on the host system.

| File | Family | Role | License |
|---|---|---|---|
| `LiberationSans-Regular.ttf` | Liberation Sans | body / labels / ticks / legends — **fallback** sans-serif | SIL Open Font License 1.1 — see `LiberationSans-OFL.txt` |
| `STIXTwoMath-Regular.ttf` | STIX Two Math | `$...$` math spans (Greek, operators, radicals, Mathematical Alphanumeric Symbols) | SIL Open Font License 1.1 — see `STIXTwoMath-OFL.txt` |

Both are licensed under the SIL Open Font License, Version 1.1, which permits
bundling and redistribution (including embedding in documents) provided the
license text accompanies the font software. The license texts are included
alongside the fonts here and are shipped in the source distribution.

## Body font resolution (Arial / Helvetica)

For body text, pyplotrs prefers the host's **Arial**, then **Helvetica**, before
falling back to the bundled Liberation Sans (matplotlib's `font.sans-serif`
behaviour; configurable via `pyplotrs.set_font_family([...])`). **Arial and
Helvetica are proprietary** typefaces (Monotype / Linotype) and are *not*
bundled or redistributed by pyplotrs — they are only ever used when already
present on the user's machine.

**Liberation Sans** is metrically compatible with Arial (identical glyph
advances), so figures laid out against the bundled fallback size and line-break
identically to ones rendered with the real Arial. It is the standard permissive
Arial substitute.

### Saved figures view consistently across machines

Whichever font is chosen, it is **embedded into the saved figure**: PDF and SVG
carry a subset/`@font-face` copy of the exact glyphs, PNG bakes them into
pixels, and HTML inlines the font. So a figure saved on one machine looks
identical when opened on any other, independent of what fonts the viewer has
installed — the body-font choice only affects how that one rendering looks, not
its portability.

STIX Fonts™ is a trademark of the Institute of Electrical and Electronics
Engineers, Inc.; the font is used here under the OFL and the "STIX" name is not
used to identify modified versions. "Liberation" is a Reserved Font Name under
the OFL; the bundled file is the unmodified upstream font.
