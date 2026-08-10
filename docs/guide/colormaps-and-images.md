# Colormaps & images

## Displaying a field

[`imshow`][pyplotrs.axes.Axes.imshow] renders a 2D array of numbers as a
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

~125 continuous colormaps ship as **exact** 256-entry tables — bit-for-bit
faithful to their upstream source, not approximations — curated from three
places:

* **matplotlib** — the perceptually-uniform maps (`viridis`, `plasma`,
  `inferno`, `magma`, `cividis`), the ColorBrewer-derived sequential/diverging
  families (`Blues`, `RdBu`, `Spectral`, ...), the cyclic maps (`twilight`,
  `hsv`), and the miscellaneous/rainbow family (`turbo`, `cubehelix`, ...) —
  upstream names and casing kept exactly.
* **[colorcet](https://colorcet.holoviz.org/)** — prefixed `cet_` (e.g.
  `cet_fire`, `cet_coolwarm`, `cet_glasbey` for large categorical sets — see
  [Palettes][pyplotrs.palettes]). CC-BY 4.0, Peter Kovesi et al.
* **[cmocean](https://matplotlib.org/cmocean/)** — prefixed `cmo_` (e.g.
  `cmo_thermal`, `cmo_balance`, `cmo_phase`), oceanography-oriented maps. MIT,
  Kristen Thyng et al.

Append `_r` to any name to reverse it (e.g. `"viridis_r"`).

```python
--8<-- "examples/colormaps.py"
```

![colormaps](../gallery/images/colormaps.png){ width="480" }

List them at runtime, optionally filtered to a category (`"sequential"`,
`"diverging"`, `"cyclic"`, `"perceptually_uniform"`, `"miscellaneous"`):

```python
from pyplotrs import colormaps
colormaps.available()                       # 125+ names
colormaps.available(category="diverging")   # ['BrBG', 'PRGn', ..., 'cmo_balance', ...]
```

For **categorical** data (a handful of distinct groups, not a continuous
scale), see [`pyplotrs.palettes`][pyplotrs.palettes] — `tab10`, the
ColorBrewer qualitative sets, seaborn's named palettes, and colorcet's
`glasbey` family for many-category data.

## Custom colormaps

Build a [`Colormap`][pyplotrs.colormaps.Colormap] from a short list of
`(position, (r, g, b))` stops:

```python
from pyplotrs.colormaps import Colormap

warm = Colormap("warm", [
    (0.0, (0, 0, 0)),
    (0.5, (200, 60, 0)),
    (1.0, (255, 220, 80)),
])
ax.imshow(data, cmap=warm)
```

Stops are resampled to 256 entries by interpolating in **Oklab** by default —
a perceptually uniform color space, so the gradient looks smooth rather than
banding or dipping in perceived brightness the way interpolating raw sRGB
does. Pass `space="srgb"` for the old naive-lerp behavior, or `"lab"`/
`"linear"` for the other supported spaces — see
[Color science][pyplotrs.color] for the conversions themselves.

A `Colormap` is just a callable `t -> (r, g, b, a)` over `t in [0, 1]`, so you
can sample it directly (e.g. to colour a series), and `warm.reversed()` flips
it. [`pyplotrs.color.cvd_safe_report`][pyplotrs.color.cvd_safe_report] checks
any colormap (built-in or custom) for colorblind-safety.
