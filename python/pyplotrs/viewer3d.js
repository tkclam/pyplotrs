// Interactive viewer for 3D figures saved as HTML. Expects `FIG` (the payload
// from Axes3D._payload) to be defined. The projection mirrors axes3d.py.
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
function plainText(s){ return typeof s === "string" ? s.replace(/\$/g, "") : s; }

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
  constructor(canvas, data){
    this.cv = canvas; this.ctx = canvas.getContext("2d"); this.d = data;
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
    const ctx = this.ctx, d = this.d, P = this._proj();
    ctx.clearRect(0, 0, this.W, this.H);
    ctx.fillStyle = rgba(d.theme.bg); ctx.fillRect(0, 0, this.W, this.H);
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
    ctx.setLineDash(m.dash || []); ctx.strokeStyle = rgba(m.color); ctx.lineWidth = m.linewidth; ctx.stroke(); ctx.setLineDash([]);
  }
  _scatter(ctx, m, P){
    const pts = m.pts.map(p => P.projn(p)).sort((a, b) => a[2] - b[2]);
    for (const dv of pts) drawMarker(ctx, dv[0], dv[1], m.d, m.marker, m.color, m.edgecolor);
  }

  _labels(ctx, d, P, zb){
    // A label centered at the projected anchor, pushed `outward` px away from
    // the cube center.
    const place = (anchor, text, size, outward) => {
      const p = P.projn(anchor); let vx = p[0]-P.center[0], vy = p[1]-P.center[1];
      const vl = Math.hypot(vx, vy) || 1;
      const px = p[0] + vx/vl*outward, py = p[1] + vy/vl*outward;
      ctx.fillStyle = rgba(d.theme.text); ctx.font = size + "px " + FONT;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(plainText(text), px, py);
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
      ctx.fillStyle = rgba(d.theme.text); ctx.font = d.theme.title_size + "px " + FONT;
      ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(plainText(d.title), this.W/2, 4);
    }
  }

  _legend(ctx, lg){
    const pad = 6, gap = 5, sw = 22, fs = this.d.theme.tick_size + 1;
    ctx.font = fs + "px " + FONT; ctx.textBaseline = "middle";
    const lw = i => ctx.measureText(plainText(lg.entries[i].label)).width;
    const lh = i => fs;
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
      ctx.fillStyle = rgba(this.d.theme.text); ctx.textAlign = "left"; ctx.fillText(plainText(e.label), x + sw + 6, cy);
    });
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
  const plots = cells.map((cell, i) => new Plot3D(cell.querySelector("canvas"), FIG.axes[i]));
  const sizeAll = () => plots.forEach(p => p.resize());
  sizeAll();
  window.addEventListener("resize", sizeAll);
}
window.addEventListener("DOMContentLoaded", boot);
