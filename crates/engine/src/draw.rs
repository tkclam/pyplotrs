//! Batched drawing: turns columns of data coordinates into scene nodes in one
//! pass, so a mark with a million points costs one call, not a million.
//!
//! Every function takes a [`Transform`]; pass [`Transform::IDENTITY`] to draw
//! in device points. Non-finite coordinates are skipped (or, for polylines,
//! break the line).

use kurbo::{Affine, BezPath, Circle, Point, Rect, Shape};

use crate::geometry::{
    Transform, decimate_columns, marker_is_stroked, marker_path, polyline, simplify_polyline,
};
use crate::kernels::ColorMapper;
use crate::scene::{
    ClipPath, Color, FillRule, Group, ImageData, ImageNode, LineCap, LineJoin, MarkerNode, Node,
    PathNode, Scene, Stroke,
};

/// A scene under construction, with a stack of open groups.
pub struct SceneBuilder {
    scene: Scene,
    stack: Vec<Group>,
}

impl SceneBuilder {
    pub fn new(width: f64, height: f64) -> Self {
        Self {
            scene: Scene::new(kurbo::Size::new(width, height)),
            stack: Vec::new(),
        }
    }

    pub fn push(&mut self, node: impl Into<Node>) {
        match self.stack.last_mut() {
            Some(group) => group.children.push(node.into()),
            None => self.scene.push(node),
        }
    }

    /// Open a group: children are transformed by `transform`, clipped to
    /// `clip` (in the group's own coordinates) and composited at `opacity`.
    pub fn begin_group(&mut self, transform: Affine, clip: Option<ClipPath>, opacity: f32) {
        self.stack.push(Group {
            transform,
            clip,
            opacity,
            children: Vec::new(),
        });
    }

    pub fn end_group(&mut self) {
        if let Some(group) = self.stack.pop() {
            self.push(group);
        }
    }

    /// The finished scene. Groups left open are closed.
    pub fn scene(&self) -> Scene {
        let mut scene = self.scene.clone();
        let mut open: Vec<Group> = self.stack.clone();
        while let Some(group) = open.pop() {
            match open.last_mut() {
                Some(parent) => parent.children.push(group.into()),
                None => scene.push(group),
            }
        }
        scene
    }

    /// Borrow the scene directly when no groups are open (the common case for
    /// rendering), avoiding a copy.
    pub fn finished(&self) -> Option<&Scene> {
        self.stack.is_empty().then_some(&self.scene)
    }
}

/// A clip region: a rectangle or a circle.
pub fn clip_rect(x: f64, y: f64, w: f64, h: f64) -> ClipPath {
    ClipPath::rect(Rect::new(x, y, x + w, y + h))
}

pub fn clip_polygon(xs: &[f64], ys: &[f64]) -> ClipPath {
    let pts = xs.iter().zip(ys).map(|(&x, &y)| Point::new(x, y));
    ClipPath {
        geometry: polyline(pts, true),
        rule: FillRule::NonZero,
    }
}

pub fn clip_circle(cx: f64, cy: f64, r: f64) -> ClipPath {
    ClipPath {
        geometry: Circle::new(Point::new(cx, cy), r).to_path(0.05),
        rule: FillRule::NonZero,
    }
}

/// How a path is painted. Either part may be absent.
#[derive(Clone, Debug, Default)]
pub struct Paint {
    pub fill: Option<Color>,
    pub stroke: Option<Stroke>,
}

impl Paint {
    fn node(&self, geometry: BezPath) -> Node {
        Node::Path(PathNode {
            geometry,
            fill: self.fill,
            fill_rule: FillRule::NonZero,
            stroke: self.stroke.clone(),
        })
    }
}

/// Give an opaque, unstroked cell a hairline in its own color, so abutting
/// cells (a mesh, hexbin) show no background seam between them.
fn seal(p: &mut Paint) {
    if p.stroke.is_none() && p.fill.is_some_and(|c| c.a == 255) {
        p.stroke = p.fill.map(|c| Stroke {
            join: LineJoin::Round,
            ..Stroke::new(c, 0.5)
        });
    }
}

/// Per-element fill colors: flat RGBA bytes, four per element.
fn color_at(colors: &[u8], i: usize) -> Option<Color> {
    colors
        .get(i * 4..i * 4 + 4)
        .map(|c| Color::rgba(c[0], c[1], c[2], c[3]))
}

/// Column width, in points, for decimating dense lines: a quarter point is
/// finer than a pixel at 288 dpi.
const COLUMN: f64 = 0.25;

/// A polyline through `(xs[i], ys[i])`. Non-finite points split it into
/// separate runs. With `simplify`, vertices within that many device points of
/// a straight run are dropped.
pub fn polyline_path(
    xs: &[f64],
    ys: &[f64],
    tf: &Transform,
    close: bool,
    simplify: Option<f64>,
) -> BezPath {
    let mut geometry = BezPath::new();
    let mut run: Vec<Point> = Vec::new();
    let flush = |run: &mut Vec<Point>, geometry: &mut BezPath| {
        let pts = thin(run, simplify);
        run.clear();
        if pts.is_empty() {
            return;
        }
        geometry.extend(polyline(pts, close).elements().iter().copied());
    };
    for (&x, &y) in xs.iter().zip(ys) {
        match tf.point(x, y) {
            Some(p) => run.push(p),
            None => flush(&mut run, &mut geometry),
        }
    }
    flush(&mut run, &mut geometry);
    geometry
}

/// The vertices of `run` worth drawing: dense columns decimated and straight
/// stretches simplified to within `simplify` points.
fn thin(run: &[Point], simplify: Option<f64>) -> Vec<Point> {
    match simplify {
        Some(tol) if run.len() >= 3 => {
            let dense = decimate_columns(run, COLUMN);
            simplify_polyline(dense.as_deref().unwrap_or(run), tol)
        }
        _ => run.to_vec(),
    }
}

/// A polyline whose color follows `values` through `mapper`: each segment
/// takes the color of its midpoint value. Consecutive segments that land on
/// the same colormap entry are joined into one path, so a slowly varying
/// value costs a few paths, not one per segment. Non-finite points or values
/// leave gaps.
#[allow(clippy::too_many_arguments)]
pub fn colored_line(
    xs: &[f64],
    ys: &[f64],
    values: &[f64],
    tf: &Transform,
    mapper: &ColorMapper,
    lut: &[u8],
    stroke: &Stroke,
    simplify: Option<f64>,
) -> Vec<Node> {
    let mut nodes = Vec::new();
    let mut run: Vec<Point> = Vec::new();
    let mut entry = 0usize;
    let mut flush = |run: &mut Vec<Point>, entry: usize| {
        if run.len() >= 2 {
            let c = &lut[entry * 4..entry * 4 + 4];
            nodes.push(Node::Path(PathNode {
                geometry: polyline(thin(run, simplify), false),
                fill: None,
                fill_rule: FillRule::NonZero,
                stroke: Some(Stroke {
                    color: Color::rgba(c[0], c[1], c[2], c[3]),
                    ..stroke.clone()
                }),
            }));
        }
        run.clear();
    };
    let mut prev: Option<(Point, f64)> = None;
    for i in 0..xs.len().min(ys.len()).min(values.len()) {
        let here = tf.point(xs[i], ys[i]).map(|p| (p, values[i]));
        let segment = prev.zip(here).and_then(|((a, va), (b, vb))| {
            let t = mapper.position((va + vb) / 2.0)?;
            Some((a, b, ((t * 255.0).round() as usize).min(255)))
        });
        match segment {
            Some((a, b, k)) => {
                if run.is_empty() || k != entry {
                    flush(&mut run, entry);
                    run.push(a);
                    entry = k;
                }
                run.push(b);
            }
            None => flush(&mut run, entry),
        }
        prev = here;
    }
    flush(&mut run, entry);
    nodes
}

/// Independent straight segments from `(x0, y0)` to `(x1, y1)`, as one path.
pub fn segments_path(x0: &[f64], y0: &[f64], x1: &[f64], y1: &[f64], tf: &Transform) -> BezPath {
    let mut geometry = BezPath::new();
    for i in 0..x0.len().min(y0.len()).min(x1.len()).min(y1.len()) {
        if let (Some(a), Some(b)) = (tf.point(x0[i], y0[i]), tf.point(x1[i], y1[i])) {
            geometry.move_to(a);
            geometry.line_to(b);
        }
    }
    geometry
}

/// Axis-aligned rectangles spanning `x0..x1` by `y0..y1`, one node each so
/// overlapping translucent rectangles blend like separate shapes. `fills`
/// (flat RGBA, optional) overrides the paint's fill per rectangle.
#[allow(clippy::too_many_arguments)]
pub fn rects(
    out: &mut SceneBuilder,
    x0: &[f64],
    y0: &[f64],
    x1: &[f64],
    y1: &[f64],
    tf: &Transform,
    paint: &Paint,
    fills: &[u8],
) {
    let n = x0.len().min(y0.len()).min(x1.len()).min(y1.len());
    for i in 0..n {
        let (Some(a), Some(b)) = (tf.point(x0[i], y0[i]), tf.point(x1[i], y1[i])) else {
            continue;
        };
        let mut p = paint.clone();
        if !fills.is_empty() {
            p.fill = color_at(fills, i);
            seal(&mut p);
        }
        out.push(p.node(Rect::from_points(a, b).to_path(0.1)));
    }
}

/// Closed polygons, the `k`-th taking the next `counts[k]` vertices.
pub fn polygons(
    out: &mut SceneBuilder,
    xs: &[f64],
    ys: &[f64],
    counts: &[u32],
    tf: &Transform,
    paint: &Paint,
    fills: &[u8],
) {
    let mut start = 0usize;
    for (k, &count) in counts.iter().enumerate() {
        let end = (start + count as usize).min(xs.len()).min(ys.len());
        let pts: Vec<Point> = (start..end)
            .filter_map(|i| tf.point(xs[i], ys[i]))
            .collect();
        start = end;
        if pts.len() < 3 {
            continue;
        }
        let mut p = paint.clone();
        if !fills.is_empty() {
            p.fill = color_at(fills, k);
            seal(&mut p);
        }
        out.push(p.node(polyline(pts, true)));
    }
}

/// The region between `lo` and `hi` along `seq` (filled band). With `swap`,
/// `seq` runs along y and the band extends in x.
pub fn band_path(seq: &[f64], lo: &[f64], hi: &[f64], tf: &Transform, swap: bool) -> BezPath {
    let n = seq.len().min(lo.len()).min(hi.len());
    let at = |s: f64, v: f64| if swap { tf.point(v, s) } else { tf.point(s, v) };
    let front = (0..n).filter_map(|i| at(seq[i], lo[i]));
    let back = (0..n).rev().filter_map(|i| at(seq[i], hi[i]));
    let pts: Vec<Point> = front.chain(back).collect();
    if pts.len() < 3 {
        BezPath::new()
    } else {
        polyline(pts, true)
    }
}

/// A marker stamped at every point. `colors` (flat RGBA, optional) gives each
/// point its own fill.
#[allow(clippy::too_many_arguments)]
pub fn markers(
    xs: &[f64],
    ys: &[f64],
    tf: &Transform,
    marker: &str,
    diameter: f64,
    fill: Option<Color>,
    colors: &[u8],
    edge: Option<Stroke>,
) -> MarkerNode {
    let n = xs.len().min(ys.len());
    let shape = marker_path(marker, diameter / 2.0);
    let per_point = !colors.is_empty();
    let mut positions = Vec::with_capacity(n);
    let mut point_colors = Vec::with_capacity(if per_point { n } else { 0 });
    for i in 0..n {
        if let Some(p) = tf.point(xs[i], ys[i]) {
            if per_point {
                let Some(c) = color_at(colors, i) else { break };
                point_colors.push(c);
            }
            positions.push(p);
        }
    }
    if marker_is_stroked(marker) {
        let color = edge
            .as_ref()
            .map(|s| s.color)
            .or(fill)
            .unwrap_or(Color::BLACK);
        let width = edge.as_ref().map_or(1.0, |s| s.width).max(1.0);
        return MarkerNode {
            marker: shape,
            fill: None,
            fill_rule: FillRule::NonZero,
            stroke: Some(Stroke {
                cap: LineCap::Round,
                ..Stroke::new(color, width)
            }),
            positions,
            colors: None,
        };
    }
    MarkerNode {
        marker: shape,
        fill: if per_point {
            point_colors.first().copied()
        } else {
            fill
        },
        fill_rule: FillRule::NonZero,
        stroke: edge,
        positions,
        colors: per_point.then_some(point_colors),
    }
}

/// A `width x height` grid of values colormapped into an image placed at
/// `rect`. The normalized values travel with the pixels so a resampling
/// backend can average data rather than colors.
#[allow(clippy::too_many_arguments)]
pub fn colormapped_image(
    values: &[f64],
    width: usize,
    height: usize,
    mapper: &ColorMapper,
    lut: &[u8],
    origin_upper: bool,
    flip_x: bool,
    rect: Rect,
) -> ImageNode {
    let mut rgba = vec![0u8; width * height * 4];
    let mut plane = vec![f32::NAN; width * height];
    for row in 0..height {
        let src_row = if origin_upper { row } else { height - 1 - row };
        for col in 0..width {
            let src_col = if flip_x { width - 1 - col } else { col };
            let Some(&v) = values.get(src_row * width + src_col) else {
                continue;
            };
            if let Some(t) = mapper.position(v) {
                let o = row * width + col;
                plane[o] = t;
                let i = ((t * 255.0).round() as usize).min(255) * 4;
                rgba[o * 4..o * 4 + 4].copy_from_slice(&lut[i..i + 4]);
            }
        }
    }
    ImageNode::new(
        ImageData::from_rgba8(rgba, width as u32, height as u32).with_field(plane, lut.to_vec()),
        rect,
    )
}

/// An RGBA image placed at `rect`, optionally mirrored.
pub fn image(
    rgba: &[u8],
    width: usize,
    height: usize,
    flip_x: bool,
    flip_y: bool,
    rect: Rect,
) -> ImageNode {
    let mut buf = vec![0u8; width * height * 4];
    for row in 0..height {
        let src_row = if flip_y { height - 1 - row } else { row };
        for col in 0..width {
            let src_col = if flip_x { width - 1 - col } else { col };
            let (s, d) = ((src_row * width + src_col) * 4, (row * width + col) * 4);
            if let Some(px) = rgba.get(s..s + 4) {
                buf[d..d + 4].copy_from_slice(px);
            }
        }
    }
    ImageNode::new(
        ImageData::from_rgba8(buf, width as u32, height as u32),
        rect,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn nan_breaks_a_polyline_into_runs() {
        let xs = [0.0, 1.0, f64::NAN, 3.0, 4.0];
        let ys = [0.0, 1.0, 2.0, 3.0, 4.0];
        let path = polyline_path(&xs, &ys, &Transform::IDENTITY, false, None);
        let moves = path
            .elements()
            .iter()
            .filter(|e| matches!(e, kurbo::PathEl::MoveTo(_)))
            .count();
        assert_eq!(moves, 2);
    }

    #[test]
    fn colored_line_joins_runs_of_one_color() {
        let lut: Vec<u8> = (0..=255u8).flat_map(|i| [i, 0, 0, 255]).collect();
        let mapper = ColorMapper::new(&lut, crate::geometry::Scale::Linear, 0.0, 1.0);
        let xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0];
        let ys = [0.0; 6];
        // Two segments at 0, a NaN gap, then two segments at 1.
        let vs = [0.0, 0.0, 0.0, f64::NAN, 1.0, 1.0];
        let stroke = Stroke::new(Color::BLACK, 1.0);
        let nodes = colored_line(
            &xs,
            &ys,
            &vs,
            &Transform::IDENTITY,
            &mapper,
            &lut,
            &stroke,
            None,
        );
        let reds: Vec<u8> = nodes
            .iter()
            .map(|n| match n {
                Node::Path(p) => p.stroke.as_ref().unwrap().color.r,
                _ => panic!("expected a path"),
            })
            .collect();
        assert_eq!(reds, vec![0, 255]);
    }

    #[test]
    fn per_point_colors_follow_surviving_points() {
        let xs = [0.0, f64::NAN, 2.0];
        let ys = [0.0, 0.0, 0.0];
        let colors = [1, 1, 1, 255, 2, 2, 2, 255, 3, 3, 3, 255];
        let m = markers(
            &xs,
            &ys,
            &Transform::IDENTITY,
            "o",
            4.0,
            None,
            &colors,
            None,
        );
        let got: Vec<u8> = m.colors.unwrap().iter().map(|c| c.r).collect();
        assert_eq!(got, vec![1, 3]);
    }

    #[test]
    fn rects_skip_points_outside_log_domain() {
        let mut b = SceneBuilder::new(10.0, 10.0);
        let tf = Transform {
            yscale: crate::geometry::Scale::Log,
            ..Transform::IDENTITY
        };
        rects(
            &mut b,
            &[0.0, 1.0],
            &[0.0, 1.0],
            &[1.0, 2.0],
            &[1.0, 10.0],
            &tf,
            &Paint::default(),
            &[],
        );
        assert_eq!(b.finished().unwrap().nodes.len(), 1);
    }
}
