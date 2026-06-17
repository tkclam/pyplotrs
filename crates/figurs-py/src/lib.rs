//! figurs-py: PyO3 bindings exposing the figurs Rust core as `_figurs_core`.
//!
//! This crate is a thin shell over the Rust core. It exposes:
//!
//! - a stateful [`Scene`] builder (paths / text / images / transform+clip
//!   groups) that the Python layer drives to construct a `figurs_core::Scene`,
//!   then renders via the three backend crates;
//! - [`nice_ticks`] and [`solve_layout`], so axis ticking and the single-pass
//!   figure layout (both in `figurs-layout`) are the one source of truth,
//!   shared by the Python API rather than reimplemented there.

use std::sync::OnceLock;

use figurs_core::kurbo::{Affine, BezPath, Circle, Point, Rect as KRect, Shape, Size};
use figurs_core::{
    ClipPath, Color, FillRule, FontData, Group, ImageData, ImageNode, LineCap, LineJoin,
    MarkerNode, Node, PathNode, Scene as CoreScene, Stroke as CoreStroke, TextNode,
};
use figurs_layout::solve::{AxesBands, FigureSpec};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// The bundled body font (Inter Regular, SIL OFL), shared by shaping,
/// measurement, and PDF embedding so layout and rendering never drift apart.
fn body_font() -> &'static FontData {
    static FONT: OnceLock<FontData> = OnceLock::new();
    FONT.get_or_init(|| {
        let bytes: &[u8] = include_bytes!("../../../assets/fonts/Inter-Regular.ttf");
        FontData::from_bytes(bytes.to_vec(), 0)
    })
}

/// The bundled math font (STIX Two Math, SIL OFL): full coverage of Greek,
/// operators, radicals and the Mathematical Alphanumeric Symbols block, used
/// for `$...$` spans by the `mathtext` layer.
fn math_font() -> &'static FontData {
    static FONT: OnceLock<FontData> = OnceLock::new();
    FONT.get_or_init(|| {
        let bytes: &[u8] = include_bytes!("../../../assets/fonts/STIXTwoMath-Regular.ttf");
        FontData::from_bytes(bytes.to_vec(), 0)
    })
}

/// Resolve a font selector string (`"body"` / `"math"`) to bundled font data.
/// Unknown selectors fall back to the body font.
fn font_for_kind(kind: &str) -> &'static FontData {
    match kind {
        "math" => math_font(),
        _ => body_font(),
    }
}

fn color_from_rgba(rgba: (u8, u8, u8, u8)) -> Color {
    Color::rgba(rgba.0, rgba.1, rgba.2, rgba.3)
}

fn parse_cap(s: &str) -> LineCap {
    match s {
        "round" => LineCap::Round,
        "square" => LineCap::Square,
        _ => LineCap::Butt,
    }
}

fn parse_join(s: &str) -> LineJoin {
    match s {
        "miter" => LineJoin::Miter,
        "bevel" => LineJoin::Bevel,
        _ => LineJoin::Round,
    }
}

fn parse_fill_rule(s: &str) -> FillRule {
    match s {
        "evenodd" => FillRule::EvenOdd,
        _ => FillRule::NonZero,
    }
}

/// Collapse runs of near-collinear vertices in a device-space polyline
/// (matplotlib's `path.simplify`). Within a run, each point's perpendicular
/// deviation is measured against the run's *initial* direction; the run is cut
/// as soon as the signed spread (max deviation either side of that direction)
/// exceeds `tol` device points, or the path doubles back. Dropped points lie
/// within ~`tol` of the retained polyline, so the stroke is visually identical
/// while the vertex count - and thus PDF/SVG size and draw time - falls sharply
/// on smooth or axis-aligned data. Endpoints are always preserved exactly.
fn simplify_polyline(pts: &[Point], tol: f64) -> Vec<Point> {
    if pts.len() < 3 || tol <= 0.0 {
        return pts.to_vec();
    }
    let tol2 = tol * tol;
    let mut out: Vec<Point> = Vec::with_capacity(pts.len() / 2 + 2);
    out.push(pts[0]);

    let mut anchor = pts[0];
    let mut have_ref = false; // a reference direction has been established
    let (mut rdx, mut rdy, mut rnorm2) = (0.0_f64, 0.0_f64, 0.0_f64);
    let mut dmax = 0.0_f64; // largest +side perpendicular distance^2 seen
    let mut dmin = 0.0_f64; // largest -side perpendicular distance^2 seen
    let mut cand = pts[0]; // last point that still fit the current run

    for &p in &pts[1..] {
        let dx = p.x - anchor.x;
        let dy = p.y - anchor.y;
        if !have_ref {
            let n2 = dx * dx + dy * dy;
            if n2 <= tol2 {
                // Within tol of the anchor: hold as candidate, no direction yet.
                cand = p;
                continue;
            }
            rdx = dx;
            rdy = dy;
            rnorm2 = n2;
            have_ref = true;
            cand = p;
            continue;
        }
        let totdot = rdx * dx + rdy * dy;
        let perp2 = (dx * dx + dy * dy - totdot * totdot / rnorm2).max(0.0);
        if rdx * dy - rdy * dx >= 0.0 {
            dmax = dmax.max(perp2);
        } else {
            dmin = dmin.max(perp2);
        }
        if dmax.sqrt() + dmin.sqrt() > tol || totdot < 0.0 {
            // Run can no longer be one segment: emit it, restart from `cand`.
            out.push(cand);
            anchor = cand;
            dmax = 0.0;
            dmin = 0.0;
            let ndx = p.x - anchor.x;
            let ndy = p.y - anchor.y;
            let n2 = ndx * ndx + ndy * ndy;
            have_ref = n2 > tol2;
            if have_ref {
                rdx = ndx;
                rdy = ndy;
                rnorm2 = n2;
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

/// Append one marker of radius `r` centered at `(cx, cy)` to `path`. Filled
/// shapes are closed subpaths; `+`/`x` are open stroked subpaths.
fn append_marker(path: &mut BezPath, marker: &str, cx: f64, cy: f64, r: f64) {
    match marker {
        "s" => {
            path.move_to((cx - r, cy - r));
            path.line_to((cx + r, cy - r));
            path.line_to((cx + r, cy + r));
            path.line_to((cx - r, cy + r));
            path.close_path();
        }
        "^" => {
            let s = r * 0.95;
            path.move_to((cx, cy - r));
            path.line_to((cx + s, cy + r * 0.8));
            path.line_to((cx - s, cy + r * 0.8));
            path.close_path();
        }
        "v" => {
            let s = r * 0.95;
            path.move_to((cx, cy + r));
            path.line_to((cx - s, cy - r * 0.8));
            path.line_to((cx + s, cy - r * 0.8));
            path.close_path();
        }
        "D" => {
            path.move_to((cx, cy - r));
            path.line_to((cx + r * 0.8, cy));
            path.line_to((cx, cy + r));
            path.line_to((cx - r * 0.8, cy));
            path.close_path();
        }
        "+" => {
            path.move_to((cx - r, cy));
            path.line_to((cx + r, cy));
            path.move_to((cx, cy - r));
            path.line_to((cx, cy + r));
        }
        "x" => {
            path.move_to((cx - r, cy - r));
            path.line_to((cx + r, cy + r));
            path.move_to((cx - r, cy + r));
            path.line_to((cx + r, cy - r));
        }
        _ => {
            // "o" and unknown -> exact Bezier circle.
            path.extend(Circle::new(Point::new(cx, cy), r).path_elements(0.2));
        }
    }
}

/// A scene under construction.
///
/// Drawing calls append to the *current group* if one is open (see
/// [`Scene::begin_group`] / [`Scene::end_group`]), else to the scene root.
#[pyclass]
struct Scene {
    inner: CoreScene,
    /// Stack of groups currently being built (innermost last).
    stack: Vec<Group>,
}

impl Scene {
    /// Append a node to the innermost open group, or the root if none.
    fn push_node(&mut self, node: Node) {
        match self.stack.last_mut() {
            Some(group) => group.children.push(node),
            None => self.inner.push(node),
        }
    }
}

#[pymethods]
impl Scene {
    /// Create a new scene of the given size, in points (1/72 inch).
    #[new]
    fn new(width: f64, height: f64) -> Self {
        Self {
            inner: CoreScene::new(Size::new(width, height)),
            stack: Vec::new(),
        }
    }

    /// Add a (poly)line path. `points` is a list of `(x, y)` tuples in the
    /// current local coordinate space (points, y-down, origin top-left).
    #[pyo3(signature = (
        points,
        stroke_color=None,
        stroke_width=1.0,
        fill_color=None,
        close=false,
        dash=None,
        cap="butt",
        join="round",
        fill_rule="nonzero",
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_path(
        &mut self,
        points: Vec<(f64, f64)>,
        stroke_color: Option<(u8, u8, u8, u8)>,
        stroke_width: f64,
        fill_color: Option<(u8, u8, u8, u8)>,
        close: bool,
        dash: Option<Vec<f32>>,
        cap: &str,
        join: &str,
        fill_rule: &str,
    ) {
        let mut geometry = BezPath::new();
        let mut iter = points.into_iter();
        if let Some((x, y)) = iter.next() {
            geometry.move_to(Point::new(x, y));
            for (x, y) in iter {
                geometry.line_to(Point::new(x, y));
            }
            if close {
                geometry.close_path();
            }
        }

        self.push_node(Node::Path(PathNode {
            geometry,
            fill: fill_color.map(color_from_rgba),
            fill_rule: parse_fill_rule(fill_rule),
            stroke: stroke_color.map(|c| CoreStroke {
                color: color_from_rgba(c),
                width: stroke_width,
                cap: parse_cap(cap),
                join: parse_join(join),
                dash: dash.filter(|d| d.len() >= 2),
            }),
        }));
    }

    /// Fast path: add a polyline straight from raw data arrays, mapping each
    /// point through the linear data->device transform
    /// `(dx, dy) = (ax·x + bx, ay·y + by)` **in Rust**. This avoids building a
    /// Python list of `(x, y)` tuples and doing per-point arithmetic in Python,
    /// which is the bottleneck for large (1e5-1e6 point) line plots.
    #[pyo3(signature = (
        xs, ys, ax, bx, ay, by,
        stroke_color, stroke_width=1.0, dash=None, cap="round", join="round",
        simplify=true, simplify_threshold=0.1,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_line_xform(
        &mut self,
        xs: Vec<f64>,
        ys: Vec<f64>,
        ax: f64,
        bx: f64,
        ay: f64,
        by: f64,
        stroke_color: (u8, u8, u8, u8),
        stroke_width: f64,
        dash: Option<Vec<f32>>,
        cap: &str,
        join: &str,
        simplify: bool,
        simplify_threshold: f64,
    ) {
        let n = xs.len().min(ys.len());
        let mut pts: Vec<Point> = (0..n)
            .map(|i| Point::new(ax * xs[i] + bx, ay * ys[i] + by))
            .collect();
        if simplify && pts.len() >= 3 {
            pts = simplify_polyline(&pts, simplify_threshold);
        }
        let mut geometry = BezPath::new();
        if let Some((first, rest)) = pts.split_first() {
            geometry.move_to(*first);
            for p in rest {
                geometry.line_to(*p);
            }
        }
        self.push_node(Node::Path(PathNode {
            geometry,
            fill: None,
            fill_rule: FillRule::NonZero,
            stroke: Some(CoreStroke {
                color: color_from_rgba(stroke_color),
                width: stroke_width,
                cap: parse_cap(cap),
                join: parse_join(join),
                dash: dash.filter(|d| d.len() >= 2),
            }),
        }));
    }

    /// Fast path: add many identical markers from raw data arrays, mapped
    /// through the linear data->device transform in Rust and emitted as one
    /// `PathNode` (a single fill, or a single stroke for `+`/`x`).
    #[pyo3(signature = (
        xs, ys, ax, bx, ay, by,
        marker, diameter, fill_color, edge_color=None, edge_width=1.0,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_markers_xform(
        &mut self,
        xs: Vec<f64>,
        ys: Vec<f64>,
        ax: f64,
        bx: f64,
        ay: f64,
        by: f64,
        marker: &str,
        diameter: f64,
        fill_color: (u8, u8, u8, u8),
        edge_color: Option<(u8, u8, u8, u8)>,
        edge_width: f64,
    ) {
        let n = xs.len().min(ys.len());
        let r = diameter / 2.0;

        // Describe the marker outline *once*, centered at the origin; the
        // backends stamp it at each position (PDF XObject / SVG <use> / raster
        // path reuse) instead of duplicating the geometry per point.
        let mut marker_path = BezPath::new();
        append_marker(&mut marker_path, marker, 0.0, 0.0, r);

        let positions: Vec<Point> = (0..n)
            .map(|i| Point::new(ax * xs[i] + bx, ay * ys[i] + by))
            .collect();

        let stroke_only = marker == "+" || marker == "x";
        let node = if stroke_only {
            MarkerNode {
                marker: marker_path,
                fill: None,
                fill_rule: FillRule::NonZero,
                stroke: Some(CoreStroke {
                    color: color_from_rgba(edge_color.unwrap_or(fill_color)),
                    width: edge_width.max(1.0),
                    cap: LineCap::Round,
                    join: LineJoin::Round,
                    dash: None,
                }),
                positions,
            }
        } else {
            MarkerNode {
                marker: marker_path,
                fill: Some(color_from_rgba(fill_color)),
                fill_rule: FillRule::NonZero,
                stroke: edge_color.map(|c| CoreStroke {
                    color: color_from_rgba(c),
                    width: edge_width,
                    cap: LineCap::Round,
                    join: LineJoin::Round,
                    dash: None,
                }),
                positions,
            }
        };
        self.push_node(Node::Markers(node));
    }

    /// Fast path: colormap a 2D field and add it as an image, doing the
    /// per-pixel value->color lookup **in Rust**. `values` is the field in
    /// row-major data order (length `width*height`); `lut` is a 256-entry RGBA
    /// table (1024 bytes). Non-finite values become transparent. `origin_upper`
    /// places data row 0 at the top of the destination rect `(x, y, w, h)`.
    #[pyo3(signature = (
        values, width, height, vmin, vmax, lut, origin_upper, x, y, w, h,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_colormapped_image(
        &mut self,
        values: Vec<f64>,
        width: u32,
        height: u32,
        vmin: f64,
        vmax: f64,
        lut: Vec<u8>,
        origin_upper: bool,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
    ) {
        let wi = width as usize;
        let hi = height as usize;
        let span = if vmax > vmin { vmax - vmin } else { 1.0 };
        let mut buf = vec![0u8; wi * hi * 4];
        for row in 0..hi {
            let drow = if origin_upper { row } else { hi - 1 - row };
            let src = drow * wi;
            let dst = row * wi * 4;
            for col in 0..wi {
                let v = values[src + col];
                if !v.is_finite() {
                    continue; // leave RGBA = 0 (transparent)
                }
                let t = ((v - vmin) / span).clamp(0.0, 1.0);
                let li = ((t * 255.0).round() as usize) * 4;
                let o = dst + col * 4;
                buf[o] = lut[li];
                buf[o + 1] = lut[li + 1];
                buf[o + 2] = lut[li + 2];
                buf[o + 3] = lut[li + 3];
            }
        }
        self.push_node(Node::Image(ImageNode {
            data: ImageData::from_rgba8(buf, width, height),
            rect: KRect::new(x, y, x + w, y + h),
        }));
    }

    /// Add a run of text with its baseline origin at `(x, y)`. `font` selects
    /// the bundled face: `"body"` (Inter) or `"math"` (STIX Two Math).
    #[pyo3(signature = (x, y, text, size, color=(0, 0, 0, 255), font="body"))]
    fn add_text(
        &mut self,
        x: f64,
        y: f64,
        text: &str,
        size: f64,
        color: (u8, u8, u8, u8),
        font: &str,
    ) {
        let run = figurs_text::shape_text(font_for_kind(font), text, size as f32);
        self.push_node(Node::Text(TextNode {
            origin: Point::new(x, y),
            runs: vec![run],
            color: color_from_rgba(color),
        }));
    }

    /// Lay out and add a (LaTeX) math/text string with its left edge at `x`
    /// and baseline at `y`. Plain strings (no `$`) are shaped as a single
    /// body-font run; `$...$` spans are typeset by `figurs-math` using the
    /// math font's OpenType MATH table (real editable glyphs + vector rules),
    /// then appended to the current group/scene.
    #[pyo3(signature = (x, y, text, size, color=(0, 0, 0, 255)))]
    fn add_math(&mut self, x: f64, y: f64, text: &str, size: f64, color: (u8, u8, u8, u8)) {
        let (nodes, _m) = figurs_math::render(
            math_font(),
            body_font(),
            text,
            size as f32,
            x as f32,
            y as f32,
            color_from_rgba(color),
        );
        for node in nodes {
            self.push_node(node);
        }
    }

    /// Measure a math/text string: `(width, ascent, depth)` in points.
    #[pyo3(signature = (text, size))]
    fn measure_math(&self, text: &str, size: f64) -> (f64, f64, f64) {
        let (w, a, d) = figurs_math::measure(math_font(), body_font(), text, size as f32);
        (w as f64, a as f64, d as f64)
    }

    /// Add an RGBA8 image filling the destination rect `(x, y, w, h)`.
    #[pyo3(signature = (rgba, width, height, x, y, w, h))]
    #[allow(clippy::too_many_arguments)]
    fn add_image(
        &mut self,
        rgba: Vec<u8>,
        width: u32,
        height: u32,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
    ) {
        self.push_node(Node::Image(ImageNode {
            data: ImageData::from_rgba8(rgba, width, height),
            rect: KRect::new(x, y, x + w, y + h),
        }));
    }

    /// Open a group applying the affine matrix `[a b c d e f]` (mapping
    /// `(x, y) -> (a·x + c·y + e, b·x + d·y + f)`), an optional rectangular
    /// clip `(x, y, w, h)` in the group's local space, and `opacity`.
    /// Subsequent draw calls go into this group until [`Scene::end_group`].
    #[pyo3(signature = (a, b, c, d, e, f, clip=None, opacity=1.0))]
    #[allow(clippy::too_many_arguments)]
    fn begin_group(
        &mut self,
        a: f64,
        b: f64,
        c: f64,
        d: f64,
        e: f64,
        f: f64,
        clip: Option<(f64, f64, f64, f64)>,
        opacity: f32,
    ) {
        self.stack.push(Group {
            transform: Affine::new([a, b, c, d, e, f]),
            clip: clip.map(|(x, y, w, h)| ClipPath::rect(KRect::new(x, y, x + w, y + h))),
            opacity,
            children: Vec::new(),
        });
    }

    /// Close the most recently opened group, appending it to its parent.
    fn end_group(&mut self) {
        if let Some(group) = self.stack.pop() {
            self.push_node(Node::Group(group));
        }
    }

    /// Total horizontal advance of `text` at `size` (points) - for layout.
    /// `font` selects the bundled face (`"body"` / `"math"`).
    #[pyo3(signature = (text, size, font="body"))]
    fn measure_text(&self, text: &str, size: f64, font: &str) -> f64 {
        let run = figurs_text::shape_text(font_for_kind(font), text, size as f32);
        figurs_text::run_width(&run) as f64
    }

    /// Vertical font metrics `(ascent, descent, line_gap)` at `size` (points).
    /// `font` selects the bundled face (`"body"` / `"math"`).
    #[pyo3(signature = (size, font="body"))]
    fn font_vmetrics(&self, size: f64, font: &str) -> (f64, f64, f64) {
        let m = figurs_text::font_vmetrics(font_for_kind(font), size as f32);
        (m.ascent as f64, m.descent as f64, m.line_gap as f64)
    }

    /// Render to PDF bytes (real, embedded/subsetted, editable text). When
    /// `tagged` is set, emit a tagged/accessible PDF whose content is one
    /// `Figure` structure element carrying `alt` text, plus document metadata.
    #[pyo3(signature = (tagged=false, title=None, alt=None))]
    fn to_pdf<'py>(
        &self,
        py: Python<'py>,
        tagged: bool,
        title: Option<&str>,
        alt: Option<&str>,
    ) -> Bound<'py, PyBytes> {
        let bytes = if tagged {
            figurs_render_pdf::render_pdf_tagged(&self.inner, title, alt.unwrap_or("figure"))
        } else {
            figurs_render_pdf::render_pdf(&self.inner)
        };
        PyBytes::new(py, &bytes)
    }

    /// Render to an SVG document string (real `<text>` elements).
    fn to_svg(&self) -> String {
        figurs_render_svg::render_svg(&self.inner)
    }

    /// Render to PNG bytes at `dpi` dots per inch (the PNG carries a `pHYs`
    /// chunk recording its physical size). PDF/SVG are resolution-independent
    /// and ignore dpi.
    #[pyo3(signature = (dpi=200.0))]
    fn to_png<'py>(&self, py: Python<'py>, dpi: f64) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &figurs_render_raster::render_png(&self.inner, dpi))
    }
}

/// An axis-aligned rectangle `(x, y, w, h)` returned by [`solve_layout`].
#[pyclass(skip_from_py_object)]
#[derive(Clone, Copy)]
struct Rect {
    #[pyo3(get)]
    x: f64,
    #[pyo3(get)]
    y: f64,
    #[pyo3(get)]
    w: f64,
    #[pyo3(get)]
    h: f64,
}

impl From<figurs_layout::solve::Rect> for Rect {
    fn from(r: figurs_layout::solve::Rect) -> Self {
        Self {
            x: r.x,
            y: r.y,
            w: r.w,
            h: r.h,
        }
    }
}

#[pymethods]
impl Rect {
    #[getter]
    fn x1(&self) -> f64 {
        self.x + self.w
    }
    #[getter]
    fn y1(&self) -> f64 {
        self.y + self.h
    }
    fn __repr__(&self) -> String {
        format!(
            "Rect(x={:.2}, y={:.2}, w={:.2}, h={:.2})",
            self.x, self.y, self.w, self.h
        )
    }
}

/// Computed rectangles for one axes.
#[pyclass(skip_from_py_object)]
#[derive(Clone, Copy)]
struct AxesLayout {
    #[pyo3(get)]
    cell: Rect,
    #[pyo3(get)]
    plot: Rect,
    #[pyo3(get)]
    title: Rect,
    #[pyo3(get)]
    xlabel: Rect,
    #[pyo3(get)]
    ylabel: Rect,
    #[pyo3(get)]
    x_tick: Rect,
    #[pyo3(get)]
    y_tick: Rect,
    #[pyo3(get)]
    cbar: Rect,
}

/// The full solved figure layout.
#[pyclass]
struct Layout {
    #[pyo3(get)]
    axes: Vec<AxesLayout>,
    #[pyo3(get)]
    suptitle: Rect,
    #[pyo3(get)]
    legend: Rect,
}

/// Locate "nice" axis ticks for `[vmin, vmax]`, returning `(value, label)`
/// pairs. Backed by `figurs_layout::ticks`.
#[pyfunction]
#[pyo3(signature = (vmin, vmax, max_ticks=7))]
fn nice_ticks(vmin: f64, vmax: f64, max_ticks: usize) -> Vec<(f64, String)> {
    figurs_layout::ticks::ticks(vmin, vmax, max_ticks)
        .into_iter()
        .map(|t| (t.value, t.label))
        .collect()
}

/// Solve a figure layout in one pass. `cells` is a row-major list of
/// `(title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w)` band sizes
/// (points). Returns a [`Layout`] with every reserved rectangle.
#[pyfunction]
#[pyo3(signature = (
    width, height, nrows, ncols,
    cells,
    outer_margin=5.0, hspace=0.0, wspace=0.0, suptitle_h=0.0, legend_w=0.0,
))]
#[allow(clippy::too_many_arguments)]
fn solve_layout(
    width: f64,
    height: f64,
    nrows: usize,
    ncols: usize,
    cells: Vec<(f64, f64, f64, f64, f64, f64)>,
    outer_margin: f64,
    hspace: f64,
    wspace: f64,
    suptitle_h: f64,
    legend_w: f64,
) -> Layout {
    let spec = FigureSpec {
        width,
        height,
        nrows,
        ncols,
        outer_margin,
        hspace,
        wspace,
        suptitle_h,
        legend_w,
        cells: cells
            .into_iter()
            .map(|(title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w)| AxesBands {
                title_h,
                xlabel_h,
                ylabel_w,
                x_tick_h,
                y_tick_w,
                cbar_w,
            })
            .collect(),
    };
    let result = figurs_layout::solve::solve(&spec);
    Layout {
        axes: result
            .axes
            .into_iter()
            .map(|a| AxesLayout {
                cell: a.cell.into(),
                plot: a.plot.into(),
                title: a.title.into(),
                xlabel: a.xlabel.into(),
                ylabel: a.ylabel.into(),
                x_tick: a.x_tick.into(),
                y_tick: a.y_tick.into(),
                cbar: a.cbar.into(),
            })
            .collect(),
        suptitle: result.suptitle.into(),
        legend: result.legend.into(),
    }
}

/// Encode a sequence of equally-sized [`Scene`]s as an animated GIF. `scale` =
/// dpi/72 (device pixels per point); `delay_cs` = per-frame delay in
/// centiseconds; `infinite` loops forever vs. plays once.
#[pyfunction]
#[pyo3(signature = (scenes, scale, delay_cs, infinite=true))]
fn scenes_to_gif<'py>(
    py: Python<'py>,
    scenes: Vec<Py<Scene>>,
    scale: f64,
    delay_cs: u16,
    infinite: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    if scenes.is_empty() {
        return Err(PyValueError::new_err("animation needs at least one frame"));
    }
    // `guards` keeps each Scene borrowed; `refs` borrows from `guards`; both
    // outlive the render call, so no copying or unsafe is needed.
    let guards: Vec<PyRef<Scene>> = scenes.iter().map(|s| s.borrow(py)).collect();
    let refs: Vec<&CoreScene> = guards.iter().map(|g| &g.inner).collect();
    let bytes = figurs_render_raster::render_gif(&refs, scale, delay_cs, infinite);
    Ok(PyBytes::new(py, &bytes))
}

/// Encode a sequence of equally-sized [`Scene`]s as an animated PNG (full
/// colour, no palette quantization). `delay_num`/`delay_den` give the per-frame
/// delay in seconds; `infinite` loops forever vs. plays once.
#[pyfunction]
#[pyo3(signature = (scenes, dpi, delay_num, delay_den, infinite=true))]
fn scenes_to_apng<'py>(
    py: Python<'py>,
    scenes: Vec<Py<Scene>>,
    dpi: f64,
    delay_num: u16,
    delay_den: u16,
    infinite: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    if scenes.is_empty() {
        return Err(PyValueError::new_err("animation needs at least one frame"));
    }
    let guards: Vec<PyRef<Scene>> = scenes.iter().map(|s| s.borrow(py)).collect();
    let refs: Vec<&CoreScene> = guards.iter().map(|g| &g.inner).collect();
    let bytes = figurs_render_raster::render_apng(&refs, dpi, delay_num, delay_den, infinite);
    Ok(PyBytes::new(py, &bytes))
}

#[pymodule]
fn _figurs_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Scene>()?;
    m.add_class::<Rect>()?;
    m.add_class::<AxesLayout>()?;
    m.add_class::<Layout>()?;
    m.add_function(wrap_pyfunction!(nice_ticks, m)?)?;
    m.add_function(wrap_pyfunction!(solve_layout, m)?)?;
    m.add_function(wrap_pyfunction!(scenes_to_gif, m)?)?;
    m.add_function(wrap_pyfunction!(scenes_to_apng, m)?)?;
    Ok(())
}
