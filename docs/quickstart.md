# Quickstart

This page gets you from zero to a saved, publication-ready figure in a few
minutes. It assumes pyplotrs is [installed](installation.md). For a longer,
build-it-up walkthrough, see the [tutorial](tutorial.md); to run this page a
cell at a time instead of reading it, see the
[quickstart notebook](notebooks/01_quickstart.ipynb).

## Your first figure

Everything starts with [`subplots`][pyplotrs.subplots], which returns a
`Figure` and one or more `Axes`:

```python
import pyplotrs as pp

fig, ax = pp.subplots()
ax.line([0, 1, 2, 3, 4], [0, 1, 4, 9, 16])
fig.save("first.png")
```

That's the whole loop: **make a figure, draw on the axes, save.** There is no
hidden "current figure" — `fig` and `ax` are ordinary objects you hold onto, so
a function that builds a figure can just return it.

!!! tip "In a notebook"
    A `Figure` renders itself inline, so ending a cell with `fig` displays it.
    You never need a `show()`.

## Adding marks

An `Axes` carries a vocabulary of *marks*. Calls are chainable and the palette
cycles automatically, so each series gets a distinct, colorblind-safe color:

```python
import math
import pyplotrs as pp

xs = [i * 0.1 for i in range(80)]

fig, ax = pp.subplots()
ax.line(xs, [math.sin(x) for x in xs], label="sin")
ax.line(xs, [math.cos(x) for x in xs], label="cos", linestyle="dashed")
ax.scatter([1, 3, 5], [0.8, -0.1, -0.96], label="samples")
ax.legend()
ax.set(title="Trigonometric functions", xlabel="t", ylabel="value")
fig.save("trig.png")
```

`set(...)` is the one-stop method for titles, axis labels, limits, scales, ticks
and margins — pyplotrs has no `set_xlabel`/`set_xlim` family. `legend()` builds a
legend whose keys mirror the actual mark styles.

See [plot types](guide/plot-types.md) for the full mark vocabulary (`bar`,
`hist`, `boxplot`, `fill_between`, `errorbar`, `contour`, `imshow`, …).

## Reading an axes back

Writing is `set(**kwargs)`; reading is the `get_*` accessors. Every getter
reports the **effective** value — what will actually be drawn, autoscaling
included — not just what you happened to set:

```python
ax.get_xlim()        # (0.0, 8.0) even though no xlim was set
ax.get_xticks()      # the located tick positions
ax.get_yticklabels() # the strings that will be drawn
```

## Saving in any format

The format comes from the file extension:

```python
fig.save("figure.pdf")            # vector, with real editable/selectable text
fig.save("figure.svg")            # vector, fonts embedded
fig.save("figure.png", dpi=300)   # raster (200 dpi default)
fig.save("figure.html")           # self-contained page, selectable text
```

The **PDF** keeps text as genuine embedded fonts — open it in Illustrator and
every label is selectable and editable. More in [saving figures](guide/saving.md).

## Multiple panels

Pass a grid shape to `subplots`. With one row or column you get a flat list of
axes; with a full grid you get a list of rows:

```python
fig, axs = pp.subplots(1, 2, figsize=(500, 200), sharey=True)
axs[0].line(xs, [math.sin(x) for x in xs])
axs[1].line(xs, [math.cos(x) for x in xs])
axs[0].set(ylabel="y")
fig.set(suptitle="Two panels, shared y-axis")
fig.save("panels.png")
```

Uneven grids, spanning panels, twin axes and insets are all in the
[layout guide](guide/layout.md).

## Sizing in points

`figsize` is the canvas `(width, height)` in **points** by default (1 pt =
1/72 inch), so you can reason about a plot directly against its font scale. The
default is 250×200 pt — a single journal column wide, i.e. publication size out
of the box. Pass `units="in"`, `"cm"` or `"mm"` for another unit:

```python
pp.subplots(figsize=(89, 60), units="mm")   # a single Nature column
pp.subplots(figsize=(4, 3), units="in")
```

## Data pyplotrs accepts

Marks take any iterable of numbers — lists, tuples, generators, NumPy arrays,
pandas/polars columns. NumPy is not a dependency. Two input types also *choose
the axis for you*:

```python
ax.bar(["ash", "birch", "cedar"], [12, 19, 7])          # categorical x-axis
ax.line([date(2026, 1, 1), date(2026, 2, 1)], [3, 5])   # date x-axis
```

Non-finite values (`NaN`/`inf`) are ignored when autoscaling and break a line
into a gap rather than distorting the plot. More in
[scales & ticks](guide/scales-and-ticks.md).

## A taste of more

=== "Themes"

    ```python
    fig, ax = pp.subplots(theme="dark")
    ax.line(xs, [math.sin(x) for x in xs])
    fig.save("slide.png")
    ```

    [More on styling & themes →](guide/styling-and-themes.md)

=== "LaTeX math"

    ```python
    ax.set(title=r"$E = mc^2$", xlabel=r"$\omega_0$")
    ax.line(xs, ys, label=r"$\int_0^\infty e^{-x}\,dx$")
    ```

    [More on math & annotations →](guide/math-and-annotations.md)

=== "Images"

    ```python
    m = ax.imshow(field, cmap="magma")
    fig.colorbar(m, label="intensity")
    ```

    [More on colormaps & images →](guide/colormaps-and-images.md)

=== "Polar"

    ```python
    fig, ax = pp.subplots(projection="polar")
    ax.plot(theta, r, label="response")
    ```

    [More on polar plots →](guide/polar.md)

=== "3D"

    ```python
    fig, ax = pp.subplots(projection="3d")
    ax.surface(X, Y, Z, cmap="viridis")
    fig.save("surface.pdf")
    ```

    [More on 3D plots →](guide/3d.md)

Ready for the details? Work through the [tutorial](tutorial.md), continue to the
[user guide](guide/figure-and-axes.md), or jump into the
[gallery](gallery/index.md). Coming from matplotlib? Start with
[the differences](migrating-from-matplotlib.md).
