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
    "nice-number" ticks out of the box. No styling needed to look finished.

-   :material-rocket-launch:{ .lg .middle } **Fast**

    ---

    The hot per-point and per-pixel loops live in Rust. Million-point line and
    scatter exports are sub-second, and the single-pass layout means the lead
    grows with panel count.

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
| **2D marks** | `line`, `scatter`, `bar`, `hist`, `fill_between`, `errorbar`, `imshow` + `colorbar` |
| **3D** | `scatter`, `plot`, `surface` — projected to editable 2D vectors, with an interactive HTML viewer |
| **Themes** | `default`, `nature`, `grayscale`, `presentation`, plus `Theme.with_(...)` |
| **Annotations** | `text`, `annotate` with callout arrows; LaTeX math anywhere |
| **Grammar of graphics** | `pyplotrs.gg` — declarative `Plot(...).add(geom).facet(...)` |
| **Animation** | `animate(render, frames)` → GIF / APNG |
| **Formats** | PDF, SVG, PNG (with DPI), and self-contained HTML |

See the [gallery](gallery/index.md) for the full set, each with runnable source.

## Install

```bash
pip install pyplotrs
```

Pre-built wheels bundle the Rust core and fonts — no toolchain required. See
[installation](installation.md) for details and building from source.
