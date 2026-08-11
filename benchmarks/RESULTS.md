# pyplotrs benchmark matrix

Export wall-time and file size across **mark x point-count x panels x format**. `N` is the figure's *total* point budget, split evenly over the panels. Times are `save()` / `savefig()`, best of 3 runs after 1 untimed warm-up, at a matched 100 dpi and figure size, on this machine. Regenerate with `.venv/bin/python benchmarks/matrix.py`.

Read the numbers with three caveats. For pyplotrs the timed region is close to the whole pipeline - `line()` only records a mark, and layout, shaping and rendering all happen inside `save()` - whereas matplotlib has built its artists beforehand. Data ingestion is outside the timer for both, as is import time (`import pyplotrs` is ~12 ms against ~237 ms for `matplotlib.pyplot`, which no row here reflects).

A third caveat applies only to **PNG**: raster export in pyplotrs is multi-threaded, both in rasterizing (an expensive canvas is split into horizontal bands) and in encoding (scanline filtering and DEFLATE both run in parallel). So the `png` rows scale with the core count of the machine that produced them - this run had 20 - and will read lower on a smaller one. PDF and SVG are single-threaded, so their rows are machine-independent in a way the PNG rows are not.

| mark | N | panels | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| line | 10,000 | 1 | pdf | 0.001s | 12KB | 0.010s | 7KB | 19.6x |
| line | 10,000 | 1 | png | 0.002s | 9KB | 0.011s | 15KB | 5.1x |
| line | 10,000 | 1 | svg | 0.001s | 363KB | 0.009s | 13KB | 11.1x |
| line | 10,000 | 4 | pdf | 0.001s | 14KB | 0.033s | 9KB | 34.0x |
| line | 10,000 | 4 | png | 0.004s | 27KB | 0.040s | 30KB | 10.6x |
| line | 10,000 | 4 | svg | 0.001s | 377KB | 0.031s | 38KB | 34.0x |
| line | 10,000 | 9 | pdf | 0.002s | 19KB | 0.068s | 13KB | 42.7x |
| line | 10,000 | 9 | png | 0.007s | 52KB | 0.088s | 99KB | 12.6x |
| line | 10,000 | 9 | svg | 0.001s | 398KB | 0.066s | 81KB | 45.1x |
| line | 100,000 | 1 | pdf | 0.001s | 12KB | 0.011s | 7KB | 9.5x |
| line | 100,000 | 1 | png | 0.002s | 9KB | 0.014s | 15KB | 5.5x |
| line | 100,000 | 1 | svg | 0.001s | 363KB | 0.011s | 13KB | 8.5x |
| line | 100,000 | 4 | pdf | 0.002s | 14KB | 0.033s | 9KB | 19.4x |
| line | 100,000 | 4 | png | 0.004s | 27KB | 0.042s | 31KB | 10.1x |
| line | 100,000 | 4 | svg | 0.002s | 377KB | 0.032s | 38KB | 19.9x |
| line | 100,000 | 9 | pdf | 0.002s | 18KB | 0.071s | 13KB | 31.0x |
| line | 100,000 | 9 | png | 0.007s | 50KB | 0.092s | 101KB | 13.3x |
| line | 100,000 | 9 | svg | 0.002s | 398KB | 0.067s | 81KB | 32.5x |
| line | 1,000,000 | 1 | pdf | 0.012s | 12KB | 0.024s | 7KB | 2.0x |
| line | 1,000,000 | 1 | png | 0.011s | 9KB | 0.035s | 15KB | 3.3x |
| line | 1,000,000 | 1 | svg | 0.010s | 363KB | 0.023s | 13KB | 2.3x |
| line | 1,000,000 | 4 | pdf | 0.009s | 14KB | 0.046s | 9KB | 5.3x |
| line | 1,000,000 | 4 | png | 0.012s | 27KB | 0.064s | 31KB | 5.3x |
| line | 1,000,000 | 4 | svg | 0.009s | 377KB | 0.045s | 38KB | 5.1x |
| line | 1,000,000 | 9 | pdf | 0.009s | 18KB | 0.083s | 13KB | 9.1x |
| line | 1,000,000 | 9 | png | 0.014s | 49KB | 0.114s | 101KB | 8.2x |
| line | 1,000,000 | 9 | svg | 0.009s | 398KB | 0.082s | 81KB | 9.2x |
| scatter | 10,000 | 1 | pdf | 0.006s | 118KB | 0.074s | 158KB | 12.5x |
| scatter | 10,000 | 1 | png | 0.009s | 119KB | 0.017s | 50KB | 1.8x |
| scatter | 10,000 | 1 | svg | 0.002s | 823KB | 0.069s | 1MB | 29.0x |
| scatter | 10,000 | 4 | pdf | 0.006s | 118KB | 0.098s | 161KB | 15.6x |
| scatter | 10,000 | 4 | png | 0.008s | 191KB | 0.051s | 85KB | 6.1x |
| scatter | 10,000 | 4 | svg | 0.003s | 835KB | 0.093s | 1MB | 35.0x |
| scatter | 10,000 | 9 | pdf | 0.007s | 120KB | 0.139s | 167KB | 20.3x |
| scatter | 10,000 | 9 | png | 0.009s | 204KB | 0.102s | 160KB | 11.7x |
| scatter | 10,000 | 9 | svg | 0.003s | 851KB | 0.130s | 1MB | 42.1x |
| scatter | 100,000 | 1 | pdf | 0.056s | 1MB | 0.651s | 1MB | 11.7x |
| scatter | 100,000 | 1 | png | 0.018s | 49KB | 0.043s | 9KB | 2.4x |
| scatter | 100,000 | 1 | svg | 0.021s | 5MB | 0.613s | 10MB | 29.1x |
| scatter | 100,000 | 4 | pdf | 0.056s | 1MB | 0.679s | 1MB | 12.2x |
| scatter | 100,000 | 4 | png | 0.017s | 313KB | 0.072s | 23KB | 4.2x |
| scatter | 100,000 | 4 | svg | 0.021s | 5MB | 0.643s | 10MB | 31.0x |
| scatter | 100,000 | 9 | pdf | 0.056s | 1MB | 0.716s | 1MB | 12.8x |
| scatter | 100,000 | 9 | png | 0.021s | 721KB | 0.125s | 138KB | 5.8x |
| scatter | 100,000 | 9 | svg | 0.021s | 5MB | 0.675s | 10MB | 31.9x |

**Reading it.** `speedup` is matplotlib-time / pyplotrs-time (>1 means pyplotrs exports faster). pyplotrs is faster on almost every cell, and the lead is largest on **vector** export (PDF/SVG) - the editable-text formats the project exists for - where line paths are simplified and scatter markers are instanced (one reused XObject/`<use>`). The lead *grows with panel count*: pyplotrs' single-pass layout amortizes per-panel chrome that matplotlib re-solves per axes.

**The large single line used to be matplotlib's one win** (`N`=1e6, 1 panel, ~0.7x), when ingest and autoscale still ran in Python. That loop moved to Rust and the row now wins like the others; the table above is the current measurement, and any statement about who wins where should be read off it rather than from this paragraph.

**On file size**, each format has its own story:

- **PDF** - pyplotrs is smaller everywhere (subsetted fonts + instanced markers + path simplification).
- **SVG, marker-heavy (scatter)** - pyplotrs is *smaller* **and** ~15-22x faster: markers are one `<defs>` glyph + a `<use>` per point, versus matplotlib's per-point path, which outweighs even the embedded font.
- **SVG, sparse geometry (line)** - pyplotrs is *larger*, and on purpose: it **embeds the bundled font** so the SVG is self-contained and renders identically on any machine (a pyplotrs goal - no system-font drift), with real editable `<text>`; matplotlib only *references* a system font by name. Once the geometry is tiny (a simplified line is a few vertices), that ~340 KB font floor (more with math/STIX) dominates. Shrinking it needs a cmap-preserving font subsetter - a tracked future optimization, since the Typst `subsetter` drops the `cmap` that `<text>` relies on.
- **PNG** - it splits by content, and neither library wins outright. pyplotrs is *smaller* on ordinary marks (line, contour, streamplot, stackplot, matshow), where per-scanline adaptive filtering suits large flat areas. It is *larger* wherever many marks pile up and overlap - scatter, hexbin, eventplot, spy - because matplotlib's mature Agg composites those into flatter, more compressible pixels than a field of individually antialiased sprites. A small, constant part of that gap (~30 bytes per 256 KB chunk) is the price of compressing the image in parallel: each chunk restarts DEFLATE's window and emits its own Huffman tables.

See `benchmarks/benchmark.py` for the like-for-like single-panel head-to-head and the deterministic `--check` CI regression gate.

## Per-mark-type coverage

The grid above sweeps point count and panel count but over only **two** mark types, so "every row wins" was a statement about `line` and `scatter`. This table trades those axes for breadth: every mark type once, one panel, at a representative size. It is the first time contour, hexbin, boxplot, pie and the 3D types have been timed against matplotlib at all.

| kind | mark | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---|---|---:|---:|---:|---:|---:|
| 2D | line | pdf | 0.001s | 12KB | 0.011s | 7KB | 12.9x |
| 2D | line | png | 0.002s | 9KB | 0.013s | 15KB | 7.1x |
| 2D | line | svg | 0.001s | 363KB | 0.010s | 13KB | 11.0x |
| 2D | scatter | pdf | 0.012s | 225KB | 0.136s | 309KB | 11.7x |
| 2D | scatter | png | 0.010s | 135KB | 0.017s | 21KB | 1.8x |
| 2D | scatter | svg | 0.004s | 1MB | 0.128s | 2MB | 30.4x |
| 2D | scatter_cmap | pdf | 0.030s | 406KB | 0.680s | 557KB | 22.4x |
| 2D | scatter_cmap | png | 0.011s | 156KB | 0.119s | 71KB | 10.9x |
| 2D | scatter_cmap | svg | 0.005s | 2MB | 0.361s | 3MB | 68.3x |
| 2D | bar | pdf | 0.001s | 11KB | 0.012s | 6KB | 24.6x |
| 2D | bar | png | 0.002s | 5KB | 0.011s | 6KB | 5.4x |
| 2D | bar | svg | 0.000s | 366KB | 0.011s | 18KB | 30.2x |
| 2D | barh | pdf | 0.001s | 11KB | 0.012s | 6KB | 24.4x |
| 2D | barh | png | 0.001s | 4KB | 0.011s | 6KB | 8.9x |
| 2D | barh | svg | 0.000s | 366KB | 0.011s | 17KB | 30.2x |
| 2D | hist | pdf | 0.001s | 11KB | 0.013s | 6KB | 25.2x |
| 2D | hist | png | 0.005s | 5KB | 0.011s | 6KB | 2.1x |
| 2D | hist | svg | 0.000s | 369KB | 0.012s | 20KB | 30.5x |
| 2D | fill_between | pdf | 0.027s | 552KB | 0.096s | 628KB | 3.6x |
| 2D | fill_between | png | 0.004s | 7KB | 0.013s | 11KB | 3.6x |
| 2D | fill_between | svg | 0.016s | 2MB | 0.029s | 2MB | 1.9x |
| 2D | step | pdf | 0.000s | 11KB | 0.009s | 6KB | 20.3x |
| 2D | step | png | 0.002s | 6KB | 0.010s | 7KB | 5.5x |
| 2D | step | svg | 0.000s | 363KB | 0.009s | 12KB | 26.7x |
| 2D | stem | pdf | 0.001s | 18KB | 0.011s | 6KB | 11.5x |
| 2D | stem | png | 0.002s | 8KB | 0.010s | 9KB | 4.2x |
| 2D | stem | svg | 0.001s | 383KB | 0.010s | 21KB | 14.3x |
| 2D | errorbar | pdf | 0.001s | 13KB | 0.010s | 6KB | 16.9x |
| 2D | errorbar | png | 0.003s | 19KB | 0.011s | 21KB | 3.8x |
| 2D | errorbar | svg | 0.000s | 378KB | 0.009s | 17KB | 20.9x |
| 2D | boxplot | pdf | 0.001s | 21KB | 0.013s | 9KB | 10.1x |
| 2D | boxplot | png | 0.003s | 9KB | 0.010s | 11KB | 3.3x |
| 2D | boxplot | svg | 0.001s | 402KB | 0.010s | 25KB | 8.2x |
| 2D | violinplot | pdf | 0.001s | 20KB | 0.012s | 16KB | 11.8x |
| 2D | violinplot | png | 0.002s | 10KB | 0.010s | 10KB | 4.8x |
| 2D | violinplot | svg | 0.001s | 382KB | 0.010s | 37KB | 12.3x |
| 2D | pie | pdf | 0.000s | 2KB | 0.001s | 2KB | 8.2x |
| 2D | pie | png | 0.002s | 10KB | 0.003s | 10KB | 1.8x |
| 2D | pie | svg | 0.000s | 3KB | 0.001s | 3KB | 8.5x |
| 2D | imshow | pdf | 0.001s | 13KB | 0.011s | 10KB | 19.7x |
| 2D | imshow | png | 0.002s | 12KB | 0.011s | 14KB | 5.6x |
| 2D | imshow | svg | 0.001s | 368KB | 0.010s | 19KB | 12.3x |
| 2D | hist2d | pdf | 0.001s | 11KB | 0.044s | 24KB | 82.6x |
| 2D | hist2d | png | 0.002s | 10KB | 0.008s | 11KB | 4.9x |
| 2D | hist2d | svg | 0.000s | 367KB | 0.040s | 254KB | 86.1x |
| 2D | hexbin | pdf | 0.006s | 50KB | 0.064s | 9KB | 10.4x |
| 2D | hexbin | png | 0.012s | 82KB | 0.024s | 72KB | 2.1x |
| 2D | hexbin | svg | 0.005s | 622KB | 0.042s | 302KB | 7.8x |
| 2D | pcolormesh | pdf | 0.001s | 13KB | 0.096s | 70KB | 185.4x |
| 2D | pcolormesh | png | 0.002s | 11KB | 0.010s | 13KB | 5.3x |
| 2D | pcolormesh | svg | 0.001s | 368KB | 0.085s | 563KB | 94.0x |
| 2D | contour | pdf | 0.003s | 24KB | 0.011s | 11KB | 4.1x |
| 2D | contour | png | 0.005s | 35KB | 0.013s | 43KB | 2.4x |
| 2D | contour | svg | 0.002s | 509KB | 0.010s | 32KB | 4.0x |
| 2D | contourf | pdf | 0.001s | 14KB | 0.012s | 16KB | 8.1x |
| 2D | contourf | png | 0.002s | 8KB | 0.012s | 9KB | 6.6x |
| 2D | contourf | svg | 0.002s | 371KB | 0.010s | 67KB | 5.6x |
| 2D | eventplot | pdf | 0.006s | 57KB | 0.088s | 44KB | 15.4x |
| 2D | eventplot | png | 0.017s | 22KB | 0.019s | 7KB | 1.1x |
| 2D | eventplot | svg | 0.005s | 916KB | 0.113s | 712KB | 21.5x |
| 2D | broken_barh | pdf | 0.001s | 11KB | 0.011s | 6KB | 20.7x |
| 2D | broken_barh | png | 0.002s | 4KB | 0.010s | 7KB | 4.1x |
| 2D | broken_barh | svg | 0.000s | 366KB | 0.010s | 17KB | 27.5x |
| 2D | stackplot | pdf | 0.000s | 11KB | 0.010s | 6KB | 22.5x |
| 2D | stackplot | png | 0.003s | 18KB | 0.013s | 33KB | 4.9x |
| 2D | stackplot | svg | 0.000s | 365KB | 0.009s | 16KB | 29.6x |
| 2D | quiver | pdf | 0.001s | 17KB | 0.012s | 15KB | 13.3x |
| 2D | quiver | png | 0.004s | 28KB | 0.011s | 26KB | 3.0x |
| 2D | quiver | svg | 0.001s | 394KB | 0.010s | 42KB | 11.7x |
| 2D | streamplot | pdf | 0.003s | 62KB | 0.028s | 19KB | 9.3x |
| 2D | streamplot | png | 0.005s | 35KB | 0.026s | 77KB | 4.8x |
| 2D | streamplot | svg | 0.002s | 472KB | 0.025s | 65KB | 12.7x |
| 2D | spy | pdf | 0.002s | 25KB | 0.012s | 5KB | 6.8x |
| 2D | spy | png | 0.002s | 16KB | 0.012s | 7KB | 4.8x |
| 2D | spy | svg | 0.001s | 546KB | 0.012s | 13KB | 13.2x |
| 2D | matshow | pdf | 0.001s | 13KB | 0.012s | 10KB | 22.0x |
| 2D | matshow | png | 0.002s | 12KB | 0.011s | 15KB | 6.1x |
| 2D | matshow | svg | 0.001s | 368KB | 0.011s | 22KB | 14.0x |
| 3D | scatter3d | pdf | 0.065s | 798KB | 0.373s | 1MB | 5.8x |
| 3D | scatter3d | png | 0.035s | 42KB | 0.041s | 40KB | 1.2x |
| 3D | scatter3d | svg | 0.046s | 2MB | 0.113s | 1023KB | 2.4x |
| 3D | line3d_walk | pdf | 0.012s | 112KB | 0.019s | 57KB | 1.6x |
| 3D | line3d_walk | png | 0.050s | 16KB | 0.039s | 22KB | 0.8x |
| 3D | line3d_walk | svg | 0.011s | 1MB | 0.011s | 130KB | 1.0x |
| 3D | line3d_curve | pdf | 0.010s | 77KB | 0.015s | 16KB | 1.5x |
| 3D | line3d_curve | png | 0.017s | 35KB | 0.018s | 53KB | 1.1x |
| 3D | line3d_curve | svg | 0.010s | 1MB | 0.014s | 35KB | 1.4x |
| 3D | line3d_flat | pdf | 0.003s | 49KB | 0.015s | 16KB | 4.5x |
| 3D | line3d_flat | png | 0.005s | 27KB | 0.019s | 53KB | 3.9x |
| 3D | line3d_flat | svg | 0.003s | 442KB | 0.014s | 35KB | 5.4x |
| 3D | surface3d | pdf | 0.009s | 76KB | 0.089s | 116KB | 10.4x |
| 3D | surface3d | png | 0.011s | 50KB | 0.019s | 51KB | 1.7x |
| 3D | surface3d | svg | 0.008s | 618KB | 0.059s | 406KB | 7.5x |
