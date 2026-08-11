# pyplotrs

**A blazingly fast, publication-quality plotting library for Python, powered by Rust.**

`pyplotrs` (pronounced *py-plotters*) pairs a clean, modern Python API with a
Rust rendering core. It is built for **beautiful static figures you can drop
straight into a paper, a slide, or a web page** — and, uniquely, **PDF output
whose text stays real, selectable, and editable in Illustrator** (genuine
embedded/subset fonts, never outlines).

```python
import pyplotrs as plt

fig, ax = plt.subplots()
ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="y = x²")
ax.scatter([0, 1, 2, 3], [0, 1, 4, 9])
ax.set(title="Hello, pyplotrs", xlabel="x", ylabel="y")
ax.legend()

fig.save("hello.pdf")   # editable vector text
fig.save("hello.png")   # 200 dpi by default
```

[Get started :material-arrow-right:](quickstart.md){ .md-button .md-button--primary }
[Work through the tutorial :material-school:](tutorial.md){ .md-button }
[Browse the gallery :material-image-multiple:](gallery/index.md){ .md-button }

## Why pyplotrs?

<div class="grid cards" markdown>

-   :material-vector-square:{ .lg .middle } **Editable-text PDF**

    ---

    Text is embedded and subset, not outlined — open a saved PDF in
    Illustrator/Inkscape and select, re-type, or restyle every label.
    `save(..., tagged=True)` writes accessible, tagged PDF.

-   :material-palette:{ .lg .middle } **Publication-quality defaults**

    ---

    A colorblind-safe palette, a sensible type scale, despined axes, and
    "nice-number" ticks out of the box, at journal-column size. No styling
    needed to look finished.

-   :material-rocket-launch:{ .lg .middle } **Fast**

    ---

    The hot per-point and per-pixel loops live in Rust. A million-point line
    exports to PDF in ~0.5 s, a million-point scatter to PNG in ~0.15 s, the
    single-pass layout means the lead grows with panel count, and the GIL is
    released while rendering.

-   :material-earth:{ .lg .middle } **Portable output**

    ---

    The chosen font is embedded into every saved file (PDF/SVG/PNG/HTML), so a
    figure looks identical on any machine regardless of installed fonts.

-   :material-function-variant:{ .lg .middle } **Real LaTeX math**

    ---

    `$...$` spans are typeset by a faithful, MathJax-grade engine driven by the
    math font's OpenType MATH table — and stay selectable text in the output.

-   :material-code-braces:{ .lg .middle } **No global state**

    ---

    Every figure is an explicit object. No `pyplot` current-figure surprises;
    the same API works cleanly under threads.

</div>

## What can it draw?

| Area | What you get |
|---|---|
| **Lines & points** | `line`, `scatter`, `step`, `stairs`, `stem`, `loglog`/`semilogx`/`semilogy` |
| **Bars & categories** | `bar`, `barh`, `broken_barh`, `eventplot`, plus automatic categorical axes from string data |
| **Distributions** | `hist`, `boxplot`, `violinplot` (Rust KDE), `pie` |
| **Uncertainty** | `errorbar`, `fill_between`, `fill_betweenx`, `stackplot` |
| **Fields & images** | `imshow` + `colorbar`, `matshow`, `spy`, `pcolormesh`, `hist2d`, `hexbin`, `contour`, `contourf`, `quiver`, `streamplot` |
| **Guides & shapes** | `axhline`/`axvline`, `axhspan`/`axvspan`, `axline`, `hlines`/`vlines`, `rectangle`, `circle`, `ellipse`, `polygon`, `arrow` |
| **Polar** | `plot`, `scatter` on a configurable dial |
| **3D** | `scatter`, `plot`, `surface`, `bar3d`, `plot_wireframe`, `contour3d`, `plot_trisurf`, `quiver3d`, `voxels` — projected to editable 2D vectors, with an interactive HTML viewer |
| **Axes** | Linear, log, symlog, logit, date and categorical scales; 8 tick formatters; 4 color norms |
| **Layout** | Grids with ratios, `subplot_mosaic`, `GridSpec`, twin axes, insets, secondary axes |
| **Themes** | `default`, `nature`, `grayscale`, `presentation`, plus `Theme.with_(...)` |
| **Color** | 127 exact colormaps, 25 categorical palettes, Oklab/CAM16-UCS conversion and CVD checks |
| **Annotations** | `text`, `annotate` with callout arrows; LaTeX math anywhere |
| **Animation** | `animate(render, frames)` → GIF / APNG |
| **Formats** | PDF, SVG, PNG (with DPI), and self-contained HTML |

See the [gallery](gallery/index.md) for the full set, each with runnable source.

## Install

```bash
pip install pyplotrs
```

Pre-built wheels bundle the Rust core and fonts — no toolchain required, and no
required runtime dependencies (not even NumPy). See
[installation](installation.md) for details and building from source.

## Where to start

- **New here?** [Quickstart](quickstart.md), then the
  [tutorial](tutorial.md).
- **Coming from matplotlib?** [The differences](migrating-from-matplotlib.md).
- **Looking for a specific mark?** [Plot types](guide/plot-types.md) or the
  [gallery](gallery/index.md).
- **Looking for a signature?** [API reference](api/figure.md).
