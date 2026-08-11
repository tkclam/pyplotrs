# Figures & axes

pyplotrs has two central objects: a **`Figure`** (the output canvas) and one or
more **`Axes`** (a coordinate system you draw on). There is deliberately **no
global state** — no "current figure", no `pyplot`-style implicit target. You
always hold explicit `fig` and `ax` references.

## Creating figures

The ergonomic entry point is [`subplots`][pyplotrs.subplots]:

```python
import pyplotrs as plt

fig, ax = plt.subplots()                    # a single axes
fig, axs = plt.subplots(1, 3)               # a row → flat list of 3
fig, axs = plt.subplots(3, 1)               # a column → flat list of 3
fig, grid = plt.subplots(2, 3)              # a full grid → list of rows
```

The return shape mirrors the grid:

| Call | `ax` is |
|---|---|
| `subplots()` | a single `Axes` |
| `subplots(1, n)` or `subplots(n, 1)` | a flat list `[ax, ...]` |
| `subplots(r, c)` | a nested list `[[ax, ...], ...]` (row-major) |

`projection="polar"` or `projection="3d"` makes every panel a
[`PolarAxes`](polar.md) or an [`Axes3D`](3d.md) instead.
[`plt.figure()`][pyplotrs.figure] creates a figure with **no** axes, for when
every panel is placed by hand — see [layout](layout.md). Either way, `fig.axes`
is the flat, row-major list of what a figure holds.

## Sizing

`figsize` is `(width, height)` in **points** by default (1 pt = 1/72 inch).
Sizing in points lets you reason about a figure directly against its font scale —
the default 250×200 pt figure with a 10 pt font. That default is a single
journal column wide (~3.5 in), so a figure comes out at publication size rather
than needing to be scaled down to one. Other units are available via `units`:

```python
plt.subplots(figsize=(250, 200))               # points (the default)
plt.subplots(figsize=(4, 3), units="in")       # inches
plt.subplots(figsize=(89, 60), units="mm")     # a Nature single column
plt.subplots(figsize=(12, 8), units="cm")
```

## Drawing & the `set` method

Each `Axes` exposes the mark vocabulary (`line`, `scatter`, `bar`, …) plus a
[`set`][pyplotrs.axes.Axes.set] method for everything else:

```python
ax.line(xs, ys, label="series")
ax.set(title="My plot", xlabel="x", ylabel="y", xlim=(0, 10), ylim=(-1, 1))
ax.legend(loc="upper right")
```

Mark methods return the axes, so calls chain:

```python
ax.line(xs, a).line(xs, b, linestyle="dashed").scatter(xs, c)
```

`set` also carries the scales, ticks, formatters, margins, aspect and grid —
see [scales & ticks](scales-and-ticks.md) for that half of it.

## Reading an axes back

Writing is `set(**kwargs)`; reading is the `get_*` accessors. The split is
deliberate: one way to change an axes, one way to interrogate it, rather than
parallel `get_x`/`set_x` pairs *plus* a bulk `set`.

```python
ax.get_xlim(), ax.get_ylim()
ax.get_xlabel(), ax.get_ylabel(), ax.get_title()
ax.get_xscale(), ax.get_yscale(), ax.get_aspect()
ax.get_xticks(), ax.get_xticklabels()
ax.get_legend_handles_labels()
```

Every getter reports the **effective** value — what will actually be drawn.
`get_xlim()` on an axes with no explicit limit returns the autoscaled range;
`get_xticks()` returns the located ticks; on a `sharex` figure they report the
range the whole row settled on. "What did I set" is already visible in the
calling code; "what will I get" is not.

`Axes3D` and `PolarAxes` carry the same idea with their own vocabulary
(`get_zlim`, `get_view`, `get_rlim`, `get_rticks`, …).

## Shared axes

`sharex` / `sharey` unify the data range across all panels so they line up and
are directly comparable:

```python
fig, axs = plt.subplots(1, 3, sharey=True)
for k, ax in enumerate(axs):
    ax.line(xs, [f(x, k) for x in xs])
```

More on grids, spanning panels, insets and twin axes in [layout](layout.md).

## Figure-level chrome

A `Figure` can carry a super-title and a single shared legend that collects the
labeled marks of every panel into a reserved column (so it never overlaps the
data):

```python
fig.set(suptitle="An overview")
fig.legend(loc="right")
```

## Displaying and saving

```python
fig.save("out.pdf")     # format from the extension
fig                     # in a notebook: renders inline
```

A `Figure` renders itself in Jupyter, so a bare `fig` at the end of a cell
displays it — there is no `show()`. See [saving figures](saving.md).

## A note on data inputs

Marks accept any iterable of numbers — Python lists, tuples, generators, NumPy
arrays, pandas/polars columns. There is no hard dependency on NumPy; anything
exposing an `f64` buffer is read directly, without an intermediate Python list.

Two input types also pick the axis scale for you: **strings** give a categorical
axis and **datetimes** give a date axis (see
[scales & ticks](scales-and-ticks.md#scales-the-data-chooses)).

Non-finite values (`NaN`/`inf`) are ignored when autoscaling and **break a line
into a gap** (rather than distorting the plot), matching matplotlib's behavior.
