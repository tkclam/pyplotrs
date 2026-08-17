# Figure & Axes

The core 2D/3D plotting API.

## Entry points

::: pyplotrs.subplots

::: pyplotrs.subplot_mosaic

::: pyplotrs.figure

## Figure

::: pyplotrs.Figure
    options:
      members:
        - set
        - add_gridspec
        - add_subplot
        - legend
        - colorbar
        - save

::: pyplotrs.GridSpec

## Axes

::: pyplotrs.axes.Axes
    options:
      inherited_members: true
      members:
        - line
        - scatter
        - bar
        - barh
        - hist
        - boxplot
        - violinplot
        - pie
        - fill_between
        - fill_betweenx
        - errorbar
        - step
        - stairs
        - stem
        - broken_barh
        - eventplot
        - stackplot
        - imshow
        - matshow
        - spy
        - pcolormesh
        - pcolor
        - hist2d
        - hexbin
        - contour
        - contourf
        - quiver
        - streamplot
        - loglog
        - semilogx
        - semilogy
        - hlines
        - vlines
        - axhline
        - axvline
        - axhspan
        - axvspan
        - axline
        - rectangle
        - circle
        - ellipse
        - polygon
        - fill
        - arrow
        - text
        - annotate
        - legend
        - axis
        - twinx
        - twiny
        - inset_axes
        - secondary_xaxis
        - secondary_yaxis
        - set
        - get_xlim
        - get_ylim
        - get_xlabel
        - get_ylabel
        - get_title
        - get_xscale
        - get_yscale
        - get_aspect
        - get_xticks
        - get_yticks
        - get_xticklabels
        - get_yticklabels
        - get_legend_handles_labels

## PolarAxes

::: pyplotrs.polar.PolarAxes
    options:
      inherited_members: true
      members:
        - plot
        - scatter
        - legend
        - set
        - get_rlim
        - get_rticks
        - get_thetagrids
        - get_theta_direction

## Axes3D

::: pyplotrs.axes3d.Axes3D
    options:
      inherited_members: true
      members:
        - scatter
        - plot
        - surface
        - bar3d
        - plot_wireframe
        - contour3d
        - plot_trisurf
        - quiver3d
        - voxels
        - legend
        - set
        - get_xlim
        - get_ylim
        - get_zlim
        - get_xlabel
        - get_ylabel
        - get_zlabel
        - get_view

## Fonts

These module-level helpers configure body-font resolution, and which family
`$...$` math is drawn in.

::: pyplotrs.set_font_family

::: pyplotrs.get_font_family

::: pyplotrs.resolved_font_name

::: pyplotrs.resolved_font_variants

::: pyplotrs.set_mathtext_fontset

::: pyplotrs.get_mathtext_fontset

## Number formatting

::: pyplotrs.set_unicode_minus

::: pyplotrs.get_unicode_minus
