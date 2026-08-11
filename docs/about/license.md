# License

pyplotrs is released under the
**MIT license** ([LICENSE](https://github.com/tkclam/pyplotrs/blob/main/LICENSE)).

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in the work by you shall be licensed as above, without any
additional terms or conditions.

## Bundled third-party assets

pyplotrs embeds a small number of third-party assets, each under a permissive
license. Every license and notice below is installed into
`pyplotrs-<version>.dist-info/licenses/` with the wheel, so a redistributor
does not have to fetch this page.

[`THIRD-PARTY-NOTICES.md`](https://github.com/tkclam/pyplotrs/blob/main/THIRD-PARTY-NOTICES.md)
is the single generated file listing all of it, including the ~110 Rust crates
compiled into the extension module.

### Fonts (embedded in the compiled extension)

- **Liberation Sans** — © 2012 Red Hat, Inc. (digitized data © 2010 Google
  Corp.). SIL Open Font License 1.1. The bundled, permissive, Arial-metric-
  compatible fallback for body text.
  Source: <https://github.com/liberationfonts>.
  License text: [`assets/fonts/LiberationSans-OFL.txt`](https://github.com/tkclam/pyplotrs/blob/main/assets/fonts/LiberationSans-OFL.txt).
- **STIX Two Math** — © 2001–2021 The STIX Fonts Project Authors. SIL Open Font
  License 1.1. Used for `$...$` math.
  Source: <https://github.com/stipub/stixfonts>.
  License text: [`assets/fonts/STIXTwoMath-OFL.txt`](https://github.com/tkclam/pyplotrs/blob/main/assets/fonts/STIXTwoMath-OFL.txt).

Arial and Helvetica are **not** bundled (they are proprietary). pyplotrs prefers
host Arial/Helvetica for body text when installed, else the bundled Liberation
Sans; the chosen font is embedded into every saved figure. See
[`assets/fonts/NOTICE.md`](https://github.com/tkclam/pyplotrs/blob/main/assets/fonts/NOTICE.md)
for which file plays which role.

### Colormap and palette data

pyplotrs embeds **127 colormaps and 25 categorical palettes**, compiled into the
extension as lookup tables (`crates/pyplotrs-color`) so that naming one at
runtime pulls in no third-party package. The full source-by-source breakdown,
with licenses and the required colorcet attribution, is in
[`THIRD_PARTY_COLORMAPS.md`](https://github.com/tkclam/pyplotrs/blob/main/THIRD_PARTY_COLORMAPS.md);
in summary the data comes from matplotlib, [colorcet](https://colorcet.holoviz.org/)
(CC-BY 4.0, `cet_*`), [cmocean](https://matplotlib.org/cmocean/) (MIT, `cmo_*`)
and [seaborn](https://seaborn.pydata.org/) (BSD-3-Clause, `sns_*`).

Among them, the `viridis`, `plasma`, `inferno`, `magma` and `cividis` tables are
the canonical perceptually-uniform colormaps created for matplotlib by Stefan van
der Walt and Nathaniel Smith, dedicated to the **public domain (CC0)**.

### MathJax (inlined into HTML math output)

- **MathJax 3.2.2** — © 2009–2022 The MathJax Consortium. **Apache License
  2.0**. `Figure.save("*.html")` re-typesets `$...$` math with MathJax so it
  stays selectable and copyable in a browser, and inlines the whole library so
  the page needs no network access. This is separate from pyplotrs' own math
  engine (`crates/pyplotrs-math`), which typesets math for PDF, SVG and PNG
  from the math font's OpenType MATH table and uses none of this code.
  Source: <https://github.com/mathjax/MathJax>.
  License text:
  [`python/pyplotrs/_vendor/MATHJAX-LICENSE.txt`](https://github.com/tkclam/pyplotrs/blob/main/python/pyplotrs/_vendor/MATHJAX-LICENSE.txt);
  what the bundle contains, including the Speech Rule Engine and the TeX
  extension set, is in
  [`MATHJAX-NOTICE.md`](https://github.com/tkclam/pyplotrs/blob/main/python/pyplotrs/_vendor/MATHJAX-NOTICE.md).
  Because each generated `.html` file carries its own copy, an attribution
  banner is prepended at inline time so the notice travels with it.

### PDF writer (compiled into the extension)

- **krilla** — © Laurenz Stampfl. **MIT OR Apache-2.0**. The PDF backend.
  pyplotrs carries a minimally patched copy under
  [`vendor/krilla-0.8.2`](https://github.com/tkclam/pyplotrs/blob/main/vendor/krilla-0.8.2),
  which cuts export time on point-heavy figures without changing output
  semantics; the changes and their rationale are documented in
  [`PYPLOTRS_PATCH.md`](https://github.com/tkclam/pyplotrs/blob/main/vendor/krilla-0.8.2/PYPLOTRS_PATCH.md),
  and the license texts travel with it as `LICENSE-MIT` and `LICENSE-APACHE`.
  Source: <https://github.com/LaurenzV/krilla>.
