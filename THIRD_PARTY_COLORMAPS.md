# Third-party colormap & palette data

pyplotrs embeds a curated set of colormap/palette tables directly into the
compiled extension (`crates/pyplotrs-color`, via Rust `include_bytes!`), so
using a built-in colormap by name has no runtime dependency on the packages
that originated its data. The tables were pulled once by
`tools/extract_colormaps.py` (a dev-only tool, not shipped) and are committed
as ordinary source (`crates/pyplotrs-color/data/continuous.bin` +
`crates/pyplotrs-color/src/data/*_gen.rs`); see
`tools/colormap_manifest.json` for the exact name -> source mapping.

| Source | License | What's included |
|---|---|---|
| [matplotlib](https://matplotlib.org/) | matplotlib's own license (BSD-compatible); the five perceptually-uniform maps (`viridis`/`plasma`/`inferno`/`magma`/`cividis`) are CC0 | ~80 continuous colormaps (unprefixed, upstream names/casing) and the qualitative sets `tab10`/`tab20`/`tab20b`/`tab20c`/`Set1`-`Set3`/`Pastel1`-`Pastel2`/`Dark2`/`Accent`/`Paired`/`okabe_ito` |
| [colorcet](https://colorcet.holoviz.org/) (Peter Kovesi et al.) | CC-BY 4.0 | ~26 continuous colormaps and 6 `glasbey` categorical sets, all prefixed `cet_` |
| [cmocean](https://matplotlib.org/cmocean/) (Kristen Thyng et al.) | MIT | ~22 oceanography-oriented continuous colormaps, prefixed `cmo_` |
| [seaborn](https://seaborn.pydata.org/) | BSD-3-Clause | 6 named qualitative palettes (`deep`/`muted`/`bright`/`pastel`/`dark`/`colorblind`), prefixed `sns_` |

**CC-BY 4.0 attribution** (colorcet): the `cet_*` colormaps are derived from
Peter Kovesi, "Good Colour Maps: How to Design Them,"
[arXiv:1509.03700](https://arxiv.org/abs/1509.03700), used under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
No changes were made beyond resampling to a 256-entry RGB table.

All other bundled sources use permissive (BSD/MIT/CC0-family) licenses that do
not require attribution beyond this notice, which is included here as a matter
of good practice and to document provenance for anyone auditing the wheel's
contents.
