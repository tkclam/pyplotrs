# pyplotrs benchmark matrix

Export wall-time and file size across **mark x point-count x panels x format**. `N` is the figure's *total* point budget, split evenly over the panels. Times are `save()` / `savefig()`, best of 3 runs after 1 untimed warm-up, at a matched 100 dpi and figure size, on this machine. Regenerate with `.venv/bin/python benchmarks/matrix.py`.

Read the numbers with three caveats. For pyplotrs the timed region is close to the whole pipeline - `line()` only records a mark, and layout, shaping and rendering all happen inside `save()` - whereas matplotlib has built its artists beforehand. Data ingestion is outside the timer for both, as is import time (`import pyplotrs` is ~12 ms against ~237 ms for `matplotlib.pyplot`, which no row here reflects).

The `line` rows use a smooth damped sinusoid, whose consecutive points are near-collinear at export resolution, so both libraries' simplification passes collapse most of them - the drawn geometry is far smaller than `N`. That is the honest shape for a sampled signal, but it is the best case, so `line_dense` repeats it with random `y`, where nothing collapses and every vertex survives. Neither row measures the case where consecutive points are far apart *in x* (unsorted data, or a parametric curve crossing the panel): raster cost tracks the polyline's length in device pixels, not its vertex count, and that shape is a different regime. See the performance guide.

A third caveat applies only to **PNG**: raster export in pyplotrs is multi-threaded, both in rasterizing (an expensive canvas is split into horizontal bands) and in encoding (scanline filtering and DEFLATE both run in parallel). So the `png` rows scale with the core count of the machine that produced them - this run had 20 - and will read lower on a smaller one. PDF and SVG are single-threaded, so their rows are machine-independent in a way the PNG rows are not.

| mark | N | panels | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| line | 10,000 | 1 | pdf | 0.001s | 12KB | 0.011s | 7KB | 18.8x |
| line | 10,000 | 1 | png | 0.002s | 8KB | 0.012s | 15KB | 7.5x |
| line | 10,000 | 1 | svg | 0.001s | 363KB | 0.010s | 13KB | 11.1x |
| line | 10,000 | 4 | pdf | 0.001s | 14KB | 0.034s | 9KB | 34.2x |
| line | 10,000 | 4 | png | 0.004s | 26KB | 0.042s | 30KB | 11.0x |
| line | 10,000 | 4 | svg | 0.001s | 377KB | 0.032s | 38KB | 33.5x |
| line | 10,000 | 9 | pdf | 0.002s | 19KB | 0.069s | 13KB | 41.4x |
| line | 10,000 | 9 | png | 0.007s | 51KB | 0.093s | 99KB | 13.3x |
| line | 10,000 | 9 | svg | 0.002s | 398KB | 0.069s | 81KB | 44.0x |
| line | 100,000 | 1 | pdf | 0.001s | 12KB | 0.012s | 7KB | 9.5x |
| line | 100,000 | 1 | png | 0.002s | 8KB | 0.013s | 15KB | 6.2x |
| line | 100,000 | 1 | svg | 0.001s | 363KB | 0.011s | 13KB | 8.7x |
| line | 100,000 | 4 | pdf | 0.002s | 14KB | 0.034s | 9KB | 19.4x |
| line | 100,000 | 4 | png | 0.004s | 26KB | 0.043s | 31KB | 10.6x |
| line | 100,000 | 4 | svg | 0.002s | 377KB | 0.032s | 38KB | 20.0x |
| line | 100,000 | 9 | pdf | 0.002s | 18KB | 0.070s | 13KB | 29.8x |
| line | 100,000 | 9 | png | 0.007s | 51KB | 0.093s | 101KB | 13.4x |
| line | 100,000 | 9 | svg | 0.002s | 398KB | 0.070s | 81KB | 32.4x |
| line | 1,000,000 | 1 | pdf | 0.013s | 12KB | 0.025s | 7KB | 2.0x |
| line | 1,000,000 | 1 | png | 0.011s | 8KB | 0.035s | 15KB | 3.3x |
| line | 1,000,000 | 1 | svg | 0.010s | 363KB | 0.024s | 13KB | 2.4x |
| line | 1,000,000 | 4 | pdf | 0.009s | 14KB | 0.047s | 9KB | 5.3x |
| line | 1,000,000 | 4 | png | 0.012s | 26KB | 0.068s | 31KB | 5.7x |
| line | 1,000,000 | 4 | svg | 0.009s | 377KB | 0.048s | 38KB | 5.3x |
| line | 1,000,000 | 9 | pdf | 0.010s | 18KB | 0.087s | 13KB | 8.8x |
| line | 1,000,000 | 9 | png | 0.015s | 51KB | 0.120s | 101KB | 8.2x |
| line | 1,000,000 | 9 | svg | 0.010s | 398KB | 0.085s | 81KB | 8.7x |
| line_dense | 10,000 | 1 | pdf | 0.002s | 41KB | 0.015s | 45KB | 8.2x |
| line_dense | 10,000 | 1 | png | 0.034s | 8KB | 0.049s | 10KB | 1.5x |
| line_dense | 10,000 | 1 | svg | 0.001s | 414KB | 0.010s | 107KB | 10.0x |
| line_dense | 10,000 | 4 | pdf | 0.004s | 75KB | 0.045s | 84KB | 12.0x |
| line_dense | 10,000 | 4 | png | 0.011s | 28KB | 0.073s | 25KB | 6.4x |
| line_dense | 10,000 | 4 | svg | 0.002s | 478KB | 0.034s | 212KB | 17.3x |
| line_dense | 10,000 | 9 | pdf | 0.005s | 85KB | 0.083s | 76KB | 17.2x |
| line_dense | 10,000 | 9 | png | 0.013s | 57KB | 0.124s | 105KB | 9.9x |
| line_dense | 10,000 | 9 | svg | 0.003s | 526KB | 0.072s | 258KB | 25.3x |
| line_dense | 100,000 | 1 | pdf | 0.005s | 101KB | 0.018s | 52KB | 3.5x |
| line_dense | 100,000 | 1 | png | 0.136s | 7KB | 0.102s | 7KB | 0.8x |
| line_dense | 100,000 | 1 | svg | 0.003s | 522KB | 0.012s | 126KB | 3.9x |
| line_dense | 100,000 | 4 | pdf | 0.009s | 182KB | 0.060s | 162KB | 6.4x |
| line_dense | 100,000 | 4 | png | 0.028s | 25KB | 0.207s | 18KB | 7.4x |
| line_dense | 100,000 | 4 | svg | 0.005s | 676KB | 0.038s | 418KB | 7.6x |
| line_dense | 100,000 | 9 | pdf | 0.014s | 264KB | 0.123s | 310KB | 8.9x |
| line_dense | 100,000 | 9 | png | 0.040s | 50KB | 0.317s | 67KB | 7.9x |
| line_dense | 100,000 | 9 | svg | 0.007s | 842KB | 0.076s | 822KB | 10.3x |
| scatter | 10,000 | 1 | pdf | 0.006s | 118KB | 0.075s | 158KB | 12.5x |
| scatter | 10,000 | 1 | png | 0.009s | 120KB | 0.018s | 50KB | 1.9x |
| scatter | 10,000 | 1 | svg | 0.002s | 823KB | 0.072s | 1MB | 29.7x |
| scatter | 10,000 | 4 | pdf | 0.006s | 118KB | 0.101s | 161KB | 15.9x |
| scatter | 10,000 | 4 | png | 0.009s | 191KB | 0.050s | 85KB | 5.8x |
| scatter | 10,000 | 4 | svg | 0.003s | 835KB | 0.098s | 1MB | 38.6x |
| scatter | 10,000 | 9 | pdf | 0.007s | 120KB | 0.145s | 167KB | 20.5x |
| scatter | 10,000 | 9 | png | 0.008s | 202KB | 0.110s | 160KB | 12.9x |
| scatter | 10,000 | 9 | svg | 0.003s | 851KB | 0.139s | 1MB | 42.8x |
| scatter | 100,000 | 1 | pdf | 0.059s | 1MB | 0.674s | 1MB | 11.4x |
| scatter | 100,000 | 1 | png | 0.019s | 49KB | 0.045s | 9KB | 2.4x |
| scatter | 100,000 | 1 | svg | 0.022s | 5MB | 0.642s | 10MB | 29.0x |
| scatter | 100,000 | 4 | pdf | 0.058s | 1MB | 0.698s | 1MB | 12.0x |
| scatter | 100,000 | 4 | png | 0.017s | 313KB | 0.074s | 23KB | 4.5x |
| scatter | 100,000 | 4 | svg | 0.021s | 5MB | 0.674s | 10MB | 31.3x |
| scatter | 100,000 | 9 | pdf | 0.058s | 1MB | 0.746s | 1MB | 12.9x |
| scatter | 100,000 | 9 | png | 0.021s | 726KB | 0.127s | 138KB | 6.1x |
| scatter | 100,000 | 9 | svg | 0.022s | 5MB | 0.717s | 10MB | 33.0x |

**Reading it.** `speedup` is matplotlib-time / pyplotrs-time (>1 means pyplotrs exports faster). pyplotrs is faster on almost every cell, and the lead is largest on **vector** export (PDF/SVG) - the editable-text formats the project exists for - where line paths are simplified and scatter markers are instanced (one reused XObject/`<use>`). The lead *grows with panel count*: pyplotrs' single-pass layout amortizes per-panel chrome that matplotlib re-solves per axes.

**Where matplotlib wins.** 1 of 63 rows come out below 1.0x: `line_dense` N=100,000 1 panel(s) png (0.8x). These are kept in the table rather than trimmed out of it - a benchmark with no losses in it is a benchmark that has not looked hard enough.

**On file size**, each format has its own story:

- **PDF** - pyplotrs is smaller on 9 of 21 rows (instanced markers and path simplification), and *larger* on the rest. The difference is the embedded font: pyplotrs subsets and embeds it so the file renders identically anywhere, which is a fixed cost a sparse figure never earns back, while matplotlib leaves a simple line plot's text referencing a system font.
- **SVG, marker-heavy (scatter)** - pyplotrs is *smaller* **and** ~29-43x faster: markers are one `<defs>` glyph and a `<use>` per point, versus matplotlib's per-point path, which outweighs even the embedded font.
- **SVG, sparse geometry (line)** - pyplotrs is *larger*, and on purpose: it **embeds the bundled font** so the SVG is self-contained and renders identically on any machine (a pyplotrs goal - no system-font drift), with real editable `<text>`; matplotlib only *references* a system font by name. Once the geometry is tiny (a simplified line is a few vertices), that ~340 KB font floor (more with math/STIX) dominates. Shrinking it needs a cmap-preserving font subsetter - a tracked future optimization, since the Typst `subsetter` drops the `cmap` that `<text>` relies on.
- **PNG** - it splits by content, and neither library wins outright. pyplotrs is *smaller* on ordinary marks (line, contour, streamplot, stackplot, matshow), where per-scanline adaptive filtering suits large flat areas. It is *larger* wherever many marks pile up and overlap - scatter, hexbin, eventplot, spy - because matplotlib's mature Agg composites those into flatter, more compressible pixels than a field of individually antialiased sprites. A small, constant part of that gap (~30 bytes per 256 KB chunk) is the price of compressing the image in parallel: each chunk restarts DEFLATE's window and emits its own Huffman tables.

See `benchmarks/benchmark.py` for the like-for-like single-panel head-to-head and the deterministic `--check` CI regression gate.

## Per-mark-type coverage

The grid above sweeps point count and panel count but over only **two** mark types, so "every row wins" was a statement about `line` and `scatter`. This table trades those axes for breadth: every mark type once, one panel, at a representative size. It is the first time contour, hexbin, boxplot, pie and the 3D types have been timed against matplotlib at all.

| kind | mark | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---|---|---:|---:|---:|---:|---:|
| 2D | line | pdf | 0.001s | 12KB | 0.012s | 7KB | 12.9x |
| 2D | line | png | 0.002s | 8KB | 0.013s | 15KB | 6.7x |
| 2D | line | svg | 0.001s | 363KB | 0.011s | 13KB | 11.8x |
| 2D | scatter | pdf | 0.012s | 225KB | 0.147s | 309KB | 12.3x |
| 2D | scatter | png | 0.010s | 135KB | 0.019s | 21KB | 1.8x |
| 2D | scatter | svg | 0.005s | 1MB | 0.138s | 2MB | 30.3x |
| 2D | scatter_cmap | pdf | 0.032s | 406KB | 0.693s | 557KB | 21.6x |
| 2D | scatter_cmap | png | 0.011s | 156KB | 0.124s | 71KB | 11.0x |
| 2D | scatter_cmap | svg | 0.006s | 2MB | 0.367s | 3MB | 64.7x |
| 2D | bar | pdf | 0.000s | 11KB | 0.013s | 6KB | 26.3x |
| 2D | bar | png | 0.002s | 5KB | 0.011s | 6KB | 5.3x |
| 2D | bar | svg | 0.000s | 366KB | 0.012s | 18KB | 29.4x |
| 2D | barh | pdf | 0.001s | 11KB | 0.013s | 6KB | 24.6x |
| 2D | barh | png | 0.001s | 4KB | 0.011s | 6KB | 9.3x |
| 2D | barh | svg | 0.000s | 366KB | 0.012s | 17KB | 29.2x |
| 2D | hist | pdf | 0.001s | 11KB | 0.014s | 6KB | 26.1x |
| 2D | hist | png | 0.005s | 5KB | 0.012s | 6KB | 2.2x |
| 2D | hist | svg | 0.000s | 369KB | 0.013s | 20KB | 31.5x |
| 2D | fill_between | pdf | 0.027s | 582KB | 0.101s | 628KB | 3.7x |
| 2D | fill_between | png | 0.004s | 7KB | 0.013s | 11KB | 3.5x |
| 2D | fill_between | svg | 0.016s | 2MB | 0.030s | 2MB | 1.8x |
| 2D | step | pdf | 0.000s | 11KB | 0.010s | 6KB | 20.5x |
| 2D | step | png | 0.002s | 5KB | 0.010s | 7KB | 5.4x |
| 2D | step | svg | 0.000s | 363KB | 0.010s | 12KB | 28.0x |
| 2D | stem | pdf | 0.001s | 18KB | 0.012s | 6KB | 11.9x |
| 2D | stem | png | 0.003s | 8KB | 0.011s | 9KB | 4.1x |
| 2D | stem | svg | 0.001s | 383KB | 0.010s | 21KB | 14.3x |
| 2D | errorbar | pdf | 0.001s | 13KB | 0.011s | 6KB | 16.6x |
| 2D | errorbar | png | 0.003s | 19KB | 0.012s | 21KB | 4.0x |
| 2D | errorbar | svg | 0.000s | 378KB | 0.010s | 17KB | 21.2x |
| 2D | boxplot | pdf | 0.001s | 21KB | 0.014s | 9KB | 10.2x |
| 2D | boxplot | png | 0.003s | 9KB | 0.010s | 11KB | 3.7x |
| 2D | boxplot | svg | 0.001s | 402KB | 0.011s | 25KB | 8.5x |
| 2D | violinplot | pdf | 0.001s | 20KB | 0.012s | 16KB | 11.4x |
| 2D | violinplot | png | 0.002s | 10KB | 0.010s | 10KB | 4.9x |
| 2D | violinplot | svg | 0.001s | 382KB | 0.010s | 37KB | 13.2x |
| 2D | pie | pdf | 0.000s | 2KB | 0.001s | 2KB | 9.1x |
| 2D | pie | png | 0.002s | 12KB | 0.003s | 10KB | 1.7x |
| 2D | pie | svg | 0.000s | 3KB | 0.001s | 3KB | 9.9x |
| 2D | imshow | pdf | 0.001s | 13KB | 0.011s | 10KB | 18.5x |
| 2D | imshow | png | 0.002s | 12KB | 0.011s | 14KB | 5.6x |
| 2D | imshow | svg | 0.001s | 368KB | 0.011s | 19KB | 13.4x |
| 2D | hist2d | pdf | 0.001s | 11KB | 0.047s | 24KB | 80.9x |
| 2D | hist2d | png | 0.002s | 10KB | 0.009s | 11KB | 5.2x |
| 2D | hist2d | svg | 0.000s | 367KB | 0.043s | 254KB | 89.2x |
| 2D | hexbin | pdf | 0.007s | 52KB | 0.067s | 9KB | 9.6x |
| 2D | hexbin | png | 0.026s | 88KB | 0.025s | 72KB | 1.0x |
| 2D | hexbin | svg | 0.006s | 712KB | 0.044s | 302KB | 7.0x |
| 2D | pcolormesh | pdf | 0.001s | 13KB | 0.102s | 70KB | 190.8x |
| 2D | pcolormesh | png | 0.002s | 12KB | 0.011s | 13KB | 5.7x |
| 2D | pcolormesh | svg | 0.001s | 368KB | 0.088s | 563KB | 91.0x |
| 2D | contour | pdf | 0.001s | 16KB | 0.012s | 11KB | 10.2x |
| 2D | contour | png | 0.003s | 20KB | 0.014s | 43KB | 4.2x |
| 2D | contour | svg | 0.001s | 381KB | 0.011s | 32KB | 9.5x |
| 2D | contourf | pdf | 0.002s | 14KB | 0.013s | 16KB | 8.0x |
| 2D | contourf | png | 0.002s | 7KB | 0.012s | 9KB | 7.2x |
| 2D | contourf | svg | 0.002s | 370KB | 0.011s | 67KB | 6.2x |
| 2D | eventplot | pdf | 0.006s | 57KB | 0.092s | 44KB | 15.8x |
| 2D | eventplot | png | 0.018s | 22KB | 0.020s | 7KB | 1.1x |
| 2D | eventplot | svg | 0.005s | 916KB | 0.119s | 712KB | 22.4x |
| 2D | broken_barh | pdf | 0.001s | 11KB | 0.011s | 6KB | 20.4x |
| 2D | broken_barh | png | 0.002s | 4KB | 0.011s | 7KB | 4.3x |
| 2D | broken_barh | svg | 0.000s | 366KB | 0.011s | 17KB | 25.7x |
| 2D | stackplot | pdf | 0.000s | 11KB | 0.010s | 6KB | 22.5x |
| 2D | stackplot | png | 0.003s | 18KB | 0.013s | 33KB | 5.0x |
| 2D | stackplot | svg | 0.000s | 365KB | 0.010s | 16KB | 26.3x |
| 2D | quiver | pdf | 0.001s | 17KB | 0.013s | 15KB | 13.2x |
| 2D | quiver | png | 0.003s | 27KB | 0.012s | 26KB | 3.4x |
| 2D | quiver | svg | 0.001s | 394KB | 0.012s | 42KB | 12.3x |
| 2D | streamplot | pdf | 0.003s | 62KB | 0.030s | 19KB | 9.3x |
| 2D | streamplot | png | 0.005s | 34KB | 0.027s | 77KB | 5.0x |
| 2D | streamplot | svg | 0.002s | 472KB | 0.026s | 65KB | 13.3x |
| 2D | spy | pdf | 0.002s | 25KB | 0.013s | 5KB | 7.1x |
| 2D | spy | png | 0.002s | 16KB | 0.013s | 7KB | 5.2x |
| 2D | spy | svg | 0.001s | 546KB | 0.013s | 13KB | 12.8x |
| 2D | matshow | pdf | 0.001s | 13KB | 0.013s | 10KB | 22.0x |
| 2D | matshow | png | 0.002s | 12KB | 0.012s | 15KB | 6.1x |
| 2D | matshow | svg | 0.001s | 368KB | 0.012s | 22KB | 14.5x |
| 3D | scatter3d | pdf | 0.064s | 798KB | 0.390s | 1MB | 6.1x |
| 3D | scatter3d | png | 0.036s | 42KB | 0.043s | 40KB | 1.2x |
| 3D | scatter3d | svg | 0.048s | 2MB | 0.114s | 1023KB | 2.4x |
| 3D | line3d_walk | pdf | 0.012s | 112KB | 0.020s | 57KB | 1.6x |
| 3D | line3d_walk | png | 0.052s | 16KB | 0.041s | 22KB | 0.8x |
| 3D | line3d_walk | svg | 0.012s | 1MB | 0.012s | 130KB | 1.1x |
| 3D | line3d_curve | pdf | 0.010s | 77KB | 0.016s | 16KB | 1.6x |
| 3D | line3d_curve | png | 0.018s | 35KB | 0.019s | 53KB | 1.1x |
| 3D | line3d_curve | svg | 0.011s | 1MB | 0.015s | 35KB | 1.4x |
| 3D | line3d_flat | pdf | 0.003s | 49KB | 0.016s | 16KB | 4.8x |
| 3D | line3d_flat | png | 0.005s | 27KB | 0.020s | 53KB | 4.2x |
| 3D | line3d_flat | svg | 0.003s | 442KB | 0.014s | 35KB | 5.4x |
| 3D | surface3d | pdf | 0.009s | 76KB | 0.094s | 116KB | 10.3x |
| 3D | surface3d | png | 0.012s | 50KB | 0.020s | 51KB | 1.7x |
| 3D | surface3d | svg | 0.008s | 618KB | 0.062s | 406KB | 7.8x |
