# Styling & themes

## Themes

A [`Theme`][pyplotrs.theme.Theme] bundles every *style* choice — palette, type
scale, spines, grid, default line weights, legend colours. There is **no global
"current theme"**: you pass a theme to `subplots` (or `Figure`) and it flows to
every axes.

```python
import pyplotrs as plt

fig, ax = plt.subplots(theme="presentation")
ax.line(xs, ys)
```

Built-in presets (pass the name, or `pyplotrs.themes.<name>`):

| Preset | For |
|---|---|
| `default` | The zero-config publication default (Okabe-Ito palette, despined, no grid) |
| `nature` | Compact: smaller type and thinner rules for dense two-column figures |
| `grayscale` (alias `bw`) | Print-safe monochrome palette with black spines/text |
| `presentation` | Large type, heavy strokes and a light grid, tuned for slides |

```python
--8<-- "examples/themes.py"
```

<div class="grid" markdown>
![default](../gallery/images/theme_default.png)
![nature](../gallery/images/theme_nature.png)
![grayscale](../gallery/images/theme_grayscale.png)
![presentation](../gallery/images/theme_presentation.png)
</div>

## Deriving your own theme

`Theme` is an immutable dataclass; [`with_`][pyplotrs.theme.Theme.with_] returns
a copy with changes applied:

```python
import pyplotrs as plt

mine = plt.themes.default.with_(
    grid=True,
    line_width=2.0,
    axes_facecolor=(248, 248, 248, 255),
)
fig, ax = plt.subplots(theme=mine)
```

Useful knobs include `palette`, `text_color`, `spine_color`, `spines` (which of
`"left"/"right"/"top"/"bottom"` to draw), `spine_width`, the type-scale sizes
(`tick_label_size`, `axis_label_size`, `title_size`, `suptitle_size`,
`legend_size`), the chrome weights (`title_weight`, `suptitle_weight`,
`axis_label_weight`), `line_width`, `grid` / `grid_color` / `grid_width`,
`axes_facecolor`, and the legend colours. See the
[Theme API](../api/themes.md) for the full list.

## Colours

Anywhere a `color=` is accepted you can give:

- `None` — take the next colour from the theme palette (auto-cycling);
- `"C0" … "C7"` — an index into *this theme's* palette (so `"C3"` follows the
  active theme, not a fixed global colour);
- `(r, g, b)` or `(r, g, b, a)` — literal bytes in `0–255`.

```python
ax.line(xs, ys, color="C2")               # third palette colour
ax.line(xs, ys, color=(214, 39, 40))      # literal RGB
ax.scatter(xs, ys, color=(31, 119, 180, 128))   # semi-transparent
```

The default palette is **Okabe-Ito**, a colorblind-safe categorical set.

## Fonts

For body text pyplotrs prefers the host's **Arial**, then **Helvetica**, before
falling back to the bundled **Liberation Sans** (Arial-metric-compatible). It is
matplotlib's `font.sans-serif` behaviour, and configurable:

```python
import pyplotrs as plt

plt.set_font_family("Calibri", "Arial")     # try Calibri, then Arial, then fallback
plt.get_font_family()                       # the current preference list
plt.resolved_font_name()                    # what it actually resolves to here
plt.set_font_family()                       # reset to the default
```

Whichever font is chosen is **embedded into every saved figure** (PDF/SVG/PNG and
the 3D-HTML viewer), so a file saved on one machine looks identical when opened
on another — the font choice only affects how that one rendering looks, never its
portability. Arial and Helvetica are proprietary and are *never* bundled; they
are only used when already installed on the machine.

### Bold and italic

Free text takes `weight` (`"normal"`/`"bold"`) and `style`
(`"normal"`/`"italic"`), which select a **real face** of the family rather than
synthetically slanting or smearing the regular one:

```python
ax.text(0.1, 0.9, "emphasis", weight="bold", style="italic")
ax.annotate("callout", (1, 1), xytext=(1.2, 2), weight="bold")
```

The figure's own chrome is a theme choice, since bold panel titles are a
document-wide decision rather than a per-call one:

```python
journal = plt.themes.nature.with_(title_weight="bold")
fig, ax = plt.subplots(theme=journal)
```

Each face is embedded as its own subset, so a figure using all four carries four
subsetted fonts and every one stays selectable, editable text.

Font matching is approximate: a family with no italic face resolves to its
regular one, so text stays legible but is not slanted. `resolved_font_variants()`
reports what each face landed on — two selectors reporting the same PostScript
name means the host has no distinct face for one of them.

All four Liberation Sans faces are **bundled**, so emphasis works even on a
machine with no fonts installed at all — a slim container, a wheel builder — and
a figure looks the same wherever it is generated.
