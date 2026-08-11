# Figures & axes

pyplotrs has two central objects: a **`Figure`** (the output canvas) and one or
more **`Axes`** (a coordinate system you draw on). There is deliberately **no
global state** — no "current figure", no `pyplot`-style implicit target. You
always hold explicit `fig` and `ax` references.

## Creating figures

The ergonomic entry point is [`subplots`][pyplotrs.figure.subplots]:

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

You can also construct a [`Figure`][pyplotrs.figure.Figure] directly and reach
its axes through `fig.axes` (a flat, row-major list).

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
[`set`][pyplotrs.axes.Axes.set] method for chrome:

```python
ax.line(xs, ys, label="series")
ax.set(title="My plot", xlabel="x", ylabel="y", xlim=(0, 10), ylim=(-1, 1))
ax.legend(loc="upper right")
```

Mark methods return the axes, so calls chain:

```python
ax.line(xs, a).line(xs, b, linestyle="dashed").scatter(xs, c)
```

## Shared axes

`sharex` / `sharey` unify the data range across all panels so they line up and
are directly comparable:

```python
fig, axs = plt.subplots(1, 3, sharey=True)
for k, ax in enumerate(axs):
    ax.line(xs, [f(x, k) for x in xs])
```

## Figure-level chrome

A `Figure` can carry a super-title and a single shared legend that collects the
labeled marks of every panel into a reserved column (so it never overlaps the
data):

```python
fig.set(suptitle="An overview")
fig.legend(loc="right")
```

## A note on data inputs

Marks accept any iterable of numbers — Python lists, tuples, generators, NumPy
arrays, pandas/polars columns. There is no hard dependency on NumPy. Non-finite
values (`NaN`/`inf`) are ignored when autoscaling and **break a line into a gap**
(rather than distorting the plot), matching matplotlib's behaviour.

## Unequal panel sizes

`width_ratios` and `height_ratios` weight the columns and rows:

```python
fig, axs = plt.subplots(1, 2, width_ratios=[3, 1])   # wide panel, narrow panel
fig, axs = plt.subplots(2, 2, height_ratios=[1, 2])  # short row over a tall one
```

Only the proportions matter — `[3, 1]` and `[0.75, 0.25]` are the same — and the
gutters keep their size, so weighting changes the panels rather than the space
between them. A malformed hint (wrong length, zero or negative) falls back to an
even grid instead of raising.

`Figure.add_gridspec` takes them too:

```python
gs = fig.add_gridspec(2, 2, width_ratios=[2, 1])
```
