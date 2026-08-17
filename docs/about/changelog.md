# Changelog

All notable changes to pyplotrs are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project follows
[Semantic Versioning](https://semver.org/).

!!! note "What 0.x means here"
    Below 1.0 the API may change in a minor release. Breaking changes are
    listed under **Changed** with the replacement spelled out, and there are no
    backports — a fix ships in the next version.

## Unreleased

### Added

- **Rich text: style a *substring* of any label.** `weight=`/`style=` applied to
  a whole label, so emphasis was all-or-nothing — a whole title could be bold,
  one word in it could not. `pp.rich(...)` and its shorthands `pp.bold`,
  `pp.italic`, `pp.underline`, `pp.strike` and `pp.mark` build a span tree that
  every label slot accepts: titles, axis labels, tick labels, `label=`, `text`
  and `annotate`. Styles are `weight`, `style`, `color`, `bgcolor`,
  `underline`, `strike`, and `scale`/`size`; spans nest, and an inner style
  wins, so a run can opt back out of what encloses it. Colors resolve against
  the figure's theme, `"C0"` palette indices included. `pp.plain(label)` gives
  the text back unstyled, which is what the tagged-PDF description now uses.
  Underline and strikeout rules come from the face's own `post`/`OS/2` metrics
  rather than a fraction of the type size, so they sit where the type designer
  put them and move correctly between faces.
- **Rich text carries into math.** A span's weight and slant become the
  *ambient* face of any `$...$` it contains, so `pp.bold(r"$E = mc^2$")` is bold
  throughout — variables included — rather than half-bold.
- **`\textcolor{...}{...}` and `\colorbox{...}{...}` inside math**, for tinting
  or highlighting one term of an expression rather than the whole label. Both
  take any color spelling the rest of the library takes (`"C1"`, CSS names,
  hex), resolved against the theme before the typesetter sees them. Nesting
  resolves innermost-first, and a color that does not parse costs the color and
  not the term it wraps. Fraction bars, radical rules and accents take the color
  along with the glyphs, and the text stays real, selectable text in PDF/SVG.
- **`set_mathtext_fontset()` / `get_mathtext_fontset()`** — which family `$...$`
  math is drawn in, pyplotrs' analog of matplotlib's
  `rcParams["mathtext.fontset"]`. `"sans"` is the new default (see **Changed**);
  `"stix"` sets every atom in STIX Two Math, for figures whose body text is a
  serif too.

### Changed

- **`$...$` math is now set in your own body family**, not split between it and
  a serif math font. Variables and Greek come from the body italic, digits and
  operators from the face the label is in, and STIX Two Math draws only what a
  text face cannot: big operators, radicals, stretchy fences, the
  blackboard/script/Fraktur alphabets, and any symbol the family is missing
  (checked glyph by glyph). Before this, one expression could hold two
  typefaces — `$E = mc^2$` set a serif `E m c` beside a sans `=` and `2` —
  because the rule that kept a `$10^{-3}$` tick matching its neighbors covered
  only the upright, text-like atoms.
  matplotlib's default `dejavusans` set draws the same line. Three consequences:
  a **bold** label's math is now bold throughout rather than half-bold; math
  follows `set_font_family`, so Helvetica body text gets Helvetica Italic
  variables; and most figures no longer embed the math font at all, which is
  around 2 MB off an SVG. `set_mathtext_fontset("stix")` restores uniformly
  serif math. Every figure with math renders differently — the gallery,
  tutorial and notebook images are regenerated.

    A **95 KB subset of DejaVu Sans** is bundled alongside, supplying sans
    shapes for the symbols a text family does not carry. Coverage of the symbol
    blocks is ragged in every text family — Arial and Liberation Sans have
    `→ ← ↔` but not `⇒ ⇐ ↦`, `∩` but not `∪`, `≤ ≥ ≠ ≈` but not `≪ ≫ ∝ ∼`, `±`
    but not `∓` — so falling straight from the body face to a serif math font
    split symbol families down the middle: a sans `$A \cap B$` beside a serif
    `$A \cup B$`. It closes 108 of the 111 gaps; the three it misses are big
    operators, which come from the math font regardless. It supplies shapes
    only — its MATH table is dropped at subset time, and DejaVu's would be
    unusable anyway, with ten of twenty-four constants unset and no vertical
    construction for `√`. `tools/build_math_symbol_font.py` regenerates it.

    **Fira Math** (SIL OFL, 175 KB) is bundled as the sans math font, so `√`,
    `∑`, `∫` and auto-sized `\left...\right` fences are monoline marks matching
    the label rather than high-contrast Times shapes. These are the parts that
    have to *grow* with their content, which needs the variant and assembly
    chains of an OpenType MATH table — no text font has one. DejaVu Sans, the
    obvious candidate, cannot serve: it leaves ten of twenty-four MATH constants
    unset and has no vertical construction for `√` at all. (matplotlib uses it
    only because it hardcodes a `DejaVuSansFontConstants` class instead of
    reading the table; pyplotrs reads the table.) Nor would scaling one base
    glyph up do — that thickens the strokes as the glyph grows, so a tall
    delimiter comes out heavier than the text it wraps. Fira Math leaves no
    constant unset, gives `√` sixteen designed variants plus an assembly, and
    carries 244 italic corrections. It is OpenType/CFF, so it embeds in PDF as a
    subset `CIDFontType0`/`FontFile3` beside the body family's `CIDFontType2` —
    still real, selectable text, never outlines.

    STIX Two Math stays bundled: it draws a whole span under
    `set_mathtext_fontset("stix")`, and under `sans` it is the last resort for
    the Script and Fraktur alphabets and double-struck digits, which no sans
    math font here carries.

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
- **Marks now sit flush against the spine they rest on.** Autoscaling padded
  every axis by 5% unconditionally, so a `stackplot` floated above the x spine
  with a strip of background beneath it, and the total looked like it started
  somewhere other than where it did. Each mark now records the values it *rests
  on* — a stack's floor, a bar's base, an image's extent — and the margin is
  clamped there. The margin is unchanged everywhere a mark merely *stops*:
  `fill_between(x, y, 0)` still gets its 5%, because 0 is just another curve.
- `bar(bottom=...)` and `barh(left=...)` sit on the base they were given. The
  baseline was forced to zero, which squeezed `bar(bottom=10)` into the top
  third of an otherwise empty panel; `barh` had no baseline handling at all, so
  its bars floated off their value axis in every case.
- **`xmargin`/`ymargin` now work on every scale.** Each scale padded itself with
  a hardcoded 5%, so the margin arguments were silently ignored on log, symlog,
  logit, date and categorical axes. The margin is now applied once, in
  transformed space — on a log axis it is 5% of the *decade* span, so it means
  the same thing at both ends — and mark-aware bounds such as an image extent
  survive the switch to a non-linear scale.
- `axhline`, `axvline`, `axhspan` and `axvspan` contribute the coordinate they
  are positioned at, so a guide can no longer land outside the frame and go
  missing. They still contribute nothing to the direction they span, which is an
  axes fraction rather than data. `axline` is unchanged: it is infinite.
- `boxplot(showfliers=False)` no longer scales the value axis to the outliers it
  is hiding, which had squeezed the visible box into an eighth of the panel.
- A constant series expands relative to its own value rather than by a fixed
  half-unit, so a flat line at y=1000 gets a readable scale instead of ticks
  reading 999.5 / 1000 / 1000.5.
- A vertex with a non-finite coordinate no longer moves the other axis: `(100,
  NaN)` is not drawn, but an independent scan of x used to stretch the axis to
  reach it.
- A margin of -0.5 or below is rejected instead of silently producing a
  zero-width or inverted axis, and a span near the float ceiling no longer pads
  to infinity.
- `sharex`/`sharey` preserve an inverted panel's direction. The union was taken
  with a plain min/max over the endpoints, so a panel set to `yinverted=True`
  inside a shared row came back ascending.

### Changed

- A `boxplot`'s category axis is sized from the category slot rather than from
  `widths`, so narrowing the boxes thins the glyphs instead of zooming the axis
  in on them — every width used to fill about 91% of the axis.
- `violinplot` evaluates its KDE over the data range rather than 15% past each
  end, so the axis is bounded by the sample instead of overhanging it by 21.5%.
- `contour` pins the view to its grid, as `contourf` already did.

### Documentation

- **Six runnable notebooks** under `docs/notebooks/`, rendered into the site and
  on GitHub from their committed output: a
  [quickstart](../notebooks/01_quickstart.ipynb), a
  [coming-from-matplotlib](../notebooks/02_from_matplotlib.ipynb) walkthrough
  that renders the same data in both libraries side by side, the full
  [plot-type](../notebooks/03_plot_types.ipynb) vocabulary,
  [layout and composition](../notebooks/04_layout_and_composition.ipynb),
  [styling, color and text](../notebooks/05_styling_color_and_text.ipynb), and
  [output formats and performance](../notebooks/06_output_and_performance.ipynb)
  with a live benchmark against matplotlib.
- `tools/build_notebooks.py` re-executes them reproducibly (pinned font, no
  timing metadata, normalized kernel metadata); `tests/test_notebooks.py` and a
  CI step keep them running against the current API.
- Removed `notebooks/verify_core_plots.ipynb`, a development scratchpad whose
  job — proving each plot type still renders — belongs to
  `tests/test_golden.py` and `tests/test_plot_types.py`.

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
