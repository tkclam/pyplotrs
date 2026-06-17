//! figurs-render-svg: renders a [`figurs_core::Scene`] to an SVG document.
//!
//! Text is emitted as real `<text>` elements (using each run's
//! `source_text`), with fonts embedded inline as base64 `@font-face` rules so
//! the output is self-contained and remains selectable/editable. Groups map
//! to `<g>` with `transform`/`opacity`/`clip-path`, and images to `<image>`
//! with an embedded base64 PNG.

use base64::Engine;
use figurs_core::kurbo::{Affine, PathEl};
use figurs_core::{
    Color, FillRule, Group, ImageNode, MarkerNode, Node, PathNode, Scene, TextNode,
};
use std::fmt::Write as _;

fn fmt_num(v: f64) -> String {
    format!("{v:.3}")
}

fn color_hex(c: Color) -> String {
    format!("#{:02x}{:02x}{:02x}", c.r, c.g, c.b)
}

/// Emit an `opacity="..."` fragment if `a < 255`, else nothing.
fn opacity_attr(a: u8) -> String {
    if a == 255 {
        String::new()
    } else {
        format!(r#" opacity="{:.3}""#, a as f64 / 255.0)
    }
}

fn path_data(path: &figurs_core::kurbo::BezPath) -> String {
    let mut d = String::new();
    for el in path.elements() {
        match *el {
            PathEl::MoveTo(p) => write!(d, "M{} {} ", fmt_num(p.x), fmt_num(p.y)).unwrap(),
            PathEl::LineTo(p) => write!(d, "L{} {} ", fmt_num(p.x), fmt_num(p.y)).unwrap(),
            PathEl::QuadTo(p1, p2) => write!(
                d,
                "Q{} {} {} {} ",
                fmt_num(p1.x),
                fmt_num(p1.y),
                fmt_num(p2.x),
                fmt_num(p2.y)
            )
            .unwrap(),
            PathEl::CurveTo(p1, p2, p3) => write!(
                d,
                "C{} {} {} {} {} {} ",
                fmt_num(p1.x),
                fmt_num(p1.y),
                fmt_num(p2.x),
                fmt_num(p2.y),
                fmt_num(p3.x),
                fmt_num(p3.y)
            )
            .unwrap(),
            PathEl::ClosePath => d.push_str("Z "),
        }
    }
    d.trim_end().to_string()
}

fn escape_xml(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            _ => out.push(c),
        }
    }
    out
}

/// Encode raw RGBA8 pixels as a PNG byte stream (for `<image>` embedding).
fn rgba_to_png(rgba: &[u8], width: u32, height: u32) -> Vec<u8> {
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().expect("png header");
        writer.write_image_data(rgba).expect("png data");
    }
    out
}

/// Names assigned to each unique embedded font, keyed by buffer identity.
type FontTable = Vec<(*const Vec<u8>, String)>;

fn collect_fonts(nodes: &[Node], table: &mut FontTable, css: &mut String) {
    for node in nodes {
        match node {
            Node::Text(text) => {
                for run in &text.runs {
                    let key = run.font.key();
                    if !table.iter().any(|(k, _)| *k == key) {
                        let name = format!("FigursFont{}", table.len());
                        let b64 =
                            base64::engine::general_purpose::STANDARD.encode(&*run.font.data);
                        writeln!(
                            css,
                            "@font-face{{font-family:'{name}';src:url(data:font/ttf;base64,{b64}) format('truetype');}}"
                        )
                        .unwrap();
                        table.push((key, name));
                    }
                }
            }
            Node::Group(g) => collect_fonts(&g.children, table, css),
            Node::Path(_) | Node::Image(_) | Node::Markers(_) => {}
        }
    }
}

/// SVG serialization state for one document.
struct SvgWriter<'a> {
    fonts: &'a FontTable,
    body: String,
    /// Extra `<defs>` content (clip-path and marker definitions) emitted as we
    /// recurse.
    defs: String,
    clip_counter: usize,
    marker_counter: usize,
}

impl SvgWriter<'_> {
    fn family_for(&self, key: *const Vec<u8>) -> &str {
        self.fonts
            .iter()
            .find(|(k, _)| *k == key)
            .map(|(_, n)| n.as_str())
            .unwrap_or("sans-serif")
    }

    fn render_path(&mut self, p: &PathNode) {
        let d = path_data(&p.geometry);
        let fill = match p.fill {
            Some(c) => color_hex(c),
            None => "none".to_string(),
        };
        write!(self.body, r#"<path d="{d}" fill="{fill}""#).unwrap();
        if let Some(c) = p.fill {
            self.body.push_str(&opacity_attr_named("fill-opacity", c.a));
        }
        if matches!(p.fill_rule, FillRule::EvenOdd) {
            self.body.push_str(r#" fill-rule="evenodd""#);
        }
        if let Some(stroke) = &p.stroke {
            write!(
                self.body,
                r#" stroke="{}" stroke-width="{}""#,
                color_hex(stroke.color),
                fmt_num(stroke.width)
            )
            .unwrap();
            self.body
                .push_str(&opacity_attr_named("stroke-opacity", stroke.color.a));
            match stroke.cap {
                figurs_core::LineCap::Round => self.body.push_str(r#" stroke-linecap="round""#),
                figurs_core::LineCap::Square => self.body.push_str(r#" stroke-linecap="square""#),
                figurs_core::LineCap::Butt => {}
            }
            match stroke.join {
                figurs_core::LineJoin::Round => self.body.push_str(r#" stroke-linejoin="round""#),
                figurs_core::LineJoin::Bevel => self.body.push_str(r#" stroke-linejoin="bevel""#),
                figurs_core::LineJoin::Miter => {}
            }
            if let Some(dash) = &stroke.dash {
                let dashes: Vec<String> = dash.iter().map(|d| fmt_num(*d as f64)).collect();
                write!(self.body, r#" stroke-dasharray="{}""#, dashes.join(",")).unwrap();
            }
        } else {
            self.body.push_str(r#" stroke="none""#);
        }
        writeln!(self.body, "/>").unwrap();
    }

    fn render_text(&mut self, t: &TextNode) {
        let mut x = t.origin.x;
        let y = t.origin.y;
        for run in &t.runs {
            let family = self.family_for(run.font.key()).to_string();
            writeln!(
                self.body,
                r#"<text x="{}" y="{}" font-family="{}" font-size="{}" fill="{}"{}>{}</text>"#,
                fmt_num(x),
                fmt_num(y),
                family,
                run.size,
                color_hex(t.color),
                opacity_attr(t.color.a),
                escape_xml(&run.source_text)
            )
            .unwrap();
            x += run.glyphs.iter().map(|g| g.advance as f64).sum::<f64>();
        }
    }

    fn render_markers(&mut self, m: &MarkerNode) {
        if m.positions.is_empty() {
            return;
        }
        // Define the marker outline once in <defs>, then place it with a <use>
        // per point: the SVG stays small and every marker is still a real,
        // editable shape (not flattened pixels).
        let id = format!("m{}", self.marker_counter);
        self.marker_counter += 1;
        writeln!(self.defs, r#"<path id="{id}" d="{}"/>"#, path_data(&m.marker)).unwrap();

        // A wrapping <g> carries the shared paint; the <use> children inherit
        // it, so the fill/stroke is described once for the whole scatter.
        let mut attrs = String::new();
        match m.fill {
            Some(c) => {
                write!(attrs, r#" fill="{}""#, color_hex(c)).unwrap();
                attrs.push_str(&opacity_attr_named("fill-opacity", c.a));
            }
            None => attrs.push_str(r#" fill="none""#),
        }
        if matches!(m.fill_rule, FillRule::EvenOdd) {
            attrs.push_str(r#" fill-rule="evenodd""#);
        }
        if let Some(stroke) = &m.stroke {
            write!(
                attrs,
                r#" stroke="{}" stroke-width="{}""#,
                color_hex(stroke.color),
                fmt_num(stroke.width)
            )
            .unwrap();
            attrs.push_str(&opacity_attr_named("stroke-opacity", stroke.color.a));
            match stroke.cap {
                figurs_core::LineCap::Round => attrs.push_str(r#" stroke-linecap="round""#),
                figurs_core::LineCap::Square => attrs.push_str(r#" stroke-linecap="square""#),
                figurs_core::LineCap::Butt => {}
            }
            match stroke.join {
                figurs_core::LineJoin::Round => attrs.push_str(r#" stroke-linejoin="round""#),
                figurs_core::LineJoin::Bevel => attrs.push_str(r#" stroke-linejoin="bevel""#),
                figurs_core::LineJoin::Miter => {}
            }
        } else {
            attrs.push_str(r#" stroke="none""#);
        }
        writeln!(self.body, "<g{attrs}>").unwrap();
        for pos in &m.positions {
            writeln!(
                self.body,
                r##"<use xlink:href="#{id}" x="{}" y="{}"/>"##,
                fmt_num(pos.x),
                fmt_num(pos.y)
            )
            .unwrap();
        }
        self.body.push_str("</g>\n");
    }

    fn render_image(&mut self, im: &ImageNode) {
        let png = rgba_to_png(&im.data.rgba, im.data.width, im.data.height);
        let b64 = base64::engine::general_purpose::STANDARD.encode(&png);
        writeln!(
            self.body,
            r#"<image x="{}" y="{}" width="{}" height="{}" preserveAspectRatio="none" xlink:href="data:image/png;base64,{}"/>"#,
            fmt_num(im.rect.x0),
            fmt_num(im.rect.y0),
            fmt_num(im.rect.width()),
            fmt_num(im.rect.height()),
            b64
        )
        .unwrap();
    }

    fn render_group(&mut self, g: &Group) {
        let mut attrs = String::new();
        if g.transform != Affine::IDENTITY {
            let [a, b, c, d, e, f] = g.transform.as_coeffs();
            write!(
                attrs,
                r#" transform="matrix({},{},{},{},{},{})""#,
                fmt_num(a),
                fmt_num(b),
                fmt_num(c),
                fmt_num(d),
                fmt_num(e),
                fmt_num(f)
            )
            .unwrap();
        }
        if g.opacity < 1.0 {
            write!(attrs, r#" opacity="{:.3}""#, g.opacity).unwrap();
        }
        if let Some(clip) = &g.clip {
            let id = format!("clip{}", self.clip_counter);
            self.clip_counter += 1;
            let rule = if matches!(clip.rule, FillRule::EvenOdd) {
                r#" clip-rule="evenodd""#
            } else {
                ""
            };
            writeln!(
                self.defs,
                r#"<clipPath id="{id}" clipPathUnits="userSpaceOnUse"><path d="{}"{rule}/></clipPath>"#,
                path_data(&clip.geometry)
            )
            .unwrap();
            write!(attrs, r#" clip-path="url(#{id})""#).unwrap();
        }
        writeln!(self.body, "<g{attrs}>").unwrap();
        for child in &g.children {
            self.render_node(child);
        }
        self.body.push_str("</g>\n");
    }

    fn render_node(&mut self, node: &Node) {
        match node {
            Node::Path(p) => self.render_path(p),
            Node::Text(t) => self.render_text(t),
            Node::Image(im) => self.render_image(im),
            Node::Markers(m) => self.render_markers(m),
            Node::Group(g) => self.render_group(g),
        }
    }
}

fn opacity_attr_named(name: &str, a: u8) -> String {
    if a == 255 {
        String::new()
    } else {
        format!(r#" {name}="{:.3}""#, a as f64 / 255.0)
    }
}

/// Render `scene` to a complete SVG document string.
pub fn render_svg(scene: &Scene) -> String {
    let w = scene.size.width;
    let h = scene.size.height;

    let mut fonts: FontTable = Vec::new();
    let mut font_face_css = String::new();
    collect_fonts(&scene.nodes, &mut fonts, &mut font_face_css);

    let mut writer = SvgWriter {
        fonts: &fonts,
        body: String::new(),
        defs: String::new(),
        clip_counter: 0,
        marker_counter: 0,
    };
    for node in &scene.nodes {
        writer.render_node(node);
    }

    let mut out = String::new();
    writeln!(
        out,
        r#"<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">"#
    )
    .unwrap();

    if !font_face_css.is_empty() || !writer.defs.is_empty() {
        out.push_str("<defs>");
        if !font_face_css.is_empty() {
            write!(out, "<style>\n{font_face_css}</style>").unwrap();
        }
        out.push_str(&writer.defs);
        out.push_str("</defs>\n");
    }

    out.push_str(&writer.body);
    out.push_str("</svg>\n");
    out
}
