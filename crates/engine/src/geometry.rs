//! Data-to-device transforms, polyline simplification and marker shapes.

use kurbo::{BezPath, Circle, Point, Shape};

const LN10: f64 = std::f64::consts::LN_10;

/// An axis scale's forward transform. Values outside its domain (`x <= 0` on a
/// log axis) map to NaN, which every drawing routine treats as a gap.
///
/// Must stay numerically identical to `Scale.transform` in `scales.py`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Scale {
    Linear,
    Log,
    /// Symmetric log with its linear threshold.
    Symlog(f64),
    Logit,
}

impl Scale {
    /// Parse a scale code: `linear`, `log`, `logit`, `symlog` or
    /// `symlog:<threshold>`. Unknown codes are linear.
    pub fn parse(code: &str) -> Scale {
        match code {
            "log" => Scale::Log,
            "logit" => Scale::Logit,
            "symlog" => Scale::Symlog(1.0),
            _ => match code.split_once(':') {
                Some(("symlog", t)) => Scale::Symlog(
                    t.parse()
                        .ok()
                        .filter(|v: &f64| v.is_finite() && *v > 0.0)
                        .unwrap_or(1.0),
                ),
                _ => Scale::Linear,
            },
        }
    }

    #[inline]
    pub fn apply(self, v: f64) -> f64 {
        match self {
            Scale::Linear => v,
            Scale::Log => {
                if v > 0.0 {
                    v.log10()
                } else {
                    f64::NAN
                }
            }
            Scale::Symlog(t) => {
                // One decade of the linear region spans as much as one log decade.
                let adj = 1.0 / (1.0 - 1.0 / 10.0);
                let a = v.abs();
                if a <= t {
                    v * adj
                } else {
                    v.signum() * t * (adj + (a / t).ln() / LN10)
                }
            }
            Scale::Logit => {
                if v > 0.0 && v < 1.0 {
                    (v / (1.0 - v)).log10()
                } else {
                    f64::NAN
                }
            }
        }
    }
}

/// Maps data coordinates to device points: each axis is scaled, then mapped
/// affinely (`device = a * scale(v) + b`).
#[derive(Debug, Clone, Copy)]
pub struct Transform {
    pub ax: f64,
    pub bx: f64,
    pub ay: f64,
    pub by: f64,
    pub xscale: Scale,
    pub yscale: Scale,
}

impl Transform {
    pub const IDENTITY: Transform = Transform {
        ax: 1.0,
        bx: 0.0,
        ay: 1.0,
        by: 0.0,
        xscale: Scale::Linear,
        yscale: Scale::Linear,
    };

    #[inline]
    pub fn x(&self, x: f64) -> f64 {
        self.ax * self.xscale.apply(x) + self.bx
    }

    #[inline]
    pub fn y(&self, y: f64) -> f64 {
        self.ay * self.yscale.apply(y) + self.by
    }

    /// The device point for `(x, y)`, or `None` if it falls outside a scale's
    /// domain or is not finite.
    #[inline]
    pub fn point(&self, x: f64, y: f64) -> Option<Point> {
        let p = Point::new(self.x(x), self.y(y));
        (p.x.is_finite() && p.y.is_finite()).then_some(p)
    }
}

/// Drop vertices that lie within `tol` device points of the line through their
/// neighbors (matplotlib's `path.simplify`). Endpoints are kept exactly.
///
/// Each point's deviation is measured against the direction the current run
/// started in; the run is cut once the spread to either side exceeds `tol`, or
/// the path doubles back.
pub fn simplify_polyline(pts: &[Point], tol: f64) -> Vec<Point> {
    if pts.len() < 3 || tol <= 0.0 {
        return pts.to_vec();
    }
    let tol2 = tol * tol;
    let mut out = Vec::with_capacity(pts.len() / 2 + 2);
    out.push(pts[0]);

    let mut anchor = pts[0];
    let mut have_dir = false;
    let (mut rdx, mut rdy, mut rnorm2) = (0.0, 0.0, 0.0);
    let (mut dmax, mut dmin) = (0.0_f64, 0.0_f64);
    let mut cand = pts[0];

    for &p in &pts[1..] {
        let (dx, dy) = (p.x - anchor.x, p.y - anchor.y);
        if !have_dir {
            let n2 = dx * dx + dy * dy;
            if n2 > tol2 {
                (rdx, rdy, rnorm2, have_dir) = (dx, dy, n2, true);
            }
            cand = p;
            continue;
        }
        let along = rdx * dx + rdy * dy;
        let perp2 = (dx * dx + dy * dy - along * along / rnorm2).max(0.0);
        if rdx * dy - rdy * dx >= 0.0 {
            dmax = dmax.max(perp2);
        } else {
            dmin = dmin.max(perp2);
        }
        if dmax.sqrt() + dmin.sqrt() > tol || along < 0.0 {
            out.push(cand);
            anchor = cand;
            dmax = 0.0;
            dmin = 0.0;
            let (ndx, ndy) = (p.x - anchor.x, p.y - anchor.y);
            let n2 = ndx * ndx + ndy * ndy;
            have_dir = n2 > tol2;
            if have_dir {
                (rdx, rdy, rnorm2) = (ndx, ndy, n2);
            }
        }
        cand = p;
    }
    let last = pts[pts.len() - 1];
    if *out.last().unwrap() != last {
        out.push(last);
    }
    out
}

/// Reduce a dense polyline whose x only increases (or only decreases) to the
/// first, lowest, highest and last point of every `bucket`-wide column (M4
/// decimation). The drawn line is visually unchanged at that resolution.
/// Returns `None` when x is not monotonic or there is nothing to gain.
pub fn decimate_columns(pts: &[Point], bucket: f64) -> Option<Vec<Point>> {
    let (first, last) = (pts.first()?.x, pts.last()?.x);
    let columns = ((last - first).abs() / bucket).ceil();
    if !(columns.is_finite() && (pts.len() as f64) > 8.0 * (columns + 1.0)) {
        return None;
    }
    let dir = if last >= first { 1.0 } else { -1.0 };
    let mut out = Vec::with_capacity(4 * columns as usize + 4);
    let mut i = 0;
    while i < pts.len() {
        let col = ((pts[i].x - first) * dir / bucket).floor();
        let start = i;
        let (mut lo, mut hi) = (i, i);
        while i < pts.len() && ((pts[i].x - first) * dir / bucket).floor() == col {
            if i > start && (pts[i].x - pts[i - 1].x) * dir < 0.0 {
                return None; // x went backwards
            }
            if pts[i].y < pts[lo].y {
                lo = i;
            }
            if pts[i].y > pts[hi].y {
                hi = i;
            }
            i += 1;
        }
        if i < pts.len() && (pts[i].x - pts[i - 1].x) * dir < 0.0 {
            return None;
        }
        let end = i - 1;
        let (a, b) = if lo < hi { (lo, hi) } else { (hi, lo) };
        for k in [start, a, b, end] {
            if out.last() != Some(&pts[k]) {
                out.push(pts[k]);
            }
        }
    }
    Some(out)
}

/// Marker names understood by [`marker_path`].
pub const MARKERS: &[&str] = &["o", "s", "^", "v", "D", "+", "x", "|", "_"];

/// Markers drawn as strokes only (they have no area to fill).
pub fn marker_is_stroked(marker: &str) -> bool {
    matches!(marker, "+" | "x" | "|" | "_")
}

/// A marker outline of radius `r` centered on the origin.
pub fn marker_path(marker: &str, r: f64) -> BezPath {
    let mut p = BezPath::new();
    let poly = |p: &mut BezPath, pts: &[(f64, f64)]| {
        p.move_to(pts[0]);
        for &q in &pts[1..] {
            p.line_to(q);
        }
        p.close_path();
    };
    match marker {
        "s" => poly(&mut p, &[(-r, -r), (r, -r), (r, r), (-r, r)]),
        "^" => poly(
            &mut p,
            &[(0.0, -r), (0.95 * r, 0.8 * r), (-0.95 * r, 0.8 * r)],
        ),
        "v" => poly(
            &mut p,
            &[(0.0, r), (-0.95 * r, -0.8 * r), (0.95 * r, -0.8 * r)],
        ),
        "D" => poly(
            &mut p,
            &[(0.0, -r), (0.8 * r, 0.0), (0.0, r), (-0.8 * r, 0.0)],
        ),
        "+" => {
            p.move_to((-r, 0.0));
            p.line_to((r, 0.0));
            p.move_to((0.0, -r));
            p.line_to((0.0, r));
        }
        "x" => {
            p.move_to((-r, -r));
            p.line_to((r, r));
            p.move_to((-r, r));
            p.line_to((r, -r));
        }
        "|" => {
            p.move_to((0.0, -r));
            p.line_to((0.0, r));
        }
        "_" => {
            p.move_to((-r, 0.0));
            p.line_to((r, 0.0));
        }
        _ => p.extend(Circle::new(Point::ORIGIN, r).path_elements(0.2)),
    }
    p
}

/// A polyline (closed if `close`) through `pts`.
pub fn polyline(pts: impl IntoIterator<Item = Point>, close: bool) -> BezPath {
    let mut p = BezPath::new();
    let mut it = pts.into_iter();
    if let Some(first) = it.next() {
        p.move_to(first);
        for q in it {
            p.line_to(q);
        }
        if close {
            p.close_path();
        }
    }
    p
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collinear_points_collapse_to_endpoints() {
        let pts: Vec<Point> = (0..100)
            .map(|i| Point::new(i as f64, 2.0 * i as f64))
            .collect();
        assert_eq!(simplify_polyline(&pts, 0.1), vec![pts[0], pts[99]]);
    }

    #[test]
    fn column_decimation_keeps_the_envelope() {
        let pts: Vec<Point> = (0..10_000)
            .map(|i| Point::new(i as f64 * 0.001, if i % 2 == 0 { 0.0 } else { 1.0 }))
            .collect();
        let out = decimate_columns(&pts, 0.25).unwrap();
        assert!(out.len() < 200);
        assert_eq!(out.first(), pts.first());
        assert_eq!(out.last(), pts.last());
        assert!(out.iter().any(|p| p.y == 1.0) && out.iter().any(|p| p.y == 0.0));
        let back: Vec<Point> = pts.iter().rev().copied().collect();
        assert!(decimate_columns(&back, 0.25).is_some());
        let mut zigzag = pts.clone();
        zigzag.swap(10, 5000);
        assert!(decimate_columns(&zigzag, 0.25).is_none());
    }

    #[test]
    fn corners_survive_simplification() {
        let pts = [
            Point::new(0.0, 0.0),
            Point::new(10.0, 0.0),
            Point::new(10.0, 10.0),
        ];
        assert_eq!(simplify_polyline(&pts, 0.1).len(), 3);
    }

    #[test]
    fn scales_map_out_of_domain_values_to_nan() {
        assert!(Scale::Log.apply(0.0).is_nan());
        assert!(Scale::Logit.apply(1.0).is_nan());
        assert_eq!(Scale::Log.apply(100.0), 2.0);
        assert_eq!(Scale::parse("symlog:0.5"), Scale::Symlog(0.5));
    }

    #[test]
    fn symlog_is_odd_and_continuous_at_threshold() {
        let s = Scale::Symlog(1.0);
        assert_eq!(s.apply(-3.0), -s.apply(3.0));
        assert!((s.apply(1.0 - 1e-9) - s.apply(1.0 + 1e-9)).abs() < 1e-6);
    }
}
