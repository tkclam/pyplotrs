# Math & annotations

## LaTeX math

Any text — titles, axis labels, tick labels, legend entries, annotations — may
contain `$...$` math. It is typeset by a faithful, MathJax-grade engine driven by
the math font's OpenType MATH table, and **stays real, selectable text** in the
PDF/SVG output (copy-paste yields the Unicode math).

```python
--8<-- "examples/math_labels.py"
```

![math labels](../gallery/images/math_labels.png){ width="560" }

Supported syntax includes:

- super/subscripts `^` `_` (and both on one nucleus, `x_0^2`);
- `{...}` grouping;
- `\frac{a}{b}`, `\binom{n}{k}`;
- `\sqrt{...}` and `\sqrt[n]{...}` (a stretchy radical);
- auto-sized `\left...\right` fences;
- a broad Greek / operator / relation / arrow table (`\alpha`, `\sum`, `\int`,
  `\leq`, `\to`, `\infty`, `\partial`, …);
- accents `\hat`, `\bar`, `\vec`, `\tilde`, `\dot`, `\ddot`, …;
- math alphabets `\mathbf`, `\mathit`, `\mathbb`, `\mathcal`, `\mathfrak`,
  `\mathsf`, `\mathtt`, …;
- `\text{...}` and `\operatorname{...}` for upright runs.

!!! tip "Raw strings"
    Write math labels as raw strings (`r"$\alpha$"`) so Python doesn't interpret
    the backslashes.

When you save to **HTML** and a label contains `$...$`, the math is re-rendered
by an inlined copy of MathJax (SVG output), so it stays selectable and you can
right-click → *Show Math As* to copy the LaTeX/MathML — fully offline.

## Text annotations

[`text`][pyplotrs.axes.Axes.text] draws a string at data coordinates, with
horizontal (`ha`) and vertical (`va`) alignment:

```python
ax.text(2.5, 0.8, r"region of interest", ha="center", color="C1")
```

## Callout arrows

[`annotate`][pyplotrs.axes.Axes.annotate] points text at a data location,
optionally with an arrow from the text to the point:

```python
--8<-- "examples/annotations.py"
```

![annotations](../gallery/images/annotations.png){ width="540" }

`xy` is the point being annotated and `xytext` is where the label sits (defaults
to `xy`). Set `arrow=False` for a plain floating label. Both coordinates are in
data space, and the text may itself contain `$...$` math.
