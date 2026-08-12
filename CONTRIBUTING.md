# Contributing to pyplotrs

Thanks for taking a look. Bug reports and small, focused pull requests are both
welcome.

## Getting set up

You need a **Rust toolchain 1.92 or newer** and Python 3.9+.

```bash
git clone https://github.com/tkclam/pyplotrs
cd pyplotrs

uv venv && source .venv/bin/activate     # or: python -m venv .venv
uv pip install maturin
maturin develop --release                # builds the Rust core into the venv
uv pip install -e ".[test,docs,bench,dev]"
```

`maturin develop` needs an **activated** virtualenv — it refuses to run
without one. Use `pip install -e .` if you would rather not think about it.

Rebuild the extension with `maturin develop --release` after any change under
`crates/`. Changes under `python/` take effect immediately.

## The gate

These are exactly the commands CI runs. If they pass locally they pass there.

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
ruff check .
pytest -q --strict-markers
pytest -q --strict-markers -m packaging   # slow: builds and resolves an sdist
python benchmarks/benchmark.py --check
python tools/build_notebooks.py --check   # every documentation notebook runs
mkdocs build --strict
```

`ruff format` is deliberately **not** part of the gate — it would rewrite 80 of
103 files, and several tables in this codebase are hand-aligned to be read as
tables. `ruff check`'s rule set is chosen to catch defects; see the comment on
`[tool.ruff.lint] select` in `pyproject.toml`.

## What the code expects of a change

- **A bug fix comes with a test that fails without it.** Most of
  `tests/test_regressions.py` is one test per historical bug, and the docstring
  says what the bug looked like — follow that shape.
- **Every new public `Axes` method must be classified.**
  `tests/test_api.py::test_every_public_axes_method_is_classified` fails until
  a new method is either registered in `_MARK_CALLS` (which subjects it to five
  behavioral checks: it records a mark, `alpha` changes the rendered bytes,
  `label` reaches the legend, the legend draws, `zorder` survives) or listed in
  `_NOT_MARKS` with a reason. This exists because three separate audits found
  the same bug — a contract true of the marks it was written against and
  silently false of the ones added next.
- **Module sizes are capped.** `tests/test_module_layout.py` holds `axes.py`
  under 3,200 lines and every other module under 1,200.
- **Golden images move only on purpose.** If a change shifts pixels,
  `PYPLOTRS_UPDATE_GOLDEN=1 pytest tests/test_golden.py` regenerates them —
  but look at the diff before you commit it. A regenerated golden has hidden a
  real bug here before.
- **Wrong input must raise, not draw.** A figure that looks deliberate and is
  wrong is the one failure mode this library cannot have. New validation goes
  in `tests/test_errors.py`.

## Style

Match the file you are editing. The two things worth stating:

- **One name per concept.** `linewidth` is always a stroke width in points;
  `width` is always an extent in data units. `markersize` is a diameter in
  points.
- **Comments say why, not what.** The interesting comments in this codebase
  explain a decision or a bug that motivated the code — that is the standard.

American English throughout: `color`, `center`, `normalize`, `gray`.

## Committed artifacts

Three things in the tree are generated and committed, so a change that moves
rendering has to regenerate them or they become claims about an older build:

```bash
python tools/build_gallery_images.py     # docs/gallery/images/, from examples/
python tools/build_tutorial_images.py    # docs/images/, for the tutorial page
python tools/build_notebooks.py          # docs/notebooks/*.ipynb, in place
```

All three pin the bundled Liberation Sans, so their output is reproducible on a
machine that has Arial or Helvetica installed and on CI, which has neither.

## Reporting a bug

Open an issue with the output of:

```python
import pyplotrs, sys
print(pyplotrs.__version__, sys.version, pyplotrs.resolved_font_name())
```

plus the smallest script that reproduces it and the output format
(`.pdf`/`.svg`/`.png`/`.html`) — the backends diverge, and which one you used
is usually the first question.

## Licensing of contributions

Unless you state otherwise, any contribution you intentionally submit for
inclusion in this work is licensed under the [MIT license](https://github.com/tkclam/pyplotrs/blob/main/LICENSE), with no
additional terms.

If your change adds a third-party asset or a Rust dependency, run
`python tools/gen_third_party_notices.py` and commit the regenerated
`THIRD-PARTY-NOTICES.md`; `tests/test_packaging.py` fails if it is stale, and
the generator refuses any license outside its allowlist.
