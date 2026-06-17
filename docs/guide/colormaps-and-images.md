# Colormaps & images

## Displaying a field

[`imshow`][pyplotrs.figure.Axes.imshow] renders a 2D array of numbers as a
colormapped image. `data` is a sequence of equal-length rows.

```python
--8<-- "examples/heatmap.py"
```

![heatmap](../gallery/images/heatmap.png){ width="520" }

Key options:

| Argument | Meaning |
|---|---|
| `cmap` | a colormap name or a `Colormap` (default `"viridis"`) |
| `vmin`, `vmax` | data values mapped to the low/high end (default: data min/max) |
| `extent` | `(x0, x1, y0, y1)` data coordinates of the image edges |
| `origin` | `"upper"` (row 0 at top, default) or `"lower"` |

Non-finite values (`NaN`/`inf`) render as transparent, so masked regions show
the background through.

## Colorbars

`imshow` returns a handle you pass to
[`Figure.colorbar`][pyplotrs.figure.Figure.colorbar]; the colorbar is laid out
in a reserved band beside its axes (never overlapping the data):

```python
m = ax.imshow(data, cmap="magma", vmin=0, vmax=1)
fig.colorbar(m, label="intensity")
```

## Built-in colormaps

The perceptually-uniform maps (`viridis`, `plasma`, `inferno`, `magma`,
`cividis`) are the **exact** 256-entry CC0 tables from matplotlib — bit-for-bit
faithful, not approximations. Also bundled: `coolwarm` (diverging) and `grays`.
Append `_r` to any name to reverse it (e.g. `"viridis_r"`).

```python
--8<-- "examples/colormaps.py"
```

![colormaps](../gallery/images/colormaps.png){ width="480" }

List them at runtime:

```python
from pyplotrs import colormaps
colormaps.available()      # ['cividis', 'coolwarm', 'gray', 'grays', ...]
```

## Custom colormaps

Build a [`Colormap`][pyplotrs.colormaps.Colormap] from a short list of
`(position, (r, g, b))` stops with linear interpolation between them:

```python
from pyplotrs.colormaps import Colormap

warm = Colormap("warm", [
    (0.0, (0, 0, 0)),
    (0.5, (200, 60, 0)),
    (1.0, (255, 220, 80)),
])
ax.imshow(data, cmap=warm)
```

A `Colormap` is just a callable `t -> (r, g, b, a)` over `t in [0, 1]`, so you
can sample it directly (e.g. to colour a series), and `warm.reversed()` flips it.
