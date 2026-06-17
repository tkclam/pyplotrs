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
a 480×360 pt figure with a 10 pt font. Other units are available via `units`:

```python
plt.subplots(figsize=(480, 360))               # points (default)
plt.subplots(figsize=(4, 3), units="in")       # inches
plt.subplots(figsize=(89, 60), units="mm")     # a Nature single column
plt.subplots(figsize=(12, 8), units="cm")
```

## Drawing & the `set` method

Each `Axes` exposes the mark vocabulary (`line`, `scatter`, `bar`, …) plus a
[`set`][pyplotrs.figure.Axes.set] method for chrome:

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
labelled marks of every panel into a reserved column (so it never overlaps the
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
