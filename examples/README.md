# figurs examples

Runnable example scripts. Each is self-contained and writes its figures into
[`output/`](output/) regardless of the directory you run it from, so the scripts
and their generated artifacts stay separate.

```sh
.venv/bin/python examples/hello.py        # minimal first plot (pdf/svg/png/html)
.venv/bin/python examples/phase1a.py      # multi-axes grid, ticks, shared axes
.venv/bin/python examples/phase1b.py      # core 2D marks + auto-legends
.venv/bin/python examples/phase1c.py      # imshow heatmaps + colorbars
.venv/bin/python examples/phase1d.py      # basic 3D (surface, line, scatter)
.venv/bin/python examples/phase1e.py      # mathtext + MathJax .html path
.venv/bin/python examples/phase2.py       # themes, annotations, tagged PDF, gg layer
.venv/bin/python examples/phase3.py       # animated GIF/APNG + interactive 3D .html
.venv/bin/python examples/math_check.py   # math rendering across every format
```

`output/` holds only generated artifacts — delete it any time and re-run a script
to regenerate. Performance benchmarks live in [`../benchmarks/`](../benchmarks).
