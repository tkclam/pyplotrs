//! The `Scene` class: a figure being drawn, and its export to PDF/SVG/PNG.

use std::sync::Arc;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use pyplotrs_engine::draw::{self, Paint, SceneBuilder};
use pyplotrs_engine::fonts::Fonts;
use pyplotrs_engine::geometry::Scale;
use pyplotrs_engine::kernels::ColorMapper;
use pyplotrs_engine::kurbo::{Affine, Rect};
use pyplotrs_engine::math::{self, FaceStyle, FontSet};
use pyplotrs_engine::render::{pdf, raster, svg};
use pyplotrs_engine::resample::VECTOR_IMAGE_PPI;
use pyplotrs_engine::scene::{self as ir, FillRule, Node, PathNode};
use pyplotrs_engine::text;

use crate::convert::{Bytes, F64s, Rgba, Transform, color, stroke, transform, value_err};

/// A figure being drawn: device coordinates are points, y down.
#[pyclass(module = "pyplotrs._core")]
pub struct Scene {
    pub(crate) builder: SceneBuilder,
    fonts: Arc<Fonts>,
}

impl Scene {
    /// Render with the finished scene, copying it only if groups are open.
    pub(crate) fn with_scene<R>(&self, f: impl FnOnce(&ir::Scene) -> R) -> R {
        match self.builder.finished() {
            Some(scene) => f(scene),
            None => f(&self.builder.scene()),
        }
    }
}

fn face(bold: bool, italic: bool) -> FaceStyle {
    FaceStyle { bold, italic }
}

#[pymethods]
impl Scene {
    /// `font_family` lists preferred body families, tried in order before the
    /// bundled Liberation Sans. `math_fontset` is `"sans"` or `"stix"`.
    #[new]
    #[pyo3(signature = (width, height, font_family=Vec::new(), math_fontset="sans"))]
    fn new(
        width: f64,
        height: f64,
        font_family: Vec<String>,
        math_fontset: &str,
    ) -> PyResult<Self> {
        let set = match math_fontset {
            "sans" => FontSet::Sans,
            "stix" => FontSet::Stix,
            other => {
                return Err(PyValueError::new_err(format!(
                    "math_fontset must be 'sans' or 'stix', got {other:?}"
                )));
            }
        };
        Ok(Scene {
            builder: SceneBuilder::new(width, height),
            fonts: Fonts::resolve(&font_family, set),
        })
    }

    // -- vector marks ----------------------------------------------------

    /// A polyline through the points; NaN breaks it. With `fill` and `close`
    /// it is a filled polygon. `simplify` drops vertices within that many
    /// points of a straight run.
    #[pyo3(signature = (xs, ys, tf=None, *, stroke=None, width=1.0, fill=None, close=false,
                        dash=None, cap="butt", join="round", simplify=None))]
    #[allow(clippy::too_many_arguments)]
    fn path(
        &mut self,
        xs: F64s,
        ys: F64s,
        tf: Option<&Transform>,
        stroke: Option<Rgba>,
        width: f64,
        fill: Option<Rgba>,
        close: bool,
        dash: Option<Vec<f32>>,
        cap: &str,
        join: &str,
        simplify: Option<f64>,
    ) -> PyResult<()> {
        let stroke = crate::convert::stroke(stroke, width, dash, cap, join)?;
        let geometry = draw::polyline_path(&xs, &ys, &transform(tf), close, simplify);
        self.builder.push(Node::Path(PathNode {
            geometry,
            fill: fill.map(color),
            fill_rule: FillRule::NonZero,
            stroke,
        }));
        Ok(())
    }

    /// Independent segments `(x0[i], y0[i]) -> (x1[i], y1[i])`.
    #[pyo3(signature = (x0, y0, x1, y1, tf=None, *, color, width=1.0, dash=None, cap="butt"))]
    #[allow(clippy::too_many_arguments)]
    fn segments(
        &mut self,
        x0: F64s,
        y0: F64s,
        x1: F64s,
        y1: F64s,
        tf: Option<&Transform>,
        color: Rgba,
        width: f64,
        dash: Option<Vec<f32>>,
        cap: &str,
    ) -> PyResult<()> {
        let stroke = stroke(Some(color), width, dash, cap, "miter")?;
        let geometry = draw::segments_path(&x0, &y0, &x1, &y1, &transform(tf));
        self.builder.push(Node::Path(PathNode {
            geometry,
            fill: None,
            fill_rule: FillRule::NonZero,
            stroke,
        }));
        Ok(())
    }

    /// Axis-aligned rectangles; `fills` (flat RGBA bytes) colors each one.
    #[pyo3(signature = (x0, y0, x1, y1, tf=None, *, fill=None, fills=None, stroke=None, width=1.0))]
    #[allow(clippy::too_many_arguments)]
    fn rects(
        &mut self,
        x0: F64s,
        y0: F64s,
        x1: F64s,
        y1: F64s,
        tf: Option<&Transform>,
        fill: Option<Rgba>,
        fills: Option<Bytes>,
        stroke: Option<Rgba>,
        width: f64,
    ) -> PyResult<()> {
        let paint = Paint {
            fill: fill.map(color),
            stroke: crate::convert::stroke(stroke, width, None, "butt", "miter")?,
        };
        let fills = fills.map(|b| b.0).unwrap_or_default();
        draw::rects(
            &mut self.builder,
            &x0,
            &y0,
            &x1,
            &y1,
            &transform(tf),
            &paint,
            &fills,
        );
        Ok(())
    }

    /// Closed polygons; polygon `k` takes the next `counts[k]` vertices.
    #[pyo3(signature = (xs, ys, counts, tf=None, *, fill=None, fills=None, stroke=None, width=1.0))]
    #[allow(clippy::too_many_arguments)]
    fn polygons(
        &mut self,
        xs: F64s,
        ys: F64s,
        counts: Vec<u32>,
        tf: Option<&Transform>,
        fill: Option<Rgba>,
        fills: Option<Bytes>,
        stroke: Option<Rgba>,
        width: f64,
    ) -> PyResult<()> {
        let paint = Paint {
            fill: fill.map(color),
            stroke: crate::convert::stroke(stroke, width, None, "butt", "round")?,
        };
        let fills = fills.map(|b| b.0).unwrap_or_default();
        draw::polygons(
            &mut self.builder,
            &xs,
            &ys,
            &counts,
            &transform(tf),
            &paint,
            &fills,
        );
        Ok(())
    }

    /// The filled region between `lo` and `hi` along `seq`; with `swap`,
    /// `seq` runs along y.
    #[pyo3(signature = (seq, lo, hi, tf=None, *, fill, swap=false))]
    fn band(
        &mut self,
        seq: F64s,
        lo: F64s,
        hi: F64s,
        tf: Option<&Transform>,
        fill: Rgba,
        swap: bool,
    ) {
        let geometry = draw::band_path(&seq, &lo, &hi, &transform(tf), swap);
        if !geometry.elements().is_empty() {
            self.builder.push(Node::Path(PathNode {
                geometry,
                fill: Some(color(fill)),
                fill_rule: FillRule::NonZero,
                stroke: None,
            }));
        }
    }

    /// A marker of diameter `size` points at every point. `fills` (flat RGBA
    /// bytes) colors each marker.
    #[pyo3(signature = (xs, ys, tf=None, *, marker="o", size=5.0, fill=None, fills=None,
                        edge=None, edge_width=1.0))]
    #[allow(clippy::too_many_arguments)]
    fn markers(
        &mut self,
        xs: F64s,
        ys: F64s,
        tf: Option<&Transform>,
        marker: &str,
        size: f64,
        fill: Option<Rgba>,
        fills: Option<Bytes>,
        edge: Option<Rgba>,
        edge_width: f64,
    ) -> PyResult<()> {
        let marker = crate::convert::marker(marker)?;
        let edge = stroke(edge, edge_width, None, "round", "round")?;
        let fills = fills.map(|b| b.0).unwrap_or_default();
        let node = draw::markers(
            &xs,
            &ys,
            &transform(tf),
            marker,
            size,
            fill.map(color),
            &fills,
            edge,
        );
        self.builder.push(Node::Markers(node));
        Ok(())
    }

    // -- images ------------------------------------------------------------

    /// An RGBA image (`width * height * 4` bytes) placed at `(x, y, w, h)`.
    #[pyo3(signature = (rgba, width, height, x, y, w, h, *, flip_x=false, flip_y=false))]
    #[allow(clippy::too_many_arguments)]
    fn image(
        &mut self,
        rgba: Bytes,
        width: usize,
        height: usize,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
        flip_x: bool,
        flip_y: bool,
    ) -> PyResult<()> {
        if rgba.0.len() < width * height * 4 {
            return Err(PyValueError::new_err(
                "image buffer is smaller than width * height * 4",
            ));
        }
        let node = draw::image(
            &rgba.0,
            width,
            height,
            flip_x,
            flip_y,
            Rect::new(x, y, x + w, y + h),
        );
        self.builder.push(node);
        Ok(())
    }

    /// A row-major grid of values colormapped through `lut` (256 RGBA
    /// entries) and placed at `(x, y, w, h)`. Row 0 is the top row when
    /// `origin_upper`.
    #[pyo3(signature = (values, width, height, lut, vmin, vmax, x, y, w, h, *, norm="linear",
                        origin_upper=true, flip_x=false))]
    #[allow(clippy::too_many_arguments)]
    fn colormapped_image(
        &mut self,
        values: F64s,
        width: usize,
        height: usize,
        lut: Bytes,
        vmin: f64,
        vmax: f64,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
        norm: &str,
        origin_upper: bool,
        flip_x: bool,
    ) -> PyResult<()> {
        if lut.0.len() != 1024 {
            return Err(PyValueError::new_err(
                "lut must be 256 RGBA entries (1024 bytes)",
            ));
        }
        let mapper = ColorMapper::new(&lut.0, Scale::parse(norm), vmin, vmax);
        let node = draw::colormapped_image(
            &values,
            width,
            height,
            &mapper,
            &lut.0,
            origin_upper,
            flip_x,
            Rect::new(x, y, x + w, y + h),
        );
        self.builder.push(node);
        Ok(())
    }

    // -- text --------------------------------------------------------------

    /// Draw `s` (which may contain `$...$` math) with its left end at `x` and
    /// its baseline at `y`.
    #[pyo3(signature = (x, y, s, size, color, *, bold=false, italic=false))]
    #[allow(clippy::too_many_arguments)]
    fn text(&mut self, x: f64, y: f64, s: &str, size: f64, color: Rgba, bold: bool, italic: bool) {
        let fonts = self.fonts.math(face(bold, italic));
        let (nodes, _) = math::render(
            &fonts,
            s,
            size as f32,
            x as f32,
            y as f32,
            crate::convert::color(color),
        );
        for node in nodes {
            self.builder.push(node);
        }
    }

    /// `(width, ascent, depth)` of `s` in points.
    #[pyo3(signature = (s, size, *, bold=false, italic=false))]
    fn measure(&self, s: &str, size: f64, bold: bool, italic: bool) -> (f64, f64, f64) {
        let (w, a, d) = math::measure(&self.fonts.math(face(bold, italic)), s, size as f32);
        (w as f64, a as f64, d as f64)
    }

    /// The body font's `(ascent, descent, underline_offset, underline_width,
    /// strike_offset, strike_width)` at `size`, offsets measured downward
    /// from the baseline.
    #[pyo3(signature = (size, *, bold=false, italic=false))]
    fn font_metrics(&self, size: f64, bold: bool, italic: bool) -> (f64, f64, f64, f64, f64, f64) {
        let m = text::font_vmetrics(&self.fonts.face(face(bold, italic)).data, size as f32);
        (
            m.ascent as f64,
            m.descent as f64,
            m.underline_offset as f64,
            m.underline_thickness as f64,
            m.strikeout_offset as f64,
            m.strikeout_thickness as f64,
        )
    }

    /// TeX commands in `s` the math engine does not implement.
    fn unknown_commands(&self, s: &str, size: f64) -> Vec<String> {
        math::unknown_commands(&self.fonts.math(FaceStyle::default()), s, size as f32)
    }

    /// Characters in `s` that no available font can draw.
    fn missing_glyphs(&self, s: &str) -> Vec<String> {
        let body = &self.fonts.face(FaceStyle::default()).data;
        text::missing_glyphs(body, s)
            .into_iter()
            .filter(|c| {
                let one = c.to_string();
                self.fonts
                    .text_fallbacks()
                    .iter()
                    .all(|f| !text::missing_glyphs(f, &one).is_empty())
            })
            .map(String::from)
            .collect()
    }

    /// `[(family, postscript name), ...]` for regular, italic, bold and bold
    /// italic body text, as resolved on this machine.
    fn font_faces(&self) -> Vec<(String, String)> {
        [
            face(false, false),
            face(false, true),
            face(true, false),
            face(true, true),
        ]
        .map(|f| {
            let r = self.fonts.face(f);
            (r.family.clone(), r.postscript.clone())
        })
        .to_vec()
    }

    /// The regular body face's font file.
    fn font_data<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new(py, &self.fonts.face(FaceStyle::default()).data.data)
    }

    // -- groups ------------------------------------------------------------

    /// Open a group with an affine `(a, b, c, d, e, f)` transform, an optional
    /// clip (`clip=(x, y, w, h)`, `clip_circle=(cx, cy, r)` or a polygon
    /// `clip_path=(xs, ys)`) and opacity.
    #[pyo3(signature = (transform=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0), *, clip=None, clip_circle=None,
                        clip_path=None, opacity=1.0))]
    fn begin_group(
        &mut self,
        transform: (f64, f64, f64, f64, f64, f64),
        clip: Option<(f64, f64, f64, f64)>,
        clip_circle: Option<(f64, f64, f64)>,
        clip_path: Option<(F64s, F64s)>,
        opacity: f32,
    ) {
        let (a, b, c, d, e, f) = transform;
        let clip = match (clip_path, clip_circle, clip) {
            (Some((xs, ys)), _, _) => Some(draw::clip_polygon(&xs, &ys)),
            (None, Some((cx, cy, r)), _) => Some(draw::clip_circle(cx, cy, r)),
            (None, None, Some((x, y, w, h))) => Some(draw::clip_rect(x, y, w, h)),
            (None, None, None) => None,
        };
        self.builder
            .begin_group(Affine::new([a, b, c, d, e, f]), clip, opacity);
    }

    fn end_group(&mut self) {
        self.builder.end_group();
    }

    // -- export ------------------------------------------------------------

    /// PDF bytes. `dpi` sets the resolution of embedded images. `tagged`
    /// writes an accessible PDF with `title` and `alt` text.
    #[pyo3(signature = (*, dpi=VECTOR_IMAGE_PPI, tagged=false, title=None, alt=None))]
    fn to_pdf<'py>(
        &self,
        py: Python<'py>,
        dpi: f64,
        tagged: bool,
        title: Option<&str>,
        alt: Option<&str>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let bytes = py
            .detach(|| {
                self.with_scene(|s| {
                    if tagged {
                        pdf::render_pdf_tagged_at(s, title, alt.unwrap_or("figure"), dpi)
                    } else {
                        pdf::render_pdf_at(s, dpi)
                    }
                })
            })
            .map_err(value_err)?;
        Ok(PyBytes::new(py, &bytes))
    }

    /// SVG document text. `dpi` sets the resolution of embedded images.
    #[pyo3(signature = (*, dpi=VECTOR_IMAGE_PPI))]
    fn to_svg(&self, py: Python<'_>, dpi: f64) -> String {
        py.detach(|| self.with_scene(|s| svg::render_svg_at(s, dpi)))
    }

    /// PNG bytes at `dpi`; white background unless `transparent`.
    #[pyo3(signature = (*, dpi=200.0, transparent=false))]
    fn to_png<'py>(
        &self,
        py: Python<'py>,
        dpi: f64,
        transparent: bool,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let bytes = py
            .detach(|| self.with_scene(|s| raster::render_png(s, dpi, transparent)))
            .map_err(value_err)?;
        Ok(PyBytes::new(py, &bytes))
    }
}
