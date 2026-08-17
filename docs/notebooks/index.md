# Notebooks

Eight runnable notebooks that cover the library end to end. They are the same
material as the [user guide](../guide/figure-and-axes.md), in the form you can
run a cell at a time and change the numbers in.

Each one is committed **with its output**, so it reads as a finished document
here and on GitHub without running anything. Every figure was produced by the
code above it — nothing is a screenshot.

| # | Notebook | What it covers | Needs |
|---|---|---|---|
| 1 | [Quickstart](01_quickstart.ipynb) | The make–draw–save loop, marks, `set`/`get_*`, saving, panels, sizing, themes | — |
| 2 | [Coming from matplotlib](02_from_matplotlib.ipynb) | Every API difference, plus the same data rendered by both libraries side by side | matplotlib, NumPy |
| 3 | [Plot types](03_plot_types.ipynb) | The whole mark vocabulary — 2D, statistical, images, fields, shapes, polar, 3D | — |
| 4 | [Layout and composition](04_layout_and_composition.ipynb) | Grids and ratios, mosaics, `GridSpec`, twin and secondary axes, insets, colorbars | — |
| 5 | [Styling and color](05_styling_and_color.ipynb) | Themes, palettes, the 127 colormaps, norms, color science | — |
| 6 | [Text and math](06_text_and_math.ipynb) | Fonts, `text`/`annotate`, styling a substring with `rich`, `$…$` math | — |
| 7 | [Animation](07_animation.ipynb) | The render callback, GIF vs APNG, `dpi`, and what makes one readable | — |
| 8 | [Output and performance](08_output_and_performance.ipynb) | What each format guarantees, tagged PDF, threads, speed against matplotlib | matplotlib |

Start at the quickstart if pyplotrs is new to you, or at
[coming from matplotlib](02_from_matplotlib.ipynb) if it is not.

## Running them yourself

Every notebook runs on a plain install; only 2 and 8 want matplotlib, and only
for the comparisons.

```bash
pip install pyplotrs jupyterlab
# optional, for notebooks 2 and 8:
pip install matplotlib numpy

jupyter lab      # then open any notebook under docs/notebooks/
```

The notebooks take the default font, which is the host's Arial, then Helvetica,
then the Liberation Sans compiled into the extension — so they show you what
`pp.subplots()` gives you on your own machine rather than a face pinned for the
docs' convenience. The committed images were rendered where Arial resolved. If
your machine picks a different face the figures you re-run will not match them
glyph for glyph, because every advance — and so every laid-out box — moves.

The gallery and tutorial images are pinned to Liberation Sans instead, since
those are byte-compared by the test suite; see `tools/build_gallery_images.py`.

## Regenerating the committed output

Contributors: after a change that moves rendering, re-run the notebooks so the
committed images stop being a claim about an older build.

```bash
python tools/build_notebooks.py           # execute all eight, in place
python tools/build_notebooks.py --check   # execute, write nothing (what CI runs)
```

The tool normalizes kernel metadata and drops execution timings, so a rebuild
that changed nothing produces no diff.
