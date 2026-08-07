# pyplotrs

**A blazingly fast, publication-quality plotting library for Python, powered by Rust.**

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
- **Fast** — the hot per-point/per-pixel loops live in Rust. Million-point line
  and scatter exports are sub-second, and the single-pass layout engine means
  the lead grows with panel count.
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
| **2D marks** | `line`, `scatter`, `bar`, `hist`, `fill_between`, `errorbar`, `imshow` + `colorbar` |
| **3D** | `scatter`, `plot`, `surface` — projected to editable 2D vectors, with an interactive HTML viewer |
| **Themes** | `default`, `nature`, `grayscale`, `presentation`, plus `Theme.with_(...)` to derive your own |
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

Full docs, a [quickstart](https://tkclam.github.io/pyplotrs/quickstart/), a
[user guide](https://tkclam.github.io/pyplotrs/guide/figure-and-axes/), and a
[gallery](https://tkclam.github.io/pyplotrs/gallery/) live at
**<https://tkclam.github.io/pyplotrs/>**.

To build the docs locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```

## License

Licensed under the [MIT license](LICENSE).

The bundled fonts (Liberation Sans, STIX Two Math) are under the SIL Open Font
License 1.1 and the colormap data is CC0; see
[docs/about/license.md](docs/about/license.md).
