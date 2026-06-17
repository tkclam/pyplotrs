//! pyplotrs-render-pdf: renders a [`pyplotrs_core::Scene`] to a PDF document
//! using `krilla`.
//!
//! Text is drawn via `Surface::draw_glyphs` with the pre-shaped glyph
//! IDs/positions from `pyplotrs-text`, so it is embedded as real,
//! subsetted, selectable/editable text - never converted to outline paths.
//! Groups map onto krilla's `push_transform`/`push_clip_path`/`push_opacity`
//! state stack, and images are drawn via `draw_image`.

use std::collections::HashMap;

use pyplotrs_core::kurbo::{Affine, PathEl};
use pyplotrs_core::{
    Color, FillRule as CoreFillRule, Group, ImageNode, LineCap as CoreLineCap,
    LineJoin as CoreLineJoin, MarkerNode, Node, PathNode, Scene, Stroke as CoreStroke, TextNode,
};
use krilla::color::rgb;
use krilla::geom::{Path, PathBuilder, Point, Size as KSize, Transform};
use krilla::graphic::Graphic;
use krilla::num::NormalizedF32;
use krilla::page::PageSettings;
use krilla::paint::{Fill, FillRule, LineCap, LineJoin, Stroke, StrokeDash};
use krilla::metadata::Metadata;
use krilla::surface::Surface;
use krilla::tagging::{ContentTag, Tag, TagGroup, TagTree};
use krilla::text::{Font, GlyphId, KrillaGlyph};
use krilla::Document;

fn to_krilla_path(geometry: &pyplotrs_core::kurbo::BezPath) -> Option<Path> {
    let mut pb = PathBuilder::new();
    for el in geometry.elements() {
        match *el {
            PathEl::MoveTo(p) => pb.move_to(p.x as f32, p.y as f32),
            PathEl::LineTo(p) => pb.line_to(p.x as f32, p.y as f32),
            PathEl::QuadTo(p1, p2) => pb.quad_to(p1.x as f32, p1.y as f32, p2.x as f32, p2.y as f32),
            PathEl::CurveTo(p1, p2, p3) => pb.cubic_to(
                p1.x as f32,
                p1.y as f32,
                p2.x as f32,
                p2.y as f32,
                p3.x as f32,
                p3.y as f32,
            ),
            PathEl::ClosePath => pb.close(),
        }
    }
    pb.finish()
}

fn krilla_color(c: Color) -> rgb::Color {
    rgb::Color::new(c.r, c.g, c.b)
}

/// Map a [`pyplotrs_core`] alpha (0-255) to a krilla [`NormalizedF32`].
fn alpha(a: u8) -> NormalizedF32 {
    NormalizedF32::new(a as f32 / 255.0).unwrap_or(NormalizedF32::ONE)
}

fn to_transform(affine: Affine) -> Transform {
    let [a, b, c, d, e, f] = affine.as_coeffs();
    Transform::from_row(a as f32, b as f32, c as f32, d as f32, e as f32, f as f32)
}

fn to_fill_rule(rule: CoreFillRule) -> FillRule {
    match rule {
        CoreFillRule::NonZero => FillRule::NonZero,
        CoreFillRule::EvenOdd => FillRule::EvenOdd,
    }
}

fn to_krilla_stroke(s: &CoreStroke) -> Stroke {
    Stroke {
        paint: krilla_color(s.color).into(),
        width: s.width as f32,
        opacity: alpha(s.color.a),
        line_cap: match s.cap {
            CoreLineCap::Butt => LineCap::Butt,
            CoreLineCap::Round => LineCap::Round,
            CoreLineCap::Square => LineCap::Square,
        },
        line_join: match s.join {
            CoreLineJoin::Miter => LineJoin::Miter,
            CoreLineJoin::Round => LineJoin::Round,
            CoreLineJoin::Bevel => LineJoin::Bevel,
        },
        dash: s.dash.as_ref().map(|array| StrokeDash {
            array: array.clone(),
            offset: 0.0,
        }),
        ..Default::default()
    }
}

/// Per-document state shared across the recursive walk.
struct PdfRenderer {
    /// krilla `Font`s cached by underlying-buffer identity so each distinct
    /// font is parsed (and later embedded/subsetted) only once.
    fonts: HashMap<*const Vec<u8>, Font>,
}

impl PdfRenderer {
    fn font_for(&mut self, run_font: &pyplotrs_core::FontData) -> Font {
        self.fonts
            .entry(run_font.key())
            .or_insert_with(|| {
                Font::new(run_font.data.clone().into(), run_font.index)
                    .expect("invalid font data")
            })
            .clone()
    }

    fn draw_path(&self, surface: &mut Surface, p: &PathNode) {
        let Some(path) = to_krilla_path(&p.geometry) else {
            return;
        };
        surface.set_fill(p.fill.map(|c| Fill {
            paint: krilla_color(c).into(),
            opacity: alpha(c.a),
            rule: to_fill_rule(p.fill_rule),
        }));
        surface.set_stroke(p.stroke.as_ref().map(to_krilla_stroke));
        surface.draw_path(&path);
    }

    fn draw_text(&mut self, surface: &mut Surface, text: &TextNode) {
        surface.set_fill(Some(Fill {
            paint: krilla_color(text.color).into(),
            opacity: alpha(text.color.a),
            rule: FillRule::NonZero,
        }));
        surface.set_stroke(None);

        for run in &text.runs {
            let font = self.font_for(&run.font);
            // Each glyph is drawn at its absolute position, carrying the
            // slice of `source_text` for its cluster - this keeps the PDF's
            // ToUnicode/copy-paste text correct without requiring krilla's
            // pen to re-accumulate advances.
            for (i, glyph) in run.glyphs.iter().enumerate() {
                let start = Point::from_xy(
                    text.origin.x as f32 + glyph.x,
                    text.origin.y as f32 + glyph.y,
                );
                let cluster_start = glyph.cluster as usize;
                let cluster_end = run
                    .glyphs
                    .get(i + 1)
                    .map(|g| g.cluster as usize)
                    .unwrap_or(run.source_text.len())
                    .max(cluster_start);
                let slice = &run.source_text[cluster_start..cluster_end];

                let kglyph = KrillaGlyph::new(
                    GlyphId::new(glyph.glyph_id as u32),
                    glyph.advance / run.size,
                    0.0,
                    0.0,
                    0.0,
                    0..slice.len(),
                    None,
                );
                surface.draw_glyphs(start, &[kglyph], font.clone(), slice, run.size, false);
            }
        }
    }

    fn draw_markers(&self, surface: &mut Surface, m: &MarkerNode) {
        let Some(path) = to_krilla_path(&m.marker) else {
            return;
        };
        // Describe the marker once as a reusable Form XObject. krilla writes the
        // XObject's content stream a single time and dedupes it across all the
        // `draw_graphic` invocations below, so a 1e6-point scatter is one small
        // glyph definition plus N cheap `q cm Do Q` placements - not N copies of
        // the bezier outline. Each placement is a pure translation, so stroke
        // widths and shape are preserved exactly.
        let graphic = {
            let mut builder = surface.stream_builder();
            let mut sub = builder.surface();
            sub.set_fill(m.fill.map(|c| Fill {
                paint: krilla_color(c).into(),
                opacity: alpha(c.a),
                rule: to_fill_rule(m.fill_rule),
            }));
            sub.set_stroke(m.stroke.as_ref().map(to_krilla_stroke));
            sub.draw_path(&path);
            sub.finish();
            Graphic::new(builder.finish(), false)
        };
        for pos in &m.positions {
            surface.push_transform(&Transform::from_translate(pos.x as f32, pos.y as f32));
            surface.draw_graphic(graphic.clone());
            surface.pop();
        }
    }

    fn draw_image(&self, surface: &mut Surface, image: &ImageNode) {
        let img = krilla::image::Image::from_rgba8(
            (*image.data.rgba).clone(),
            image.data.width,
            image.data.height,
        );
        // `draw_image` covers (0,0)..(w,h) in the current space; translate to
        // the destination rect's top-left and let `size` scale it to fill.
        surface.push_transform(&Transform::from_translate(
            image.rect.x0 as f32,
            image.rect.y0 as f32,
        ));
        if let Some(size) = KSize::from_wh(image.rect.width() as f32, image.rect.height() as f32) {
            surface.draw_image(img, size);
        }
        surface.pop();
    }

    fn render_node(&mut self, surface: &mut Surface, node: &Node) {
        match node {
            Node::Path(p) => self.draw_path(surface, p),
            Node::Text(t) => self.draw_text(surface, t),
            Node::Image(im) => self.draw_image(surface, im),
            Node::Markers(m) => self.draw_markers(surface, m),
            Node::Group(g) => self.render_group(surface, g),
        }
    }

    fn render_group(&mut self, surface: &mut Surface, g: &Group) {
        let mut pushed = 0;
        if g.transform != Affine::IDENTITY {
            surface.push_transform(&to_transform(g.transform));
            pushed += 1;
        }
        if let Some(clip) = &g.clip {
            if let Some(path) = to_krilla_path(&clip.geometry) {
                surface.push_clip_path(&path, &to_fill_rule(clip.rule));
                pushed += 1;
            }
        }
        if g.opacity < 1.0 {
            surface.push_opacity(NormalizedF32::new(g.opacity).unwrap_or(NormalizedF32::ONE));
            pushed += 1;
        }
        for child in &g.children {
            self.render_node(surface, child);
        }
        for _ in 0..pushed {
            surface.pop();
        }
    }
}

/// Render `scene` to PDF bytes.
pub fn render_pdf(scene: &Scene) -> Vec<u8> {
    let mut document = Document::new();
    render_into(&mut document, scene, None);
    document.finish().expect("PDF serialization should not fail")
}

/// Render `scene` as a **tagged, accessible PDF**: all marks are wrapped in one
/// `Figure` structure element carrying `alt` text (so a screen reader announces
/// the chart), and the document gets a `/Lang` + title in its metadata and a
/// marked structure tree. `title` defaults the figure's document title.
pub fn render_pdf_tagged(scene: &Scene, title: Option<&str>, alt: &str) -> Vec<u8> {
    let mut document = Document::new();
    render_into(&mut document, scene, Some(alt));

    let mut meta = Metadata::new()
        .language("en".to_string())
        .producer("pyplotrs".to_string());
    if let Some(t) = title {
        meta = meta.title(t.to_string());
    }
    document.set_metadata(meta);
    document.finish().expect("PDF serialization should not fail")
}

/// Shared render body. When `alt` is `Some`, the page's content is enclosed in a
/// single tagged marked-content sequence referenced by a `Figure` struct
/// element (the whole chart is one accessible figure with alternate text), and a
/// tag tree is attached to the document.
fn render_into(document: &mut Document, scene: &Scene, alt: Option<&str>) {
    let mut page = document.start_page_with(
        PageSettings::from_wh(scene.size.width as f32, scene.size.height as f32)
            .expect("scene size must be positive"),
    );
    let mut surface = page.surface();

    let mut renderer = PdfRenderer {
        fonts: HashMap::new(),
    };

    let content_id = alt.map(|_| surface.start_tagged(ContentTag::Other));
    for node in &scene.nodes {
        renderer.render_node(&mut surface, node);
    }
    if content_id.is_some() {
        surface.end_tagged();
    }

    surface.finish();
    page.finish();

    if let (Some(id), Some(alt)) = (content_id, alt) {
        let mut figure = TagGroup::new(Tag::Figure(Some(alt.to_string())));
        figure.push(id);
        let mut tree = TagTree::new();
        tree.push(figure);
        document.set_tag_tree(tree);
    }
}
