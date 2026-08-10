//! pyplotrs-3d: the orthographic camera and the batch vertex projection behind
//! [`pyplotrs_py`]'s 3D axes.
//!
//! 3D in pyplotrs is a *projection layer*, not a second renderer: an
//! orthographic camera turns 3D primitives into ordinary 2D paths, which then
//! flow through the same Scene IR and the same PDF/SVG/raster backends as
//! everything else. From a backend's point of view a 3D axes is
//! indistinguishable from a 2D one.
//!
//! The camera math is small; what matters is that it runs **per vertex**. Doing
//! it in Python cost a `Camera3D.view` call, three `dot` calls and a device-map
//! call for every point of every surface, line and scatter, which was about a
//! quarter of a 3D save and grew with vertex count. [`project_batch`] does the
//! whole array in one pass here instead.

/// A 3D point.
pub type Vec3 = (f64, f64, f64);

fn dot(a: Vec3, b: Vec3) -> f64 {
    a.0 * b.0 + a.1 * b.1 + a.2 * b.2
}

fn cross(a: Vec3, b: Vec3) -> Vec3 {
    (
        a.1 * b.2 - a.2 * b.1,
        a.2 * b.0 - a.0 * b.2,
        a.0 * b.1 - a.1 * b.0,
    )
}

fn normalize(v: Vec3) -> Vec3 {
    let n = (v.0 * v.0 + v.1 * v.1 + v.2 * v.2).sqrt();
    if n < 1e-12 {
        (0.0, 0.0, 0.0)
    } else {
        (v.0 / n, v.1 / n, v.2 / n)
    }
}

/// An orthographic camera looking at the origin from `(elev, azim)` degrees,
/// matching matplotlib's mplot3d angle convention.
///
/// `elev` is the angle above the x-y plane, `azim` the rotation about the
/// vertical (z) axis. The basis is orthonormal, so projecting is three dot
/// products and no division.
#[derive(Debug, Clone, Copy)]
pub struct Camera3D {
    pub right: Vec3,
    pub up: Vec3,
    pub dir: Vec3,
}

impl Camera3D {
    pub fn new(elev: f64, azim: f64) -> Self {
        let e = elev.to_radians();
        let a = azim.to_radians();
        // Unit vector from the origin toward the camera.
        let dir = normalize((e.cos() * a.cos(), e.cos() * a.sin(), e.sin()));
        let world_up: Vec3 = (0.0, 0.0, 1.0);
        let mut right = cross(world_up, dir);
        if right.0 * right.0 + right.1 * right.1 + right.2 * right.2 < 1e-12 {
            // Looking straight down or up: any perpendicular will do.
            right = (1.0, 0.0, 0.0);
        }
        let right = normalize(right);
        let up = cross(dir, right); // already unit: orthonormal basis
        Self { right, up, dir }
    }

    /// Project a world point to `(screen_x, screen_y, depth)`. Larger `depth`
    /// is nearer the camera, so back-to-front order is ascending depth.
    #[inline]
    pub fn view(&self, p: Vec3) -> (f64, f64, f64) {
        (dot(p, self.right), dot(p, self.up), dot(p, self.dir))
    }
}

/// How data coordinates become the normalized `[-0.5, 0.5]^3` cube the camera
/// looks at, and how the projected cube maps onto the device plot rect.
#[derive(Debug, Clone, Copy)]
pub struct Frame {
    pub xmin: f64,
    pub xspan: f64,
    pub ymin: f64,
    pub yspan: f64,
    pub zmin: f64,
    pub zspan: f64,
    /// Device centre of the plot rect.
    pub ccx: f64,
    pub ccy: f64,
    /// Centre of the projected cube's screen bbox.
    pub scx: f64,
    pub scy: f64,
    /// Screen-to-device scale (already includes the cube fill factor).
    pub scale: f64,
}

impl Frame {
    /// Normalize one data point into the unit cube.
    #[inline]
    pub fn normalize_point(&self, x: f64, y: f64, z: f64) -> Vec3 {
        (
            (x - self.xmin) / self.xspan - 0.5,
            (y - self.ymin) / self.yspan - 0.5,
            (z - self.zmin) / self.zspan - 0.5,
        )
    }

    /// Map a projected screen point onto the device rect. Device y runs
    /// downward, hence the sign flip.
    #[inline]
    pub fn to_device(&self, sx: f64, sy: f64) -> (f64, f64) {
        (
            self.ccx + (sx - self.scx) * self.scale,
            self.ccy - (sy - self.scy) * self.scale,
        )
    }
}

/// Project `n` data-space vertices to device space in one pass.
///
/// Returns `(device_x, device_y, depth)`, each of length `n`. `depth` is in
/// eye space and is only ever compared, never drawn, so it stays unscaled.
pub fn project_batch(
    xs: &[f64],
    ys: &[f64],
    zs: &[f64],
    cam: &Camera3D,
    frame: &Frame,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let n = xs.len().min(ys.len()).min(zs.len());
    let mut dx = Vec::with_capacity(n);
    let mut dy = Vec::with_capacity(n);
    let mut dz = Vec::with_capacity(n);
    for i in 0..n {
        let p = frame.normalize_point(xs[i], ys[i], zs[i]);
        let (sx, sy, depth) = cam.view(p);
        let (px, py) = frame.to_device(sx, sy);
        dx.push(px);
        dy.push(py);
        dz.push(depth);
    }
    (dx, dy, dz)
}

/// Project vertices that are **already normalized** into the unit cube (the
/// axis chrome: panes, gridlines, tick anchors).
pub fn project_normalized(
    pts: &[Vec3],
    cam: &Camera3D,
    frame: &Frame,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let mut dx = Vec::with_capacity(pts.len());
    let mut dy = Vec::with_capacity(pts.len());
    let mut dz = Vec::with_capacity(pts.len());
    for p in pts {
        let (sx, sy, depth) = cam.view(*p);
        let (px, py) = frame.to_device(sx, sy);
        dx.push(px);
        dy.push(py);
        dz.push(depth);
    }
    (dx, dy, dz)
}

/// The 8 corners of the normalized unit cube, used to fit the projection into
/// the plot rect before anything is drawn.
pub const CUBE_CORNERS: [Vec3; 8] = [
    (-0.5, -0.5, -0.5),
    (-0.5, -0.5, 0.5),
    (-0.5, 0.5, -0.5),
    (-0.5, 0.5, 0.5),
    (0.5, -0.5, -0.5),
    (0.5, -0.5, 0.5),
    (0.5, 0.5, -0.5),
    (0.5, 0.5, 0.5),
];

/// The projected screen bbox of the unit cube: `(min_x, max_x, min_y, max_y)`.
/// The Python side needs this to compute `Frame::scale` before it can build a
/// `Frame`, so it is exposed separately from the projection itself.
pub fn cube_screen_bbox(cam: &Camera3D) -> (f64, f64, f64, f64) {
    let mut min_x = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut min_y = f64::INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    for c in CUBE_CORNERS {
        let (sx, sy, _) = cam.view(c);
        min_x = min_x.min(sx);
        max_x = max_x.max(sx);
        min_y = min_y.min(sy);
        max_y = max_y.max(sy);
    }
    (min_x, max_x, min_y, max_y)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn approx(a: f64, b: f64) {
        assert!((a - b).abs() < 1e-9, "{a} != {b}");
    }

    #[test]
    fn basis_is_orthonormal() {
        for (elev, azim) in [(30.0, -60.0), (0.0, 0.0), (89.0, 137.0), (-45.0, 200.0)] {
            let c = Camera3D::new(elev, azim);
            approx(dot(c.right, c.right), 1.0);
            approx(dot(c.up, c.up), 1.0);
            approx(dot(c.dir, c.dir), 1.0);
            approx(dot(c.right, c.up), 0.0);
            approx(dot(c.right, c.dir), 0.0);
            approx(dot(c.up, c.dir), 0.0);
        }
    }

    #[test]
    fn looking_straight_down_still_has_a_basis() {
        let c = Camera3D::new(90.0, 0.0);
        approx(dot(c.right, c.right), 1.0);
        approx(dot(c.up, c.up), 1.0);
    }

    #[test]
    fn depth_increases_toward_the_camera() {
        let c = Camera3D::new(0.0, 0.0); // camera on +x
        let near = c.view((1.0, 0.0, 0.0)).2;
        let far = c.view((-1.0, 0.0, 0.0)).2;
        assert!(near > far, "{near} should exceed {far}");
    }

    #[test]
    fn normalize_maps_the_data_box_onto_the_unit_cube() {
        let f = Frame {
            xmin: 10.0,
            xspan: 20.0,
            ymin: 0.0,
            yspan: 4.0,
            zmin: -1.0,
            zspan: 2.0,
            ccx: 0.0,
            ccy: 0.0,
            scx: 0.0,
            scy: 0.0,
            scale: 1.0,
        };
        approx(f.normalize_point(10.0, 0.0, -1.0).0, -0.5);
        approx(f.normalize_point(30.0, 4.0, 1.0).0, 0.5);
        approx(f.normalize_point(20.0, 2.0, 0.0).1, 0.0);
    }

    #[test]
    fn device_y_runs_downward() {
        let f = Frame {
            xmin: 0.0,
            xspan: 1.0,
            ymin: 0.0,
            yspan: 1.0,
            zmin: 0.0,
            zspan: 1.0,
            ccx: 100.0,
            ccy: 100.0,
            scx: 0.0,
            scy: 0.0,
            scale: 2.0,
        };
        let (_, up_y) = f.to_device(0.0, 1.0);
        let (_, down_y) = f.to_device(0.0, -1.0);
        assert!(up_y < down_y, "screen +y must map to a smaller device y");
    }

    #[test]
    fn batch_matches_point_by_point() {
        let cam = Camera3D::new(30.0, -60.0);
        let frame = Frame {
            xmin: 0.0,
            xspan: 2.0,
            ymin: 0.0,
            yspan: 2.0,
            zmin: 0.0,
            zspan: 2.0,
            ccx: 50.0,
            ccy: 40.0,
            scx: 0.1,
            scy: 0.2,
            scale: 30.0,
        };
        let xs = [0.0, 1.0, 2.0];
        let ys = [2.0, 1.0, 0.0];
        let zs = [1.0, 0.0, 2.0];
        let (dx, dy, dz) = project_batch(&xs, &ys, &zs, &cam, &frame);
        for i in 0..3 {
            let p = frame.normalize_point(xs[i], ys[i], zs[i]);
            let (sx, sy, d) = cam.view(p);
            let (ex, ey) = frame.to_device(sx, sy);
            approx(dx[i], ex);
            approx(dy[i], ey);
            approx(dz[i], d);
        }
    }

    #[test]
    fn cube_bbox_is_symmetric_about_the_origin() {
        let cam = Camera3D::new(30.0, -60.0);
        let (min_x, max_x, min_y, max_y) = cube_screen_bbox(&cam);
        approx(min_x, -max_x);
        approx(min_y, -max_y);
    }
}
