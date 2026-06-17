# figurs: A blazingly fast, Rust-core publication plotting library

## Context

matplotlib is the de facto standard for scientific plotting in Python, but it has well-known pain points: a confusing pyplot-vs-OO API with lots of boilerplate, layout engines (`tight_layout`/`constrained_layout`) that fail or require manual fiddling, ugly defaults that need heavy `rcParams` customization to look "publication ready," slow rendering for large datasets, and PDF export whose text often isn't cleanly editable in Illustrator (glyphs become per-character outlines).

The goal of **figurs** is a from-scratch plotting library that is genuinely fast (Rust core, Python-facing API), looks publication-quality out of the box with zero configuration, exports to PDF/SVG/PNG with **real, editable text** (critical for the Illustrator post-processing workflow scientists rely on), and fixes the above pain points by construction rather than via opt-in workarounds.

Decisions already made with the user:
- **Architecture**: Python package, Rust core, via PyO3 + maturin.
- **API philosophy**: Fresh, redesigned API — not a matplotlib-compatible shim.
- **Speed priority**: Fast *static export* (PDF/SVG/PNG, potentially large datasets) is priority #1; interactivity is not a v1 goal but shouldn't be architecturally precluded.
- **MVP scope (v1)**: Core 2D (line/scatter/bar/hist/fill_between/errorbar + axes/legends/text/subplots) **+** images/heatmaps/colorbars **+** basic 3D (scatter/line/surface) — all three backends.

This plan was developed via research into the current (mid-2026) Rust 2D-graphics/PDF/text ecosystem. The single most important finding — verified independently — is that **`krilla`** (a PDF crate by LaurenzV, the author of `svg2pdf`/`resvg`, built on `pdf-writer`) provides a `draw_text()`/`draw_glyphs()` API that produces **real embedded, subsetted, selectable PDF text** — not outlines. This directly solves the highest-risk requirement (Illustrator-editable text) and anchors the whole architecture below. By contrast, `svg2pdf` — the more obvious "SVG → PDF" choice — converts text to outline paths and does **not** embed real text (confirmed via Typst's own GitHub issue tracker), so an "SVG-first" pipeline was rejected in favor of a custom intermediate representation.

---

## Big architectural decisions

1. **Python + Rust core** via PyO3/maturin. Rust does layout, geometry, text shaping, and rendering; Python is the user-facing, fully-typed API. Ships as prebuilt wheels (Linux/macOS/Windows).
2. **Custom backend-agnostic Scene IR** (not SVG-first). A Rust data structure of groups/transforms/paths/text-runs/images/clips is figurs' own internal representation. All three backends (PDF/SVG/PNG) render directly from it.
3. **PDF backend = `krilla`**. Walks the IR, calls `draw_path` for geometry and `draw_text`/`draw_glyphs` for **pre-shaped** text runs → real embedded/subsetted fonts, genuinely editable in Illustrator.
4. **Raster backend = `tiny-skia`**. Walks the IR, builds paths/paints directly; rasterizes shaped glyphs via `skrifa`.
5. **SVG backend = direct serializer**. Walks the IR, emits `<path>`/`<text>` (real `<text>` elements using the original source string) — SVG output is *also* genuinely editable text, "for free."
6. **Layout = `taffy`** (CSS Grid/Flexbox engine, used by Bevy/Dioxus/Zed). Figure → subplot grid → per-axes flex regions (title/labels/ticks/plot-area/colorbar) → legend region, all solved as **one constraint pass before any drawing**, using *pre-measured* real text extents (shaped via figurs' text stack) as inputs. This is the direct fix for `tight_layout`/`constrained_layout` instability and legend/colorbar overlap — they get reserved regions, never overlays.
7. **Text shaping = `rustybuzz` + `skrifa` + `fontique`** (thin custom wrapper, not full `parley` — parley is scoped for editable rich text/cursors, more than we need).
8. **Math notation = hand-rolled "mathtext-lite"** covering super/subscripts, Greek letters, common symbols (via Unicode + bundled STIX Two Math font), simple fractions/radicals. Full LaTeX-subset (e.g. via `typst-layout`) is a post-MVP stretch goal.
9. **3D = a projection layer**, not a separate renderer. Camera (orthographic/perspective) projects 3D primitives to ordinary 2D Scene IR fragments (with painter's-algorithm depth sorting), which then flow through the *same* 2D layout/render pipeline.
10. **Python API = layered**. Phase 1 ships an imperative, type-hinted, matplotlib-OO-*shaped*-but-fresh API (`fig, ax = figurs.subplots(...)`, `ax.line(...)`, `ax.set(...)`) with **no pyplot/global-state layer at all** (directly fixes the state-machine confusion). A declarative grammar-of-graphics layer (`figurs.gg`) is Phase 2+, built on the same underlying "mark" objects.
11. **Publication-quality defaults are baked in**: bundled fonts (no DejaVu fallback), Okabe-Ito-derived colorblind-safe categorical palette, bundled perceptually-uniform colormaps (viridis/plasma/inferno/magma/cividis), despined-by-default chrome, spacing derived from font metrics.

---

## Technology stack (researched & spot-checked mid-2026)

| Concern | Crate(s) | Notes |
|---|---|---|
| PDF output (real text) | **`krilla`** (+ `pdf-writer`, `subsetter` transitively) | Verified: `draw_text`/`draw_glyphs` + `PathBuilder`; built specifically for "IR → PDF" use cases; supports PDF/A and PDF/UA (tagged/accessible PDF) as a bonus. Pin a version; budget minor upgrade work (pre-1.0). |
| Raster (PNG/JPG) | `tiny-skia` | Pure-Rust CPU rasterizer (Skia subset). `kurbo::BezPath` → `tiny_skia::Path` is near-trivial. |
| SVG output | direct serializer (no dependency) | `usvg`'s `Tree`/`Group`/`Path`/`Text` shape is a useful reference for our IR design. |
| 2D geometry | `kurbo` | Bezier paths/points/affines — the "lingua franca" geometry type converted to/from by all three backends. |
| Styling (brush/stroke) | `peniko` | Solid/gradient brushes, stroke caps/joins/dashes — shared vocabulary with the wider Linebender ecosystem (useful if a GPU backend is added later). |
| Text shaping | `rustybuzz` (HarfBuzz port) | string+font → positioned glyph IDs (kerning, ligatures). |
| Font parsing/metrics | `skrifa` (+ `ttf-parser` as needed) | Aligns with krilla's font stack — share font-loading/caching code. |
| Font discovery/fallback | `fontique` | System font fallback for user-specified fonts; bundled fonts avoid needing this for defaults. |
| Math layout | hand-rolled `figurs-math` | Recursive box model (sup/sub, frac, sqrt) over Unicode + STIX Two Math; `typst-layout` flagged as a Phase 2+ option for full LaTeX. |
| Layout engine | `taffy` | Flexbox+Grid; used beyond UI for report/plot layouts already. |
| 3D math | `glam` (small addition) | kurbo is 2D-only; need a minimal 4x4 matrix/Vec3 for camera projection. |
| Color science | `palette` + hand-rolled colormap tables | `palette` for color-space math (sRGB/OkLab/CIELAB); colormap LUTs (viridis etc.) as static data, matplotlib-derived/public-domain. |
| Python bindings | `pyo3` + `maturin` + `numpy` (rust-numpy) | Mature/production-ready; `PyReadonlyArray` gives zero-copy `ndarray` views over NumPy buffers. |

---

## Repo / Cargo workspace layout

```
figurs/                              (repo root = Cargo workspace root)
├── Cargo.toml                       # [workspace] members below
├── pyproject.toml                   # maturin config -> crates/figurs-py
├── python/figurs/
│   ├── __init__.py                  # re-exports compiled _figurs_core + pure-Python API
│   ├── _figurs_core.pyi             # type stubs for the compiled extension
│   ├── figure.py                    # Figure, Axes classes
│   ├── marks.py                     # Line, Scatter, Bar, Histogram, FillBetween, ErrorBar, Image, Surface3D...
│   ├── theme.py                     # Theme dataclass + built-in presets
│   └── colormaps.py
├── tests/                           # pytest integration tests, incl. "PDF has real text" checks
└── crates/
    ├── figurs-core/                 # Scene IR: Group, Path, TextRun, Image, Clip, Transform, Style
    │                                 #   deps: kurbo, peniko. NO rendering/layout - pure data model.
    ├── figurs-text/                 # rustybuzz + skrifa + fontique wrapper; bundled font loading/caching
    ├── figurs-math/                 # mathtext-lite parser + box-model layout -> figurs-core fragments
    ├── figurs-layout/               # taffy-based figure/axes/legend/colorbar arrangement
    ├── figurs-scene/                # user data + plot spec + layout rects -> figurs-core IR tree
    │                                 #   scales, tick locator/formatter, colormap LUTs, mark geometry
    ├── figurs-3d/                   # camera/projection: 3D primitives -> 2D figurs-core fragments
    ├── figurs-render-pdf/           # IR -> krilla::Document
    ├── figurs-render-raster/        # IR -> tiny-skia::Pixmap -> PNG/JPEG
    ├── figurs-render-svg/           # IR -> SVG XML (serializer)
    └── figurs-py/                   # PyO3 bindings (only crate depending on pyo3/numpy); maturin cdylib
```

Rationale: `figurs-core` has zero knowledge of PDF/SVG/raster, so all three backends depend only on it — this is what makes "one IR, three renderers" enforceable and independently testable. A future GPU/interactive backend (`figurs-render-gpu`, vello-based) would slot in the same way. Not all crates need real content in Phase 0 — stubs are fine initially; some (e.g. `figurs-math` into `figurs-text`) could even start merged and split later if that's less ceremony.

---

## Scene IR design (`figurs-core`)

A tree of nodes close in spirit to `usvg::Tree`, but **text is kept as pre-shaped glyph runs, never collapsed to paths** — this is the crux of the editable-text requirement and must survive end-to-end:

```rust
pub struct Scene { pub root: Group, pub size: Size }   // size in points (1/72in) - PDF's native unit

pub struct Group {
    pub transform: kurbo::Affine,
    pub clip: Option<ClipPath>,
    pub opacity: f32,
    pub children: Vec<Node>,
}

pub enum Node { Group(Group), Path(PathNode), Text(TextNode), Image(ImageNode) }

pub struct PathNode { pub geometry: kurbo::BezPath, pub fill: Option<Fill>, pub stroke: Option<Stroke> }

pub struct TextNode { pub origin: kurbo::Point, pub runs: Vec<GlyphRun>, pub color: peniko::Brush }

pub struct GlyphRun {
    pub font: FontRef,
    pub size: f32,
    pub glyphs: Vec<PositionedGlyph>,  // from rustybuzz shaping
    pub source_text: String,           // preserved for SVG <text> real content
}

pub struct ImageNode { pub data: ImageData, pub rect: kurbo::Rect }
pub struct ClipPath { pub geometry: kurbo::BezPath }
```

- **One geometry type** (`kurbo::BezPath`) converts trivially to `tiny_skia::Path`, krilla `PathBuilder` calls, and SVG path-data strings.
- **Shaping happens once**, upstream (in `figurs-scene`/`figurs-math` via `figurs-text`), producing exact glyph IDs+positions consumed identically by all three backends — PDF via krilla's positioned-glyph API (real text), raster via `skrifa` rasterization at those positions, SVG via `<text>`/`<tspan>` using `source_text`. This is what makes "editable text" a property of the whole pipeline, not a PDF-only hack.
- **`ImageNode`** carries raw RGBA for `imshow`/heatmaps; each backend embeds/composites it appropriately.

---

## Layout engine (`figurs-layout`, on `taffy`)

The layout tree is solved **before** any Scene IR is produced:

```
Figure (taffy root, fixed size e.g. 6.4in x 4.8in)
└── Grid (subplot rows/cols)
    ├── [optional] suptitle row (height = measured text height)
    ├── Subplot cell -> flex column:
    │   ├── title band (height = measured text)
    │   ├── flex row: y-label band | y-tick-label band | PLOT AREA (grow) | [colorbar band]
    │   ├── x-tick-label band
    │   └── x-label band
    └── [optional] legend region (own reserved column/row)
```

**Key move**: tick values/labels, titles, and axis labels are generated and **shaped+measured via `figurs-text` before** building the taffy tree, so every "auto" band gets a real `Dimension::Length(measured_px)` instead of `Auto` requiring iteration. This single decision is the direct fix for matplotlib's `tight_layout`/`constrained_layout` instability and clipped-label complaints — layout is solved once, with real measurements, by a constraint solver, not via draw-measure-adjust loops. Legends and colorbars are **first-class taffy nodes with reserved space**, eliminating overlap by construction.

---

## 3D handling (`figurs-3d`)

A thin `Camera { eye, target, up, projection: Orthographic{scale} | Perspective{fov} }` (mirrors matplotlib's own `proj_type`/focal-length model). For each mark type:
- **scatter3d**: project each point to 2D, retain eye-space depth, sort back-to-front (painter's algorithm), emit as `PathNode`s.
- **plot3d** (line): project vertices to a single `BezPath` polyline.
- **surface**: triangulate the grid, project vertices, depth-sort triangles by centroid, emit each as a filled `PathNode` colored via colormap(z) — the classic shaded-surface look.
- **3D axes/gridlines/ticks**: themselves projected 3D→2D primitives, fed into the *same* plot-area region `figurs-layout` already computed.

Output of `figurs-3d` is just another `Group` — from the renderer's perspective, 3D and 2D subplots are indistinguishable. All 3D-specific work happens before the IR.

---

## Python API

Layered: a small, type-hinted, chainable **core object model** (the Phase 1 focus) plus an optional **declarative mark/encoding layer** later, sharing the same underlying `figurs.marks` vocabulary (`Line`, `Scatter`, `Bar`, `Histogram`, `FillBetween`, `ErrorBar`, `Image`, `Surface3D`, ...). No pyplot/global "current figure" state anywhere.

```python
import numpy as np
import figurs

x = np.linspace(0, 10, 500)
fig, axes = figurs.subplots(1, 2, figsize=(6.5, 3.0), sharey=True)

axes[0].line(x, np.sin(x), color="C0", label="sin(x)")
axes[0].line(x, np.cos(x), color="C1", label="cos(x)", linestyle="dashed")
axes[0].set(xlabel="x", ylabel="amplitude", title="Trigonometric functions")
axes[0].legend(loc="upper right")

data = np.random.default_rng(0).normal(size=10_000)
axes[1].hist(data, bins=50, color="C2")
axes[1].set(xlabel="value", title="Sample distribution")

fig.save("figure.pdf")   # .svg / .png / .html too - format inferred from extension
```

```python
# heatmap + colorbar: layout-aware, no manual make_axes dance
fig, ax = figurs.subplots(figsize=(4, 3.5))
im = ax.imshow(data_2d, cmap="viridis", extent=(0, 10, 0, 10))
fig.colorbar(im, label="intensity")
fig.save("heatmap.svg")

# 3D surface
fig, ax = figurs.subplots(projection="3d", figsize=(5, 4))
ax.surface(X, Y, Z, cmap="plasma")
ax.set(xlabel="x", ylabel="y", zlabel="z", title="Surface plot")
fig.save("surface.pdf")
```

```python
# Phase 2+ declarative layer (sketch, not v1)
from figurs.gg import Plot, Line, facet
(Plot(df, x="time", y="value", color="treatment")
    .add(Line())
    .facet(facet.wrap("subject", ncols=3))
    .theme(figurs.themes.nature)
    .save("faceted.pdf"))
```

Object model: `figurs.Figure` (canvas, owns `Theme` + layout tree, `.save(path)`, `.subplots()` as plain constructor), `figurs.Axes` (`.line/.scatter/.bar/.hist/.fill_between/.errorbar/.imshow/.surface/.scatter3d/.plot3d/.legend/.set(...)`), `figurs.Theme` (fonts, color cycle, spacing, grid/spine style — `figurs.themes.default/nature/bw/...`). Full type hints + `.pyi` stubs (numpy array types, `Literal[...]` enums for `linestyle` etc.) for IDE discoverability and friendly errors.

**Data ingestion**: `figurs-py` accepts `PyReadonlyArray1/2<f64>` (zero-copy `ndarray` views via rust-numpy) for numpy input; the Python layer calls `np.asarray()` on any input first, so pandas/polars/lists all funnel through the same zero-copy-where-possible numpy path (matches how matplotlib itself normalizes input).

---

## Default theme — "publication quality" with zero config

- **Fonts**: bundle **Inter** (or Source Sans 3) for body/labels + **STIX Two Math** for math (same family matplotlib uses, pairs with Source Serif/Sans) — embedded via `include_bytes!` so rendering is fully reproducible without relying on OS fonts. Verify SIL OFL licensing before bundling.
- **Type scale**: tick labels 9pt, axis labels 10pt, title 11pt, suptitle 13pt — calibrated for legible output at typical journal figure sizes (e.g. ~3.3in two-column width).
- **Color**: Okabe-Ito-derived 8-10 color colorblind-safe categorical cycle (`C0`-`C9`); bundled perceptually-uniform colormaps (viridis/plasma/inferno/magma/cividis + diverging via `palette`/CIELAB).
- **Spacing**: paddings derived from font metrics (e.g. label-to-tick gap = 0.3× label font size) so defaults scale sensibly across figure sizes.
- **Chrome**: thin spines, top/right removed by default (seaborn's `despine()` as default, not opt-in), legend outside axes via reserved taffy region, light/no gridlines by default.

---

## Phased roadmap

### Phase 0 — Scaffolding & "hello world" round trip (the go/no-go gate)

Goal: prove the riskiest bet (krilla → Illustrator-editable text) end-to-end in the smallest vertical slice, before building out the full IR/layout/marks machinery.

1. Cargo workspace skeleton: minimal `figurs-core` IR (`Scene` of `PathNode`/`TextNode` only — no `Group`/clip/transform yet), stub `figurs-render-{pdf,raster,svg}`, `figurs-py` + maturin/pyproject, `python/figurs/` skeleton.
2. `figurs-text`: load one bundled font (Inter Regular) via `skrifa`, shape one string via `rustybuzz` → `Vec<PositionedGlyph>`.
3. `figurs-render-pdf`: hand-built `Scene` (one rect + one text) → krilla `draw_path`/`draw_text`/`draw_glyphs` → `out.pdf`.
4. `figurs-render-raster`: same `Scene` → `tiny-skia::Pixmap` → `out.png`.
5. `figurs-render-svg`: same `Scene` → `<rect>` + `<text>` → `out.svg`.
6. `figurs-py`: one function dispatching to the right backend by file extension; minimal `Figure`/`Axes`/`.line()`/`.set()`/`.save()` with hardcoded (non-taffy) margins, enough for:
   ```python
   import figurs
   fig, ax = figurs.subplots(figsize=(4, 3))
   ax.line([0,1,2,3], [0,1,4,9], label="y = x²")
   ax.set(title="Hello, figurs", xlabel="x", ylabel="y")
   fig.save("hello.pdf"); fig.save("hello.svg"); fig.save("hello.png")
   ```
7. **Acceptance gate (manual)**: open `hello.pdf` in **Adobe Illustrator**, select the title and axis-label text, confirm (a) selectable as text not paths, (b) editable without mangling, (c) font shows as an embedded subset (also check Acrobat's Document Properties → Fonts). Confirm `hello.svg` has real `<text>` in a browser/Inkscape, and `hello.png` renders correctly.
8. Parallel spike: a standalone 2×2 `taffy` tree (title band + plot area + tick-label bands) to de-risk the layout approach independent of the rendering spike.

### Phase 1 — MVP (full v1 scope)

- **1a. Core IR + layout**: full `figurs-core` (`Group`, transforms, clipping, images); full `figurs-layout` (figure→grid→axes flex tree, suptitle, legend/colorbar regions, pre-measurement single-pass solve); tick locator/formatter (port of matplotlib's "nice intervals" `MaxNLocator`/`AutoLocator` logic). All renderers handle `Group`/clip/transform/image.
- **1b. Core 2D marks**: line, scatter (marker shape library), bar (incl. horizontal), hist, fill_between, errorbar; auto-legend whose glyphs mirror actual mark styles; default theme applied; `figurs.subplots(nrows, ncols, sharex=, sharey=)`.
- **1c. Images/heatmaps + colorbar**: `imshow`-equivalent (colormap LUT or RGB(A) passthrough); `colorbar()` reuses `imshow` + axis machinery, placed in a reserved taffy region.
- **1d. Basic 3D**: `figurs-3d` camera/projection; `scatter3d`/`plot3d`/`surface`, reusing 2D primitives.
- **1e. mathtext-lite**: `figurs-math` parser + box layout (sup/sub, Greek, symbols, simple fractions/radicals) for `$...$` in titles/labels/legends.
- **1f. Performance + polish**: stress-test large datasets (10^5-10^6 points) for line/scatter export to PDF/PNG/SVG with an explicit benchmark suite vs. matplotlib on identical inputs (this is the "blazingly fast" receipt); `.pyi` completeness; cross-platform wheels (Linux x86_64/aarch64, macOS x86_64/arm64, Windows x86_64) via maturin + GitHub Actions.

**Acceptance criteria**: figurs reproduces matplotlib's core "sample plots" gallery within v1 scope (line/scatter/bar/hist/fill_between/errorbar/imshow+colorbar/3D scatter-line-surface/multi-panel subplots/legends/basic mathtext) to PDF/SVG/PNG, with PDF text confirmed editable in Illustrator for a figure with multiple text elements (title, axis labels, legend, ticks all independently selectable).

### Phase 2 — Polish & ergonomics

- Additional built-in themes (journal presets, grayscale/print-safe, presentation).
- Expand math toward fuller LaTeX subset (re-evaluate `typst-layout` once IR is stable).
- Declarative grammar-of-graphics layer (`figurs.gg`): faceting, statistical transforms, grouped encodings.
- Annotation helpers (arrows/callouts).
- Tagged/accessible PDF output (`fig.save("out.pdf", tagged=True)`) — krilla supports PDF/UA-1 already.

### Phase 3+ — Benchmarks & possible interactive/GPU backend

- Published benchmark suite vs. matplotlib (and plotters/Vega-Lite static export) across (point count × panel count × format) as both marketing proof and a CI regression gate.
- Re-evaluate `vello`/`vello_cpu` maturity for a faster raster backend and/or a genuinely interactive `figurs-render-gpu` consuming the same IR.
- Animation/multi-frame export.

---

## matplotlib pain-point → figurs solution

| Pain point | figurs fix |
|---|---|
| Verbose/inconsistent pyplot-vs-OO API | No pyplot/global state at all; plain `figurs.subplots()` constructor; bulk `.set(...)` setter |
| `tight_layout`/`constrained_layout` instability | One-shot `taffy` constraint solve using pre-measured real text extents |
| Legend/colorbar overlap | Reserved taffy regions, never overlays |
| Clipped tick/axis labels | Label bands sized from real shaped-text measurements before layout runs |
| Ugly defaults / heavy `rcParams` tuning | Single carefully-designed bundled `Theme` (fonts, colorblind-safe palette, despined chrome) as the only default |
| PDF text not editable in Illustrator | `krilla`-based PDF backend: real embedded/subsetted fonts via `draw_text`/`draw_glyphs` |
| Slow export for large datasets/many subplots | Rust geometry generation over zero-copy numpy buffers; single IR walk per backend, no intermediate-format round-trips |
| Awkward color/colormap handling | One `Color` type; curated bundled colormaps via consistent CIELAB/OkLab interpolation |
| mathtext slow/inconsistent vs. regular text | `figurs-math` uses the same shaping/font pipeline as regular text (STIX Two Math paired with body font) |
| mplot3d z-order bugs, bolted-on feel | Explicit projection + painter's-algorithm depth sort producing ordinary 2D IR |
| Inconsistent fonts across machines (DejaVu fallback) | Default fonts bundled in the wheel via `include_bytes!` |

---

## Key risks / open questions to resolve early (Phase 0)

1. **krilla's font-subsetting lifecycle** across many `TextNode`s sharing a font in one document — confirm whether krilla's `Document`/`Surface` handles accumulation/subsetting transparently, or whether `figurs-render-pdf` needs cross-node font-state bookkeeping.
2. **krilla is pre-1.0** (0.8.x) — pin a version, budget occasional upgrade work.
3. **Shared font bytes**: `figurs-text` (shaping/measurement for layout) and `figurs-render-pdf` (krilla embedding) must consume the *same* bundled `&'static [u8]` font data — otherwise layout measurements and embedded-font metrics could drift apart, reintroducing the layout/render mismatch this architecture is designed to avoid.
4. Tick locator/formatter porting is real (if well-understood) work and is load-bearing for the pre-measurement layout strategy — don't underscope in 1a.
5. Font license audit (Inter/Source Sans/STIX Two Math → SIL OFL) before bundling in Phase 1.

---

## Verification plan

- **Phase 0 gate** (above): manual open-in-Illustrator check of `hello.pdf` is the literal go/no-go for the whole architecture — do this before investing in 1a-1f.
- **Phase 1**: pytest integration tests that (a) render each mark type to all three backends without error, (b) parse generated PDFs to assert real text objects exist (not just for `hello.pdf` but for a multi-element figure), (c) visually compare PNG output against reference images for regression detection.
- **Phase 1f**: benchmark script comparing figurs vs. matplotlib wall-clock time for identical figures at increasing point counts/panel counts, run in CI as a regression gate.
- **End-to-end UX check**: once Phase 1b lands, run the example snippets above as real scripts and inspect the output files (PDF in Illustrator/Acrobat, SVG in a browser, PNG visually) to confirm the "intuitive, looks good by default" goal is actually met, not just "renders without crashing."
