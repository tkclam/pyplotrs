# Changelog

All notable changes to pyplotrs are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project follows
[Semantic Versioning](https://semver.org/).

!!! note "What 0.x means here"
    Below 1.0 the API may change in a minor release. Breaking changes are
    listed under **Changed** with the replacement spelled out, and there are no
    backports — a fix ships in the next version.

## Unreleased

Nothing yet.

## 0.1.0 — 2026-08-20

The first public release. Everything below is what the package *is*, rather
than what changed — there is no previous version to compare against.

### Figures and output

- **PDF with real text.** Fonts are embedded and subset, never converted to
  outlines, so a saved figure opens in Illustrator or Inkscape with every label
  selectable, re-typeable and restylable. `pdftotext` extracts it, and
  `save(..., tagged=True)` writes tagged, accessible PDF with a document title,
  language and alt text.
- **Four formats from one call**, chosen by extension: `.pdf`, `.svg`, `.png`
  (at any `dpi`, with physical-size metadata), and `.html` — a single
  self-contained page that fetches nothing when opened.
- **`transparent=True` means "no page"** in every format, including a page the
  theme itself states. That is what lets a dark figure be composited onto a
  background of your own rather than baking the near-black into the alpha
  channel. Themes that state no page are unaffected in every format.
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
- **Images are resampled onto the grid they will actually occupy** before any
  backend sees them, with a separable box filter that is per-axis by
  construction: a reduced axis is area-averaged, a magnified one keeps hard
  block edges with a single pixel of antialiasing. A tall or wide image is
  magnified along one axis and reduced along the other, and the two want
  opposite filters — but a backend offers only one for the whole image
  (tiny-skia's `FilterQuality`, SVG's `image-rendering`, PDF's `/Interpolate`),
  so resampling up front is what makes `.png`, `.svg`, `.pdf` and `.html`
  agree. Magnified blocks are evenly sized: each block boundary lands at its
  exact fractional position rather than rounding to a whole pixel.

### Animation

- **`animate(render, frames)`** to GIF or APNG.
- **`Animation.to_bytes(format, *, dpi, fps)`** gives the encoded animation
  without a file; `save` is a thin wrapper over it. Reach for it when the
  destination is an HTTP response, a zip member or a `BytesIO`. `save` also
  takes a `format=` override for a path without a useful extension, mirroring
  the extension sniff.
- **Animations display inline in notebooks.** A bare `anim` in a cell plays,
  the way a bare `fig` renders as a PNG: `Animation` implements
  `_repr_mimebundle_` emitting an `image/gif` — the one animated format every
  frontend plays — and a `__repr__` that says how many frames at what rate. The
  inline render is 100 dpi (`_INLINE_ANIM_DPI`, below a still figure's 150,
  since an animation multiplies that by its frame count and lands base64-encoded
  in the `.ipynb`) and refuses over 20 MB rather than silently truncating.
- **APNG frames deflate against each other**, in parallel with the still-PNG
  encoder rather than one frame at a time on one thread. A 30-frame colormapped
  field encodes in 0.10 s, a 20k-point scatter in 0.21 s; the path scales with
  cores (0.96 s on one thread, 0.26 s on four, 0.09 s on twenty). Frames stay
  full keyframes, so the decoded animation is pixel-exact against the still
  renders.

### Axes, layout and style

- Linear, log, symlog, logit, date and categorical scales; 8 tick formatters;
  4 color normalizations.
- Grids with width/height ratios, `subplot_mosaic`, `GridSpec`, twin axes,
  insets, secondary axes — all solved in **one layout pass** against measured
  text, so nothing overlaps and there is no draw-measure-redraw step.
- **Three themes** — `default`, `dark` and `grayscale` (`bw` is an alias for
  `grayscale`) — plus `Theme.with_(...)` to derive your own.
    - `default` carries a compact type scale: tick labels 8pt, axis labels 9pt,
      title 10pt, suptitle 11pt, legend 8pt, spines 0.8pt, lines 1.2pt.
    - `dark` is `default` with the ink and the paper swapped: a near-black page,
      off-white type and spines, and the palette re-aimed at a dark background.
      The palette is Okabe-Ito index for index — `C3` is the same bluish green
      in both themes, so a figure keeps its series colors across the switch.
      Only two entries move: `C0` black becomes off-white, since black cannot be
      lifted without becoming a different color, and `C0` stands for "ink, no
      hue" rather than for black in particular; and Okabe-Ito's blue at `C5`
      reaches just 3.6:1 against the dark page, so it is lifted in Oklch (hue
      held, chroma shrunk only as far as the sRGB gamut demands) to the smallest
      lightness clearing 4.5:1.
    - `grayscale` is exactly `default` with the color taken out — a palette swap
      and nothing else, so a figure keeps its shape on the way to a mono press.
- **`Theme.figure_facecolor`** is the page the whole figure is drawn on, painted
  before anything else. Light themes leave it `None` and nothing changes: `.png`
  already fills its page white, and `.pdf`/`.svg`/`.html` deliberately paint
  nothing so a figure drops onto whatever is behind it. A dark theme has to
  state its page, because white text over "nothing" is white text on a white
  page in every viewer that opens it.
- **Margins are clamped where a mark rests.** Each mark records the values it
  *rests on* — a stack's floor, a bar's base, an image's extent — so a
  `stackplot` sits flush against the x spine instead of floating above it. The
  5% margin is unchanged everywhere a mark merely *stops*: `fill_between(x, y,
  0)` still gets it, because 0 is just another curve. `bar(bottom=...)` and
  `barh(left=...)` sit on the base they were given.
- **`xmargin`/`ymargin` work on every scale.** The margin is applied once, in
  transformed space — on a log axis it is 5% of the *decade* span, so it means
  the same thing at both ends — and mark-aware bounds such as an image extent
  survive the switch to a non-linear scale. A margin of -0.5 or below is
  rejected rather than silently producing a zero-width or inverted axis, and a
  span near the float ceiling does not pad to infinity.
- `axhline`, `axvline`, `axhspan` and `axvspan` contribute the coordinate they
  are positioned at, so a guide cannot land outside the frame and go missing.
  They contribute nothing to the direction they span, which is an axes fraction
  rather than data. `axline` is infinite and contributes nothing.
- `boxplot(showfliers=False)` does not scale the value axis to the outliers it
  is hiding; a `boxplot`'s category axis is sized from the category slot rather
  than from `widths`, so narrowing the boxes thins the glyphs instead of zooming
  in on them. `violinplot` evaluates its KDE over the data range rather than
  past each end, and `contour` pins the view to its grid as `contourf` does.
- A constant series expands relative to its own value rather than by a fixed
  half-unit, so a flat line at y=1000 gets a readable scale instead of ticks
  reading 999.5 / 1000 / 1000.5. `sharex`/`sharey` preserve an inverted panel's
  direction.
- A full getter layer (`get_xlim`, `get_xticklabels`, `get_legend_handles_labels`,
  …) reporting the **effective** value, with autoscaling and `sharex`/`sharey`
  resolved.

### Color

- **127 exact colormaps and 25 categorical palettes**, compiled in, plus
  sRGB/XYZ/Lab/Oklab/Oklch/CAM16-UCS conversion, color-vision-deficiency
  simulation, and colormap distinguishability and uniformity scoring — so the
  defaults can be checked rather than asserted.
- **The default palette is Okabe-Ito, in its published order.** Scored as a
  *cycle* — the worst-separated pair among the first n entries, under normal,
  protan and deutan vision, in CAM16-UCS — the published order ties the best of
  all 40320 orderings of these eight colors at n=2 and n=3. Two consequences
  worth knowing: **`C0` is black**, so a single unstyled line draws in ink
  rather than blue, which is what a lone series wants, having nothing to
  contrast against; and **`C4` is yellow** at 1.32:1 against a white page, fine
  as a fill but faint as a 1.2 pt line, so a five-line plot on the stock palette
  has one weak line — reach past it with `color="C5"` or reorder the palette in
  a derived theme. The indices do not correspond to matplotlib's.
- The separator hairline that keeps histogram-bin and pie-wedge seams reading as
  "the background showing through" falls through `axes_facecolor` →
  `figure_facecolor` → white, so a theme that darkens the page and lets it show
  through the plot area does not grow white outlines between its bins.

### Text and math

- **`$...$` LaTeX math without a LaTeX install**, typeset from the math font's
  OpenType MATH table and left as real selectable text in the output.
- **Math is set in your own body family**, not split between it and a serif math
  font. Variables and Greek come from the body italic, digits and operators from
  the face the label is in, and a math font draws only what a text face cannot:
  big operators, radicals, stretchy fences, the blackboard/script/Fraktur
  alphabets, and any symbol the family is missing (checked glyph by glyph). So a
  **bold** label's math is bold throughout, math follows `set_font_family` —
  Helvetica body text gets Helvetica Italic variables — and most figures do not
  embed a math font at all, which is around 2 MB off an SVG.
  `set_mathtext_fontset()` / `get_mathtext_fontset()` select the family:
  `"sans"` is the default, and `"stix"` sets every atom in STIX Two Math, for
  figures whose body text is a serif too.
    - **Fira Math** (SIL OFL, 175 KB) is the bundled sans math font, so `√`,
      `∑`, `∫` and auto-sized `\left...\right` fences are monoline marks matching
      the label rather than high-contrast Times shapes. These are the parts that
      have to *grow* with their content, which needs the variant and assembly
      chains of an OpenType MATH table — no text font has one. DejaVu Sans, the
      obvious candidate, cannot serve: it leaves ten of twenty-four MATH
      constants unset and has no vertical construction for `√` at all.
      (matplotlib uses it only because it hardcodes a `DejaVuSansFontConstants`
      class instead of reading the table; pyplotrs reads the table.) Nor would
      scaling one base glyph up do — that thickens the strokes as the glyph
      grows, so a tall delimiter comes out heavier than the text it wraps. Fira
      Math leaves no constant unset, gives `√` sixteen designed variants plus an
      assembly, and carries 244 italic corrections. It is OpenType/CFF, so it
      embeds in PDF as a subset `CIDFontType0`/`FontFile3` beside the body
      family's `CIDFontType2` — still real, selectable text, never outlines.
    - A **95 KB subset of DejaVu Sans** supplies sans shapes for the symbols a
      text family does not carry. Coverage of the symbol blocks is ragged in
      every text family — Arial and Liberation Sans have `→ ← ↔` but not
      `⇒ ⇐ ↦`, `∩` but not `∪`, `≤ ≥ ≠ ≈` but not `≪ ≫ ∝ ∼`, `±` but not `∓` —
      so falling straight from the body face to a serif math font would split
      symbol families down the middle: a sans `$A \cap B$` beside a serif
      `$A \cup B$`. It closes 108 of the 111 gaps; the three it misses are big
      operators, which come from the math font regardless. It supplies shapes
      only — its MATH table is dropped at subset time.
      `tools/build_math_symbol_font.py` regenerates it.
    - **STIX Two Math** draws a whole span under `set_mathtext_fontset("stix")`,
      and under `sans` is the last resort for the Script and Fraktur alphabets
      and double-struck digits, which no sans math font here carries.
- **Rich text: style a *substring* of any label.** `pp.rich(...)` and its
  shorthands `pp.bold`, `pp.italic`, `pp.underline`, `pp.strike` and `pp.mark`
  build a span tree that every label slot accepts: titles, axis labels, tick
  labels, `label=`, `text` and `annotate`. Styles are `weight`, `style`,
  `color`, `bgcolor`, `underline`, `strike`, and `scale`/`size`; spans nest, and
  an inner style wins, so a run can opt back out of what encloses it. Colors
  resolve against the figure's theme, `"C0"` palette indices included.
  `pp.plain(label)` gives the text back unstyled, which is what the tagged-PDF
  description uses. Underline and strikeout rules come from the face's own
  `post`/`OS/2` metrics rather than a fraction of the type size, so they sit
  where the type designer put them and move correctly between faces.
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
  corrupting the axis limits. A vertex with a non-finite coordinate does not
  move the other axis: `(100, NaN)` is not drawn, and x is not stretched to
  reach it.
- `Figure.save` and `Animation.save` both take a `str` or a `pathlib.Path`.

### Documentation

- **Eight runnable notebooks** under `docs/notebooks/`, rendered into the site
  and on GitHub from their committed output: a
  [quickstart](../notebooks/01_quickstart.ipynb), a
  [coming-from-matplotlib](../notebooks/02_from_matplotlib.ipynb) walkthrough
  that renders the same data in both libraries side by side, the full
  [plot-type](../notebooks/03_plot_types.ipynb) vocabulary,
  [layout and composition](../notebooks/04_layout_and_composition.ipynb),
  [styling and color](../notebooks/05_styling_and_color.ipynb),
  [text and math](../notebooks/06_text_and_math.ipynb) — fonts, rich text and
  `$…$` — [animation](../notebooks/07_animation.ipynb), and
  [output formats and performance](../notebooks/08_output_and_performance.ipynb)
  with a live benchmark against matplotlib.
- `tools/build_notebooks.py` re-executes them reproducibly (pinned font, no
  timing metadata, normalized kernel metadata); `tests/test_notebooks.py` and a
  CI step keep them running against the current API.

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
