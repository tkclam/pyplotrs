"""Phase 1e smoke test: mathtext-lite. Math spans ($...$) in the suptitle,
axis titles, axis labels, and legend entries - exercising superscripts,
subscripts, Greek letters, \\frac and \\sqrt. The math is rendered as ordinary
positioned text runs + thin rules, so it stays real, editable text in the PDF.

The ``.html`` save shows the MathJax path: because labels contain ``$...$``, the
math is re-typeset by an inlined copy of MathJax (selectable, copy-as-LaTeX via
right-click), while the page stays a single self-contained offline file.
"""

import math
import os

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


xs = [(-5.0 + 10.0 * i / 400.0) for i in range(401)]


def gaussian(x, mu, sig):
    return math.exp(-((x - mu) ** 2) / (2.0 * sig * sig)) / (sig * math.sqrt(2.0 * math.pi))


g1 = [gaussian(x, 0.0, 1.0) for x in xs]
g2 = [gaussian(x, -1.0, 1.6) for x in xs]

fig, axes = figurs.subplots(1, 2, figsize=(619, 259))
fig.set(suptitle=r"Normal density $\phi(x)=\frac{1}{\sqrt{2\pi}\,\sigma}\,e^{-x^2/2\sigma^2}$")

# Left: two Gaussians with math legend labels.
ax = axes[0]
ax.line(xs, g1, color="C0", label=r"$\mu=0,\ \sigma=1$")
ax.line(xs, g2, color="C1", label=r"$\mu=-1,\ \sigma=1.6$", linestyle="dashed")
ax.set(title=r"Densities $\phi(x)$", xlabel=r"$x$", ylabel=r"$\phi(x)$")
ax.legend(loc="upper right")

# Right: a curve exercising sub/superscripts and Greek in labels.
t = xs
y = [math.exp(-0.2 * abs(x)) * math.cos(2.0 * x) for x in t]
ax = axes[1]
ax.line(t, y, color="C2", label=r"$A_0 e^{-\lambda|t|}\cos(\omega t)$")
ax.set(title=r"Damped: $x_0^2 + \omega^2$", xlabel=r"time $t$ $(\mu s)$",
       ylabel=r"amplitude $A_{n}$")
ax.legend(loc="upper left")

fig.save(out("phase1e.pdf"))
fig.save(out("phase1e.svg"))
fig.save(out("phase1e.png"))
fig.save(out("phase1e.html"))  # math re-rendered by inlined MathJax (copyable, offline)
print("done ->", _OUT)
