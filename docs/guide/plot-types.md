# Plot types

Every 2D mark is a method on [`Axes`][pyplotrs.figure.Axes]. They share a few
conventions:

- `color` may be `None` (cycle the palette), a `"C0".."C7"` palette index, or an
  `(r, g, b)` / `(r, g, b, a)` byte tuple.
- `label=` registers the mark in the legend.
- Calls return the axes, so they chain.

## Line

[`line`][pyplotrs.figure.Axes.line] plots a polyline. `linestyle` is one of
`solid`, `dashed`, `dotted`, `dashdot` (or `none` for markers only); an optional
`marker` draws a glyph at each vertex.

```python
--8<-- "examples/line.py"
```

![line plot](../gallery/images/line.png){ width="520" }

!!! tip "Dense data"
    `line` collapses runs of near-collinear vertices in device space by default
    (`simplify=True`) — visually identical output, far smaller and faster vector
    files on large data. Pass `simplify=False` to keep every vertex exactly.

## Scatter

[`scatter`][pyplotrs.figure.Axes.scatter] places markers. `size` is the marker
**area** in pt² (matching matplotlib's `s`), so the drawn diameter is
`sqrt(size)`. Marker shapes: `o` `s` `^` `v` `D` (filled) and `+` `x` (stroked).

```python
--8<-- "examples/scatter.py"
```

![scatter plot](../gallery/images/scatter.png){ width="520" }

## Bar

[`bar`][pyplotrs.figure.Axes.bar] draws vertical bars. The y-range is forced to
include the 0 baseline when all heights are non-negative.

```python
--8<-- "examples/bar.py"
```

![bar chart](../gallery/images/bar.png){ width="460" }

## Histogram

[`hist`][pyplotrs.figure.Axes.hist] bins data into equal-width bins. Use
`density=True` to normalize to a probability density, and `range=(lo, hi)` to fix
the binning extent.

```python
--8<-- "examples/histogram.py"
```

![histogram](../gallery/images/histogram.png){ width="460" }

## Fill between

[`fill_between`][pyplotrs.figure.Axes.fill_between] shades the band between two
curves (or a curve and a constant) — ideal for confidence intervals. `alpha`
controls transparency.

```python
--8<-- "examples/fill_between.py"
```

![fill between](../gallery/images/fill_between.png){ width="520" }

## Error bars

[`errorbar`][pyplotrs.figure.Axes.errorbar] draws symmetric `yerr`/`xerr` bars
with caps, optionally connected by a line and decorated with markers.

```python
--8<-- "examples/errorbar.py"
```

![error bars](../gallery/images/errorbar.png){ width="520" }

## Images & heatmaps

[`imshow`][pyplotrs.figure.Axes.imshow] displays a 2D field as a colormapped
image and returns a handle you can pass to
[`Figure.colorbar`][pyplotrs.figure.Figure.colorbar]. See
[colormaps & images](colormaps-and-images.md) for the full story.

```python
--8<-- "examples/heatmap.py"
```

![heatmap](../gallery/images/heatmap.png){ width="520" }
