# MathJax — third-party notice

`mathjax-tex-svg-full.min.js` in this directory is a verbatim, unmodified copy
of a **MathJax v3.2.2** distribution bundle (the `tex-svg-full` component:
the TeX input processor, the SVG output processor, and the full extension set).

| | |
|---|---|
| **Component** | MathJax |
| **Version** | 3.2.2 (`e.VERSION="3.2.2"` in the bundle) |
| **Copyright** | © 2009–2022 The MathJax Consortium |
| **License** | Apache License 2.0 — full text in [`MATHJAX-LICENSE.txt`](MATHJAX-LICENSE.txt) |
| **Source** | <https://github.com/mathjax/MathJax> |
| **Homepage** | <https://www.mathjax.org/> |

## Why it ships

`Figure.save("*.html")` re-typesets `$...$` math with MathJax so the result is
selectable and copyable in a browser, and inlines the whole library into the
page so that page works with no network access. See
`python/pyplotrs/_htmlmath.py`.

This is **separate from** pyplotrs' own math engine (`crates/pyplotrs-math`),
which typesets math for PDF, SVG and PNG from the math font's OpenType MATH
table and uses none of this code.

## Components inside the bundle

MathJax's distribution bundles are built from several projects. All are
redistributed here under the terms above; where a component carries its own
upstream license, that license is compatible with Apache-2.0 and the component
is distributed by MathJax under Apache-2.0 as part of the bundle.

| Component | Role | Upstream |
|---|---|---|
| MathJax core, TeX input, SVG output | typesetting | <https://github.com/mathjax/MathJax-src> |
| Speech Rule Engine 4.0.6 | accessibility / speech text | <https://github.com/zorkow/speech-rule-engine> |
| `wicked-good-xpath` | XPath shim used by the Speech Rule Engine | <https://github.com/google/wicked-good-xpath> |
| TeX extensions (`mhchem`, `ams`, `physics`, `mathtools`, …) | TeX macro packages | shipped in MathJax-src |

## Requirements this file satisfies

Apache-2.0 §4 requires that a redistribution carry the license text (§4(a)) and
any attribution notices (§4(d)). Both files in this directory are listed in
`[project] license-files` in `pyproject.toml`, so they are installed into
`pyplotrs-<version>.dist-info/licenses/` in every wheel and are present in the
source distribution.

Because `_htmlmath.py` inlines the bundle into each generated `.html` file,
that file is itself a redistribution. A short attribution banner is prepended
at inline time so the notice travels with it; see `_MATHJAX_BANNER` in
`python/pyplotrs/_htmlmath.py`.

## Updating

Replace `mathjax-tex-svg-full.min.js` with the new `tex-svg-full.js` from the
MathJax release, and update the version and copyright range in this file and in
`docs/about/license.md`. `tests/test_packaging.py` asserts that the version
recorded here matches the one in the bundle.
