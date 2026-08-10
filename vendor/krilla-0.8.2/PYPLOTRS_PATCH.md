# pyplotrs patch notes

> **License.** krilla is © Laurenz Stampfl, dual-licensed **MIT OR
> Apache-2.0**; pyplotrs redistributes it under those terms, unchanged. The
> crates.io `.crate` tarball ships no license files, so verbatim copies are
> included here as [`LICENSE-MIT`](LICENSE-MIT) and
> [`LICENSE-APACHE`](LICENSE-APACHE) — both licenses require the notice to
> travel with the source, and this copy goes out in pyplotrs' sdist and is
> compiled into every wheel. See also `docs/about/license.md`.

This is a vendored copy of [`krilla`](https://github.com/LaurenzV/krilla)
0.8.2 (MIT OR Apache-2.0, per its `Cargo.toml`), pulled from crates.io and
patched by pyplotrs to remove per-placement overhead that showed up when
profiling large marker-instanced PDF scatters (see
`crates/pyplotrs-render-pdf`, which places one shared Form XObject per data
point - e.g. one per point of a 200k-point scatter). None of this changes
krilla's output semantics; it only removes redundant work on hot paths. All
701 of pyplotrs' Python tests and the full Rust workspace test suite
(including krilla-output-sensitive golden/PDF-structure tests) pass against
this patch.

Wired into the workspace via `[patch.crates-io] krilla = { path =
"vendor/krilla-0.8.2" }` in the root `Cargo.toml`, so every crate's plain
`krilla = "0.8"` dependency resolves here instead of crates.io - no call
sites needed to change.

## What changed and why

Profiling `pyplotrs_render_pdf::render_pdf` on a 200k-point scatter (see the
investigation behind this patch) found effectively all of the time in two
places, in this order of impact:

1. **`src/stream.rs` - content-stream compression level.** By far the
   largest cost (~80% of total export time on the scatter case). Content
   streams (page content, Form XObjects, patterns, shadings, CID cmaps) are
   mostly ASCII drawing operators wrapped around per-point numeric
   coordinates - high-entropy text that compresses poorly no matter the
   effort spent. `deflate_encode_memoized` (the path `new_from_content_stream`
   uses) now compresses at zlib level 3 instead of 6; `deflate_encode`
   (fonts, images - more compressible, so worth the extra effort) is
   untouched at level 6. Measured on the scatter case: ~2.2x faster for
   ~5% larger output.

2. **`src/resource.rs`, `src/serialize.rs` - hot lookup maps.** Every
   `Surface::draw_graphic` call re-hashes and looks up the placed resource
   (`SerializeContext::cached_mappings`, keyed by content hash) and its
   in-page name (`ResourceMapper::backward`, keyed by `Ref`) - once per data
   point for an instanced scatter. Both maps switched from `std::HashMap`
   (SipHash - deliberately DoS-resistant, and correspondingly slower for
   this many small-key lookups) to `rustc_hash::FxHashMap`, the same fast
   hasher krilla's own font/CID caches already use elsewhere (`text/cid.rs`,
   `text/mod.rs`) - this just extends that existing pattern to two hot
   dedup maps that hadn't gotten it. There's no adversarial input here to
   defend against (a document is built once, from trusted caller code), so
   the DoS-resistance tradeoff SipHash exists for doesn't apply.

3. **`ResourceMapper::remap_with_name`** now caches each resource's
   formatted PDF name (`"G0"`, `"G1"`, ...) as an `Arc<str>` the first time
   it's assigned, instead of re-running `format!` on every placement of an
   already-registered resource. `register_resource` and `ContentColorSpace::
   Named` changed from `String` to `Arc<str>` to carry the cached value
   through; `NameExt` gained an `Arc<str>` impl alongside its existing
   `String`/`&str` ones. In isolation this measured within noise once (1)
   and (2) were applied, but it's a strict reduction in redundant work with
   no behavior change, so it stayed.

## Upgrading

This is a point-in-time fork of 0.8.2, not a tracking branch. Bumping krilla
means re-applying these changes (a `diff` against a fresh `0.8.2` checkout
from crates.io will show exactly this patch) or re-evaluating whether
upstream has since addressed the same hot paths.
