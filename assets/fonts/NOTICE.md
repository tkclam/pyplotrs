# Bundled fonts

figurs embeds these fonts directly into the compiled extension (via Rust
`include_bytes!`) so that rendering is fully reproducible without relying on
any fonts installed on the host system.

| File | Family | Role | License |
|---|---|---|---|
| `Inter-Regular.ttf` | Inter | body / labels / ticks / legends | SIL Open Font License 1.1 — see `Inter-OFL.txt` |
| `STIXTwoMath-Regular.ttf` | STIX Two Math | `$...$` math spans (Greek, operators, radicals, Mathematical Alphanumeric Symbols) | SIL Open Font License 1.1 — see `STIXTwoMath-OFL.txt` |

Both are licensed under the SIL Open Font License, Version 1.1, which permits
bundling and redistribution (including embedding in documents) provided the
license text accompanies the font software. The license texts are included
alongside the fonts here and are shipped in the source distribution.

`Inter-Regular.ttf` is a static Regular instance (weight 400, optical size 14)
instantiated from the upstream Inter variable font.

STIX Fonts™ is a trademark of the Institute of Electrical and Electronics
Engineers, Inc.; the font is used here under the OFL and the "STIX" name is not
used to identify modified versions.
