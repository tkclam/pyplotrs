# Phase 3 evaluation: `vello` / `vello_cpu` for a faster / interactive backend

**Question (from the roadmap, Phase 3+):** *"Re-evaluate `vello`/`vello_cpu`
maturity for a faster raster backend and/or a genuinely interactive
`figurs-render-gpu` consuming the same IR."*

**Verdict: defer the GPU (`vello`) backend; keep `vello_cpu` on a watch-list.**
Nothing in figurs' current goals is bottlenecked on rasterization, and the
costs (a `wgpu` dependency tree, runtime GPU availability, wheel size) buy us
nothing today. The IR was deliberately designed to keep this door open, so
waiting costs nothing.

---

## What these crates are

- **`vello`** - a GPU-first 2D renderer (Linebender) that encodes a scene of
  paths/brushes/glyphs/images and rasterizes it with compute shaders on top of
  `wgpu`. State of the art antialiasing and throughput on large scenes,
  *provided a GPU is present*.
- **`vello_cpu`** - a CPU rasterizer that shares vello's scene/encoding model
  but renders on the CPU (multithreaded, SIMD), with no `wgpu`/GPU dependency.
  Positioned as a portable fallback / headless renderer with vello-quality
  output.

Both consume a `peniko`/`kurbo`-shaped scene - the same Linebender geometry and
styling vocabulary figurs already uses in `figurs-core`.

## Why the architectural fit is good (and why that's not the deciding factor)

figurs' IR (`figurs-core`) was intentionally built on `kurbo` (geometry) +
`peniko` (brush/stroke) so that a vello-family backend could slot in exactly
like the existing ones: a new `figurs-render-vello` / `figurs-render-vello-cpu`
would walk the same `Node` tree (`Group`/`PathNode`/`TextNode`/`MarkerNode`/
`ImageNode`) and emit vello scene commands - structurally identical to the
`tiny-skia` walker in `figurs-render-raster`. So *adoption is cheap whenever we
decide we want it*. The question is whether we want it now, and the answer turns
entirely on what such a backend could actually improve.

## The decisive constraint: backends split into "pixels" vs "editable text"

figurs exists for **editable text** in **PDF and SVG**. Those two backends
(`krilla` and the custom SVG serializer) emit real, selectable, subsettable text
objects - a vello/GPU/CPU rasterizer fundamentally cannot, because its output is
a raster image with no text objects. **A vello backend can therefore only ever
replace the `tiny-skia` raster (PNG/JPEG) path - never the PDF/SVG backends that
are the project's reason to exist.** The entire upside is "faster PNG."

## Is "faster PNG" actually needed?

No, not today. The Phase 1f + raster sprite-stamping work already brought
figurs' PNG export to ~parity with matplotlib's mature C/Agg rasterizer
(~0.36 s for 1e6 instanced markers), and the Phase 3 benchmark matrix
(`benchmarks/RESULTS.md`) confirms PNG is near-parity across the grid. figurs'
real raster workloads are dominated by either:

- **instanced markers** - already sprite-stamped once per sub-pixel phase, so
  the per-point cost is a memcpy-blit, not scan conversion; or
- **simplified polylines** - already collapsed to a handful of device-space
  vertices before they reach the rasterizer.

There is no current raster hot spot that a faster rasterizer would meaningfully
relieve. Spending a large dependency to shave an already-competitive,
non-bottleneck path is a bad trade.

## Costs of adopting now

- **`vello` (GPU):** pulls in the `wgpu` stack (`naga`, platform backends for
  Vulkan/Metal/DX12, windowing/handle crates) - a large build-time and
  binary-size cost for a `pip install` scientific library. Worse, it needs a
  usable GPU **adapter at runtime**, and figurs' core users batch-render figures
  exactly where GPUs are absent or headless-awkward: **CI, HPC clusters,
  headless servers, manylinux wheel builds.** A GPU backend therefore can
  never be the *default*; it would be an opt-in fast path guarded by adapter
  detection - more surface area, more failure modes.
- **`vello_cpu`:** much cheaper (no GPU, no `wgpu`), but it is young and
  pre-1.0 with a moving API, and its win over `tiny-skia` (already fast,
  battle-tested via `resvg`) is **unproven for figurs' scene shapes**. Since
  tiny-skia is already at Agg parity, the bar a replacement must clear is high.
  Neither crate is even present in this project's dependency closure today (see
  snapshot below), so adoption starts from a clean "add a new dependency"
  decision, not an incremental upgrade.

## Interactivity

The plan scopes interactivity *out* of v1 ("not a v1 goal but shouldn't be
architecturally precluded"). A genuinely interactive `figurs-render-gpu`
(pan/zoom/live updates) is a different product: it needs an event loop, a
windowing/surface layer, and incremental scene diffing - none of which the
static-export mission requires. The IR remains GPU-ready, so this stays
*possible* later; there is simply no driver for it now.

## Recommendation

1. **Defer the `vello` (GPU) backend.** No raster bottleneck justifies the
   `wgpu` dependency, headless-GPU friction, and wheel-size cost. We lose
   nothing by waiting, because the IR is already vello-ready.
2. **Watch-list `vello_cpu`** as a potential drop-in faster raster backend.
   Adopt **only** if a concrete benchmark shows it beating `tiny-skia` on
   figurs' actual scene shapes (instanced markers, simplified polylines, filled
   surfaces) by a margin that matters, *and* it has shipped a stable release.
3. **Revisit when** either (a) an interactive / notebook-live rendering use case
   becomes an actual goal (then `vello` GPU + a windowing/event layer is the
   natural path), or (b) `vello_cpu` reaches a stable release with published
   benchmarks beating `tiny-skia`.

## Registry snapshot (2026-06-15)

- `tiny-skia` (incumbent raster backend, `crates/figurs-render-raster`):
  **0.12** - at matplotlib/Agg parity for figurs' workloads.
- `vello` / `vello_cpu`: **not present** in this project's local cargo registry
  / dependency closure - adopting either is a from-scratch new-dependency
  decision. The analysis above is independent of their exact version: it turns
  on the editable-text constraint (a rasterizer can only replace the PNG path,
  never PDF/SVG) and the absence of any raster bottleneck, not on maturity.
