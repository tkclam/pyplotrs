"""Self-contained, MathJax-backed HTML export for 2D figures that contain math.

When a 2D figure's labels use ``$...$``, ``Figure.save("x.html")`` routes here
instead of inlining the baked-vector SVG. The math is **re-rendered by MathJax**
so it is selectable and copyable as LaTeX or MathML (right-click -> *Show Math
As*), while everything else stays the same crisp pyplotrs SVG.

How it fits together:

- During the HTML build, ``Figure._build_scene(capture=...)`` wraps the real
  ``Scene`` in :class:`_MathCapture`. That proxy forwards every call verbatim
  **except** ``add_math`` for a ``$``-bearing string: it records the run's TeX,
  its final left-edge/baseline, its measured box ``(width, ascent, depth)``, its
  colour, and the *composed* group transform in effect (so rotated axis/colorbar
  labels are reproduced) -- and then **drops** the baked glyphs. Because the math
  glyph runs are never added, the bundled STIX math font is not embedded in the
  SVG either, so the SVG stays small.
- :func:`figure_to_math_html` lays the figure's SVG at a fixed pixel size (1 SVG
  user unit = 1 CSS px) and places one absolutely-positioned ``<div>`` per math
  run, centred on the exact ink box pyplotrs reserved, rotated by the captured
  transform. MathJax (SVG output, fonts embedded) typesets those divs.
- The whole MathJax library is inlined, so the page is fully offline.

Trade-off: math is rendered by MathJax (its metrics, not pyplotrs'), so it can
differ by a hair from the PDF/PNG, and with JavaScript disabled the math labels
do not appear (the rest of the figure does). 3D figures are unaffected -- they
take the Canvas2D path in ``_html3d.py``.
"""

from __future__ import annotations

import html
import math
from pathlib import Path

_BUNDLE_PATH = Path(__file__).parent / "_vendor" / "mathjax-tex-svg-full.min.js"
_bundle_cache: str | None = None


def _compose(p: tuple, c: tuple) -> tuple:
    """Compose two pyplotrs affines ``(a,b,c,d,e,f)`` so the result maps a point
    through the child ``c`` then the parent ``p`` -- i.e. ``p(c(point))``. The
    pyplotrs/SVG convention is ``x' = a*x + c*y + e`` , ``y' = b*x + d*y + f``."""
    pa, pb, pc, pd, pe, pf = p
    ca, cb, cc, cd, ce, cf = c
    return (
        pa * ca + pc * cb,
        pb * ca + pd * cb,
        pa * cc + pc * cd,
        pb * cc + pd * cd,
        pa * ce + pc * cf + pe,
        pb * ce + pd * cf + pf,
    )


class _MathCapture:
    """Scene proxy used only while building a figure for MathJax HTML.

    Forwards everything to the wrapped ``Scene`` except ``$``-bearing
    ``add_math`` calls, which are recorded into ``sink`` and *not* drawn (so the
    math is rendered by MathJax instead, and the math font is not embedded).
    ``begin_group``/``end_group`` are tracked to recover the absolute transform
    of each math run (rotated axis/colorbar labels)."""

    def __init__(self, real, sink: list) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_sink", sink)
        object.__setattr__(self, "_xf", [(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)])

    def __getattr__(self, name):  # forward every untouched method/attr
        return getattr(self._real, name)

    def begin_group(self, a, b, c, d, e, f, clip=None, opacity=1.0):
        self._xf.append(_compose(self._xf[-1], (a, b, c, d, e, f)))
        self._real.begin_group(a, b, c, d, e, f, clip=clip, opacity=opacity)

    def end_group(self):
        self._xf.pop()
        self._real.end_group()

    def add_math(self, x, y, text, size, color=(0, 0, 0, 255)):
        if "$" in text:
            w, a, d = self._real.measure_math(text, size)
            self._sink.append({
                "tex": text, "x": x, "baseline": y, "w": w, "a": a, "d": d,
                "size": size, "color": tuple(color), "xf": self._xf[-1],
            })
            return  # suppress the baked glyphs; MathJax draws this run
        self._real.add_math(x, y, text, size, color)


def _mathjax_bundle() -> str:
    """The inlined MathJax library, cached. Any literal ``</script`` inside JS
    string/regex literals is neutralised (``<\\/script`` is identical in JS) so
    the inline ``<script>`` cannot be closed early."""
    global _bundle_cache
    if _bundle_cache is None:
        _bundle_cache = _BUNDLE_PATH.read_text(encoding="utf-8").replace(
            "</script", "<\\/script")
    return _bundle_cache


# Recognise pyplotrs' own ``$...$`` delimiter; don't auto-typeset the page (we
# typeset only our overlay divs, never the baked SVG text); SVG output with
# fonts inlined keeps the file offline.
_MATHJAX_CONFIG = (
    "window.MathJax={"
    "tex:{inlineMath:[['$','$']],processEscapes:true},"
    "svg:{fontCache:'none'},"
    "options:{enableMenu:true},"
    "startup:{typeset:false}"
    "};"
)

_TYPESET = (
    "MathJax.startup.promise.then(function(){"
    "return MathJax.typesetPromise(document.querySelectorAll('.fxmath'));"
    "});"
)


def _overlay_div(p: dict) -> str:
    """One absolutely-positioned MathJax div, centred on the pyplotrs ink box."""
    a, d, w = p["a"], p["d"], p["w"]
    A, B, C, D, E, F = p["xf"]
    # Centre of the ink box in the run's *local* coords, then to absolute px.
    cxl = p["x"] + w / 2.0
    cyl = p["baseline"] + (d - a) / 2.0
    cx = A * cxl + C * cyl + E
    cy = B * cxl + D * cyl + F
    deg = math.degrees(math.atan2(B, A))
    col = p["color"]
    r, g, b = col[0], col[1], col[2]
    alpha = col[3] if len(col) > 3 else 255
    opacity = "" if alpha >= 255 else f"opacity:{alpha / 255:.3f};"
    rot = "" if abs(deg) < 1e-6 else f" rotate({deg:.4f}deg)"
    return (
        f'<div class="fxmath" style="left:{cx:.3f}px;top:{cy:.3f}px;'
        f'font-size:{p["size"]:.4f}px;color:rgb({r},{g},{b});{opacity}'
        f'transform:translate(-50%,-50%){rot};">'
        f'{html.escape(p["tex"])}</div>'
    )


def figure_to_math_html(svg: str, placements: list, size_pt, title: str,
                        alt: str) -> str:
    """Wrap a (math-suppressed) figure ``svg`` plus its captured math
    ``placements`` in a self-contained MathJax HTML page."""
    w_pt, h_pt = size_pt
    body = svg
    if body.startswith("<?xml"):
        body = body[body.index("?>") + 2:].lstrip("\n")
    if body.startswith("<svg "):
        body = ('<svg aria-hidden="true" '
                'style="position:absolute;top:0;left:0;width:100%;height:100%" '
                + body[len("<svg "):])
    overlays = "\n".join(_overlay_div(p) for p in placements)
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "<style>\n"
        "html,body{margin:0}\n"
        "body{background:#f5f5f5;display:flex;align-items:center;"
        "justify-content:center;min-height:100vh}\n"
        f".fxwrap{{position:relative;width:{w_pt:.3f}px;height:{h_pt:.3f}px;"
        "background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.15)}\n"
        ".fxmath{position:absolute;white-space:nowrap;line-height:1}\n"
        "mjx-container{margin:0!important}\n"
        "</style>\n</head>\n<body>\n"
        f'<div class="fxwrap" role="img" aria-label="{html.escape(alt, quote=True)}">\n'
        f"{body}\n{overlays}\n</div>\n"
        f"<script>{_MATHJAX_CONFIG}</script>\n"
        f"<script>{_mathjax_bundle()}</script>\n"
        f"<script>{_TYPESET}</script>\n"
        "</body>\n</html>\n"
    )
