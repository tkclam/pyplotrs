"""Math-rendering check across every output format.

Run:  .venv/bin/python examples/math_check.py
Writes into examples/output/ so the formats sit side by side for comparison:

  2D heavy-math figure  -> .pdf .svg .png  (figurs' native glyph engine)
                        -> .html            (re-typeset by inlined MathJax)
  3D figure w/ $math$   -> .pdf             (native math works in static 3D)
                        -> .html            (Canvas2D viewer + MathJax overlay)
"""

import math
import os

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


def heavy_math_2d() -> None:
    """One 2D figure that pushes the engine: frac, nested sqrt, sums with
    limits, integrals, matrices, \\left..\\right, accents, math alphabets,
    sub/superscripts and Greek -- in suptitle, titles, axis labels and legend."""
    xs = [(-4.0 + 8.0 * i / 400.0) for i in range(401)]
    y1 = [math.exp(-0.5 * x * x) for x in xs]
    y2 = [0.6 * math.cos(2.0 * x) * math.exp(-0.15 * abs(x)) for x in xs]

    fig, axes = figurs.subplots(1, 2, figsize=(720, 320))
    fig.set(suptitle=r"$\displaystyle \hat{f}(\xi)=\int_{-\infty}^{\infty} "
                     r"f(x)\,e^{-2\pi i x \xi}\,dx$")

    ax = axes[0]
    ax.line(xs, y1, color="C0", label=r"$e^{-x^2/2}$")
    ax.line(xs, y2, color="C1", linestyle="dashed",
            label=r"$\frac{3}{5}\cos(2x)\,e^{-|x|/7}$")
    ax.set(title=r"$\sum_{n=1}^{\infty}\frac{1}{n^2}=\frac{\pi^2}{6}$",
           xlabel=r"position $x\ (\mu\mathrm{m})$",
           ylabel=r"$\sqrt[3]{\,1+\alpha_0^{2}\,}$")
    ax.legend(loc="upper right")

    ax = axes[1]
    ax.line(xs, [math.tanh(x) for x in xs], color="C2",
            label=r"$\vec{\nabla}\times\vec{B}=\mu_0\vec{J}$")
    ax.set(title=r"$A=\left[\begin{matrix} a & b \\ c & d \end{matrix}\right],"
                 r"\ \det A = ad-bc$",
           xlabel=r"$\left(\frac{\partial u}{\partial t}\right)$",
           ylabel=r"$\mathbb{R}\to\mathcal{H},\ \bar{z}=x-iy$")
    ax.legend(loc="lower right")

    fig.save(out("math2d.pdf"))   # native: real embedded STIX glyphs, editable
    fig.save(out("math2d.svg"))   # native: selectable glyph runs + vector rules
    fig.save(out("math2d.png"))   # native: rasterized at dpi
    fig.save(out("math2d.html"))  # MathJax overlay (copy-as-LaTeX, offline)


def math_3d() -> None:
    """A 3D surface whose labels carry $...$ in title, axis labels and legend.
    Static (.pdf) routes labels through figurs-math; the interactive .html now
    typesets them with MathJax overlay divs that track the canvas as you orbit."""
    n = 36
    xs = [-3.0 + 6.0 * i / (n - 1) for i in range(n)]
    ys = [-3.0 + 6.0 * j / (n - 1) for j in range(n)]
    zz = [[math.sin(math.hypot(x, y)) for x in xs] for y in ys]

    fig, ax = figurs.subplots(projection="3d", figsize=(540, 432))
    ax.surface(xs, ys, zz, cmap="viridis", label=r"$z=\sin r$")
    ax.plot([-3, 3], [0, 0], [0, 0], color="C3", label=r"$\hat{x}$ axis")
    ax.legend(loc="upper right")
    ax.set(title=r"$z=\sin\sqrt{x^2+y^2}$",
           xlabel=r"$x\ (\mathrm{rad})$", ylabel=r"$\theta_y$",
           zlabel=r"$\Phi(z)$", elev=30.0, azim=-60.0)
    fig.save(out("math3d.pdf"))   # static: native math renders
    fig.save(out("math3d.html"))  # Canvas2D viewer + MathJax overlay


def plain_3d() -> None:
    """A 3D figure with NO math, to confirm the plain path stays untouched
    (no MathJax inlined, page stays small)."""
    n = 30
    xs = [-3.0 + 6.0 * i / (n - 1) for i in range(n)]
    ys = [-3.0 + 6.0 * j / (n - 1) for j in range(n)]
    zz = [[math.cos(math.hypot(x, y)) for x in xs] for y in ys]
    fig, ax = figurs.subplots(projection="3d", figsize=(432, 360))
    ax.surface(xs, ys, zz, cmap="magma")
    ax.set(title="plain 3d (no math)", xlabel="x", ylabel="y", zlabel="z",
           elev=28.0, azim=-50.0)
    fig.save(out("plain3d.html"))


def main() -> None:
    heavy_math_2d()
    math_3d()
    plain_3d()
    print("wrote to", _OUT)
    print(" ", ", ".join(sorted(
        f for f in os.listdir(_OUT)
        if f.startswith(("math", "plain")) and not f.endswith(".py"))))


if __name__ == "__main__":
    main()
