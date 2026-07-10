# Notebooks

Interactive notebooks for developing and verifying pyplotrs.

| Notebook | Purpose |
|---|---|
| `verify_core_plots.ipynb` | Render every core plot type inline for one-by-one visual review |

## Running

Install the dev extra (which pulls in a Jupyter kernel) into the project venv,
then open a notebook and select that environment as the kernel:

```bash
uv pip install -e '.[dev]'     # ipykernel; run maturin develop first if needed
```

The notebooks `import pyplotrs as plt`, so they need pyplotrs importable in the
kernel — i.e. built into the venv with `maturin develop` (see the top-level
build instructions). Figures display inline via `Figure._repr_png_`.
