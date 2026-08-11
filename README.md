# pyplotrs

[![CI](https://github.com/tkclam/pyplotrs/actions/workflows/CI.yml/badge.svg)](https://github.com/tkclam/pyplotrs/actions/workflows/CI.yml)
[![PyPI](https://img.shields.io/pypi/v/pyplotrs.svg)](https://pypi.org/project/pyplotrs/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyplotrs.svg)](https://pypi.org/project/pyplotrs/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/tkclam/pyplotrs/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-tkclam.github.io-blue)](https://tkclam.github.io/pyplotrs/)

**A blazingly fast, publication-quality plotting library for Python, powered by Rust.**

<p align="center">
  <img src="https://raw.githubusercontent.com/tkclam/pyplotrs/main/docs/gallery/images/subplots.png"
       alt="A four-panel pyplotrs figure: damped sinusoids with a legend, a categorical bar chart, a histogram, and a scatter plot"
       width="720">
</p>

`pyplotrs` (pronounced *py-plotters*) is a from-scratch plotting library with a
clean, modern Python API and a Rust rendering core. It is built for one thing
above all: **beautiful static figures you can drop straight into a paper, a
slide, or a web page** — and, uniquely, **PDF output whose text stays real,
selectable, and editable in Illustrator** (genuine embedded/subset fonts, never
outlines).

```python
import pyplotrs as plt

fig, ax = plt.subplots()
ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="y = x²")
ax.scatter([0, 1, 2, 3], [0, 1, 4, 9])
ax.set(title="Hello, pyplotrs", xlabel="x", ylabel="y")
ax.legend()

fig.save("hello.pdf")   # editable vector text
fig.save("hello.svg")
fig.save("hello.png")   # 200 dpi by default
fig.save("hello.html")  # self-contained, selectable text
```

## Why pyplotrs?

- **Editable-text PDF** — text is embedded and subset, not converted to
  outlines, so you can open a saved PDF in Illustrator/Inkscape and select,
  re-type, or restyle every label. `pdftotext` extracts it; screen readers can
  read it (`save(..., tagged=True)` writes accessible, tagged PDF).
- **Publication-quality defaults** — a colorblind-safe palette, sensible type
  scale, despined axes, and "nice-number" ticks out of the box. No styling
  required to get a figure that looks finished.
- **Fast** — the hot per-point/per-pixel loops live in Rust. A million-point
  line exports to PDF in ~0.5 s and SVG in ~0.25 s; a million-point scatter
  rasterizes to PNG in ~0.15 s. The single-pass layout engine means the lead
  over matplotlib grows with panel count, and the GIL is released for both
  rendering and the compute kernels, so a thread pool over figures actually
  parallelizes. See
  [benchmarks](https://tkclam.github.io/pyplotrs/guide/performance/) for the
  measured table, the machine it came from, and the one case that is *slower*
  than matplotlib.
- **Portable output** — the chosen font is **embedded into every saved file**
  (PDF/SVG/PNG/HTML), so a figure looks identical on any machine, regardless of
  the fonts installed there.
- **Real LaTeX math** — `$...$` spans are typeset by a faithful, MathJax-grade
  engine driven by the math font's OpenType MATH table, and stay selectable
  text in the output.
- **No global state** — every figure is an explicit object. No `pyplot`
  current-figure surprises; the same API works cleanly under threads.

## Features

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
| **Themes** | `default`, `nature`, `grayscale`, `presentation`, plus `Theme.with_(...)` to derive your own |
| **Color** | 127 exact colormaps, 25 categorical palettes, Oklab/CAM16-UCS conversion and CVD checks |
| **Annotations** | `text`, `annotate` with callout arrows; LaTeX math anywhere |
| **Animation** | `animate(render, frames)` → GIF / APNG |
| **Formats** | PDF, SVG, PNG (with DPI), and self-contained HTML |

## Installation

```bash
pip install pyplotrs
```

Pre-built wheels ship the Rust core and the bundled fonts — no toolchain
required. See the [installation guide](https://tkclam.github.io/pyplotrs/installation/)
for building from source.

## Documentation

Full docs live at **<https://tkclam.github.io/pyplotrs/>**:

- [Quickstart](https://tkclam.github.io/pyplotrs/quickstart/) — zero to a saved
  figure
- [Tutorial](https://tkclam.github.io/pyplotrs/tutorial/) — one publication
  figure, built step by step
- [Coming from matplotlib](https://tkclam.github.io/pyplotrs/migrating-from-matplotlib/)
  — the differences, with a translation table
- [User guide](https://tkclam.github.io/pyplotrs/guide/figure-and-axes/) —
  layout, plot types, scales, themes, 3D, saving
- [Gallery](https://tkclam.github.io/pyplotrs/gallery/) — every figure with
  runnable source
- [API reference](https://tkclam.github.io/pyplotrs/api/figure/)

To build the docs locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```

## License

Licensed under the **MIT license**
([LICENSE](https://github.com/tkclam/pyplotrs/blob/main/LICENSE)).

pyplotrs redistributes a few third-party assets, each under a permissive
license, and ships every license text in the wheel under
`pyplotrs-<version>.dist-info/licenses/`:

| Asset | License |
|---|---|
| Liberation Sans, STIX Two Math (bundled fonts) | SIL Open Font License 1.1 |
| `viridis`/`plasma`/`inferno`/`magma`/`cividis` | CC0 1.0 (public domain) |
| colorcet colormaps (`cet_*`) | **CC-BY 4.0 — attribution required** |
| cmocean (`cmo_*`) · seaborn (`sns_*`) | MIT · BSD-3-Clause |
| MathJax 3.2.2 (inlined into HTML math output) | Apache-2.0 |
| krilla (PDF backend, vendored) | MIT OR Apache-2.0 |
| ~110 Rust crates compiled into the extension | MIT / Apache-2.0 / BSD / Zlib / … |

Full details in
[THIRD-PARTY-NOTICES.md](https://github.com/tkclam/pyplotrs/blob/main/THIRD-PARTY-NOTICES.md)
and the [license page](https://tkclam.github.io/pyplotrs/about/license/).
