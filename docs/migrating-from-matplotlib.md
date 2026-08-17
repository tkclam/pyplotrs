# Coming from matplotlib

pyplotrs deliberately looks like matplotlib where matplotlib got it right, and
deliberately differs where a second try can do better. This page is the list of
differences, so you can port a script without guessing.

If a name exists in both libraries it means the same thing. The differences
below are the ones worth knowing before you start.

Throughout the documentation pyplotrs is imported as `pp`, and `plt` is left to
mean `matplotlib.pyplot`. On this page in particular that is what lets the two
libraries share a code block without a caption saying which is which.

!!! tip "See it rather than read it"
    The [coming-from-matplotlib notebook](notebooks/02_from_matplotlib.ipynb)
    is this page with the pictures: ten plot types rendered by both libraries
    from the same data, side by side, so the differences in the defaults are
    visible rather than described.

## The five that matter

### 1. There is no pyplot state machine

No current figure, no current axes, no `plt.plot(...)`, no `plt.show()`.
`subplots` hands you objects and you hold onto them.

```python
# matplotlib
import matplotlib.pyplot as plt
plt.plot(xs, ys)
plt.xlabel("x")
plt.savefig("out.png")

# pyplotrs
import pyplotrs as pp
fig, ax = pp.subplots()
ax.line(xs, ys)
ax.set(xlabel="x")
fig.save("out.png")
```

Everything follows from this: a function that builds a figure returns it, two
figures never interfere, and threads are safe by construction.

### 2. `set(**kwargs)` replaces the setter family

There is no `set_xlabel` / `set_xlim` / `set_xscale` / `set_xticks`. One method
writes an axes:

```python
ax.set(title="…", xlabel="x", ylabel="y", xlim=(0, 10),
       yscale="log", xticks=[0, 5, 10], grid=True)
```

and the `get_*` accessors read it back, reporting the **effective** value —
`get_xlim()` on an axes with no explicit limit returns the autoscaled range.

### 3. `line`, not `plot`

The 2D line mark is [`line`][pyplotrs.axes.Axes.line]. (`plot` *is* the name on
3D and polar axes, where it is unambiguous.) Marks return the axes, so calls
chain.

### 4. One name per concept, one unit per quantity

- A stroke width is **`linewidth`** on every method that draws one. There is no
  `lw` abbreviation, and `width` only ever means an extent in data units — a
  bar's thickness, a rectangle's span.
- Marker size is **`markersize`**, a *diameter in points*, on every mark
  including `scatter`. matplotlib's `s` (an area in pt²) is accepted as `size=`,
  so `size=36` and `markersize=6` agree.
- `alpha` and `zorder` are accepted on every mark, not on a subset.

### 5. `fig.save(path)`, format from the extension

```python
fig.save("out.pdf")                     # not fig.savefig(...)
fig.save("out.png", dpi=300)
fig.save("out.html")                    # matplotlib has no equivalent
fig.save("out.pdf", tagged=True)        # accessible, tagged PDF
```

## Translation table

| matplotlib | pyplotrs |
|---|---|
| `plt.subplots(...)` | `pp.subplots(...)` — same signature, plus `theme=`, `units=` |
| `ax.plot(x, y)` | `ax.line(x, y)` |
| `ax.plot(x, y, "o")` | `ax.line(x, y, marker="o", linestyle="none")` or `ax.scatter(x, y)` |
| `ax.scatter(x, y, s=36)` | `ax.scatter(x, y, markersize=6)` (or `size=36`) |
| `ax.set_xlabel("x")` | `ax.set(xlabel="x")` |
| `ax.set_xlim(0, 1)` | `ax.set(xlim=(0, 1))` |
| `ax.set_xscale("log")` | `ax.set(xscale="log")` |
| `ax.set_xticks([...])` | `ax.set(xticks=[...])` |
| `ax.set_xticklabels([...])` | `ax.set(xticklabels=[...])` |
| `ax.grid(True)` | `ax.set(grid=True)` |
| `ax.tick_params(direction="in")` | `ax.set(tick_direction="in")` |
| `ax.xaxis.set_major_formatter(f)` | `ax.set(xformatter=f)` |
| `ax.margins(0.2)` | `ax.set(margin=0.2)` |
| `ax.invert_yaxis()` | `ax.set(yinverted=True)` |
| `ax.set_aspect("equal")` | `ax.set(aspect="equal")` |
| `fig.suptitle("…")` | `fig.set(suptitle="…")` |
| `fig.savefig("f.png", dpi=300)` | `fig.save("f.png", dpi=300)` |
| `fig.tight_layout()` | *not needed* — layout is solved before drawing |
| `plt.style.use("seaborn")` | `pp.subplots(theme="dark")` or a `Theme` |
| `rcParams["font.sans-serif"]` | `pp.set_font_family(...)` |
| `rcParams["axes.unicode_minus"]` | `pp.set_unicode_minus(...)` |
| `rcParams["mathtext.fontset"]` | `pp.set_mathtext_fontset(...)` (`"sans"`, `"stix"`) |
| `ax.plot_surface(X, Y, Z)` | `ax.surface(X, Y, Z)` |
| `ax.pcolor` / `pcolormesh` | same names |
| `plt.show()` | — (a `Figure` displays itself in a notebook) |

Colors, `label=`/`legend()`, `hlines` vs `axhline`, `fill_between`, `errorbar`,
`imshow` + `colorbar`, `twinx`, `inset_axes`, `subplot_mosaic`, `GridSpec`
slicing and the `where=` argument of `step` all behave as you expect.

## Colors

Everything matplotlib accepts, plus one improvement:

```python
ax.line(xs, ys, color="C2")             # index THIS theme's palette
ax.line(xs, ys, color="steelblue")      # CSS/matplotlib color name
ax.line(xs, ys, color="#4682b4")        # hex
ax.line(xs, ys, color=(0.27, 0.51, 0.71))   # floats in 0–1, matplotlib style
ax.line(xs, ys, color=(70, 130, 180))       # bytes in 0–255, the native form
```

`"C0".."Cn"` indexes the *active theme's* palette rather than a fixed global
cycle, so restyling a figure moves every `"C3"` in it. The default palette is
Okabe-Ito, which is colorblind-safe.

Note that the indices do **not** line up with matplotlib's. Okabe-Ito leads with
black, so `C0` is ink rather than tab10's blue, and a single unstyled line comes
out black instead of blue. Ported code that names colors positionally needs its
indices read once rather than trusted.

## Figure size is in points

`figsize` is `(width, height)` in **points**, not inches, so a figure can be
reasoned about against its font scale. The default 250×200 pt is one journal
column wide. Pass `units="in"` to keep matplotlib's numbers:

```python
pp.subplots(figsize=(4, 3), units="in")   # matplotlib's default-ish size
pp.subplots(figsize=(89, 60), units="mm")
```

## Styling is a theme, not global config

There is no `rcParams` and no `style.use`. A [`Theme`][pyplotrs.theme.Theme] is
an immutable object you pass in, and `with_` derives a variant:

```python
mine = pp.themes.default.with_(grid=True, line_width=2.0, title_weight="bold")
fig, ax = pp.subplots(theme=mine)
```

Because it is an argument rather than global state, two figures in one script
can use different themes — and so can two threads.

## What pyplotrs does that matplotlib does not

- **PDF text stays editable.** Embedded, subsetted fonts rather than outlines,
  so labels are selectable, extractable and re-typeable in Illustrator.
  `tagged=True` writes accessible, tagged PDF.
- **Self-contained HTML output**, with selectable text and — for 3D — an
  interactive Canvas2D viewer, all offline.
- **3D that stays vector.** Surfaces and lines project to editable 2D paths, not
  a rasterized inset.
- **`$...$` math without a LaTeX install**, typeset from the math font's
  OpenType MATH table and left as real text in the output.
- **The GIL is released during export**, so a `ThreadPoolExecutor` over figures
  actually parallelizes.

## What is not here

- The pyplot state machine, interactive backends, `plt.show()`, and event/widget
  handling. pyplotrs makes files, not windows.
- `rcParams` and `style.use`.
- The artist tree: there are no `Line2D` objects to fetch and mutate after the
  fact. A mark is recorded when you call it and rendered at `save`.
- matplotlib's long tail of specialized marks. The vocabulary is in
  [plot types](guide/plot-types.md); if something you rely on is missing, an
  issue is the right place for it.
