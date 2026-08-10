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
- A much larger curated colormap/palette registry (`pyplotrs.colormaps`,
  `pyplotrs.palettes`) sourced from matplotlib, colorcet, cmocean and seaborn
  (see `THIRD_PARTY_COLORMAPS.md` for attribution), and a `pyplotrs.color`
  module for sRGB/XYZ/Lab/Oklab/Oklch/CAM16-UCS conversion, color-vision-
  deficiency simulation, and colormap distinguishability/uniformity scoring.
  Custom `Colormap(stops=...)` now resamples in Oklab by default, so
  hand-built gradients are perceptually smooth rather than banding. All table
  data and color-space math run in Rust (`pyplotrs-color`).
- Restored plot types: `quiver`, `streamplot` (RK4-integrated), `stackplot`,
  `matshow`, `spy`, `pcolor`.
- `Axes.fill(x, y)`, and `loglog` / `semilogx` / `semilogy` convenience wrappers
  over `line`.
- `save(path, transparent=True)` drops the white page fill from `.png` output.
- A full getter layer: `get_xlim` / `get_ylim` / `get_title` / `get_xlabel` /
  `get_xscale` / `get_aspect` / `get_xticks` / `get_xticklabels` /
  `get_legend_handles_labels`, plus 3D and polar equivalents. Every one reports
  the *effective* value (autoscaling and `sharex`/`sharey` included).
- `set(xmargin=/ymargin=/margin=)`, `xinverted`/`yinverted`, `xminor`/`yminor`
  on linear axes, `tick_direction`/`tick_length`, and `xlim="auto"` to clear a
  pinned limit.
- `text`/`annotate` `rotation=`, applied as a group transform so rotated text
  stays selectable in PDF/SVG.
- `legend(ncol=, title=, frameon=, fontsize=)` and
  `colorbar(orientation=, shrink=, ticks=, format=)`.

### Changed

- **One name per concept.** A stroke width is `linewidth` on every method that
  draws one; `width` now only ever means an extent in data units (a bar's
  thickness, a rectangle's span). `line`, `errorbar`, `step`, `stairs`,
  `Axes3D.plot`/`plot_wireframe`/`contour3d`/`quiver3d` and `PolarAxes.plot`
  took `width` for a stroke and now take `linewidth`; `contour` took
  `linewidths`.
- **One unit per quantity.** Marker size is a **diameter in points**, spelled
  `markersize`, on `line`, `errorbar` and now `scatter` too - previously
  `scatter(size=)` was an *area* in pt². `size` is still accepted and still
  means area, so ported matplotlib code keeps drawing the right size.
- **`zorder` on every mark**, for the case where something has to sit above a
  mark added after it. Insertion order remains the primary model - it is the one
  you can read off the code - and the sort is stable, so a figure that never
  sets `zorder` draws exactly as before.
- **`alpha` on every mark** (`line`, `scatter`, `bar`, `barh`, `hist`,
  `errorbar`, `step`, `stairs`, `stem`, `hlines`, `vlines`), not just the three
  that had it.
- Figure legends now include 3D and polar panels, which were silently skipped.
- `legend(loc="best")` now lives up to its name: it scores each corner by how
  much data the box would cover and takes the clearest. It was previously a
  plain alias for `upper right`.
- **`alpha` and `label` on every 3D mark** (`surface`, `bar3d`,
  `plot_wireframe`, `contour3d`, `plot_trisurf`, `quiver3d`, `voxels`), not
  just `scatter`/`plot`. Colormapped kinds (`surface`, `trisurf`, `contour3d`)
  now carry a legend swatch colour (their colormap's midpoint, or the middle
  level).
- `figure.py` split from one 5,307-line file into seven layered modules
  (`_const`/`_util`/`_draw`/`_layout`/`axes`/`axes3d`/`polar`/`figure`),
  byte-identical output. The 3D projection layer moved into a dedicated
  `pyplotrs-3d` crate with batch (whole-mark, not per-vertex) projection.

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
- The polar outer spine and a colormapped scatter's legend swatch follow the
  theme instead of hardcoded constants.
- `Axes3D.plot` accepted `alpha` and silently dropped it.
- `ax.surface(..., label=...)` / `ax.plot_trisurf(..., label=...)` followed by
  `legend()` raised `KeyError('color')`.
- `aspect="equal"` computed its scale from signed spans, so a descending limit
  mirrored the other axis.
- `+`/`x` markers with no explicit colour raised `NameError`.
- `hexbin` was not reproducible between runs (iteration order of a `HashMap`
  leaking into drawn geometry).
- `bar(width=)`/`barh(height=)`/`boxplot(widths=)` no longer shrink to the
  stroke width instead of the intended data extent.
