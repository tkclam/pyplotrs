"""Axis scales: log, symlog, an automatic date axis, and categories."""
import datetime as dt
import math

import pyplotrs as plt

fig, ((ax_log, ax_symlog), (ax_date, ax_cat)) = plt.subplots(2, 2, figsize=(620, 420))

xs = [1 + i * 0.5 for i in range(200)]
ax_log.line(xs, [x ** 2 for x in xs], label="$x^2$")
ax_log.line(xs, [math.exp(x / 20) for x in xs], label="$e^{x/20}$")
ax_log.set(title="log-log", xscale="log", yscale="log")
ax_log.legend(loc="lower right")

ts = [-100 + i for i in range(201)]
ax_symlog.line(ts, [t ** 3 / 100 for t in ts])
ax_symlog.set(title="symlog (signed, spans zero)", yscale="symlog")

# Datetime values switch that axis to a date scale automatically; the
# formatter here just shortens the auto labels from "Jan 2026" to "Jan".
day0 = dt.date(2026, 1, 1)
days = [day0 + dt.timedelta(days=7 * i) for i in range(26)]
ax_date.line(days, [20 + 8 * math.sin(i / 4) for i in range(26)])
ax_date.set(title="date axis (automatic)", ylabel="°C",
            xformatter=plt.ticker.DateFormatter("%b"))

# String coordinates switch that axis to a categorical scale.
ax_cat.bar(["ash", "birch", "cedar", "elm"], [12, 19, 7, 15])
ax_cat.set(title="categorical axis (automatic)", ylabel="count")

fig.save("scales.png")
