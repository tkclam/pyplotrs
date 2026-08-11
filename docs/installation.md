# Installation

## From PyPI

```bash
pip install pyplotrs
```

Pre-built wheels ship the compiled Rust core and the bundled fonts, so there is
**no build step and no Rust toolchain required** on the common platforms
(Linux, macOS, Windows; x86-64 and arm64).

pyplotrs supports **Python 3.9+** and has **no required runtime dependencies** —
not even NumPy. It accepts plain Python lists (and anything iterable), and works
with NumPy arrays or pandas/polars columns if you have them.

!!! tip "Virtual environments"
    As always, prefer installing into a virtual environment:

    ```bash
    python -m venv .venv
    source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install pyplotrs
    ```

## Verify

```python
import pyplotrs as plt

fig, ax = plt.subplots()
ax.line([0, 1, 2], [0, 1, 4])
fig.save("test.png")
print(plt.resolved_font_name())   # the body font resolved on this machine
```

## From source

Building from source needs a **Rust toolchain (1.92 or newer)** and
[maturin](https://www.maturin.rs/). The project uses
[uv](https://docs.astral.sh/uv/) in development, but any PEP 517 frontend works.

!!! note "What a source build actually does"
    It compiles ~110 crates with `lto = true` and `codegen-units = 1`, which
    takes a few minutes and needs network access to fetch the registry the
    first time. The build is entirely offline afterwards. You only need any of
    this on a platform with no wheel — `pip install pyplotrs` downloads a
    pre-built one on Linux, macOS and Windows, x86-64 and arm64.

=== "pip"

    ```bash
    git clone https://github.com/tkclam/pyplotrs
    cd pyplotrs
    pip install .
    ```

=== "uv + maturin (editable dev build)"

    ```bash
    git clone https://github.com/tkclam/pyplotrs
    cd pyplotrs
    uv venv
    uv pip install maturin
    maturin develop --release    # build + install into the venv
    ```

`maturin develop` builds the extension and installs it editable, so Python
changes are picked up immediately and only Rust changes need a rebuild. Drop
`--release` for faster compiles while developing (slower runtime).

## Optional extras

| Extra | Installs | For |
|---|---|---|
| `pyplotrs[docs]` | mkdocs-material, mkdocstrings, black | Building this documentation site |
| `pyplotrs[test]` | pytest | Running the test suite |
| `pyplotrs[bench]` | matplotlib, numpy | Running the head-to-head benchmarks |
| `pyplotrs[dev]` | ipykernel, matplotlib | The verify notebooks under `notebooks/` |

```bash
pip install -e ".[docs]"
mkdocs serve
```

None of these are needed to *use* pyplotrs — the library itself has no runtime
dependencies.

## What gets bundled

pyplotrs embeds two fonts into the compiled extension (so rendering always works
without relying on system fonts):

- **Liberation Sans** — the permissive, Arial-metric-compatible fallback for
  body text, labels, ticks and legends.
- **STIX Two Math** — used for `$...$` math spans.

Both are under the SIL Open Font License 1.1. For body text pyplotrs prefers the
host's Arial, then Helvetica, before falling back to Liberation Sans — and
embeds whichever it picks into every saved figure. See
[styling & themes](guide/styling-and-themes.md#fonts) for how to control this.
