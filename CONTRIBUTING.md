# Contributing to pyplotrs

Bug reports and focused pull requests are welcome.

## Setup

You need [uv](https://docs.astral.sh/uv/) and a Rust toolchain (1.92+).

```bash
git clone https://github.com/tkclam/pyplotrs && cd pyplotrs
uv sync
```

`uv sync` builds the Rust extension in release mode and installs the dev
tools. `uv run ...` rebuilds it automatically when files under `crates/`
change.

## Checks

CI runs exactly these:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test -p pyplotrs-engine --locked
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest
uv run --group docs mkdocs build --strict
```

`uv run --group bench python benchmarks/benchmark.py` compares speed with
matplotlib.

## Where things live

- `crates/engine`: pure Rust. `scene.rs` is the drawing description all
  renderers share; `draw.rs` turns columns of data into scene nodes;
  `render/` holds the PDF, SVG and PNG backends; `math/` typesets `$...$`;
  `kernels.rs` has the numeric routines (histograms, contours, ...).
- `crates/python`: the `pyplotrs._core` bindings. Keep
  `python/pyplotrs/_core.pyi` in step (a test checks the names match).
- `python/pyplotrs`: `figure.py` (page layout and saving), `axes.py` (the
  plotting API), `artists.py` (one class per kind of mark), `_frame.py`
  (ticks, spines, labels, colorbars), `_axis.py` (limits and tick location).

A new kind of mark is usually one artist class (data limits, `draw`, legend
key) plus one `Axes` method that validates input and creates it. Keep
per-point loops out of Python: if a mark needs one, add a batched primitive to
`draw.rs`.

## Conventions

- A bug fix comes with a test that fails without it.
- Invalid input raises a clear error instead of drawing something wrong.
- `linewidth` is a stroke width in points, `width` an extent in data units,
  marker `size` a diameter in points.
- Comments explain why, briefly. History belongs in commit messages.
- American English: color, center, gray.
