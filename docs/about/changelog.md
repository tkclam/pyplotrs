# Changelog

All notable changes to pyplotrs are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- 2D marks: `line`, `scatter`, `bar`, `hist`, `fill_between`, `errorbar`,
  `imshow` with `colorbar`.
- 3D plots (`scatter`, `plot`, `surface`) as an editable-vector projection layer,
  plus an interactive Canvas2D HTML viewer.
- Built-in themes (`default`, `nature`, `grayscale`, `presentation`) and
  user-derivable `Theme`.
- LaTeX `$...$` math (MathJax-grade engine) that stays selectable text.
- Text and callout-arrow annotations.
- `pyplotrs.gg` declarative grammar-of-graphics layer with faceting.
- Animation export to GIF and APNG.
- Output to PDF (editable/selectable/taggable text), SVG, PNG (with DPI) and
  self-contained HTML.
- Exact CC0 perceptually-uniform colormaps; custom `Colormap` support.
- Cross-machine font embedding in every saved format.

### Fixed

- Non-finite (`NaN`/`inf`) data no longer corrupts axis autoscaling; lines break
  into a gap at non-finite points and markers there are skipped, matching
  matplotlib.
- `Figure.save` matches the file extension case-insensitively (`.PNG`, `.PDF`, …).
