# Quickstart

This page gets you from zero to a saved, publication-ready figure in a few
minutes. It assumes pyplotrs is [installed](installation.md).

## Your first figure

Everything starts with [`subplots`][pyplotrs.figure.subplots], which returns a
`Figure` and one or more `Axes`:

```python
import pyplotrs as plt

fig, ax = plt.subplots()
ax.line([0, 1, 2, 3, 4], [0, 1, 4, 9, 16])
fig.save("first.png")
```

That's the whole loop: **make a figure, draw on the axes, save.** There is no
hidden "current figure" — `fig` and `ax` are ordinary objects you hold onto.

## Adding marks

An `Axes` carries a vocabulary of *marks*. Calls are chainable and the palette
cycles automatically, so each series gets a distinct, colorblind-safe color:

```python
import math
import pyplotrs as plt

xs = [i * 0.1 for i in range(80)]

fig, ax = plt.subplots()
ax.line(xs, [math.sin(x) for x in xs], label="sin")
ax.line(xs, [math.cos(x) for x in xs], label="cos", linestyle="dashed")
ax.scatter([1, 3, 5], [0.8, -0.1, -0.96], label="samples")
ax.legend()
ax.set(title="Trigonometric functions", xlabel="t", ylabel="value")
fig.save("trig.png")
```

`set(...)` is a one-stop method for the title, axis labels and view limits.
`legend()` builds a legend whose glyphs mirror the actual mark styles.

See [plot types](guide/plot-types.md) for the full mark vocabulary
(`bar`, `hist`, `fill_between`, `errorbar`, `imshow`, …).

## Saving in any format

The format is chosen from the file extension:

```python
fig.save("figure.pdf")    # vector, with real editable/selectable text
fig.save("figure.svg")    # vector, fonts embedded
fig.save("figure.png", dpi=300)   # raster (200 dpi default)
fig.save("figure.html")   # self-contained page, selectable text
```

The **PDF** keeps text as genuine embedded fonts — open it in Illustrator and
every label is selectable and editable. More in [saving figures](guide/saving.md).

## Multiple panels

Pass a grid shape to `subplots`. With one row or column you get a flat list of
axes; with a full grid you get rows of axes:

```python
fig, axs = plt.subplots(1, 2, figsize=(640, 260), sharey=True)
axs[0].line(xs, [math.sin(x) for x in xs])
axs[1].line(xs, [math.cos(x) for x in xs])
axs[0].set(ylabel="y")
fig.set(suptitle="Two panels, shared y-axis")
fig.save("panels.png")
```

## Sizing in points

`figsize` is the canvas `(width, height)` in **points** by default (1 pt =
1/72 inch), so you can reason about a plot directly against its font scale. The
default is 250×200 pt — a single journal column wide, i.e. publication size out
of the box. Pass `units="in"`, `"cm"` or `"mm"` for another unit:

```python
plt.subplots(figsize=(89, 60), units="mm")   # a single Nature column
plt.subplots(figsize=(4, 3), units="in")
```

## A taste of more

=== "Themes"

    ```python
    fig, ax = plt.subplots(theme="presentation")
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

=== "3D"

    ```python
    fig, ax = plt.subplots(projection="3d")
    ax.surface(X, Y, Z, cmap="viridis")
    fig.save("surface.pdf")
    ```

    [More on 3D plots →](guide/3d.md)

Ready for the details? Continue to the [user guide](guide/figure-and-axes.md), or
jump into the [gallery](gallery/index.md).
