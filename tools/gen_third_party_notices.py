#!/usr/bin/env python3
"""Regenerate ``THIRD-PARTY-NOTICES.md`` from the resolved Cargo graph.

Every crate in ``Cargo.lock`` is compiled into the extension module that ships
in each wheel, so each wheel is a binary redistribution of all of them. Several
of those licenses require the notice to travel with the binary - BSD-3-Clause
(tiny-skia) says so in clause 2, Apache-2.0 in section 4(d) - and a
redistributor packaging pyplotrs downstream needs one file to point at rather
than a dependency tree to walk.

Run from the repository root::

    python tools/gen_third_party_notices.py

and commit the result. ``tests/test_packaging.py`` fails if the committed file
does not match what this script would write, so the notices cannot silently
drift out of date when a dependency is added or bumped.

Assets that are not Cargo dependencies - the fonts, the colormap tables, the
MathJax bundle - have their own notice files and are summarized here with a
pointer rather than duplicated.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "THIRD-PARTY-NOTICES.md"

#: Licenses we accept in the dependency tree. Anything outside this set is a
#: deliberate decision someone has to make, so the script fails rather than
#: quietly writing it into the notice file.
ALLOWED = {
    "0BSD", "Apache-2.0", "Apache-2.0 WITH LLVM-exception", "BSD-2-Clause",
    "BSD-3-Clause", "BSL-1.0", "CC0-1.0", "ISC", "MIT", "MIT-0",
    "MPL-2.0", "Unicode-3.0", "Unicode-DFS-2016", "Unlicense", "Zlib",
}

HEADER = """\
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
| DejaVu Sans, math symbol subset (`$...$` math) | Bitstream Vera | [`assets/fonts/DejaVuSans-LICENSE.txt`](assets/fonts/DejaVuSans-LICENSE.txt) |
| Fira Math (sans `$...$` math) | SIL OFL 1.1 | [`assets/fonts/FiraMath-OFL.txt`](assets/fonts/FiraMath-OFL.txt) |
| Colormap and palette tables | CC0-1.0, CC-BY-4.0, MIT, BSD-3-Clause | [`THIRD_PARTY_COLORMAPS.md`](THIRD_PARTY_COLORMAPS.md) |
| MathJax 3.2.2 (HTML math export) | Apache-2.0 | [`python/pyplotrs/_vendor/MATHJAX-NOTICE.md`](python/pyplotrs/_vendor/MATHJAX-NOTICE.md) |
| krilla (PDF backend, vendored fork) | MIT OR Apache-2.0 | [`vendor/krilla-0.8.2/PYPLOTRS_PATCH.md`](vendor/krilla-0.8.2/PYPLOTRS_PATCH.md) |

`docs/about/license.md` explains what each one is for.

## Rust dependencies

Statically linked into `pyplotrs._pyplotrs_core`, the extension module in every
wheel. Dual- and multi-licensed crates are listed with the upstream expression;
pyplotrs takes them under a permissive option compatible with MIT distribution.
"""


def main() -> int:
    meta = json.loads(subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--all-features"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout)

    workspace = {m.split()[0] for m in meta["workspace_members"]}
    by_license: dict[str, list[tuple[str, str]]] = defaultdict(list)
    unknown: list[tuple[str, str]] = []

    for pkg in meta["packages"]:
        if pkg["name"] in workspace:
            continue  # pyplotrs' own crates
        expr = pkg.get("license") or "NOT DECLARED"
        by_license[expr].append((pkg["name"], pkg["version"]))
        terms = {t.strip() for part in expr.replace("/", " OR ").split(" OR ")
                 for t in part.split(" AND ")}
        terms = {t.strip("()") for t in terms}
        if not terms & ALLOWED:
            unknown.append((pkg["name"], expr))

    if unknown:
        for name, expr in unknown:
            print(f"error: {name} has license {expr!r}, which is not in ALLOWED",
                  file=sys.stderr)
        return 1

    total = sum(len(v) for v in by_license.values())
    lines = [HEADER, f"\n{total} crates, grouped by license expression.\n"]
    for expr in sorted(by_license):
        crates = sorted(by_license[expr])
        lines.append(f"\n### {expr}\n")
        lines.append(", ".join(f"`{n} {v}`" for n, v in crates) + "\n")

    lines.append(
        "\n## Full license texts\n\n"
        "The MIT, Apache-2.0, BSD, ISC, Zlib and Unicode license texts are\n"
        "reproduced by their respective crates in the Cargo registry, and the\n"
        "Apache-2.0 text is included verbatim at\n"
        "[`python/pyplotrs/_vendor/MATHJAX-LICENSE.txt`](python/pyplotrs/_vendor/MATHJAX-LICENSE.txt)\n"
        "and [`vendor/krilla-0.8.2/LICENSE-APACHE`](vendor/krilla-0.8.2/LICENSE-APACHE).\n"
        "Run `cargo license` or `cargo about generate` for per-crate texts.\n"
    )
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {total} crates, "
          f"{len(by_license)} license expressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
