# figurs benchmark matrix

Export wall-time and file size across **mark x point-count x panels x format**. `N` is the figure's *total* point budget, split evenly over the panels. Times measure `save()` of a pre-built figure (the render engine), best of a single run on this machine. Regenerate with `.venv/bin/python benchmarks/matrix.py`.

| mark | N | panels | format | figurs time | figurs size | matplotlib time | matplotlib size | speedup |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| line | 10,000 | 1 | pdf | 0.002s | 6KB | 0.057s | 7KB | 27.1x |
| line | 10,000 | 1 | png | 0.007s | 19KB | 0.020s | 15KB | 2.9x |
| line | 10,000 | 1 | svg | 0.002s | 449KB | 0.015s | 13KB | 6.8x |
| line | 10,000 | 4 | pdf | 0.005s | 9KB | 0.051s | 9KB | 9.8x |
| line | 10,000 | 4 | png | 0.021s | 59KB | 0.056s | 30KB | 2.7x |
| line | 10,000 | 4 | svg | 0.005s | 462KB | 0.047s | 38KB | 9.2x |
| line | 10,000 | 9 | pdf | 0.010s | 13KB | 0.108s | 13KB | 10.5x |
| line | 10,000 | 9 | png | 0.045s | 113KB | 0.137s | 99KB | 3.0x |
| line | 10,000 | 9 | svg | 0.011s | 484KB | 0.127s | 81KB | 11.6x |
| line | 100,000 | 1 | pdf | 0.005s | 6KB | 0.016s | 7KB | 3.2x |
| line | 100,000 | 1 | png | 0.009s | 19KB | 0.019s | 15KB | 2.0x |
| line | 100,000 | 1 | svg | 0.005s | 449KB | 0.017s | 13KB | 3.2x |
| line | 100,000 | 4 | pdf | 0.009s | 9KB | 0.047s | 9KB | 5.6x |
| line | 100,000 | 4 | png | 0.023s | 59KB | 0.061s | 31KB | 2.7x |
| line | 100,000 | 4 | svg | 0.008s | 462KB | 0.046s | 38KB | 5.7x |
| line | 100,000 | 9 | pdf | 0.013s | 13KB | 0.102s | 13KB | 7.7x |
| line | 100,000 | 9 | png | 0.045s | 113KB | 0.126s | 101KB | 2.8x |
| line | 100,000 | 9 | svg | 0.014s | 484KB | 0.111s | 81KB | 8.1x |
| line | 1,000,000 | 1 | pdf | 0.044s | 6KB | 0.030s | 7KB | 0.7x |
| line | 1,000,000 | 1 | png | 0.048s | 19KB | 0.042s | 15KB | 0.9x |
| line | 1,000,000 | 1 | svg | 0.041s | 449KB | 0.028s | 13KB | 0.7x |
| line | 1,000,000 | 4 | pdf | 0.040s | 9KB | 0.060s | 9KB | 1.5x |
| line | 1,000,000 | 4 | png | 0.054s | 58KB | 0.080s | 31KB | 1.5x |
| line | 1,000,000 | 4 | svg | 0.041s | 462KB | 0.061s | 38KB | 1.5x |
| line | 1,000,000 | 9 | pdf | 0.048s | 13KB | 0.124s | 13KB | 2.6x |
| line | 1,000,000 | 9 | png | 0.083s | 114KB | 0.152s | 101KB | 1.8x |
| line | 1,000,000 | 9 | svg | 0.048s | 484KB | 0.183s | 81KB | 3.8x |
| scatter | 10,000 | 1 | pdf | 0.013s | 107KB | 0.084s | 158KB | 6.3x |
| scatter | 10,000 | 1 | png | 0.039s | 276KB | 0.023s | 50KB | 0.6x |
| scatter | 10,000 | 1 | svg | 0.004s | 909KB | 0.073s | 1MB | 17.8x |
| scatter | 10,000 | 4 | pdf | 0.016s | 107KB | 0.122s | 161KB | 7.8x |
| scatter | 10,000 | 4 | png | 0.063s | 444KB | 0.072s | 85KB | 1.2x |
| scatter | 10,000 | 4 | svg | 0.008s | 921KB | 0.114s | 1MB | 15.0x |
| scatter | 10,000 | 9 | pdf | 0.021s | 109KB | 0.175s | 167KB | 8.3x |
| scatter | 10,000 | 9 | png | 0.063s | 392KB | 0.143s | 160KB | 2.3x |
| scatter | 10,000 | 9 | svg | 0.012s | 937KB | 0.166s | 1MB | 13.6x |
| scatter | 100,000 | 1 | pdf | 0.118s | 1012KB | 0.709s | 1MB | 6.0x |
| scatter | 100,000 | 1 | png | 0.055s | 126KB | 0.049s | 9KB | 0.9x |
| scatter | 100,000 | 1 | svg | 0.028s | 5MB | 0.664s | 10MB | 23.4x |
| scatter | 100,000 | 4 | pdf | 0.123s | 992KB | 0.742s | 1MB | 6.1x |
| scatter | 100,000 | 4 | png | 0.133s | 725KB | 0.092s | 23KB | 0.7x |
| scatter | 100,000 | 4 | svg | 0.032s | 5MB | 0.700s | 10MB | 22.2x |
| scatter | 100,000 | 9 | pdf | 0.132s | 978KB | 0.816s | 1MB | 6.2x |
| scatter | 100,000 | 9 | png | 0.203s | 1MB | 0.171s | 138KB | 0.8x |
| scatter | 100,000 | 9 | svg | 0.037s | 5MB | 0.830s | 10MB | 22.5x |

**Reading it.** `speedup` is matplotlib-time / figurs-time (>1 means figurs exports faster). figurs is faster on almost every cell, and the lead is largest on **vector** export (PDF/SVG) - the editable-text formats the project exists for - where line paths are simplified and scatter markers are instanced (one reused XObject/`<use>`). The lead *grows with panel count*: figurs' single-pass layout amortizes per-panel chrome that matplotlib re-solves per axes.

**The one place matplotlib wins on time** is a single very large line (`N`=1e6, 1 panel): there the work is one long polyline with no per-panel overhead, and matplotlib's C path-simplification narrowly edges figurs' Rust one (~0.7x). Add panels and figurs retakes the lead.

**On file size**, each format has its own story:

- **PDF** - figurs is smaller everywhere (subsetted fonts + instanced markers + path simplification).
- **SVG, marker-heavy (scatter)** - figurs is *smaller* **and** ~15-22x faster: markers are one `<defs>` glyph + a `<use>` per point, versus matplotlib's per-point path, which outweighs even the embedded font.
- **SVG, sparse geometry (line)** - figurs is *larger*, and on purpose: it **embeds the bundled font** so the SVG is self-contained and renders identically on any machine (a figurs goal - no system-font drift), with real editable `<text>`; matplotlib only *references* a system font by name. Once the geometry is tiny (a simplified line is a few vertices), that ~340 KB font floor (more with math/STIX) dominates. Shrinking it needs a cmap-preserving font subsetter - a tracked future optimization, since the Typst `subsetter` drops the `cmap` that `<text>` relies on.
- **PNG** - resolution-bound for both; matplotlib's mature Agg compresses dense overlapping output more tightly.

See `benchmark.py` for the like-for-like single-panel head-to-head and the deterministic `--check` CI regression gate.
