# Changelog

## Unreleased

**Added**

- `ax.line(x, y, c=values)` colors a line along its length through a
  colormap; pass it to `fig.colorbar`.
- `ax.scalebar(x=..., y=...)` draws labeled scale bars in a corner or at a
  data point.
- `ax.bracket(x0, x1, text)` marks a comparison between groups; a p-value
  becomes stars, and brackets stack above the data automatically.
- `ax.set(xbreak=(lo, hi))` and `ybreak` draw a broken axis.
- `bar` and `barh` take a list of colors, one per bar.

## 0.2.0

A rewrite for a smaller, clearer codebase. Output and speed are equal or
better; a few APIs changed.

**Changed**

- Plotting methods return the artist they create instead of the axes.
- Fonts live on the theme: `pp.set_theme(font_family=(...), math_fontset=...,
  unicode_minus=...)` replaces `set_font_family`, `set_mathtext_fontset` and
  `set_unicode_minus`.
- `Theme.with_` is now `Theme.replace`; `pp.set_theme` sets the default theme.
- `scatter(markersize=...)` is `scatter(size=...)`, a diameter in points.
- `legend(ncol=...)` is `legend(ncols=...)`; tick direction and length are
  theme settings.
- Figure grids: `fig.add_axes(row, col, rowspan, colspan)` replaces
  `add_gridspec` and `add_subplot`; `subplot_mosaic` also accepts `"AB;CD"`.
- Scales are `pp.scales.Log`, `Symlog`, ...; formatters are `pp.ticker.Percent`,
  `Eng`, `Scientific`, `Date`, or any format string or function.
- Norms are `pp.norms.Norm`, `LogNorm`, `TwoSlopeNorm`, `BoundaryNorm`.
- 3D: `plot` is `line`, `plot_wireframe` is `wireframe`, `quiver3d` is `quiver`.
- Python 3.11 or newer; one wheel per platform (abi3).

**Added**

- Plots align across rows and columns, and `width_ratios` sizes the plots.
- Narrow axes use fewer ticks instead of crowding or rotating labels.
- `title_loc="left"` for panel letters; partial limits such as `xlim=(0, None)`.
- `ax.line(y)` plots against 0, 1, 2, ...
- `fig.legend(loc="bottom")`, `hist(cumulative=True, histtype="step")`,
  `pie(autopct=...)`, polar `fill`.

**Removed**

- MathJax in HTML export (math is still rendered, as text and paths).
- Color-science helpers (`pyplotrs.color`), `semilogx`/`semilogy`/`loglog`
  (use `set(xscale="log")`), `broken_barh`, `spy`, `matshow`, `pcolor`,
  secondary axes, and 3D `contour3d`, `plot_trisurf`, `voxels`.

## 0.1.0

First release.
