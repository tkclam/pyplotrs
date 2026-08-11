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
  now carry a legend swatch color (their colormap's midpoint, or the middle
  level).
- `figure.py` split from one 5,307-line file into seven layered modules
  (`_const`/`_util`/`_draw`/`_layout`/`axes`/`axes3d`/`polar`/`figure`),
  byte-identical output. The 3D projection layer moved into a dedicated
  `pyplotrs-3d` crate with batch (whole-mark, not per-vertex) projection.
- `contourf` band edges now come off the same round-number lattice `contour`
  draws its lines on, extended outward to bracket the data, the way matplotlib
  picks filled levels. Bands were equal fractions of the data range while lines
  were round numbers, so a `contour` drawn over a `contourf` of the same field
  ran through the middle of the bands instead of along their boundaries. Both
  also default to the same number of levels now (7, matplotlib's) rather than 9
  bands against 8 lines. The outermost bands reach past the data as a result -
  a field over -0.78..0.78 in steps of 0.15 fills -0.9..0.9 - so colorbar ranges
  on existing figures shift out to those round numbers.

### Fixed

- Non-finite (`NaN`/`inf`) data no longer corrupts axis autoscaling; lines break
  into a gap at non-finite points and markers there are skipped, matching
  matplotlib.
- `Figure.save` matches the file extension case-insensitively (`.PNG`, `.PDF`, …).
- Float RGB colors in 0-1 (matplotlib's convention, e.g. `(0.2, 0.4, 0.6)`) are
  scaled correctly instead of being truncated to black. Hex (`"#ff0000"`) and CSS
  color names (`"steelblue"`) are now accepted anywhere a color is.
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
- `+`/`x` markers with no explicit color raised `NameError`.
- `hexbin` was not reproducible between runs (iteration order of a `HashMap`
  leaking into drawn geometry).
- `bar(width=)`/`barh(height=)`/`boxplot(widths=)` no longer shrink to the
  stroke width instead of the intended data extent.
- `contour` lines showed a hairline break at every turn: marching squares was
  drawn as one stroked path per grid cell, so neighboring pieces met butt cap
  to butt cap and left a wedge of background at each joint. The kernel now
  stitches the pieces into whole lines (matched on grid-edge identity, so the
  join is exact), and each line is one path with round joins.
- `pie` slice labels lost their last glyph (`gamma` drawn as `gamm`) and left a
  third of the cell empty. The labels sat at a rim offset in data units while
  their width is a device length, so `pie` padded its limits by a fixed factor
  and hoped: too little for a long label, too much for a short one. The pie now
  keeps its limits at its own bounding box and is fitted in device space
  against measured labels, which are drawn outside the plot clip.
- `contour(levels=N)` sliced the data range into `N + 1` equal parts, putting
  the lines on values like 0.1426 and 0.2853. `N` is now a *hint*, as it is in
  matplotlib: the levels land on multiples of a nice step, and only levels
  strictly inside the data range are drawn (one on an extreme drew nothing but
  still consumed a color).
- `contourf` left a white line down the middle of its extreme band. The band
  edges were built as `lo + (hi - lo) * i / n`, which lands the last one an ulp
  below `hi`, so every pixel interpolating the field's own maximum tested as
  *above* the top edge and was left transparent. The edges now come off the
  level lattice, and the band kernel admits a hair past each end for the case
  where a caller's own `levels` sit exactly on the extrema.
- `contour` drew nothing at all on a field of small magnitude (spanning ~1e-6
  or less). Levels are rounded to the decimals their step needs to be written
  exactly, and the count of those decimals gave up at zero for any step under
  1e-6 - so every level rounded to 0.0, fell outside the data range, and was
  dropped.
- `axis("off")` - and so every `pie` - left a blank strip down the left of the
  cell and along its bottom. The layout still reserved the bands for the tick
  marks and tick labels the frame-off axes never draws, so the plot rect sat
  off-center by the width of labels nobody saw. Those two bands are now
  dropped when the frame is off, which both centers the mark and gives it the
  space back.
- `subplot_mosaic` grew a phantom panel from an indented layout string. A mosaic
  is written inside a function, so its triple-quoted string carries that
  indentation - the form the docstring itself shows - and each leading space was
  read as a cell. Every row shared them, so they formed one solid rectangle: a
  blank axes spanning every row, as wide as the code was indented, with the real
  panels squeezed into what was left. The string is dedented before it is read
  now, and a space marks an empty cell like `.` does.
- Ticks pinned with `set(xticks=/yticks=)` outside the view were still drawn -
  placed by the same map as the rest, they landed outside the plot rect as a
  stray label floating above or below the panel. Positions outside the limits
  are dropped now, and `get_xticks()`/`get_yticklabels()` report what is left.
- A tick sitting on an axis limit did not join the end of its spine, and neither
  did two spines meeting at a corner. Both are strokes with width, drawn as
  separate paths, so each stopped on the other's centerline: the tick's own
  half-width jutted past the flat end of the spine, and the outer quarter of the
  corner was left blank - a half-point step at the corner of the frame, at the
  default spine width. Spines now run half a stroke width past any end something
  abuts, covering what a miter join between the two would have. The new theme
  knob `spine_join` picks the rule: `"miter"` (default) closes only the ends
  that need it, `"square"` overhangs every end like a projecting cap, and
  `"butt"` restores the bare endpoints exactly.
