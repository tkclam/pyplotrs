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

## PDF: editable, selectable, accessible text

This is pyplotrs' headline feature. Text in the PDF is genuine embedded,
subsetted font data — **not outlines** — so:

- opening the PDF in Illustrator/Inkscape lets you select, re-type and restyle
  every label;
- `pdftotext` / copy-paste extracts the text (math included, as Unicode);
- `pdffonts` shows the embedded subsets.

Pass `tagged=True` to write a **tagged, accessible PDF**: the whole chart becomes
one `Figure` structure element with alt text (auto-derived from the
titles/labels, or set explicitly), plus a document title and language, so screen
readers can announce it.

```python
fig.save("figure.pdf", tagged=True, title="Figure 1", alt="Response vs time")
```

## Resolution

`dpi` only affects raster (`.png`) output — PDF, SVG and HTML are
resolution-independent and ignore it. The default of 200 dpi is
publication-quality; bump it for print:

```python
fig.save("figure.png", dpi=600)
```

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

## Cross-machine consistency

Whichever body font is resolved, it is **embedded into every saved file**, so a
figure looks identical wherever it's opened — independent of the fonts installed
on the viewer's machine. See [styling & themes](styling-and-themes.md#fonts).
