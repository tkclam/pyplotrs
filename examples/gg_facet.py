"""Grammar of graphics: faceted small multiples."""
import math
from pyplotrs import gg

rows = []
for subj in ("s1", "s2", "s3", "s4", "s5", "s6"):
    phase = hash(subj) % 7
    for t in range(24):
        rows.append({"t": t, "y": math.sin(t / 3 + phase), "subject": subj})

(gg.Plot(rows, x="t", y="y")
    .add(gg.Line())
    .add(gg.Point(size=12))
    .facet(gg.facet.wrap("subject", ncols=3))
    .labs(x="t", y="signal", title="Faceted by subject")
    .save("gg_facet.png"))
