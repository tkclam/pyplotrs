"""Interactive HTML for 3D figures: a canvas you can orbit (drag), zoom
(scroll) and pan (shift-drag), with nothing fetched at view time."""

from __future__ import annotations

import base64
import html
import json
from importlib.resources import files
from typing import TYPE_CHECKING

from . import _core
from .colors import to_hex
from .text import plain

if TYPE_CHECKING:
    from .figure import Figure


def interactive_html(fig: Figure, title: str, alt: str) -> str:
    th = fig.theme
    payload = {"axes": [ax._payload() for ax in fig.axes]}
    script = (
        "const FIG = " + json.dumps(payload, separators=(",", ":")).replace("</", "<\\/") + ";\n"
    )
    script += files("pyplotrs").joinpath("viewer3d.js").read_text(encoding="utf-8")
    font = base64.b64encode(_core.Scene(1, 1, list(th.font_family)).font_data()).decode()
    w, h = fig.size
    cw, ch = w / fig.ncols, h / fig.nrows
    cells = "\n".join(
        '<div class="figcell"><canvas class="pyplotrs3d"></canvas></div>' for _ in fig.axes
    )
    bg = to_hex(th.figure_facecolor) if th.figure_facecolor else "#fff"
    ink = to_hex(th.text_color)
    suptitle = (
        f'<div class="suptitle">{html.escape(plain(fig.suptitle))}</div>\n' if fig.suptitle else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
@font-face{{font-family:'PyplotrsBody';font-display:block;src:url(data:font/ttf;base64,{font}) format('truetype')}}
html,body{{margin:0;height:100%}}
body{{display:flex;flex-direction:column;align-items:center;justify-content:center;background:{bg};color:{ink};font-family:'PyplotrsBody',sans-serif}}
.suptitle{{font-size:{th.suptitle_size}px;margin:10px 0 4px}}
.grid{{display:grid;grid-template-columns:repeat({fig.ncols},{cw:.1f}px);grid-template-rows:repeat({fig.nrows},{ch:.1f}px);gap:6px}}
.figcell{{position:relative;width:100%;height:100%}}
canvas.pyplotrs3d{{width:100%;height:100%;display:block;cursor:grab;touch-action:none}}
canvas.pyplotrs3d:active{{cursor:grabbing}}
.hint{{font-size:11px;opacity:.6;margin:6px 0 10px}}
</style>
</head>
<body>
{suptitle}<div class="grid" role="img" aria-label="{html.escape(alt)}">
{cells}
</div>
<div class="hint">drag to rotate &middot; scroll to zoom &middot; shift-drag to pan &middot; double-click to reset</div>
<script>
{script}
</script>
</body>
</html>
"""
