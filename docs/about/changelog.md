# Changelog

All notable changes to pyplotrs are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project follows
[Semantic Versioning](https://semver.org/).

!!! note "What 0.x means here"
    Below 1.0 the API may change in a minor release. Breaking changes are
    listed under **Changed** with the replacement spelled out, and there are no
    backports — a fix ships in the next version.

## Unreleased

### Fixed

- **`imshow` filters each axis on its own terms.** A tall or wide image is
  magnified along one axis and reduced along the other, and the two want
  opposite filters — but a backend offers only one for the whole image
  (tiny-skia's `FilterQuality`, SVG's `image-rendering`, PDF's `/Interpolate`),
  so whichever it picked was wrong somewhere. `imshow` of a 1000x4 array showed
  it from both sides: in `.png` every output pixel stayed pure, so four rows in
  five never reached the canvas and an even field came out as a moire pattern;
  in `.svg` the four columns smeared into a gradient, which is the same defect
  matplotlib has (it picks `nearest` only when *both* axes are magnified, so
  one long axis drags the smoothing filter onto the short one). Images are now
  resampled onto the grid they will actually occupy before any backend sees
  them, with a separable box filter that is per-axis by construction: a reduced
  axis is area-averaged, a magnified one keeps hard block edges with a single
  pixel of antialiasing. `.png`, `.svg`, `.pdf` and `.html` now agree.
- Magnified image blocks are evenly sized. Nearest-neighbor rounds each block
  boundary to a whole pixel, so 100 equal rows across 215 pixels came out as
  runs of 1, 2 and 3; each boundary now lands at its exact fractional position.

## 0.1.0 — 2026-08-11

The first public release. Everything below is what the package *is*, rather
than what changed — there is no previous version to compare against.

### Figures and output

- **PDF with real text.** Fonts are embedded and subset, never converted to
  outlines, so a saved figure opens in Illustrator or Inkscape with every label
  selectable, re-typeable and restylable. `pdftotext` extracts it, and
  `save(..., tagged=True)` writes tagged, accessible PDF with a document title,
  language and alt text.
- **Four formats from one call**, chosen by extension: `.pdf`, `.svg`, `.png`
  (at any `dpi`, with `transparent=True` and physical-size metadata), and
  `.html` — a single self-contained page that fetches nothing when opened.
- **The chosen font travels with the file** in every format, so a figure looks
  the same on a machine that does not have it installed.
- **No global state.** Every figure is an explicit object: no current figure,
  no `rcParams`, no style stack. Two threads building two figures share
  nothing, and the GIL is released for both rendering and the compute kernels.

### Plotting

- **2D marks** — `line`, `scatter`, `bar`, `barh`, `hist`, `boxplot`,
  `violinplot`, `pie`, `step`, `stairs`, `stem`, `broken_barh`, `eventplot`,
  `errorbar`, `fill_between`, `fill_betweenx`, `fill`, `stackplot`,
  `loglog`/`semilogx`/`semilogy`, and the field types `imshow`, `matshow`,
  `spy`, `pcolormesh`, `pcolor`, `hist2d`, `hexbin`, `contour`, `contourf`,
  `quiver`, `streamplot`.
- **Guides and shapes** — `axhline`/`axvline`, `axhspan`/`axvspan`, `axline`,
  `hlines`/`vlines`, `rectangle`, `circle`, `ellipse`, `polygon`, `arrow`.
- **3D** — `scatter`, `plot`, `surface`, `bar3d`, `plot_wireframe`, `contour3d`,
  `plot_trisurf`, `quiver3d`, `voxels`, projected to editable 2D vectors rather
  than a rasterized inset, with an interactive Canvas2D viewer in HTML output.
- **Polar** — `plot` and `scatter` on a configurable dial.
- **Animation** — `animate(render, frames)` to GIF or APNG.

### Axes, layout and style

- Linear, log, symlog, logit, date and categorical scales; 8 tick formatters;
  4 color normalizations.
- Grids with width/height ratios, `subplot_mosaic`, `GridSpec`, twin axes,
  insets, secondary axes — all solved in **one layout pass** against measured
  text, so nothing overlaps and there is no draw-measure-redraw step.
- Four themes (`default`, `nature`, `grayscale`, `presentation`) and
  `Theme.with_(...)` to derive your own.
- **127 exact colormaps and 25 categorical palettes**, compiled in, plus
  sRGB/XYZ/Lab/Oklab/Oklch/CAM16-UCS conversion, color-vision-deficiency
  simulation, and colormap distinguishability and uniformity scoring — so the
  defaults can be checked rather than asserted.
- A full getter layer (`get_xlim`, `get_xticklabels`, `get_legend_handles_labels`,
  …) reporting the **effective** value, with autoscaling and `sharex`/`sharey`
  resolved.

### Text

- **`$...$` LaTeX math without a LaTeX install**, typeset from the math font's
  OpenType MATH table and left as real selectable text in the output.
- Bold and italic, each embedded as its own subset;
  `resolved_font_variants()` reports what every face resolved to on this host.
- Rotated text stays selectable text, applied as a group transform rather than
  converted to paths.

### Input

- Any iterable of numbers: lists, tuples, generators, `array("d")`, NumPy
  arrays of any numeric dtype, pandas or polars columns. Buffer-backed input
  takes a memcpy path — a million-point `float64` array reaches a mark in
  about 6 ms. **NumPy is not a dependency**; there are no required runtime
  dependencies at all.
- Strings give a categorical axis; `datetime`/`datetime64` gives a date axis.
- Masked arrays become gaps, and `NaN`/`inf` break a line rather than
  corrupting the axis limits.

### Known limitations

- No pyplot state machine, interactive backends, `plt.show()`, widgets or event
  handling. pyplotrs makes files, not windows.
- No artist tree: a mark is recorded when you call it and rendered at `save`,
  so there are no `Line2D` objects to fetch and mutate afterwards.
- `tricontour`, `tripcolor`, `barbs`, `bar_label`, `clabel` and `ecdf` are not
  implemented yet.
- Rasterizing a polyline whose consecutive points are far apart in x is slow —
  cost tracks the line's length in device pixels, not its point count. See
  [performance](../guide/performance.md).
