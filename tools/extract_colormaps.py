#!/usr/bin/env python3
"""One-off data importer: matplotlib/colorcet/cmocean/seaborn -> pyplotrs-color.

This is a **dev tool**, not part of the pyplotrs package or build. It pulls a
curated set of colormap/palette tables from third-party packages and writes:

  * ``crates/pyplotrs-color/data/continuous.bin`` - concatenated 256x3-byte
    RGB tables, one per continuous colormap, in sorted-name order.
  * ``crates/pyplotrs-color/src/data/registry_gen.rs`` - generated index
    (name -> byte offset, category, source) for the continuous table above.
  * ``crates/pyplotrs-color/src/data/categorical_gen.rs`` - generated
    qualitative/categorical palettes as literal ``&[[u8; 3]]`` arrays.
  * ``tools/colormap_manifest.json`` - a human-reviewable manifest (name,
    source, category, size) for provenance/attribution.

Both generated ``.rs`` files are committed source; nothing at ``cargo build``
time touches Python or the network. Re-run this script (from a venv with
``matplotlib``, ``colorcet``, ``cmocean``, ``seaborn`` installed) only when
the curated set changes.

Usage::

    python3 -m venv /tmp/colorimport-venv
    /tmp/colorimport-venv/bin/pip install matplotlib colorcet cmocean seaborn
    /tmp/colorimport-venv/bin/python tools/extract_colormaps.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import colorcet as cc
import cmocean
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
COLOR_CRATE = ROOT / "crates" / "pyplotrs-color"
CONTINUOUS_BIN = COLOR_CRATE / "data" / "continuous.bin"
REGISTRY_RS = COLOR_CRATE / "src" / "data" / "registry_gen.rs"
CATEGORICAL_RS = COLOR_CRATE / "src" / "data" / "categorical_gen.rs"
MANIFEST_JSON = ROOT / "tools" / "colormap_manifest.json"

# -- matplotlib: curated allowlist, grouped exactly as mpl's own docs group
# them (https://matplotlib.org/stable/users/explain/colors/colormaps.html).
# Qualitative names are handled separately (categorical, not 256-entry).
MPL_PERCEPTUALLY_UNIFORM = ["viridis", "plasma", "inferno", "magma", "cividis"]
MPL_SEQUENTIAL = [
    "Greys", "Purples", "Blues", "Greens", "Oranges", "Reds",
    "YlOrBr", "YlOrRd", "OrRd", "PuRd", "RdPu", "BuPu",
    "GnBu", "PuBu", "YlGnBu", "PuBuGn", "BuGn", "YlGn",
]
MPL_SEQUENTIAL2 = [
    "binary", "gist_yarg", "gist_gray", "gray", "bone", "pink",
    "spring", "summer", "autumn", "winter", "cool", "Wistia",
    "hot", "afmhot", "gist_heat", "copper",
]
MPL_DIVERGING = [
    "PiYG", "PRGn", "BrBG", "PuOr", "RdGy", "RdBu", "RdYlBu", "RdYlGn",
    "Spectral", "coolwarm", "bwr", "seismic", "berlin", "managua", "vanimo",
]
MPL_CYCLIC = ["twilight", "twilight_shifted", "hsv"]
MPL_MISC = [
    "flag", "prism", "ocean", "gist_earth", "terrain", "gist_stern",
    "gnuplot", "gnuplot2", "CMRmap", "cubehelix", "brg", "gist_rainbow",
    "rainbow", "jet", "turbo", "nipy_spectral", "gist_ncar",
]
MPL_QUALITATIVE = [
    "Pastel1", "Pastel2", "Paired", "Accent", "Dark2",
    "Set1", "Set2", "Set3", "tab10", "tab20", "tab20b", "tab20c", "okabe_ito",
]
# Aliases: keep back-compat / alternate-spelling names pointing at the same
# table as their canonical entry (no duplicate bytes).
MPL_ALIASES = {
    "grays": "Greys",       # pyplotrs' pre-existing name
    "grey": "gray",
    "gist_grey": "gist_gray",
    "gist_yerg": "gist_yarg",
    "Grays": "Greys",
}

MPL_CATEGORY_OF = {
    **{n: "perceptually_uniform" for n in MPL_PERCEPTUALLY_UNIFORM},
    **{n: "sequential" for n in MPL_SEQUENTIAL},
    **{n: "sequential" for n in MPL_SEQUENTIAL2},
    **{n: "diverging" for n in MPL_DIVERGING},
    **{n: "cyclic" for n in MPL_CYCLIC},
    **{n: "miscellaneous" for n in MPL_MISC},
}
MPL_CONTINUOUS = list(MPL_CATEGORY_OF)

# -- colorcet: curated plain-named subset of the ~210-entry `colorcet.palette`
# registry (skips the long descriptive `linear_*_c##`/`CET_*` codenames and
# `_s25`/protanopic/tritanopic variants - see tools/colormap_manifest.json for
# the final list actually pulled).
CET_SEQUENTIAL = [
    "bgy", "bgyw", "blues", "bmw", "bmy", "dimgray", "fire", "gouldian",
    "gray", "kb", "kbc", "kbgyw", "kg", "kgy", "kr",
]
CET_DIVERGING = ["bkr", "bky", "gwv", "bjy", "cwr", "bwy", "coolwarm"]
CET_CYCLIC = ["colorwheel", "isolum"]
CET_MISC = ["rainbow", "rainbow4"]
CET_CATEGORY_OF = {
    **{n: "sequential" for n in CET_SEQUENTIAL},
    **{n: "diverging" for n in CET_DIVERGING},
    **{n: "cyclic" for n in CET_CYCLIC},
    **{n: "miscellaneous" for n in CET_MISC},
}
CET_CONTINUOUS = list(CET_CATEGORY_OF)
CET_GLASBEY = ["glasbey", "glasbey_hv", "glasbey_dark", "glasbey_light", "glasbey_cool", "glasbey_warm"]

# -- cmocean: full named set (base names only - `_r`/`_i` variants excluded;
# pyplotrs' generic `_r` suffix already reverses any registered name).
CMO_DIVERGING = ["balance", "delta", "curl", "diff", "tarn"]
CMO_CYCLIC = ["phase"]
CMO_MISC = ["topo"]
CMO_SEQUENTIAL = [
    "algae", "amp", "deep", "dense", "gray", "haline", "ice", "matter",
    "oxy", "rain", "solar", "speed", "tempo", "thermal", "turbid",
]
CMO_CATEGORY_OF = {
    **{n: "sequential" for n in CMO_SEQUENTIAL},
    **{n: "diverging" for n in CMO_DIVERGING},
    **{n: "cyclic" for n in CMO_CYCLIC},
    **{n: "miscellaneous" for n in CMO_MISC},
}
CMO_CONTINUOUS = list(CMO_CATEGORY_OF)

# -- seaborn: named qualitative palettes (10 colors each).
SNS_QUALITATIVE = ["deep", "muted", "bright", "pastel", "dark", "colorblind"]


def _mpl_table(name: str) -> list[tuple[int, int, int]]:
    cmap = plt.get_cmap(name)
    return [
        tuple(int(round(c * 255)) for c in cmap(i / 255.0)[:3])
        for i in range(256)
    ]


def _mpl_colors(name: str) -> list[tuple[int, int, int]]:
    cmap = plt.get_cmap(name)
    return [tuple(int(round(c * 255)) for c in rgb[:3]) for rgb in cmap.colors]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _cet_table(name: str) -> list[tuple[int, int, int]]:
    return [_hex_to_rgb(h) for h in cc.palette[name]]


def _cmo_table(name: str) -> list[tuple[int, int, int]]:
    cmap = cmocean.cm.cmap_d[name]
    return [
        tuple(int(round(c * 255)) for c in cmap(i / 255.0)[:3])
        for i in range(256)
    ]


def _sns_colors(name: str) -> list[tuple[int, int, int]]:
    return [tuple(int(round(c * 255)) for c in rgb) for rgb in sns.color_palette(name)]


def main() -> None:
    continuous: dict[str, tuple[list[tuple[int, int, int]], str, str]] = {}
    for n in MPL_CONTINUOUS:
        continuous[n] = (_mpl_table(n), MPL_CATEGORY_OF[n], "matplotlib")
    for n in CET_CONTINUOUS:
        continuous[f"cet_{n}"] = (_cet_table(n), CET_CATEGORY_OF[n], "colorcet")
    for n in CMO_CONTINUOUS:
        continuous[f"cmo_{n}"] = (_cmo_table(n), CMO_CATEGORY_OF[n], "cmocean")

    for alias, target in MPL_ALIASES.items():
        table, cat, src = continuous[target]
        continuous[alias] = (table, cat, src)

    categorical: dict[str, tuple[list[tuple[int, int, int]], str]] = {}
    for n in MPL_QUALITATIVE:
        categorical[n] = (_mpl_colors(n), "matplotlib")
    for n in CET_GLASBEY:
        categorical[f"cet_{n}"] = (_cet_table(n), "colorcet")
    for n in SNS_QUALITATIVE:
        categorical[f"sns_{n}"] = (_sns_colors(n), "seaborn")

    names = sorted(continuous)
    offsets: dict[str, int] = {}
    blob = bytearray()
    # Aliases and cross-source duplicates share one byte range: only the
    # first name to reach a given table's identity pays for its bytes.
    table_offset_by_id: dict[int, int] = {}
    for n in names:
        table, _cat, _src = continuous[n]
        key = id(table)
        if key in table_offset_by_id:
            offsets[n] = table_offset_by_id[key]
            continue
        offsets[n] = len(blob)
        table_offset_by_id[key] = offsets[n]
        for r, g, b in table:
            blob += bytes((r, g, b))

    CONTINUOUS_BIN.parent.mkdir(parents=True, exist_ok=True)
    CONTINUOUS_BIN.write_bytes(bytes(blob))

    REGISTRY_RS.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY_RS.open("w") as f:
        f.write("// Generated by tools/extract_colormaps.py. Do not edit by hand.\n")
        f.write("use crate::registry::{Category, ContinuousEntry, Source};\n\n")
        f.write(f"pub static CONTINUOUS: &[ContinuousEntry] = &[\n")
        for n in names:
            _table, cat, src = continuous[n]
            cat_variant = "".join(p.capitalize() for p in cat.split("_"))
            f.write(
                f'    ContinuousEntry {{ name: "{n}", offset: {offsets[n]}, '
                f"category: Category::{cat_variant}, source: Source::{src.capitalize()} }},\n"
            )
        f.write("];\n")

    with CATEGORICAL_RS.open("w") as f:
        f.write("// Generated by tools/extract_colormaps.py. Do not edit by hand.\n")
        f.write("use crate::registry::{CategoricalEntry, Source};\n\n")
        for n in sorted(categorical):
            colors, _src = categorical[n]
            const_name = "PAL_" + "".join(c if c.isalnum() else "_" for c in n).upper()
            f.write(f"static {const_name}: &[[u8; 3]] = &[\n")
            for r, g, b in colors:
                f.write(f"    [{r}, {g}, {b}],\n")
            f.write("];\n\n")
        f.write("pub static CATEGORICAL: &[CategoricalEntry] = &[\n")
        for n in sorted(categorical):
            _colors, src = categorical[n]
            const_name = "PAL_" + "".join(c if c.isalnum() else "_" for c in n).upper()
            f.write(
                f'    CategoricalEntry {{ name: "{n}", colors: {const_name}, '
                f"source: Source::{src.capitalize()} }},\n"
            )
        f.write("];\n")

    manifest = {
        "continuous": {
            n: {"category": continuous[n][1], "source": continuous[n][2], "n": len(continuous[n][0])}
            for n in names
        },
        "categorical": {
            n: {"source": categorical[n][1], "n": len(categorical[n][0])}
            for n in sorted(categorical)
        },
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"continuous: {len(names)} names, {len(blob)} bytes -> {CONTINUOUS_BIN}")
    print(f"categorical: {len(categorical)} palettes -> {CATEGORICAL_RS}")


if __name__ == "__main__":
    main()
