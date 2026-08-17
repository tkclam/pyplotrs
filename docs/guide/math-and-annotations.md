# Math & annotations

## LaTeX math

Any text — titles, axis labels, tick labels, legend entries, annotations — may
contain `$...$` math. It is typeset by a faithful, MathJax-grade engine driven by
the math font's OpenType MATH table, and **stays real, selectable text** in the
PDF/SVG output (copy-paste yields the Unicode math).

```python
--8<-- "examples/math_labels.py"
```

![math labels](../gallery/images/math_labels.png){ width="340" }

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

Math in a **tick label** works too, which is how a log axis writes its decades
as `$10^{k}$` — see [`LogFormatter`][pyplotrs.ticker.LogFormatter].

### Which face draws what

Math is set in **your own body family**, wherever that family has the glyphs.
Variables and Greek come from its italic, digits and upright roman from the
face the label itself is in, and the common operators (`+ − × · ÷ / = < > ≤ ≥ ≠
≈ ( ) [ ] ∂ ∞ → …`) from the same place. So `$\sin\omega t$` is Arial
throughout, and a **bold** title's math is bold throughout — variables
included.

What your family cannot supply are the parts that have to **grow**: a radical
sized to its content, a `\left(...\right)` fence sized to what it wraps, a
`\sum` enlarged in display style. Growing a glyph needs the variant and assembly
chains of an OpenType MATH table, and no text font has one. Those come from
**Fira Math**, a bundled *sans* math font (175 KB) — so `√`, `∑` and `∫` are
monoline marks that match Arial, not the high-contrast Times shapes a serif math
font draws.

Between the two sit two more fallbacks, each reached only when the one before it
has no glyph:

- a **DejaVu Sans subset** (95 KB) for symbols neither your family nor Fira Math
  carries. Text families cover the symbol blocks raggedly — Arial has `→ ← ↔` but
  not `⇒ ⇐ ↦`, `∩` but not `∪`, `≤ ≥ ≠ ≈` but not `≪ ≫ ∝ ∼` — so without it a
  single expression could set `$A \cap B$` sans and `$A \cup B$` serif;
- **STIX Two Math** last, for the Script and Fraktur alphabets (`\mathcal`,
  `\mathfrak`) and double-struck digits, which no sans math font here has. Those
  are calligraphic letterforms by definition, so a serif source is the right one.

Positioning constants always come from the primary math font, whichever face
ends up drawing a given mark, so a span is laid out to one font's metrics.

This is the same line matplotlib's default `dejavusans` set draws, for the same
reason: a label is read against its neighbors. Drawing math wholly from a serif
math font made a log axis label `10³` Times while the y ticks beside it read
`50` and `100` in Arial — and, less obviously, made `$E = mc^2$` mix a serif
`E m c` with a sans `=` and `2`.

Two consequences worth knowing:

- Most figures embed no math font at all — the math fonts are reached only for
  something that grows or for a symbol your family lacks.
- Math follows [`set_font_family`][pyplotrs.set_font_family]. Set Helvetica and
  your variables are Helvetica Italic.

#### Uniformly serif math

To set every atom in STIX Two Math instead — the traditional look, and what you
want when the body text is a serif too:

```python
pyplotrs.set_mathtext_fontset("stix")
pyplotrs.set_font_family("STIX Two Text", "Times New Roman")
```

`set_mathtext_fontset("sans")` (the default) restores the behavior above. It is
pyplotrs' analog of matplotlib's `rcParams["mathtext.fontset"]`.

!!! note "HTML export"
    Saving to `.html` re-renders math with MathJax, which carries its own
    (serif) TeX fonts, so an HTML figure's math will not match a `sans` PNG or
    PDF of the same figure. Everything else on the page still matches.

## Text annotations

[`text`][pyplotrs.axes.Axes.text] draws a string at data coordinates:

```python
ax.text(2.5, 0.8, r"region of interest", ha="center", color="C1")
ax.text(0.1, 0.9, "N = 42", weight="bold", style="italic", fontsize=8)
ax.text(0.5, 0.5, "sideways", rotation=90)
```

| Argument | Meaning |
|---|---|
| `ha` | `left` (default) / `center` / `right` |
| `va` | `baseline` (default) / `bottom` / `center` / `top` |
| `color` | defaults to the theme's text color |
| `fontsize` | in points; defaults to the theme's label size |
| `weight`, `style` | `normal`/`bold` and `normal`/`italic` — a **real face**, not a synthetic slant |
| `rotation` | degrees counter-clockwise about the anchor |

Rotation is applied as a group transform in the output rather than baked into
paths, so rotated text stays selectable in PDF and SVG.

## Callout arrows

[`annotate`][pyplotrs.axes.Axes.annotate] points text at a data location,
optionally with an arrow from the text to the point:

```python
--8<-- "examples/annotations.py"
```

![annotations](../gallery/images/annotations.png){ width="340" }

`xy` is the point being annotated and `xytext` is where the label sits (defaults
to `xy`). Set `arrow=False` for a plain floating label. Both coordinates are in
data space, the same `ha`/`va`/`weight`/`style`/`rotation` arguments apply, and
the text may itself contain `$...$` math.

!!! tip "Annotations do not move the view"
    Text and callouts are drawn over the data and take no part in autoscaling,
    so a label placed outside the data range will be clipped rather than
    stretching the axes to fit. Set `xlim`/`ylim` if you need room for it.
