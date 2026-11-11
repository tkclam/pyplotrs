//! Numeric kernels that would be slow in Python: data ranges, binning, density
//! estimates, contouring and colormapping.

use std::collections::HashMap;

use crate::geometry::Scale;

pub type Result<T> = std::result::Result<T, String>;

/// The largest buffer one kernel may allocate (matches the raster backend's
/// limit), so an oversized request fails with a message instead of aborting.
const MAX_KERNEL_BYTES: f64 = 4.0e9;

fn check_alloc(bytes: f64, who: &str, shape: &str) -> Result<()> {
    if bytes > MAX_KERNEL_BYTES {
        return Err(format!(
            "{who} would allocate {shape} ({:.1} GB, limit {:.0} GB); reduce the resolution or bin count",
            bytes / 1e9,
            MAX_KERNEL_BYTES / 1e9
        ));
    }
    Ok(())
}

fn check_grid(len: usize, w: usize, h: usize, who: &str) -> Result<()> {
    let want = w
        .checked_mul(h)
        .ok_or_else(|| format!("{who}: grid shape {w}x{h} overflows"))?;
    if len < want {
        return Err(format!(
            "{who}: a {w}x{h} grid needs {want} values, got {len}"
        ));
    }
    Ok(())
}

/// `(min, max)` over the finite values for which `keep` holds.
fn range_where(
    values: impl IntoIterator<Item = f64>,
    keep: impl Fn(f64) -> bool,
) -> Option<(f64, f64)> {
    let mut out: Option<(f64, f64)> = None;
    for v in values {
        if v.is_finite() && keep(v) {
            out = Some(match out {
                Some((lo, hi)) => (lo.min(v), hi.max(v)),
                None => (v, v),
            });
        }
    }
    out
}

/// `(min, max)` of the finite values.
pub fn finite_range(values: &[f64]) -> Option<(f64, f64)> {
    range_where(values.iter().copied(), |_| true)
}

/// `(min, max)` of the finite values in `scale`'s domain (positive for log).
pub fn scaled_range(values: &[f64], scale: Scale) -> Option<(f64, f64)> {
    range_where(values.iter().copied(), |v| scale.apply(v).is_finite())
}

/// `(min, max)` over `value + offset` (and `value - offset` if `two_sided`).
pub fn offset_range(values: &[f64], offsets: &[f64], two_sided: bool) -> Option<(f64, f64)> {
    let hi = range_where(values.iter().zip(offsets).map(|(v, e)| v + e), |_| true);
    if !two_sided {
        return hi;
    }
    let lo = range_where(values.iter().zip(offsets).map(|(v, e)| v - e), |_| true);
    match (lo, hi) {
        (Some(a), Some(b)) => Some((a.0.min(b.0), a.1.max(b.1))),
        (a, b) => a.or(b),
    }
}

/// The largest finite `ys[i]` whose `xs[i]` lies in `lo..=hi`.
pub fn peak(xs: &[f64], ys: &[f64], lo: f64, hi: f64) -> Option<f64> {
    xs.iter()
        .zip(ys)
        .filter(|&(&x, &y)| (lo..=hi).contains(&x) && y.is_finite())
        .map(|(_, &y)| y)
        .reduce(f64::max)
}

/// Maps values to positions on a 256-entry lookup table through a norm.
pub struct ColorMapper<'a> {
    lut: &'a [u8],
    norm: Scale,
    tmin: f64,
    span: f64,
}

impl<'a> ColorMapper<'a> {
    pub fn new(lut: &'a [u8], norm: Scale, vmin: f64, vmax: f64) -> Self {
        let (tmin, tmax) = (norm.apply(vmin), norm.apply(vmax));
        let span = if tmax > tmin { tmax - tmin } else { 1.0 };
        Self {
            lut,
            norm,
            tmin,
            span,
        }
    }

    /// Normalized position in `0..=1`, or `None` for non-finite input.
    #[inline]
    pub fn position(&self, v: f64) -> Option<f32> {
        let t = self.norm.apply(v);
        t.is_finite()
            .then(|| ((t - self.tmin) / self.span).clamp(0.0, 1.0) as f32)
    }

    /// RGBA for `v`; transparent for non-finite input.
    #[inline]
    pub fn rgba(&self, v: f64) -> [u8; 4] {
        match self.position(v) {
            Some(t) => {
                let i = ((t * 255.0).round() as usize).min(255) * 4;
                [
                    self.lut[i],
                    self.lut[i + 1],
                    self.lut[i + 2],
                    self.lut[i + 3],
                ]
            }
            None => [0; 4],
        }
    }
}

/// One RGBA quadruple per value, as a flat byte buffer.
pub fn map_colors(values: &[f64], lut: &[u8], norm: Scale, vmin: f64, vmax: f64) -> Vec<u8> {
    let m = ColorMapper::new(lut, norm, vmin, vmax);
    values.iter().flat_map(|&v| m.rgba(v)).collect()
}

/// `(edges, counts)` of a fixed-width histogram.
pub fn histogram(
    values: &[f64],
    bins: usize,
    range: Option<(f64, f64)>,
    density: bool,
) -> (Vec<f64>, Vec<f64>) {
    let vals = values;
    let bins = bins.max(1);
    let (mut lo, mut hi) = range.or_else(|| finite_range(vals)).unwrap_or((0.0, 1.0));
    if !(lo.is_finite() && hi.is_finite()) {
        lo = 0.0;
        hi = 1.0;
    }
    if lo == hi {
        hi = lo + 1.0;
    }
    let width = (hi - lo) / bins as f64;
    let edges: Vec<f64> = (0..=bins).map(|i| lo + width * i as f64).collect();

    let mut counts = vec![0.0f64; bins];
    let mut binned = 0.0f64;
    for &v in vals {
        if !v.is_finite() || v < lo || v > hi {
            continue;
        }
        let idx = (((v - lo) / width) as usize).min(bins - 1);
        counts[idx] += 1.0;
        binned += 1.0;
    }
    if density {
        let total = binned * width;
        if total != 0.0 {
            for c in counts.iter_mut() {
                *c /= total;
            }
        }
    }
    (edges, counts)
}

/// Row-major `ny x nx` bin counts.
#[allow(clippy::too_many_arguments)]
pub fn hist2d(
    xs: &[f64],
    ys: &[f64],
    nx: usize,
    ny: usize,
    xlo: f64,
    xhi: f64,
    ylo: f64,
    yhi: f64,
) -> Result<Vec<f64>> {
    if nx == 0 || ny == 0 {
        return Err("hist2d needs at least one bin on each axis".into());
    }
    check_alloc(
        nx as f64 * ny as f64 * 8.0,
        "hist2d",
        &format!("{nx} x {ny} bins"),
    )?;
    let mut counts = vec![0.0f64; nx * ny];
    let xspan = if xhi > xlo { xhi - xlo } else { 1.0 };
    let yspan = if yhi > ylo { yhi - ylo } else { 1.0 };
    for (&x, &y) in xs.iter().zip(ys.iter()) {
        if !(x.is_finite() && y.is_finite()) || x < xlo || x > xhi || y < ylo || y > yhi {
            continue;
        }
        let mut ix = ((x - xlo) / xspan * nx as f64) as usize;
        let mut iy = ((y - ylo) / yspan * ny as f64) as usize;
        if ix >= nx {
            ix = nx - 1;
        }
        if iy >= ny {
            iy = ny - 1;
        }
        counts[iy * nx + ix] += 1.0;
    }
    Ok(counts)
}

/// Gaussian kernel density of `samples` at `grid` (Scott's rule when
/// `bandwidth <= 0`).
pub fn gaussian_kde(samples: &[f64], grid: &[f64], bandwidth: f64) -> Vec<f64> {
    let n = samples.len();
    if n == 0 {
        return vec![0.0; grid.len()];
    }
    let mean = samples.iter().sum::<f64>() / n as f64;
    let var = samples.iter().map(|s| (s - mean).powi(2)).sum::<f64>() / n as f64;
    let std = var.sqrt();
    let bw = if bandwidth > 0.0 {
        bandwidth
    } else {
        let b = (n as f64).powf(-0.2) * std;
        if b > 0.0 { b } else { 1.0 }
    };
    let norm = 1.0 / (n as f64 * bw * (2.0 * std::f64::consts::PI).sqrt());
    grid.iter()
        .map(|&g| {
            let s: f64 = samples
                .iter()
                .map(|&x| {
                    let z = (g - x) / bw;
                    (-0.5 * z * z).exp()
                })
                .sum();
            s * norm
        })
        .collect()
}

/// Hexagonal binning: `(centers with counts, cell width, cell height)`.
#[allow(clippy::too_many_arguments)]
pub fn hexbin(
    xs: &[f64],
    ys: &[f64],
    gridsize: usize,
    xlo: f64,
    xhi: f64,
    ylo: f64,
    yhi: f64,
) -> (Vec<(f64, f64, f64)>, f64, f64) {
    let nx = gridsize.max(1);
    let ny = ((nx as f64 / 3.0_f64.sqrt()) as usize).max(1);
    let (xlo, xhi) = expand_if_singular(xlo, xhi);
    let (ylo, yhi) = expand_if_singular(ylo, yhi);
    let pad = 1e-9 * (xhi - xlo);
    let (xlo, xhi) = (xlo - pad, xhi + pad);
    let sx = (xhi - xlo) / nx as f64;
    let sy = (yhi - ylo) / ny as f64;
    let (nx1, ny1, nx2, ny2) = (nx + 1, ny + 1, nx, ny);
    let mut n1 = vec![0.0_f64; nx1 * ny1];
    let mut n2 = vec![0.0_f64; nx2 * ny2];
    for (&px, &py) in xs.iter().zip(ys.iter()) {
        if !(px.is_finite() && py.is_finite()) {
            continue;
        }
        let x = (px - xlo) / sx;
        let y = (py - ylo) / sy;
        let ix1 = x.round();
        let iy1 = y.round();
        let ix2 = x.floor();
        let iy2 = y.floor();
        let d1 = (x - ix1).powi(2) + 3.0 * (y - iy1).powi(2);
        let d2 = (x - ix2 - 0.5).powi(2) + 3.0 * (y - iy2 - 0.5).powi(2);
        if d1 <= d2 {
            if let (Some(ix), Some(iy)) = (in_grid(ix1, nx1), in_grid(iy1, ny1)) {
                n1[ix * ny1 + iy] += 1.0;
            }
        } else if let (Some(ix), Some(iy)) = (in_grid(ix2, nx2), in_grid(iy2, ny2)) {
            n2[ix * ny2 + iy] += 1.0;
        }
    }
    let mut out = Vec::with_capacity(nx1 * ny1 + nx2 * ny2);
    for iy in 0..ny1 {
        for ix in 0..nx1 {
            out.push((
                xlo + ix as f64 * sx,
                ylo + iy as f64 * sy,
                n1[ix * ny1 + iy],
            ));
        }
    }
    for iy in 0..ny2 {
        for ix in 0..nx2 {
            out.push((
                xlo + (ix as f64 + 0.5) * sx,
                ylo + (iy as f64 + 0.5) * sy,
                n2[ix * ny2 + iy],
            ));
        }
    }
    (out, sx, sy)
}

fn in_grid(v: f64, n: usize) -> Option<usize> {
    (v >= 0.0 && v < n as f64).then_some(v as usize)
}

fn expand_if_singular(lo: f64, hi: f64) -> (f64, f64) {
    let (lo, hi) = if hi < lo { (hi, lo) } else { (lo, hi) };
    if hi > lo {
        return (lo, hi);
    }
    if lo == 0.0 && hi == 0.0 {
        return (-0.1, 0.1);
    }
    (lo - 0.1 * lo.abs(), hi + 0.1 * hi.abs())
}

/// Where along `va..vb` the value crosses `level`.
fn iso_t(va: f64, vb: f64, level: f64) -> f64 {
    let d = vb - va;
    if d == 0.0 { 0.5 } else { (level - va) / d }
}

/// Stable ids for grid edges, shared by the two cells either side.
fn edge_h(r: usize, c: usize, w: usize) -> u64 {
    ((r * w + c) as u64) << 1
}

fn edge_v(r: usize, c: usize, w: usize) -> u64 {
    (((r * w + c) as u64) << 1) | 1
}

/// One marching-squares segment: the grid edges its ends lie on, and the
/// crossing points on them.
struct IsoSeg {
    ends: [u64; 2],
    pts: [(f64, f64); 2],
}

/// A contour polyline in grid coordinates: `(level index, closed, points)`.
pub type ContourLine = (u32, bool, Vec<(f64, f64)>);

/// Join marching-squares segments into polylines by the grid edges they share.
/// Open paths are walked from their free ends first, then closed loops.
fn stitch_polylines(segs: &[IsoSeg]) -> Vec<(bool, Vec<(f64, f64)>)> {
    const NONE: usize = usize::MAX;
    let mut adj: HashMap<u64, [usize; 2]> = HashMap::with_capacity(segs.len() * 2);
    for (i, s) in segs.iter().enumerate() {
        for &e in &s.ends {
            let slot = adj.entry(e).or_insert([NONE; 2]);
            if slot[0] == NONE {
                slot[0] = i;
            } else {
                slot[1] = i;
            }
        }
    }
    let at = |seg: usize, edge: u64| {
        let s = &segs[seg];
        if s.ends[0] == edge {
            s.pts[0]
        } else {
            s.pts[1]
        }
    };
    let walk = |start: u64, si: usize, used: &mut Vec<bool>| {
        let (mut edge, mut seg) = (start, si);
        let mut points = vec![at(seg, edge)];
        loop {
            used[seg] = true;
            let e = segs[seg].ends;
            edge = if e[0] == edge { e[1] } else { e[0] };
            if edge == start {
                return (true, points); // closed loop: back where we began
            }
            points.push(at(seg, edge));
            let n = adj[&edge];
            seg = match n.iter().find(|&&i| i != NONE && !used[i]) {
                Some(&next) => next,
                None => return (false, points),
            };
        }
    };
    let mut used = vec![false; segs.len()];
    let mut out = Vec::new();
    for (i, s) in segs.iter().enumerate() {
        if used[i] {
            continue;
        }
        if let Some(&end) = s.ends.iter().find(|e| adj[e][1] == NONE) {
            out.push(walk(end, i, &mut used));
        }
    }
    for (i, s) in segs.iter().enumerate() {
        if !used[i] {
            out.push(walk(s.ends[0], i, &mut used));
        }
    }
    out
}

/// Marching-squares iso-lines of a `w x h` row-major grid, one set per level.
pub fn contour_lines(
    values: &[f64],
    w: usize,
    h: usize,
    levels: &[f64],
) -> Result<Vec<ContourLine>> {
    check_grid(values.len(), w, h, "contour_lines")?;
    let mut out = Vec::new();
    if w < 2 || h < 2 {
        return Ok(out);
    }
    let mut segs: Vec<IsoSeg> = Vec::new();
    for (li, &level) in levels.iter().enumerate() {
        let li = li as u32;
        segs.clear();
        for r in 0..h - 1 {
            for c in 0..w - 1 {
                let a = values[r * w + c]; // A: (c,   r)
                let b = values[r * w + c + 1]; // B: (c+1, r)
                let cc = values[(r + 1) * w + c + 1]; // C: (c+1, r+1)
                let d = values[(r + 1) * w + c]; // D: (c,   r+1)
                if !(a.is_finite() && b.is_finite() && cc.is_finite() && d.is_finite()) {
                    continue;
                }
                let case = ((a >= level) as u8) << 3
                    | ((b >= level) as u8) << 2
                    | ((cc >= level) as u8) << 1
                    | (d >= level) as u8;
                if case == 0 || case == 15 {
                    continue;
                }
                let (fc, fr) = (c as f64, r as f64);
                let ab = (edge_h(r, c, w), (fc + iso_t(a, b, level), fr));
                let bc = (edge_v(r, c + 1, w), (fc + 1.0, fr + iso_t(b, cc, level)));
                let cd = (edge_h(r + 1, c, w), (fc + iso_t(d, cc, level), fr + 1.0));
                let da = (edge_v(r, c, w), (fc, fr + iso_t(a, d, level)));
                let mut seg = |p: (u64, (f64, f64)), q: (u64, (f64, f64))| {
                    segs.push(IsoSeg {
                        ends: [p.0, q.0],
                        pts: [p.1, q.1],
                    });
                };
                match case {
                    1 | 14 => seg(cd, da),
                    2 | 13 => seg(bc, cd),
                    3 | 12 => seg(bc, da),
                    4 | 11 => seg(ab, bc),
                    6 | 9 => seg(ab, cd),
                    7 | 8 => seg(ab, da),
                    5 | 10 => {
                        if ((a + b + cc + d) * 0.25 >= level) == (case == 10) {
                            seg(ab, bc);
                            seg(cd, da);
                        } else {
                            seg(da, ab);
                            seg(bc, cd);
                        }
                    }
                    _ => {}
                }
            }
        }
        out.extend(
            stitch_polylines(&segs)
                .into_iter()
                .map(|(closed, points)| (li, closed, points)),
        );
    }
    Ok(out)
}

/// Filled contours as an RGBA image, `upsample` pixels per grid cell, with each
/// band painted from `band_lut` (4 bytes per band).
pub fn contourf_image(
    values: &[f64],
    w: usize,
    h: usize,
    edges: &[f64],
    band_lut: &[u8],
    upsample: usize,
) -> Result<(Vec<u8>, usize, usize)> {
    check_grid(values.len(), w, h, "contourf_image")?;
    let up = upsample.max(1);
    if w < 2 || h < 2 || edges.len() < 2 {
        return Ok((Vec::new(), 0, 0));
    }
    let ow = (w - 1) * up + 1;
    let oh = (h - 1) * up + 1;
    check_alloc(
        ow as f64 * oh as f64 * 4.0,
        "contourf_image",
        &format!("{ow} x {oh} px"),
    )?;
    let nbands = edges.len() - 1;
    let pad = 1e-9 * (edges[nbands] - edges[0]).abs();
    let mut buf = vec![0u8; ow * oh * 4];
    for oy in 0..oh {
        let gy = (oh - 1 - oy) as f64 / up as f64;
        let r0 = gy.floor() as usize;
        let r1 = (r0 + 1).min(h - 1);
        let fy = gy - r0 as f64;
        for ox in 0..ow {
            let gx = ox as f64 / up as f64;
            let c0 = gx.floor() as usize;
            let c1 = (c0 + 1).min(w - 1);
            let fx = gx - c0 as f64;
            let v00 = values[r0 * w + c0];
            let v10 = values[r0 * w + c1];
            let v01 = values[r1 * w + c0];
            let v11 = values[r1 * w + c1];
            if !(v00.is_finite() && v10.is_finite() && v01.is_finite() && v11.is_finite()) {
                continue;
            }
            let top = v00 + (v10 - v00) * fx;
            let bot = v01 + (v11 - v01) * fx;
            let val = top + (bot - top) * fy;
            if val < edges[0] - pad || val > edges[nbands] + pad {
                continue;
            }
            let mut band = 0;
            while band + 1 < nbands && val >= edges[band + 1] {
                band += 1;
            }
            let li = band * 4;
            let o = (oy * ow + ox) * 4;
            buf[o] = band_lut[li];
            buf[o + 1] = band_lut[li + 1];
            buf[o + 2] = band_lut[li + 2];
            buf[o + 3] = band_lut[li + 3];
        }
    }
    Ok((buf, ow, oh))
}

#[cfg(test)]
mod tests {
    #[test]
    fn peak_looks_only_inside_the_range() {
        let xs = [0.0, 1.0, 2.0, 3.0];
        let ys = [5.0, 1.0, f64::NAN, 9.0];
        assert_eq!(super::peak(&xs, &ys, 0.5, 2.5), Some(1.0));
        assert_eq!(super::peak(&xs, &ys, 0.0, 3.0), Some(9.0));
        assert_eq!(super::peak(&xs, &ys, 10.0, 11.0), None);
    }
}
