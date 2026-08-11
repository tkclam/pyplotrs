# Normalizations

A `Normalize` maps data values into `[0, 1]` for colormap lookup — the color-axis
counterpart of a [`Scale`](scales.md). Pass one as `norm=` to `imshow`, a
colormapped `scatter`, or the field marks; the colorbar follows it.

::: pyplotrs.norms
    options:
      members:
        - Normalize
        - LogNorm
        - TwoSlopeNorm
        - BoundaryNorm
        - get
