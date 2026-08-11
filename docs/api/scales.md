# Scales

Axis scales: the data-space → transformed-space mapping that sits between raw
data and the device transform. Pass a name or an instance to
`Axes.set(xscale=..., yscale=...)`. See the
[scales & ticks guide](../guide/scales-and-ticks.md).

::: pyplotrs.scales
    options:
      members:
        - Scale
        - LinearScale
        - LogScale
        - SymlogScale
        - LogitScale
        - CategoricalScale
        - DateScale
        - get
        - nice_ticks
        - date2num
        - num2date
        - is_datetime_like
