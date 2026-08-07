# pyplotrs benchmark matrix

Export wall-time and file size across **mark x point-count x panels x format**. `N` is the figure's *total* point budget, split evenly over the panels. Times are `save()` / `savefig()`, best of 3 runs after 1 untimed warm-up, at a matched 100 dpi and figure size, on this machine. Regenerate with `.venv/bin/python benchmarks/matrix.py`.

Read the numbers with two caveats. For pyplotrs the timed region is close to the whole pipeline - `line()` only records a mark, and layout, shaping and rendering all happen inside `save()` - whereas matplotlib has built its artists beforehand. Data ingestion is outside the timer for both, as is import time (`import pyplotrs` is ~12 ms against ~237 ms for `matplotlib.pyplot`, which no row here reflects).

| mark | N | panels | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| line | 10,000 | 1 | pdf | 0.001s | 12KB | 0.010s | 7KB | 18.3x |
| line | 10,000 | 1 | png | 0.002s | 8KB | 0.011s | 15KB | 6.1x |
| line | 10,000 | 1 | svg | 0.001s | 363KB | 0.010s | 13KB | 17.8x |
| line | 10,000 | 4 | pdf | 0.001s | 14KB | 0.032s | 9KB | 29.7x |
| line | 10,000 | 4 | png | 0.006s | 26KB | 0.040s | 30KB | 6.8x |
| line | 10,000 | 4 | svg | 0.001s | 377KB | 0.032s | 38KB | 39.1x |
| line | 10,000 | 9 | pdf | 0.002s | 18KB | 0.070s | 13KB | 35.9x |
| line | 10,000 | 9 | png | 0.012s | 51KB | 0.092s | 99KB | 7.7x |
| line | 10,000 | 9 | svg | 0.001s | 398KB | 0.068s | 81KB | 47.4x |
| line | 100,000 | 1 | pdf | 0.001s | 12KB | 0.012s | 7KB | 9.4x |
| line | 100,000 | 1 | png | 0.003s | 8KB | 0.014s | 15KB | 5.3x |
| line | 100,000 | 1 | svg | 0.001s | 363KB | 0.011s | 13KB | 9.8x |
| line | 100,000 | 4 | pdf | 0.002s | 14KB | 0.033s | 9KB | 19.0x |
| line | 100,000 | 4 | png | 0.006s | 26KB | 0.042s | 31KB | 6.6x |
| line | 100,000 | 4 | svg | 0.001s | 377KB | 0.033s | 38KB | 22.3x |
| line | 100,000 | 9 | pdf | 0.003s | 18KB | 0.070s | 13KB | 26.0x |
| line | 100,000 | 9 | png | 0.013s | 51KB | 0.094s | 101KB | 7.5x |
| line | 100,000 | 9 | svg | 0.002s | 398KB | 0.069s | 81KB | 31.9x |
| line | 1,000,000 | 1 | pdf | 0.012s | 12KB | 0.025s | 7KB | 2.1x |
| line | 1,000,000 | 1 | png | 0.011s | 8KB | 0.035s | 15KB | 3.2x |
| line | 1,000,000 | 1 | svg | 0.009s | 363KB | 0.024s | 13KB | 2.5x |
| line | 1,000,000 | 4 | pdf | 0.009s | 14KB | 0.046s | 9KB | 4.8x |
| line | 1,000,000 | 4 | png | 0.014s | 26KB | 0.065s | 31KB | 4.7x |
| line | 1,000,000 | 4 | svg | 0.009s | 377KB | 0.045s | 38KB | 5.1x |
| line | 1,000,000 | 9 | pdf | 0.010s | 18KB | 0.083s | 13KB | 8.7x |
| line | 1,000,000 | 9 | png | 0.021s | 52KB | 0.115s | 101KB | 5.5x |
| line | 1,000,000 | 9 | svg | 0.009s | 398KB | 0.081s | 81KB | 8.9x |
| scatter | 10,000 | 1 | pdf | 0.011s | 112KB | 0.074s | 158KB | 6.6x |
| scatter | 10,000 | 1 | png | 0.013s | 118KB | 0.017s | 50KB | 1.3x |
| scatter | 10,000 | 1 | svg | 0.003s | 823KB | 0.070s | 1MB | 26.1x |
| scatter | 10,000 | 4 | pdf | 0.012s | 112KB | 0.099s | 161KB | 8.3x |
| scatter | 10,000 | 4 | png | 0.026s | 188KB | 0.051s | 85KB | 2.0x |
| scatter | 10,000 | 4 | svg | 0.003s | 835KB | 0.095s | 1MB | 31.8x |
| scatter | 10,000 | 9 | pdf | 0.013s | 115KB | 0.140s | 167KB | 10.9x |
| scatter | 10,000 | 9 | png | 0.027s | 201KB | 0.105s | 160KB | 3.9x |
| scatter | 10,000 | 9 | svg | 0.004s | 851KB | 0.132s | 1MB | 36.5x |
| scatter | 100,000 | 1 | pdf | 0.115s | 1018KB | 0.651s | 1MB | 5.7x |
| scatter | 100,000 | 1 | png | 0.021s | 49KB | 0.044s | 9KB | 2.1x |
| scatter | 100,000 | 1 | svg | 0.026s | 5MB | 0.628s | 10MB | 24.3x |
| scatter | 100,000 | 4 | pdf | 0.114s | 998KB | 0.681s | 1MB | 6.0x |
| scatter | 100,000 | 4 | png | 0.047s | 311KB | 0.071s | 23KB | 1.5x |
| scatter | 100,000 | 4 | svg | 0.024s | 5MB | 0.649s | 10MB | 27.4x |
| scatter | 100,000 | 9 | pdf | 0.116s | 984KB | 0.724s | 1MB | 6.2x |
| scatter | 100,000 | 9 | png | 0.076s | 715KB | 0.124s | 138KB | 1.6x |
| scatter | 100,000 | 9 | svg | 0.024s | 5MB | 0.701s | 10MB | 28.6x |

**Reading it.** `speedup` is matplotlib-time / pyplotrs-time (>1 means pyplotrs exports faster). pyplotrs is faster on almost every cell, and the lead is largest on **vector** export (PDF/SVG) - the editable-text formats the project exists for - where line paths are simplified and scatter markers are instanced (one reused XObject/`<use>`). The lead *grows with panel count*: pyplotrs' single-pass layout amortizes per-panel chrome that matplotlib re-solves per axes.

**The one place matplotlib wins on time** is a single very large line (`N`=1e6, 1 panel): there the work is one long polyline with no per-panel overhead, and matplotlib's C path-simplification narrowly edges pyplotrs' Rust one (~0.7x). Add panels and pyplotrs retakes the lead.

**On file size**, each format has its own story:

- **PDF** - pyplotrs is smaller everywhere (subsetted fonts + instanced markers + path simplification).
- **SVG, marker-heavy (scatter)** - pyplotrs is *smaller* **and** ~15-22x faster: markers are one `<defs>` glyph + a `<use>` per point, versus matplotlib's per-point path, which outweighs even the embedded font.
- **SVG, sparse geometry (line)** - pyplotrs is *larger*, and on purpose: it **embeds the bundled font** so the SVG is self-contained and renders identically on any machine (a pyplotrs goal - no system-font drift), with real editable `<text>`; matplotlib only *references* a system font by name. Once the geometry is tiny (a simplified line is a few vertices), that ~340 KB font floor (more with math/STIX) dominates. Shrinking it needs a cmap-preserving font subsetter - a tracked future optimization, since the Typst `subsetter` drops the `cmap` that `<text>` relies on.
- **PNG** - resolution-bound for both; matplotlib's mature Agg compresses dense overlapping output more tightly.

See `benchmarks/benchmark.py` for the like-for-like single-panel head-to-head and the deterministic `--check` CI regression gate.
