# Tick formatters

A `Formatter` turns a tick's numeric position into its label string. Pass one to
`Axes.set(xformatter=..., yformatter=...)` or to `Figure.colorbar(format=...)`;
a `"{x:.2f}"` template string or any callable is accepted in the same places.

::: pyplotrs.ticker
    options:
      members:
        - Formatter
        - ScalarFormatter
        - FixedFormatter
        - FuncFormatter
        - StrMethodFormatter
        - PercentFormatter
        - EngFormatter
        - LogFormatter
        - DateFormatter
        - get
        - fix_minus
        - MINUS
