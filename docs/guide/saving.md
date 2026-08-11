# Saving figures

[`Figure.save`][pyplotrs.figure.Figure.save] picks the format from the file
extension (case-insensitive):

```python
fig.save("figure.pdf")
fig.save("figure.svg")
fig.save("figure.png", dpi=300)
fig.save("figure.html")
```

| Extension | Output |
|---|---|
| `.pdf` | Vector PDF with **real embedded/subset fonts** — editable text |
| `.svg` | Vector SVG with the font embedded (`@font-face`) |
| `.png` | Raster at `dpi` (default **200**), with physical-size metadata |
| `.html` / `.htm` | A single self-contained page (see below) |

Anything else raises `ValueError` rather than guessing.

## PDF: editable, selectable, accessible text

This is pyplotrs' headline feature. Text in the PDF is genuine embedded,
subsetted font data — **not outlines** — so:

- opening the PDF in Illustrator/Inkscape lets you select, re-type and restyle
  every label;
- `pdftotext` / copy-paste extracts the text (math included, as Unicode);
- `pdffonts` shows the embedded subsets.

```bash
pdftotext figure.pdf - | head
pdffonts figure.pdf
```

Pass `tagged=True` to write a **tagged, accessible PDF**: the whole chart becomes
one `Figure` structure element with alt text (auto-derived from the
titles/labels, or set explicitly), plus a document title and language, so screen
readers can announce it.

```python
fig.save("figure.pdf", tagged=True, title="Figure 1", alt="Response vs time")
```

Every text face in use is embedded as its own subset, so a figure mixing
regular, bold, italic and math carries four subsets and every one of them stays
selectable.

## Resolution

`dpi` only affects raster (`.png`) output — PDF, SVG and HTML are
resolution-independent and ignore it. The default of 200 dpi is
publication-quality; bump it for print:

```python
fig.save("figure.png", dpi=600)
```

The value is also written into the PNG's `pHYs` chunk, so the file knows its own
physical size and lands at the right size in a document rather than at whatever
the importing application assumes.

## Transparent backgrounds

`transparent=True` drops the white page fill from `.png` output in favor of an
alpha channel — useful for dropping a figure onto a colored slide or webpage
background:

```python
fig.save("figure.png", transparent=True)
```

`.pdf`/`.svg`/`.html` paint no page background to begin with, so they are
already "transparent" and ignore the flag.

## HTML

`.html` writes a single portable page with **nothing fetched at view time**:

- **2D figures** are inlined as vector SVG with real selectable text and embedded
  fonts. If any label contains `$...$` math, it is re-rendered by an inlined copy
  of MathJax (so the math is selectable and copyable as LaTeX/MathML), fully
  offline.
- **3D figures** become a dependency-free Canvas2D viewer you can orbit, zoom and
  pan.

```python
fig.save("figure.html")
```

`title=` and `alt=` label the page and its inline SVG (`role="img"`) here too,
auto-derived from the figure's own titles and labels when omitted.

## Cross-machine consistency

Whichever body font is resolved, it is **embedded into every saved file**, so a
figure looks identical wherever it's opened — independent of the fonts installed
on the viewer's machine. See [styling & themes](styling-and-themes.md#fonts).

## Saving many figures at once

Rendering releases the GIL, so a thread pool over figures actually runs in
parallel — and with no global state there is nothing for the threads to fight
over:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor() as pool:
    pool.map(lambda i: build(i).save(f"panel{i}.pdf"), range(64))
```

See [performance](performance.md).

## Animated output

An [animation](animation.md) is saved through its own object, not `Figure.save`,
and writes `.gif` or `.apng`:

```python
plt.animate(render, frames=60).save("wave.gif")
```
