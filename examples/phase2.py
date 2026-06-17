"""Phase 2 feature gallery: themes, annotations, tagged PDF, fuller mathtext,
3D auto-legend, and the declarative figurs.gg layer.

Run with the project venv: ``.venv/bin/python examples/phase2.py``. Writes a
handful of files into ``examples/output/`` and prints a short report.
"""

import math
import os
import random

import figurs
from figurs.gg import Area, Histogram, Line, Plot, Point, facet

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


def themes_demo() -> None:
    """Same plot under every built-in theme."""
    xs = [i * 0.12 for i in range(80)]
    for name in ("default", "nature", "grayscale", "presentation"):
        fig, ax = figurs.subplots(figsize=(302, 216), theme=name)
        ax.line(xs, [math.sin(x) for x in xs], label="sin")
        ax.line(xs, [math.cos(x) for x in xs], label="cos", linestyle="dashed")
        ax.scatter([1, 3, 5, 7], [0.2, -0.5, 0.6, -0.1], label="obs")
        ax.set(title=f"theme = {name}", xlabel="x", ylabel="amplitude")
        ax.legend(loc="lower left")
        fig.save(out(f"phase2_theme_{name}.png"))


def annotations_demo() -> None:
    """Text + callout arrows, in data coordinates, with math."""
    xs = [i * 0.1 for i in range(80)]
    ys = [math.sin(x) * math.exp(-0.1 * x) for x in xs]
    fig, ax = figurs.subplots(figsize=(396, 252))
    ax.line(xs, ys, label="damped")
    ax.annotate(r"peak near $\frac{\pi}{2}$", (math.pi / 2, math.sin(math.pi / 2) * math.exp(-0.1 * math.pi / 2)),
                xytext=(3.0, 0.7), va="center")
    ax.annotate("first zero", (math.pi, 0.0), xytext=(4.5, -0.4))
    ax.text(6.0, 0.5, r"$y = \sin x\, e^{-x/10}$", color="C1", ha="center")
    ax.set(title="annotations", xlabel="x", ylabel="y")
    fig.save(out("phase2_annotations.pdf"))
    fig.save(out("phase2_annotations.svg"))


def tagged_pdf_demo() -> None:
    """Accessible, tagged PDF: one Figure structure element + alt text."""
    xs = [i * 0.1 for i in range(80)]
    fig, ax = figurs.subplots(figsize=(360, 252))
    ax.line(xs, [math.sin(x) for x in xs], label="signal")
    ax.set(title="Sensor reading", xlabel="time (s)", ylabel="voltage (V)")
    ax.legend()
    # alt text is auto-derived from titles/labels when not given explicitly.
    fig.save(out("phase2_tagged.pdf"), tagged=True)


def mathtext_demo() -> None:
    """Fuller LaTeX-subset: \\left\\right fences, \\sqrt[n], \\binom, \\text."""
    cases = [
        r"$\left( \frac{\partial f}{\partial x} \right)_{y}$",
        r"$\sqrt[3]{x^2 + y^2}$",
        r"$\binom{n}{k} = \frac{n!}{k!\,(n-k)!}$",
        r"$\left[ \sum_{i=1}^{N} x_i \right]^{2}$",
        r"$\left| \vec{v} \right| = \sqrt{v_x^2 + v_y^2}$",
        r"$P(x) = \frac{1}{\sqrt{2\pi}\,\sigma}\, e^{-\frac{(x-\mu)^2}{2\sigma^2}}$",
        r"$\operatorname{erf}(z),\ \text{Gauss error function}$",
    ]
    fig, ax = figurs.subplots(figsize=(432, 324))
    y = 0.92
    for c in cases:
        ax.text(0.04, y, c, fontsize=14)
        y -= 0.125
    ax.set(title="mathtext", xlim=(0, 1), ylim=(0, 1))
    fig.save(out("phase2_mathtext.pdf"))


def legend3d_demo() -> None:
    """3D auto-legend over labelled scatter/line marks."""
    random.seed(1)
    fig, ax = figurs.subplots(projection="3d", figsize=(396, 324))
    ax.scatter([random.gauss(0, 1) for _ in range(50)],
               [random.gauss(0, 1) for _ in range(50)],
               [random.gauss(0, 1) for _ in range(50)], label="cloud A", color="C0")
    ax.scatter([random.gauss(3, 1) for _ in range(50)],
               [random.gauss(3, 1) for _ in range(50)],
               [random.gauss(1, 1) for _ in range(50)], label="cloud B", color="C1", marker="^")
    t = [i * 0.2 for i in range(60)]
    ax.plot([2 * math.cos(x) for x in t], [2 * math.sin(x) for x in t], t,
            label="helix", color="C2")
    ax.set(title="3D auto-legend", xlabel="x", ylabel="y", zlabel="z")
    ax.legend(loc="upper left")
    fig.save(out("phase2_legend3d.pdf"))


def gg_demo() -> None:
    """Declarative grammar of graphics: grouped colour + faceting."""
    random.seed(2)
    rows = []
    for treat in ("ctrl", "low", "high"):
        base = {"ctrl": 1.0, "low": 1.6, "high": 2.3}[treat]
        for subj in ("s1", "s2", "s3"):
            for t in range(20):
                rows.append({"time": t,
                             "value": base * math.sin(t * 0.3) + base + random.gauss(0, 0.12),
                             "treatment": treat, "subject": subj})
    (Plot(rows, x="time", y="value", color="treatment")
        .add(Line()).add(Point(size=12))
        .facet(facet.wrap("subject", ncols=3))
        .theme(figurs.themes.nature)
        .labs(x="time (s)", y="response", title="figurs.gg: faceted, grouped")
        .save(out("phase2_gg_facet.pdf")))

    # A single-panel area + a grouped histogram (statistical transform).
    data = {"x": list(range(40)), "y": [math.exp(-((i - 20) ** 2) / 60) for i in range(40)]}
    Plot(data, x="x", y="y").add(Area()).labs(title="area").save(out("phase2_gg_area.png"))


def main() -> None:
    themes_demo()
    annotations_demo()
    tagged_pdf_demo()
    mathtext_demo()
    legend3d_demo()
    gg_demo()
    print("Phase 2 gallery written to", _OUT)
    print("  phase2_theme_*.png, phase2_annotations.{pdf,svg}, "
          "phase2_tagged.pdf, phase2_mathtext.pdf, phase2_legend3d.pdf, "
          "phase2_gg_facet.pdf, phase2_gg_area.png")


if __name__ == "__main__":
    main()
