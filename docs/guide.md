# Guide

## Figures and axes

A **figure** is the page; an **axes** is one plot on it. Make both with
`subplots`:

```python
fig, ax = pp.subplots()  # one axes
fig, axs = pp.subplots(1, 3)  # a list of three
fig, grid = pp.subplots(2, 2, sharex=True)  # a list of rows
```

Sizes are in points (1/72 inch) by default; the 250 x 200 pt default is a
single journal column. Pass `units="in"`, `"cm"` or `"mm"` to use others:

```python
fig, axs = pp.subplots(1, 2, figsize=(183, 60), units="mm", width_ratios=[2, 1])
```

Plots line up across rows and columns automatically, leaving room for every
label. For uneven layouts, name the cells:

```python
fig, axd = pp.subplot_mosaic("""
    AAB
    CDB
""")
axd["A"].line(t, v)
```

Or place axes on a grid yourself with `fig = pp.figure(nrows=2, ncols=3)` and
`fig.add_axes(row, col, rowspan=1, colspan=2)`.

`sharex`/`sharey` take `True` (all axes), `"row"` or `"col"`.

## Plotting

Every plotting method returns the artist it creates, so it can be adjusted or
passed on (for example to `fig.colorbar`).

| | |
|---|---|
| Lines and points | `line`, `scatter`, `step`, `stairs`, `stem`, `errorbar` |
| Bars and areas | `bar`, `barh`, `hist`, `fill_between`, `fill_betweenx`, `stackplot` |
| Distributions | `boxplot`, `violinplot`, `hist2d`, `hexbin`, `pie` |
| Fields | `imshow`, `pcolormesh`, `contour`, `contourf`, `quiver`, `streamplot` |
| Events | `eventplot`, `hlines`, `vlines` |
| Guides | `axhline`, `axvline`, `axhspan`, `axvspan`, `axline` |
| Shapes | `rectangle`, `circle`, `ellipse`, `polygon`, `arrow` |
| Text | `text`, `annotate` |
| Figure marks | `scalebar`, `bracket` |

Data can be lists, `array.array`, or NumPy arrays (read without copying when
they are float64). NaN leaves a gap in a line. Strings make a categorical axis
and datetimes a date axis.

Colors are names (`"steelblue"`, `"k"`), hex (`"#1f77b4"`), RGB tuples of
0-1 floats or 0-255 ints, or palette entries `"C0"`, `"C1"`, ... from the
theme. Line styles are `"solid"`, `"dashed"`, `"dotted"`, `"dashdot"` (or
`-`, `--`, `:`, `-.`); markers are `o s ^ v D + x | _`.

## Configuring an axes

All axes settings go through `set`, which returns the axes:

```python
ax.set(
    title="Response",
    xlabel="time (s)",
    ylabel=r"$\Delta F / F_0$",
    xlim=(0, 10),  # either end may be None
    yscale="log",  # linear, log, symlog, logit, date
    xticks=[0, 5, 10],
    xticklabels=["start", "mid", "end"],
    yformatter="{x:.0%}",  # a format string, a function, or pyplotrs.ticker.*
    margin=0,  # autoscale padding as a fraction of the span
    grid=True,
    aspect="equal",
)
```

Read values back with `get_xlim()`, `get_xticks()`, `get_xticklabels()`, and
so on; they report what will be drawn, including autoscaling and sharing.

To leave out an empty stretch of an axis, break it. The rest is drawn as
separate pieces, sized by their data span, with break marks on the spines:

```python
ax.bar(["walk", "groom", "rest"], [412, 23, 31])
ax.set(ybreak=(40, 390))  # a list of pairs makes several breaks
```

Other axes features: `ax.legend(loc="best", ncols=2)`, `ax.twinx()`,
`ax.twiny()`, `ax.inset_axes((x, y, w, h))`, and `ax.set(frame=False)`.
For panel letters, `ax.set(title=pp.bold("a"), title_loc="left")`.

## Colormaps and colorbars

```python
im = ax.imshow(z, cmap="magma", norm="log")
fig.colorbar(im, label="intensity")
```

`scatter` and `line` take `c=values` to color points, or a line along its
length, by value (a walking path colored by time, say):

```python
path = ax.line(x, y, c=t, cmap="viridis")
fig.colorbar(path, label="time (s)")
```

There are about 125 colormaps (`pp.colormaps.names()`) and 25 palettes
(`pp.colormaps.palette("tab10")`); add `_r` to reverse one, or build your own
with `pp.Colormap.from_colors(["navy", "white", "firebrick"])`. Norms are in
`pp.norms`: `LogNorm`, `TwoSlopeNorm` (diverging around a center) and
`BoundaryNorm` (discrete bins).

## Scale bars and significance brackets

Scale bars stand in for axes on traces and images:

```python
ax.line(t, v)
ax.scalebar(x=0.2, y=5, xlabel="200 ms", ylabel="5 mV")  # loc="lower right"
ax.set(frame=False)
```

A bracket marks a comparison between two groups. Give it text, or a p-value
to show as stars (`*` < 0.05, `**` < 0.01, `***` < 0.001, `****` < 0.0001,
otherwise `n.s.`). Brackets sit just above the data between their ends, and
stack when they overlap, so add them after the data:

```python
ax.boxplot(speeds)
ax.bracket(0, 1, 0.003)
ax.bracket(0, 2, "n.s.")
```

## Text and math

Any label can contain `$...$` TeX math, and any label can be rich text:

```python
ax.set(title=pp.rich("Growth ", pp.bold("+42%", color="C3"), " over ", pp.italic("6 months")))
```

Unknown TeX commands and characters no font can draw raise a
`pp.MathTextWarning`.

## Themes

A theme holds every style default: fonts, sizes, colors, spines, ticks and
grid. Pass one per figure, or set the default:

```python
fig, ax = pp.subplots(theme="dark")
pp.set_theme(font_family=("Helvetica", "Arial"), tick_direction="in")
mine = pp.themes.default.replace(grid=True, title_weight="bold")
```

Built in: `default`, `dark` and `grayscale`. Fonts are looked up on your
system in the order given; the bundled Liberation Sans (metric-compatible with
Arial) is the fallback, and the chosen font is embedded in every saved file.

## Saving

`fig.save(path)` picks the format from the extension:

| | |
|---|---|
| `.pdf` | vector; real embedded text; `tagged=True` for accessible PDF |
| `.svg` | vector; real text and embedded fonts |
| `.png` | raster at `dpi` (default 200) |
| `.html` | self-contained page; interactive for 3D figures |

`dpi` also sets the resolution of images inside vector files, and
`transparent=True` drops the background. `fig.to_bytes("png")` returns the
data instead of writing a file. In a notebook a figure displays itself.

## Polar, 3D and animation

```python
fig, ax = pp.subplots(projection="polar")
ax.line(theta, r)

fig, ax = pp.subplots(projection="3d")
ax.surface(X, Y, Z)  # also scatter, line, wireframe, bar3d, quiver
ax.set(elev=25, azim=-60)
fig.save("surface.html")  # drag to rotate in the browser

pp.animate(lambda i: make_figure(i), frames=60, fps=24).save("movie.gif")
```

## Coming from matplotlib

The names are mostly the same. The main differences:

- `plot` is `line` (lines) and `scatter` (markers).
- `set_xlabel(...)`, `set_xlim(...)` and friends are one call: `ax.set(xlabel=..., xlim=...)`.
- `savefig` is `save`; there is no `pyplot` state, so call methods on your
  figure and axes.
- Marker `size` is a diameter in points, not an area.
- Calling a matplotlib name that doesn't exist tells you what to use instead.
