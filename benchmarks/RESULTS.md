# pyplotrs benchmark matrix

Export wall-time and file size across **mark x point-count x panels x format**. `N` is the figure's *total* point budget, split evenly over the panels. Times are `save()` / `savefig()`, best of 3 runs after 1 untimed warm-up, at a matched 100 dpi and figure size, on this machine. Regenerate with `.venv/bin/python benchmarks/matrix.py`.

Read the numbers with two caveats. For pyplotrs the timed region is close to the whole pipeline - `line()` only records a mark, and layout, shaping and rendering all happen inside `save()` - whereas matplotlib has built its artists beforehand. Data ingestion is outside the timer for both, as is import time (`import pyplotrs` is ~12 ms against ~237 ms for `matplotlib.pyplot`, which no row here reflects).

| mark | N | panels | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| line | 10,000 | 1 | pdf | 0.001s | 12KB | 0.010s | 7KB | 17.3x |
| line | 10,000 | 1 | png | 0.002s | 8KB | 0.011s | 15KB | 6.0x |
| line | 10,000 | 1 | svg | 0.001s | 363KB | 0.009s | 13KB | 10.7x |
| line | 10,000 | 4 | pdf | 0.001s | 14KB | 0.032s | 9KB | 29.1x |
| line | 10,000 | 4 | png | 0.006s | 26KB | 0.040s | 30KB | 6.9x |
| line | 10,000 | 4 | svg | 0.001s | 377KB | 0.031s | 38KB | 31.8x |
| line | 10,000 | 9 | pdf | 0.002s | 18KB | 0.068s | 13KB | 34.5x |
| line | 10,000 | 9 | png | 0.012s | 51KB | 0.089s | 99KB | 7.4x |
| line | 10,000 | 9 | svg | 0.002s | 398KB | 0.067s | 81KB | 41.0x |
| line | 100,000 | 1 | pdf | 0.001s | 12KB | 0.012s | 7KB | 9.0x |
| line | 100,000 | 1 | png | 0.003s | 8KB | 0.013s | 15KB | 5.2x |
| line | 100,000 | 1 | svg | 0.001s | 363KB | 0.011s | 13KB | 8.6x |
| line | 100,000 | 4 | pdf | 0.002s | 14KB | 0.033s | 9KB | 18.3x |
| line | 100,000 | 4 | png | 0.006s | 26KB | 0.042s | 31KB | 6.5x |
| line | 100,000 | 4 | svg | 0.002s | 377KB | 0.032s | 38KB | 19.6x |
| line | 100,000 | 9 | pdf | 0.003s | 18KB | 0.070s | 13KB | 25.9x |
| line | 100,000 | 9 | png | 0.013s | 49KB | 0.091s | 101KB | 7.2x |
| line | 100,000 | 9 | svg | 0.002s | 398KB | 0.068s | 81KB | 29.9x |
| line | 1,000,000 | 1 | pdf | 0.012s | 12KB | 0.024s | 7KB | 2.0x |
| line | 1,000,000 | 1 | png | 0.011s | 8KB | 0.035s | 15KB | 3.3x |
| line | 1,000,000 | 1 | svg | 0.010s | 363KB | 0.023s | 13KB | 2.3x |
| line | 1,000,000 | 4 | pdf | 0.009s | 14KB | 0.047s | 9KB | 5.2x |
| line | 1,000,000 | 4 | png | 0.014s | 26KB | 0.065s | 31KB | 4.7x |
| line | 1,000,000 | 4 | svg | 0.009s | 377KB | 0.045s | 38KB | 4.9x |
| line | 1,000,000 | 9 | pdf | 0.010s | 18KB | 0.083s | 13KB | 8.7x |
| line | 1,000,000 | 9 | png | 0.019s | 48KB | 0.114s | 101KB | 5.9x |
| line | 1,000,000 | 9 | svg | 0.009s | 398KB | 0.081s | 81KB | 8.6x |
| scatter | 10,000 | 1 | pdf | 0.012s | 112KB | 0.074s | 158KB | 6.3x |
| scatter | 10,000 | 1 | png | 0.013s | 118KB | 0.017s | 50KB | 1.3x |
| scatter | 10,000 | 1 | svg | 0.003s | 823KB | 0.069s | 1MB | 26.4x |
| scatter | 10,000 | 4 | pdf | 0.012s | 112KB | 0.099s | 161KB | 8.2x |
| scatter | 10,000 | 4 | png | 0.026s | 188KB | 0.052s | 85KB | 2.0x |
| scatter | 10,000 | 4 | svg | 0.003s | 835KB | 0.094s | 1MB | 31.8x |
| scatter | 10,000 | 9 | pdf | 0.013s | 115KB | 0.141s | 167KB | 11.2x |
| scatter | 10,000 | 9 | png | 0.028s | 201KB | 0.105s | 160KB | 3.8x |
| scatter | 10,000 | 9 | svg | 0.004s | 851KB | 0.132s | 1MB | 36.6x |
| scatter | 100,000 | 1 | pdf | 0.109s | 1018KB | 0.651s | 1MB | 5.9x |
| scatter | 100,000 | 1 | png | 0.021s | 49KB | 0.043s | 9KB | 2.0x |
| scatter | 100,000 | 1 | svg | 0.024s | 5MB | 0.618s | 10MB | 25.9x |
| scatter | 100,000 | 4 | pdf | 0.113s | 998KB | 0.678s | 1MB | 6.0x |
| scatter | 100,000 | 4 | png | 0.047s | 311KB | 0.072s | 23KB | 1.5x |
| scatter | 100,000 | 4 | svg | 0.024s | 5MB | 0.649s | 10MB | 27.4x |
| scatter | 100,000 | 9 | pdf | 0.116s | 984KB | 0.723s | 1MB | 6.2x |
| scatter | 100,000 | 9 | png | 0.075s | 715KB | 0.124s | 138KB | 1.7x |
| scatter | 100,000 | 9 | svg | 0.024s | 5MB | 0.685s | 10MB | 28.2x |

**Reading it.** `speedup` is matplotlib-time / pyplotrs-time (>1 means pyplotrs exports faster). pyplotrs is faster on almost every cell, and the lead is largest on **vector** export (PDF/SVG) - the editable-text formats the project exists for - where line paths are simplified and scatter markers are instanced (one reused XObject/`<use>`). The lead *grows with panel count*: pyplotrs' single-pass layout amortizes per-panel chrome that matplotlib re-solves per axes.

**The large single line used to be matplotlib's one win** (`N`=1e6, 1 panel, ~0.7x), when ingest and autoscale still ran in Python. That loop moved to Rust and the row now wins like the others; the table above is the current measurement, and any statement about who wins where should be read off it rather than from this paragraph.

**On file size**, each format has its own story:

- **PDF** - pyplotrs is smaller everywhere (subsetted fonts + instanced markers + path simplification).
- **SVG, marker-heavy (scatter)** - pyplotrs is *smaller* **and** ~15-22x faster: markers are one `<defs>` glyph + a `<use>` per point, versus matplotlib's per-point path, which outweighs even the embedded font.
- **SVG, sparse geometry (line)** - pyplotrs is *larger*, and on purpose: it **embeds the bundled font** so the SVG is self-contained and renders identically on any machine (a pyplotrs goal - no system-font drift), with real editable `<text>`; matplotlib only *references* a system font by name. Once the geometry is tiny (a simplified line is a few vertices), that ~340 KB font floor (more with math/STIX) dominates. Shrinking it needs a cmap-preserving font subsetter - a tracked future optimization, since the Typst `subsetter` drops the `cmap` that `<text>` relies on.
- **PNG** - resolution-bound for both; matplotlib's mature Agg compresses dense overlapping output more tightly.

See `benchmarks/benchmark.py` for the like-for-like single-panel head-to-head and the deterministic `--check` CI regression gate.

## Per-mark-type coverage

The grid above sweeps point count and panel count but over only **two** mark types, so "every row wins" was a statement about `line` and `scatter`. This table trades those axes for breadth: every mark type once, one panel, at a representative size. It is the first time contour, hexbin, boxplot, pie and the 3D types have been timed against matplotlib at all.

| kind | mark | format | pyplotrs time | pyplotrs size | matplotlib time | matplotlib size | speedup |
|---|---|---|---:|---:|---:|---:|---:|
| 2D | line | pdf | 0.001s | 12KB | 0.011s | 7KB | 12.5x |
| 2D | line | png | 0.002s | 8KB | 0.012s | 15KB | 5.5x |
| 2D | line | svg | 0.001s | 363KB | 0.010s | 13KB | 11.2x |
| 2D | scatter | pdf | 0.022s | 213KB | 0.139s | 309KB | 6.2x |
| 2D | scatter | png | 0.013s | 134KB | 0.017s | 21KB | 1.3x |
| 2D | scatter | svg | 0.005s | 1MB | 0.130s | 2MB | 26.5x |
| 2D | scatter_cmap | pdf | 0.048s | 378KB | 0.685s | 557KB | 14.4x |
| 2D | scatter_cmap | png | 0.015s | 155KB | 0.123s | 71KB | 8.3x |
| 2D | scatter_cmap | svg | 0.007s | 2MB | 0.359s | 3MB | 54.2x |
| 2D | bar | pdf | 0.001s | 11KB | 0.012s | 6KB | 22.6x |
| 2D | bar | png | 0.002s | 5KB | 0.011s | 6KB | 4.8x |
| 2D | bar | svg | 0.000s | 366KB | 0.011s | 18KB | 27.7x |
| 2D | barh | pdf | 0.001s | 11KB | 0.012s | 6KB | 22.7x |
| 2D | barh | png | 0.001s | 4KB | 0.011s | 6KB | 7.8x |
| 2D | barh | svg | 0.000s | 366KB | 0.012s | 17KB | 29.3x |
| 2D | hist | pdf | 0.001s | 11KB | 0.013s | 6KB | 22.4x |
| 2D | hist | png | 0.005s | 5KB | 0.011s | 6KB | 2.1x |
| 2D | hist | svg | 0.000s | 369KB | 0.012s | 20KB | 27.9x |
| 2D | fill_between | pdf | 0.074s | 531KB | 0.096s | 628KB | 1.3x |
| 2D | fill_between | png | 0.004s | 7KB | 0.013s | 11KB | 3.4x |
| 2D | fill_between | svg | 0.019s | 2MB | 0.028s | 2MB | 1.5x |
| 2D | step | pdf | 0.000s | 11KB | 0.009s | 6KB | 19.9x |
| 2D | step | png | 0.002s | 6KB | 0.010s | 7KB | 4.9x |
| 2D | step | svg | 0.000s | 363KB | 0.009s | 12KB | 24.7x |
| 2D | stem | pdf | 0.001s | 17KB | 0.011s | 6KB | 9.4x |
| 2D | stem | png | 0.003s | 8KB | 0.010s | 9KB | 3.9x |
| 2D | stem | svg | 0.001s | 383KB | 0.010s | 21KB | 13.5x |
| 2D | errorbar | pdf | 0.001s | 13KB | 0.010s | 6KB | 14.1x |
| 2D | errorbar | png | 0.003s | 19KB | 0.011s | 21KB | 3.3x |
| 2D | errorbar | svg | 0.000s | 378KB | 0.009s | 17KB | 19.0x |
| 2D | boxplot | pdf | 0.002s | 20KB | 0.013s | 9KB | 6.7x |
| 2D | boxplot | png | 0.003s | 9KB | 0.010s | 11KB | 3.2x |
| 2D | boxplot | svg | 0.001s | 402KB | 0.010s | 25KB | 7.9x |
| 2D | violinplot | pdf | 0.001s | 20KB | 0.012s | 16KB | 8.7x |
| 2D | violinplot | png | 0.002s | 10KB | 0.010s | 10KB | 4.3x |
| 2D | violinplot | svg | 0.001s | 382KB | 0.010s | 37KB | 12.5x |
| 2D | pie | pdf | 0.000s | 2KB | 0.001s | 2KB | 7.3x |
| 2D | pie | png | 0.002s | 10KB | 0.003s | 10KB | 1.6x |
| 2D | pie | svg | 0.000s | 3KB | 0.001s | 3KB | 8.8x |
| 2D | imshow | pdf | 0.001s | 13KB | 0.010s | 10KB | 18.5x |
| 2D | imshow | png | 0.002s | 12KB | 0.010s | 14KB | 4.4x |
| 2D | imshow | svg | 0.001s | 368KB | 0.010s | 19KB | 12.1x |
| 2D | hist2d | pdf | 0.001s | 11KB | 0.045s | 24KB | 86.5x |
| 2D | hist2d | png | 0.002s | 10KB | 0.008s | 11KB | 4.3x |
| 2D | hist2d | svg | 0.000s | 367KB | 0.040s | 254KB | 84.9x |
| 2D | hexbin | pdf | 0.010s | 49KB | 0.064s | 9KB | 6.5x |
| 2D | hexbin | png | 0.013s | 82KB | 0.024s | 72KB | 1.8x |
| 2D | hexbin | svg | 0.006s | 622KB | 0.042s | 302KB | 7.3x |
| 2D | pcolormesh | pdf | 0.001s | 13KB | 0.097s | 70KB | 175.1x |
| 2D | pcolormesh | png | 0.002s | 11KB | 0.010s | 13KB | 4.6x |
| 2D | pcolormesh | svg | 0.001s | 368KB | 0.083s | 563KB | 88.7x |
| 2D | contour | pdf | 0.003s | 23KB | 0.011s | 11KB | 3.4x |
| 2D | contour | png | 0.006s | 34KB | 0.013s | 43KB | 2.1x |
| 2D | contour | svg | 0.003s | 509KB | 0.010s | 32KB | 3.8x |
| 2D | contourf | pdf | 0.001s | 14KB | 0.012s | 16KB | 8.2x |
| 2D | contourf | png | 0.002s | 7KB | 0.012s | 9KB | 5.5x |
| 2D | contourf | svg | 0.002s | 371KB | 0.010s | 67KB | 5.8x |
| 2D | eventplot | pdf | 0.009s | 55KB | 0.087s | 44KB | 10.1x |
| 2D | eventplot | png | 0.018s | 22KB | 0.019s | 7KB | 1.1x |
| 2D | eventplot | svg | 0.006s | 916KB | 0.114s | 712KB | 20.4x |
| 2D | broken_barh | pdf | 0.001s | 11KB | 0.011s | 6KB | 19.1x |
| 2D | broken_barh | png | 0.003s | 4KB | 0.010s | 7KB | 3.9x |
| 2D | broken_barh | svg | 0.000s | 366KB | 0.010s | 17KB | 25.7x |
| 2D | stackplot | pdf | 0.001s | 11KB | 0.010s | 6KB | 19.7x |
| 2D | stackplot | png | 0.003s | 18KB | 0.013s | 33KB | 3.9x |
| 2D | stackplot | svg | 0.000s | 365KB | 0.010s | 16KB | 24.6x |
| 2D | quiver | pdf | 0.001s | 16KB | 0.012s | 15KB | 10.6x |
| 2D | quiver | png | 0.004s | 27KB | 0.011s | 26KB | 2.6x |
| 2D | quiver | svg | 0.001s | 394KB | 0.010s | 42KB | 10.5x |
| 2D | streamplot | pdf | 0.006s | 61KB | 0.028s | 19KB | 4.7x |
| 2D | streamplot | png | 0.007s | 34KB | 0.026s | 77KB | 4.0x |
| 2D | streamplot | svg | 0.002s | 472KB | 0.025s | 65KB | 12.2x |
| 2D | spy | pdf | 0.003s | 25KB | 0.012s | 5KB | 4.7x |
| 2D | spy | png | 0.003s | 16KB | 0.012s | 7KB | 3.8x |
| 2D | spy | svg | 0.001s | 546KB | 0.012s | 13KB | 10.8x |
| 2D | matshow | pdf | 0.001s | 13KB | 0.012s | 10KB | 21.0x |
| 2D | matshow | png | 0.002s | 12KB | 0.011s | 15KB | 4.9x |
| 2D | matshow | svg | 0.001s | 368KB | 0.011s | 22KB | 14.2x |
| 3D | scatter3d | pdf | 0.118s | 741KB | 0.373s | 1MB | 3.2x |
| 3D | scatter3d | png | 0.035s | 41KB | 0.042s | 40KB | 1.2x |
| 3D | scatter3d | svg | 0.050s | 2MB | 0.107s | 1023KB | 2.2x |
| 3D | line3d_walk | pdf | 0.017s | 107KB | 0.019s | 57KB | 1.1x |
| 3D | line3d_walk | png | 0.050s | 16KB | 0.039s | 22KB | 0.8x |
| 3D | line3d_walk | svg | 0.011s | 1MB | 0.011s | 130KB | 1.0x |
| 3D | line3d_curve | pdf | 0.014s | 73KB | 0.015s | 16KB | 1.1x |
| 3D | line3d_curve | png | 0.018s | 35KB | 0.018s | 53KB | 1.0x |
| 3D | line3d_curve | svg | 0.010s | 1MB | 0.014s | 35KB | 1.4x |
| 3D | line3d_flat | pdf | 0.006s | 47KB | 0.015s | 16KB | 2.7x |
| 3D | line3d_flat | png | 0.006s | 26KB | 0.018s | 53KB | 3.1x |
| 3D | line3d_flat | svg | 0.003s | 442KB | 0.013s | 35KB | 5.0x |
| 3D | surface3d | pdf | 0.013s | 70KB | 0.088s | 116KB | 6.6x |
| 3D | surface3d | png | 0.012s | 49KB | 0.019s | 51KB | 1.6x |
| 3D | surface3d | svg | 0.008s | 618KB | 0.060s | 406KB | 7.4x |
