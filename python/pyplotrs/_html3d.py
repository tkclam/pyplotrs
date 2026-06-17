"""Interactive 3D HTML export.

A figure that has a 3D axes can't be frozen into a flat SVG and still rotate, so
``Figure.save("x.html")`` routes 3D figures here instead of the inline-SVG path.
We ship the 3D scene (marks pre-normalized into the unit cube, ticks, theme
colours) as JSON plus a small self-contained Canvas2D renderer that re-projects
on the client: drag to orbit, wheel to zoom, shift-drag to pan, double-click to
reset. No dependencies, nothing fetched at view time — one portable file.

The browser-side projection is a direct port of :class:`pyplotrs.threed.Camera3D`
and :meth:`pyplotrs.figure.Axes3D._draw`, so the interactive view matches the
static PDF/SVG/PNG render at the same camera angle.

Labels that use ``$...$`` are typeset by an inlined copy of MathJax (the same
offline bundle the 2D HTML path uses): each math label becomes an absolutely
positioned overlay ``<div>`` that the renderer re-pins over its canvas label
every frame, so the math tracks the title/axis/tick/legend text as you orbit,
zoom and pan. MathJax is inlined only when a label actually contains math, so
plain 3D pages stay as small and dependency-free as before. (Math labels are
display-only here -- the overlay ignores pointer events so dragging always
orbits -- whereas the 2D HTML path keeps math selectable/copyable.)
"""

from __future__ import annotations

import base64
import html
import json

from . import _pyplotrs_core as _core


def _body_font_face() -> str:
    """An ``@font-face`` rule embedding the resolved body font (the same one the
    static backends use), so the interactive canvas draws labels with it rather
    than a viewer-dependent system font - keeping the saved page consistent
    across machines."""
    b64 = base64.b64encode(_core.body_font_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'PyplotrsBody';font-display:block;"
        f"src:url(data:font/ttf;base64,{b64}) format('truetype')}}\n"
    )


# The client renderer. Kept dependency-free and small; the projection math
# mirrors threed.Camera3D / Axes3D._draw one-to-one.
_RENDER_JS = r"""
const FIG = __PAYLOAD__;
const FONT = "'PyplotrsBody',Arial,Helvetica,'Liberation Sans',system-ui,sans-serif";
const CORNERS = [];
for (const sx of [-0.5, 0.5]) for (const sy of [-0.5, 0.5]) for (const sz of [-0.5, 0.5]) CORNERS.push([sx, sy, sz]);
// The projected unit cube's bbox spans at most its space diagonal along either
// screen axis; fitting to this constant keeps the scale fixed while orbiting.
const CUBE_DIAG = Math.sqrt(3);

const sub = (a, b) => [a[0]-b[0], a[1]-b[1], a[2]-b[2]];
const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
function norm(v){ const n = Math.hypot(v[0], v[1], v[2]); return n < 1e-12 ? [0,0,0] : [v[0]/n, v[1]/n, v[2]/n]; }
function rgba(c){ return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + ((c.length > 3 ? c[3] : 255)/255) + ")"; }
function hasMath(s){ return typeof s === "string" && s.indexOf("$") >= 0; }

function camera(elev, azim){
  const e = elev*Math.PI/180, a = azim*Math.PI/180;
  const dir = norm([Math.cos(e)*Math.cos(a), Math.cos(e)*Math.sin(a), Math.sin(e)]);
  let right = cross([0,0,1], dir);
  if (right[0]**2 + right[1]**2 + right[2]**2 < 1e-12) right = [1,0,0];
  right = norm(right);
  return { dir, right, up: cross(dir, right) };
}
const viewOf = (cam, p) => [dot(p, cam.right), dot(p, cam.up), dot(p, cam.dir)];

function drawMarker(ctx, cx, cy, d, shape, fc, ec){
  const r = d/2;
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  if (shape === "+" || shape === "x"){
    ctx.strokeStyle = rgba(ec || fc); ctx.lineWidth = 1; ctx.beginPath();
    if (shape === "+"){ ctx.moveTo(cx-r, cy); ctx.lineTo(cx+r, cy); ctx.moveTo(cx, cy-r); ctx.lineTo(cx, cy+r); }
    else { ctx.moveTo(cx-r, cy-r); ctx.lineTo(cx+r, cy+r); ctx.moveTo(cx-r, cy+r); ctx.lineTo(cx+r, cy-r); }
    ctx.stroke(); return;
  }
  ctx.beginPath();
  if (shape === "s"){ ctx.rect(cx-r, cy-r, 2*r, 2*r); }
  else if (shape === "^"){ const s = r*0.95; ctx.moveTo(cx, cy-r); ctx.lineTo(cx+s, cy+r*0.8); ctx.lineTo(cx-s, cy+r*0.8); ctx.closePath(); }
  else if (shape === "v"){ const s = r*0.95; ctx.moveTo(cx, cy+r); ctx.lineTo(cx-s, cy-r*0.8); ctx.lineTo(cx+s, cy-r*0.8); ctx.closePath(); }
  else if (shape === "D"){ ctx.moveTo(cx, cy-r); ctx.lineTo(cx+r*0.8, cy); ctx.lineTo(cx, cy+r); ctx.lineTo(cx-r*0.8, cy); ctx.closePath(); }
  else { ctx.arc(cx, cy, r, 0, 2*Math.PI); }
  ctx.fillStyle = rgba(fc); ctx.fill();
  if (ec){ ctx.strokeStyle = rgba(ec); ctx.lineWidth = 1; ctx.stroke(); }
}

class Plot3D {
  constructor(canvas, overlay, data){
    this.cv = canvas; this.ctx = canvas.getContext("2d"); this.d = data;
    // Math labels are typeset by MathJax into absolutely-positioned overlay
    // divs (mdiv, keyed by role) re-positioned each frame to track the canvas;
    // mw caches their measured size for legend-box layout. Plain labels stay on
    // the canvas (fillText). `ready` gates drawing until MathJax has typeset.
    this.ovl = overlay; this.mdiv = {}; this.mw = {};
    this.ready = !FIG.hasMath;
    this.elev0 = data.elev; this.azim0 = data.azim;
    this.reset();
    this._bind();
  }
  reset(){ this.elev = this.elev0; this.azim = this.azim0; this.zoom = 1; this.panx = 0; this.pany = 0; this.schedule(); }

  resize(){
    const dpr = window.devicePixelRatio || 1;
    const w = this.cv.clientWidth, h = this.cv.clientHeight;
    this.cv.width = Math.round(w*dpr); this.cv.height = Math.round(h*dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.W = w; this.H = h; this.schedule();
  }

  // Build the per-frame projection closure from the current camera state.
  _proj(){
    const d = this.d, cam = camera(this.elev, this.azim);
    const titleH = d.title ? d.theme.title_size*1.9 : 6;
    const x0 = 6, y0 = titleH, pw = Math.max(this.W - 12, 1), ph = Math.max(this.H - titleH - 6, 1);
    let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
    for (const c of CORNERS){ const s = viewOf(cam, c); minx = Math.min(minx, s[0]); maxx = Math.max(maxx, s[0]); miny = Math.min(miny, s[1]); maxy = Math.max(maxy, s[1]); }
    // Fit to a fixed reference (not the per-frame bbox) so the zoom level stays
    // constant as you orbit — the cube never overflows because its projected
    // bbox is at most CUBE_DIAG on either axis.
    const scale = Math.min(pw, ph) / CUBE_DIAG * d.theme.cube_fill * this.zoom;
    const ccx = x0 + pw/2 + this.panx, ccy = y0 + ph/2 + this.pany;
    const scx = (minx + maxx)/2, scy = (miny + maxy)/2;
    const toDev = (sx, sy) => [ccx + (sx - scx)*scale, ccy - (sy - scy)*scale];
    const projn = p => { const s = viewOf(cam, p); const dv = toDev(s[0], s[1]); return [dv[0], dv[1], s[2]]; };
    return { cam, projn, depth: p => viewOf(cam, p)[2], center: toDev(0, 0) };
  }

  draw(){
    if (!this.ready) return;  // wait for MathJax to typeset overlay labels
    const ctx = this.ctx, d = this.d, P = this._proj();
    ctx.clearRect(0, 0, this.W, this.H);
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, this.W, this.H);
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    const pj = p => P.projn(p);

    // Back walls: the farther plane of each axis-aligned pair.
    const zb = P.depth([0,0,-0.5]) < P.depth([0,0,0.5]) ? -0.5 : 0.5;
    const xb = P.depth([-0.5,0,0]) < P.depth([0.5,0,0]) ? -0.5 : 0.5;
    const yb = P.depth([0,-0.5,0]) < P.depth([0,0.5,0]) ? -0.5 : 0.5;

    const pane = (a, b, c, e) => {
      const q = [pj(a), pj(b), pj(c), pj(e)];
      ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]);
      for (let i = 1; i < 4; i++) ctx.lineTo(q[i][0], q[i][1]);
      ctx.closePath(); ctx.fillStyle = rgba(d.theme.pane_fill); ctx.fill();
      ctx.strokeStyle = rgba(d.theme.pane_edge); ctx.lineWidth = 0.8; ctx.stroke();
    };
    const grid = (a, b) => { const p = pj(a), q = pj(b); ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.strokeStyle = rgba(d.theme.grid); ctx.lineWidth = 0.6; ctx.stroke(); };

    pane([-0.5,-0.5,zb], [0.5,-0.5,zb], [0.5,0.5,zb], [-0.5,0.5,zb]);
    for (const [nx] of d.xticks) grid([nx,-0.5,zb], [nx,0.5,zb]);
    for (const [ny] of d.yticks) grid([-0.5,ny,zb], [0.5,ny,zb]);
    pane([xb,-0.5,-0.5], [xb,0.5,-0.5], [xb,0.5,0.5], [xb,-0.5,0.5]);
    for (const [ny] of d.yticks) grid([xb,ny,-0.5], [xb,ny,0.5]);
    for (const [nz] of d.zticks) grid([xb,-0.5,nz], [xb,0.5,nz]);
    pane([-0.5,yb,-0.5], [0.5,yb,-0.5], [0.5,yb,0.5], [-0.5,yb,0.5]);
    for (const [nx] of d.xticks) grid([nx,yb,-0.5], [nx,yb,0.5]);
    for (const [nz] of d.zticks) grid([-0.5,yb,nz], [0.5,yb,nz]);

    // Surfaces, then lines, then points (painter's order, like the static render).
    for (const m of d.marks) if (m.kind === "surface") this._surface(ctx, m, P);
    for (const m of d.marks) if (m.kind === "line") this._line(ctx, m, P);
    for (const m of d.marks) if (m.kind === "scatter") this._scatter(ctx, m, P);

    this._labels(ctx, d, P, zb);
    if (d.legend) this._legend(ctx, d.legend);

    // Reveal the math overlay only once its divs have been positioned this
    // frame, so they never flash untransformed at the corner.
    if (this.ovl && this.ovl.style.visibility === "hidden") this.ovl.style.visibility = "";
  }

  _surface(ctx, m, P){
    const nr = m.nr, nc = m.nc, faces = [];
    for (let i = 0; i < nr-1; i++) for (let j = 0; j < nc-1; j++){
      const a = P.projn(m.verts[i*nc+j]), b = P.projn(m.verts[i*nc+j+1]),
            c = P.projn(m.verts[(i+1)*nc+j+1]), e = P.projn(m.verts[(i+1)*nc+j]);
      faces.push([(a[2]+b[2]+c[2]+e[2])/4, a, b, c, e, m.facecolors[i*(nc-1)+j]]);
    }
    faces.sort((p, q) => p[0] - q[0]);
    for (const f of faces){
      ctx.beginPath(); ctx.moveTo(f[1][0], f[1][1]); ctx.lineTo(f[2][0], f[2][1]); ctx.lineTo(f[3][0], f[3][1]); ctx.lineTo(f[4][0], f[4][1]); ctx.closePath();
      const col = rgba(f[5]); ctx.fillStyle = col; ctx.fill(); ctx.strokeStyle = col; ctx.lineWidth = 0.4; ctx.stroke();
    }
  }
  _line(ctx, m, P){
    if (m.pts.length < 2) return;
    ctx.beginPath();
    m.pts.forEach((p, i) => { const dv = P.projn(p); i ? ctx.lineTo(dv[0], dv[1]) : ctx.moveTo(dv[0], dv[1]); });
    ctx.setLineDash(m.dash || []); ctx.strokeStyle = rgba(m.color); ctx.lineWidth = m.width; ctx.stroke(); ctx.setLineDash([]);
  }
  _scatter(ctx, m, P){
    const pts = m.pts.map(p => P.projn(p)).sort((a, b) => a[2] - b[2]);
    for (const dv of pts) drawMarker(ctx, dv[0], dv[1], m.d, m.marker, m.color, m.edgecolor);
  }

  _labels(ctx, d, P, zb){
    // Position a label centred at the projected anchor pushed `outward` px away
    // from the cube centre. A $-bearing label is a pre-typeset overlay div
    // (translated into place); a plain one is drawn on the canvas.
    const place = (anchor, text, size, outward, role) => {
      const p = P.projn(anchor); let vx = p[0]-P.center[0], vy = p[1]-P.center[1];
      const vl = Math.hypot(vx, vy) || 1;
      const px = p[0] + vx/vl*outward, py = p[1] + vy/vl*outward;
      const el = this.mdiv[role];
      if (el){ el.style.transform = "translate(" + px + "px," + py + "px) translate(-50%,-50%)"; return; }
      ctx.fillStyle = rgba(d.theme.text); ctx.font = size + "px " + FONT;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(text, px, py);
    };
    const yEdge = P.projn([0,-0.5,zb])[1] >= P.projn([0,0.5,zb])[1] ? -0.5 : 0.5;
    const xEdge = P.projn([-0.5,0,zb])[1] >= P.projn([0.5,0,zb])[1] ? -0.5 : 0.5;
    let zc = [[-0.5,-0.5],[0.5,-0.5],[0.5,0.5],[-0.5,0.5]], zEdge = zc[0], best = Infinity;
    for (const c of zc){ const x = P.projn([c[0], c[1], 0])[0]; if (x < best){ best = x; zEdge = c; } }
    const ts = d.theme.tick_size, as = d.theme.axis_size;
    d.xticks.forEach(([nx, lab], i) => place([nx, yEdge, zb], lab, ts, 9, "xt" + i));
    d.yticks.forEach(([ny, lab], i) => place([xEdge, ny, zb], lab, ts, 9, "yt" + i));
    d.zticks.forEach(([nz, lab], i) => place([zEdge[0], zEdge[1], nz], lab, ts, 9, "zt" + i));
    if (d.xlabel) place([0, yEdge, zb], d.xlabel, as, 26, "xlabel");
    if (d.ylabel) place([xEdge, 0, zb], d.ylabel, as, 26, "ylabel");
    if (d.zlabel) place([zEdge[0], zEdge[1], 0], d.zlabel, as, 30, "zlabel");
    if (d.title){
      const el = this.mdiv["title"];
      if (el){ el.style.transform = "translate(" + (this.W/2) + "px,4px) translate(-50%,0)"; }
      else { ctx.fillStyle = rgba(d.theme.text); ctx.font = "600 " + d.theme.title_size + "px " + FONT; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(d.title, this.W/2, 4); }
    }
  }

  _legend(ctx, lg){
    const pad = 6, gap = 5, sw = 22, fs = this.d.theme.tick_size + 1;
    ctx.font = fs + "px " + FONT; ctx.textBaseline = "middle";
    // Math entries are sized from their typeset div, plain ones from measureText.
    const lw = i => this.mw["leg" + i] ? this.mw["leg" + i].w : ctx.measureText(lg.entries[i].label).width;
    const lh = i => this.mw["leg" + i] ? this.mw["leg" + i].h : fs;
    let tw = 0, mh = fs;
    for (let i = 0; i < lg.entries.length; i++){ tw = Math.max(tw, lw(i)); mh = Math.max(mh, lh(i)); }
    const bw = pad*2 + sw + 6 + tw, rh = Math.max(fs + 5, mh + 3), bh = pad*2 + rh*lg.entries.length;
    const inset = 6, loc = lg.loc || "upper right";
    const bx = loc.includes("left") ? inset : this.W - inset - bw;
    const by = loc.includes("lower") ? this.H - inset - bh : inset;
    ctx.fillStyle = "rgba(255,255,255,0.85)"; ctx.strokeStyle = "rgba(0,0,0,0.25)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.rect(bx, by, bw, bh); ctx.fill(); ctx.stroke();
    ctx.setLineDash([]);
    lg.entries.forEach((e, i) => {
      const cy = by + pad + rh*i + rh/2, x = bx + pad;
      if (e.kind === "scatter"){ drawMarker(ctx, x + sw/2, cy, 9, e.marker || "o", e.color, null); }
      else { ctx.strokeStyle = rgba(e.color); ctx.lineWidth = 2; ctx.setLineDash(e.dash || []); ctx.beginPath(); ctx.moveTo(x, cy); ctx.lineTo(x + sw, cy); ctx.stroke(); ctx.setLineDash([]); }
      const el = this.mdiv["leg" + i];
      if (el){ el.style.transform = "translate(" + (x + sw + 6) + "px," + cy + "px) translate(0,-50%)"; }
      else { ctx.fillStyle = rgba(this.d.theme.text); ctx.textAlign = "left"; ctx.fillText(e.label, x + sw + 6, cy); }
    });
  }

  // Create one hidden overlay div per $-bearing label (title/axis/tick/legend),
  // holding the raw TeX for MathJax to typeset. Mixed "text $math$" labels work
  // because MathJax processes the inline $...$ delimiters in place.
  _initMath(){
    const d = this.d;
    if (this.ovl) this.ovl.style.visibility = "hidden";
    const mk = (role, text, fontPx, color, bold) => {
      if (!hasMath(text) || !this.ovl) return;
      const el = document.createElement("div");
      el.className = "fxm";
      el.style.fontSize = fontPx + "px";
      el.style.color = rgba(color);
      if (bold) el.style.fontWeight = "600";
      el.textContent = text;
      this.ovl.appendChild(el);
      this.mdiv[role] = el;
    };
    mk("title", d.title, d.theme.title_size, d.theme.text, true);
    mk("xlabel", d.xlabel, d.theme.axis_size, d.theme.text);
    mk("ylabel", d.ylabel, d.theme.axis_size, d.theme.text);
    mk("zlabel", d.zlabel, d.theme.axis_size, d.theme.text);
    d.xticks.forEach(([_, lab], i) => mk("xt" + i, lab, d.theme.tick_size, d.theme.text));
    d.yticks.forEach(([_, lab], i) => mk("yt" + i, lab, d.theme.tick_size, d.theme.text));
    d.zticks.forEach(([_, lab], i) => mk("zt" + i, lab, d.theme.tick_size, d.theme.text));
    if (d.legend) d.legend.entries.forEach((e, i) => mk("leg" + i, e.label, d.theme.tick_size + 1, d.theme.text));
  }

  // After typesetting: cache each div's rendered box (still hidden, so no
  // flash). draw() reveals the overlay once the divs are positioned.
  _measureMath(){
    for (const k in this.mdiv){ const r = this.mdiv[k].getBoundingClientRect(); this.mw[k] = { w: r.width, h: r.height }; }
    this.ready = true;
  }

  schedule(){ if (this._raf) return; this._raf = requestAnimationFrame(() => { this._raf = 0; this.draw(); }); }

  _bind(){
    const cv = this.cv;
    cv.addEventListener("contextmenu", e => e.preventDefault());
    cv.addEventListener("pointerdown", e => {
      cv.setPointerCapture(e.pointerId); this._drag = true; this._px = e.offsetX; this._py = e.offsetY;
      this._pan = e.shiftKey || e.button === 1 || e.button === 2;
    });
    cv.addEventListener("pointermove", e => {
      if (!this._drag) return;
      const dx = e.offsetX - this._px, dy = e.offsetY - this._py; this._px = e.offsetX; this._py = e.offsetY;
      if (this._pan){ this.panx += dx; this.pany += dy; }
      else { this.azim += dx*0.4; this.elev = Math.max(-89.9, Math.min(89.9, this.elev - dy*0.4)); }
      this.schedule();
    });
    const end = e => { this._drag = false; try { cv.releasePointerCapture(e.pointerId); } catch (_){} };
    cv.addEventListener("pointerup", end); cv.addEventListener("pointercancel", end);
    cv.addEventListener("wheel", e => { e.preventDefault(); this.zoom = Math.max(0.2, Math.min(8, this.zoom * Math.exp(-e.deltaY*0.0015))); this.schedule(); }, { passive: false });
    cv.addEventListener("dblclick", () => this.reset());
  }
}

function boot(){
  // Wait for the embedded body webfont so canvas labels are drawn with the
  // exact font the figure was laid out with (not a viewer-dependent fallback).
  const fontReady = (document.fonts && document.fonts.load)
    ? document.fonts.load("16px 'PyplotrsBody'").catch(() => {})
    : Promise.resolve();
  fontReady.then(_boot);
}

function _boot(){
  const cells = [...document.querySelectorAll(".figcell")];
  const plots = cells.map((cell, i) =>
    new Plot3D(cell.querySelector("canvas"), cell.querySelector(".ovl"), FIG.axes[i]));
  const sizeAll = () => plots.forEach(p => p.resize());
  const start = () => { sizeAll(); window.addEventListener("resize", sizeAll); };
  if (FIG.hasMath && window.MathJax && MathJax.typesetPromise){
    // Typeset all math labels once, cache their sizes, then start drawing.
    plots.forEach(p => p._initMath());
    const all = [];
    plots.forEach(p => { for (const k in p.mdiv) all.push(p.mdiv[k]); });
    MathJax.startup.promise
      .then(() => MathJax.typesetPromise(all))
      .then(() => { plots.forEach(p => p._measureMath()); start(); })
      .catch(() => { plots.forEach(p => { p.ready = true; }); start(); });
  } else {
    plots.forEach(p => { p.ready = true; });
    start();
  }
}
window.addEventListener("DOMContentLoaded", boot);
"""


def _payload_has_math(ax: dict) -> bool:
    """True if any of a 3D axes' labels (title/axis/tick/legend) carry ``$...$``."""
    for key in ("title", "xlabel", "ylabel", "zlabel"):
        v = ax.get(key)
        if isinstance(v, str) and "$" in v:
            return True
    for key in ("xticks", "yticks", "zticks"):
        for _pos, lab in ax.get(key) or []:
            if isinstance(lab, str) and "$" in lab:
                return True
    lg = ax.get("legend")
    if lg:
        for e in lg.get("entries", []):
            if "$" in (e.get("label") or ""):
                return True
    return False


def figure_to_interactive_html(fig, title: str, alt: str) -> str:
    """Build a self-contained interactive HTML page for a figure that has 3D
    axes. One ``<canvas>`` per axes (a grid matching ``nrows``x``ncols``), each
    independently orbitable/zoomable/pannable.

    Labels containing ``$...$`` are typeset by an inlined copy of **MathJax**
    (SVG output, offline) into overlay ``<div>``s the renderer keeps pinned over
    the moving canvas labels — so 3D math matches the 2D HTML path. MathJax is
    only inlined when some label actually uses math, keeping plain pages small."""
    axes = [ax._interactive_payload() for ax in fig.axes]
    has_math = any(_payload_has_math(ax) for ax in axes)
    data = {
        "width": fig.size_pt[0],
        "height": fig.size_pt[1],
        "nrows": fig.nrows,
        "ncols": fig.ncols,
        "hasMath": has_math,
        "axes": axes,
    }
    payload = json.dumps(data, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")  # keep a stray "</script>" in a label safe
    script = _RENDER_JS.replace("__PAYLOAD__", payload)

    ovl = '<div class="ovl"></div>' if has_math else ""
    cells = "\n".join(
        f'<div class="figcell"><canvas class="pyplotrs3d"></canvas>{ovl}</div>'
        for _ in fig.axes
    )
    suptitle = (
        f'<div class="suptitle">{html.escape(fig.suptitle)}</div>\n' if fig.suptitle else ""
    )
    math_scripts = ""
    if has_math:
        from ._htmlmath import _MATHJAX_CONFIG, _mathjax_bundle
        math_scripts = (
            f"<script>{_MATHJAX_CONFIG}</script>\n"
            f"<script>{_mathjax_bundle()}</script>\n"
        )
    cw, ch = fig.size_pt[0] / fig.ncols, fig.size_pt[1] / fig.nrows
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "<style>\n"
        f"{_body_font_face()}"
        "html,body{margin:0;height:100%}\n"
        "body{display:flex;flex-direction:column;align-items:center;justify-content:center;"
        "background:#f5f5f5;font-family:Arial,Helvetica,'Liberation Sans',system-ui,sans-serif}\n"
        f".suptitle{{font-size:{fig.theme.suptitle_size}px;font-weight:600;margin:10px 0 4px}}\n"
        f".grid{{display:grid;grid-template-columns:repeat({fig.ncols},{cw:.1f}px);"
        f"grid-template-rows:repeat({fig.nrows},{ch:.1f}px);gap:6px;"
        "background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.15)}\n"
        ".figcell{position:relative;width:100%;height:100%}\n"
        ".ovl{position:absolute;inset:0;overflow:hidden;pointer-events:none}\n"
        ".fxm{position:absolute;left:0;top:0;white-space:nowrap;line-height:1}\n"
        "mjx-container{margin:0!important}\n"
        "canvas.pyplotrs3d{width:100%;height:100%;display:block;cursor:grab;touch-action:none}\n"
        "canvas.pyplotrs3d:active{cursor:grabbing}\n"
        ".hint{font-size:11px;color:#666;margin:6px 0 10px}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{suptitle}"
        f'<div class="grid" role="img" aria-label="{html.escape(alt)}">\n{cells}\n</div>\n'
        '<div class="hint">drag to rotate &middot; scroll to zoom &middot; shift-drag to pan &middot; double-click to reset</div>\n'
        f"{math_scripts}"
        f"<script>\n{script}\n</script>\n"
        "</body>\n"
        "</html>\n"
    )
