# Third-party notices

pyplotrs is distributed under the MIT license (see [`LICENSE`](LICENSE)). The
wheels additionally contain third-party material, listed here so that a
redistributor has a single file to carry.

This file is generated - run `python tools/gen_third_party_notices.py` after
changing a dependency, and commit the result. `tests/test_packaging.py` checks
that it is current.

## Bundled assets

| Asset | License | Notice |
|---|---|---|
| Liberation Sans (body text) | SIL OFL 1.1 | [`assets/fonts/LiberationSans-OFL.txt`](assets/fonts/LiberationSans-OFL.txt) |
| STIX Two Math (`$...$` math) | SIL OFL 1.1 | [`assets/fonts/STIXTwoMath-OFL.txt`](assets/fonts/STIXTwoMath-OFL.txt) |
| Colormap and palette tables | CC0-1.0, CC-BY-4.0, MIT, BSD-3-Clause | [`THIRD_PARTY_COLORMAPS.md`](THIRD_PARTY_COLORMAPS.md) |
| MathJax 3.2.2 (HTML math export) | Apache-2.0 | [`python/pyplotrs/_vendor/MATHJAX-NOTICE.md`](python/pyplotrs/_vendor/MATHJAX-NOTICE.md) |
| krilla (PDF backend, vendored fork) | MIT OR Apache-2.0 | [`vendor/krilla-0.8.2/PYPLOTRS_PATCH.md`](vendor/krilla-0.8.2/PYPLOTRS_PATCH.md) |

`docs/about/license.md` explains what each one is for.

## Rust dependencies

Statically linked into `pyplotrs._pyplotrs_core`, the extension module in every
wheel. Dual- and multi-licensed crates are listed with the upstream expression;
pyplotrs takes them under a permissive option compatible with MIT distribution.

108 crates, grouped by license expression.

### (MIT OR Apache-2.0) AND Unicode-3.0
`unicode-ident 1.0.24`

### 0BSD OR MIT OR Apache-2.0
`adler2 2.0.1`

### Apache-2.0
`approx 0.5.1`

### Apache-2.0 OR BSL-1.0
`ryu 1.0.23`

### Apache-2.0 OR MIT
`autocfg 1.5.1`, `equivalent 1.0.2`, `indexmap 2.14.0`, `kurbo 0.13.1`, `portable-atomic 1.13.1`, `rustc-hash 2.1.2`

### Apache-2.0 WITH LLVM-exception
`target-lexicon 0.13.5`

### BSD-2-Clause
`arrayref 0.3.9`

### BSD-3-Clause
`tiny-skia 0.12.0`, `tiny-skia-path 0.12.0`

### MIT
`color_quant 1.1.0`, `core_maths 0.1.1`, `float-cmp 0.9.0`, `fontconfig-parser 0.5.8`, `fontdb 0.23.0`, `imagesize 0.14.0`, `libm 0.2.16`, `pyplotrs-3d 0.1.0`, `pyplotrs-color 0.1.0`, `pyplotrs-core 0.1.0`, `pyplotrs-layout 0.1.0`, `pyplotrs-math 0.1.0`, `pyplotrs-py 0.1.0`, `pyplotrs-render-pdf 0.1.0`, `pyplotrs-render-raster 0.1.0`, `pyplotrs-render-svg 0.1.0`, `pyplotrs-text 0.1.0`, `rustybuzz 0.20.1`, `simd-adler32 0.3.9`, `strict-num 0.1.1`, `synstructure 0.13.2`

### MIT OR Apache-2.0
`arrayvec 0.7.6`, `base64 0.22.1`, `bitflags 2.13.0`, `bumpalo 3.20.3`, `by_address 1.2.1`, `cfg-if 1.0.4`, `crc32fast 1.5.0`, `crossbeam-deque 0.8.7`, `crossbeam-epoch 0.9.20`, `crossbeam-utils 0.8.22`, `either 1.17.0`, `euclid 0.22.14`, `fdeflate 0.3.7`, `flate2 1.1.9`, `font-types 0.11.3`, `gif 0.14.2`, `hashbrown 0.17.1`, `heck 0.5.0`, `image-webp 0.2.4`, `itoa 1.0.18`, `krilla 0.8.2`, `libc 0.2.186`, `log 0.4.32`, `memmap2 0.9.10`, `num-traits 0.2.19`, `once_cell 1.21.4`, `palette 0.7.7`, `palette_derive 0.7.7`, `palette_math 0.7.7`, `pdf-writer 0.15.0`, `png 0.18.1`, `polycool 0.4.0`, `proc-macro2 1.0.106`, `pyo3 0.28.3`, `pyo3-build-config 0.28.3`, `pyo3-ffi 0.28.3`, `pyo3-macros 0.28.3`, `pyo3-macros-backend 0.28.3`, `quote 1.0.45`, `rayon 1.12.0`, `rayon-core 1.13.0`, `read-fonts 0.39.2`, `roxmltree 0.20.0`, `skrifa 0.42.1`, `smallvec 1.15.2`, `stable_deref_trait 1.2.1`, `subsetter 0.2.6`, `syn 2.0.117`, `ttf-parser 0.25.1`, `unicode-script 0.5.8`, `weezl 0.1.12`, `write-fonts 0.48.1`, `xmp-writer 0.3.3`

### MIT OR Apache-2.0 OR Zlib
`tinyvec_macros 0.1.1`, `zune-core 0.5.1`, `zune-jpeg 0.5.15`

### MIT OR Zlib OR Apache-2.0
`miniz_oxide 0.8.9`

### MIT/Apache-2.0
`quick-error 2.0.1`, `siphasher 1.0.3`, `unicode-bidi-mirroring 0.4.0`, `unicode-ccc 0.4.0`, `unicode-properties 0.1.4`, `version_check 0.9.5`

### Unicode-3.0
`yoke 0.8.3`, `yoke-derive 0.8.2`, `zerofrom 0.1.8`, `zerofrom-derive 0.1.7`

### Unlicense OR MIT
`byteorder-lite 0.1.0`, `memchr 2.8.2`

### Zlib
`slotmap 1.1.1`

### Zlib OR Apache-2.0 OR MIT
`bytemuck 1.25.0`, `bytemuck_derive 1.10.2`, `tinyvec 1.11.0`

## Full license texts

The MIT, Apache-2.0, BSD, ISC, Zlib and Unicode license texts are
reproduced by their respective crates in the Cargo registry, and the
Apache-2.0 text is included verbatim at
[`python/pyplotrs/_vendor/MATHJAX-LICENSE.txt`](python/pyplotrs/_vendor/MATHJAX-LICENSE.txt)
and [`vendor/krilla-0.8.2/LICENSE-APACHE`](vendor/krilla-0.8.2/LICENSE-APACHE).
Run `cargo license` or `cargo about generate` for per-crate texts.
