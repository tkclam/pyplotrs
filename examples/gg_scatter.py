"""Grammar of graphics: points + a line, coloured by a category."""
import math
from pyplotrs import gg

# A small tidy dataset: two treatments measured over time.
rows = []
for treat, amp in (("A", 1.0), ("B", 0.6)):
    for t in range(20):
        rows.append({"t": t, "y": amp * math.sin(t / 3) + 0.1 * t, "treatment": treat})

(gg.Plot(rows, x="t", y="y", color="treatment")
    .add(gg.Point())
    .add(gg.Line())
    .labs(x="time (s)", y="response", title="Grammar of graphics")
    .save("gg_scatter.png"))
