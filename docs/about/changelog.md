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
- **Bold and italic text.** `Axes.text` / `Axes.annotate` take `weight` and
  `style`; `Theme` gains `title_weight`, `suptitle_weight` and
  `axis_label_weight`. Each selects a real face of the body family and is
  embedded as its own subset, so emphasis stays selectable, editable text.
  `resolved_font_variants()` reports which face each selector resolved to.
  All four Liberation Sans faces are bundled, so emphasis works on a machine
  with no fonts installed.
- More 2D plot types: `step`, `stairs`, `stem`, `broken_barh`, `eventplot`,
  `hist2d`, `hexbin`, `pcolormesh`, `contour`, `contourf`.
- `hlines` / `vlines` (data-coordinate segments that autoscale, unlike the
  `axhline` / `axvline` guides) and `fill_betweenx`.
- `width_ratios` / `height_ratios` on `subplots` and `Figure.add_gridspec`
  for unequal panel sizes.
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
- Float RGB colours in 0-1 (matplotlib's convention, e.g. `(0.2, 0.4, 0.6)`) are
  scaled correctly instead of being truncated to black. Hex (`"#ff0000"`) and CSS
  colour names (`"steelblue"`) are now accepted anywhere a colour is.
- `barh(label=...)` followed by `legend()` no longer raises `KeyError`.
- `errorbar` on a log/symlog/logit axis draws its connecting line and markers;
  previously only the whiskers survived.
- `bar3d`, `voxels` and `contour3d` no longer raise `NameError`.
- Histogram bin separators and pie wedge edges follow the theme's plot
  background instead of being hardcoded white.
- Legend swatches are drawn at the theme's legend type size, matching the box
  measured around them (visible under `themes.presentation`).
- A degenerate figure size, or a raster too large to allocate, raises
  `ValueError` instead of unwinding out of Rust as a `PanicException`.
