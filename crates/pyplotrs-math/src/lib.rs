//! pyplotrs-math: a faithful (LaTeX/MathJax-grade) math typesetter.
//!
//! Parses the TeX `$...$` subset and lays it out with Knuth's boxes-and-glue
//! model, driven by the **OpenType MATH table** of the math font (STIX Two
//! Math) rather than hand-tuned constants. Output is ordinary pyplotrs IR — real,
//! editable glyph runs plus filled/stroked vector paths for rules and stretchy
//! glyphs — so math stays selectable text in PDF/SVG.
//!
//! Public API: [`measure`] returns `(width, ascent, depth)`; [`render`] returns
//! the positioned [`pyplotrs_core::Node`]s plus those metrics. Plain strings with
//! no `$` are shaped as a single body-font run, so callers route every label
//! through here unconditionally.

mod font;
mod layout;
mod tables;

use pyplotrs_core::kurbo::Point;
use pyplotrs_core::{
    Color, FillRule, FontData, LineCap, LineJoin, Node, PathNode, Stroke, TextNode,
};

use font::MathFont;
use layout::{Draw, Layout};

/// Split `s` into `(is_math, text)` runs on unescaped `$` toggles (`\$` is a
/// literal dollar).
fn split_segments(s: &str) -> Vec<(bool, String)> {
    let mut segs = Vec::new();
    let mut buf = String::new();
    let mut math = false;
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' {
            if let Some('$') = chars.peek() {
                buf.push('$');
                chars.next();
                continue;
            }
            buf.push('\\');
            continue;
        }
        if c == '$' {
            segs.push((math, std::mem::take(&mut buf)));
            math = !math;
            continue;
        }
        buf.push(c);
    }
    segs.push((math, buf));
    segs
}

fn build_layout(math_font: &FontData, body_font: &FontData, s: &str, size: f32) -> Layout {
    let mf = MathFont::new(&math_font.data[..], math_font.index);
    let segs = split_segments(s);
    // Fast path: no math at all -> one shaped body run (kept kerned/editable).
    if !s.contains('$') || mf.is_none() {
        return layout::shaped_text_layout(body_font, s, size);
    }
    let mf = mf.unwrap();
    let mut parts: Vec<Layout> = Vec::new();
    for (is_math, seg) in segs {
        if seg.is_empty() {
            continue;
        }
        if is_math {
            let engine = layout::Engine::new(&mf, math_font, body_font, &seg);
            parts.push(engine.layout(size));
        } else {
            parts.push(layout::shaped_text_layout(body_font, &seg, size));
        }
    }
    if parts.len() == 1 {
        parts.pop().unwrap()
    } else {
        layout::hcat(parts)
    }
}

/// Measure `s` at `size`, returning `(width, ascent, depth)` in points.
pub fn measure(math_font: &FontData, body_font: &FontData, s: &str, size: f32) -> (f32, f32, f32) {
    let l = build_layout(math_font, body_font, s, size);
    (l.width, l.ascent, l.depth)
}

/// Lay out `s` with its left edge at `x` and baseline at `baseline`, returning
/// the scene nodes plus `(width, ascent, depth)`.
pub fn render(
    math_font: &FontData,
    body_font: &FontData,
    s: &str,
    size: f32,
    x: f32,
    baseline: f32,
    color: Color,
) -> (Vec<Node>, (f32, f32, f32)) {
    let l = build_layout(math_font, body_font, s, size);
    let metrics = (l.width, l.ascent, l.depth);
    let mut nodes = Vec::with_capacity(l.draws.len());
    for d in l.draws {
        match d {
            Draw::Text { x: dx, y: dy, run } => nodes.push(Node::Text(TextNode {
                origin: Point::new((x + dx) as f64, (baseline + dy) as f64),
                runs: vec![run],
                color,
            })),
            Draw::Fill { path } => {
                let geometry = layout::translate_path(&path, x as f64, baseline as f64);
                nodes.push(Node::Path(PathNode {
                    geometry,
                    fill: Some(color),
                    fill_rule: FillRule::NonZero,
                    stroke: None,
                }));
            }
            Draw::Stroke { path, width } => {
                let geometry = layout::translate_path(&path, x as f64, baseline as f64);
                nodes.push(Node::Path(PathNode {
                    geometry,
                    fill: None,
                    fill_rule: FillRule::NonZero,
                    stroke: Some(Stroke {
                        color,
                        width: width as f64,
                        cap: LineCap::Round,
                        join: LineJoin::Round,
                        dash: None,
                    }),
                }));
            }
        }
    }
    (nodes, metrics)
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyplotrs_core::kurbo::Shape;

    fn fonts() -> (FontData, FontData) {
        let math = include_bytes!("../../../assets/fonts/STIXTwoMath-Regular.ttf");
        let body = include_bytes!("../../../assets/fonts/LiberationSans-Regular.ttf");
        (
            FontData::from_bytes(math.to_vec(), 0),
            FontData::from_bytes(body.to_vec(), 0),
        )
    }

    /// Binary minus must be a real U+2212, never an ASCII hyphen.
    #[test]
    fn minus_is_u2212() {
        let (m, b) = fonts();
        let (nodes, _) = render(&m, &b, "$a - b$", 20.0, 0.0, 0.0, Color::rgba(0, 0, 0, 255));
        let mut text = String::new();
        for n in &nodes {
            if let Node::Text(t) = n {
                for r in &t.runs {
                    text.push_str(&r.source_text);
                }
            }
        }
        assert!(text.contains('\u{2212}'), "expected U+2212 minus in {text:?}");
        assert!(!text.contains('-'), "must not contain ASCII hyphen in {text:?}");
    }

    /// The radical rule must connect to the surd: its left edge meets the
    /// surd's top-right tip, and its top sits at the surd's ink top. This is
    /// the defect the old engine could not fix (fixed-size glyph + floating
    /// rule). Checked for short *and* tall content.
    #[test]
    fn radical_rule_connects_to_surd() {
        let (m, b) = fonts();
        for expr in ["$\\sqrt{x}$", "$\\sqrt{\\frac{a+b}{2}}$"] {
            let l = build_layout(&m, &b, expr, 24.0);
            // Collect filled-path bounding boxes (surd outline + rule rect).
            let mut boxes: Vec<pyplotrs_core::kurbo::Rect> = Vec::new();
            for d in &l.draws {
                if let Draw::Fill { path } = d {
                    boxes.push(path.bounding_box());
                }
            }
            assert!(boxes.len() >= 2, "{expr}: expected surd + rule fills");
            // Rule = thin/wide box (smallest height); surd = tallest box.
            let rule = *boxes
                .iter()
                .min_by(|a, c| a.height().partial_cmp(&c.height()).unwrap())
                .unwrap();
            let surd = *boxes
                .iter()
                .max_by(|a, c| a.height().partial_cmp(&c.height()).unwrap())
                .unwrap();
            let tol = 24.0 * 0.18; // ~4.3pt at size 24
            assert!(
                (rule.x0 - surd.x1).abs() < tol,
                "{expr}: rule left {:.2} should meet surd right {:.2}",
                rule.x0,
                surd.x1
            );
            assert!(
                (rule.y0 - surd.y0).abs() < tol,
                "{expr}: rule top {:.2} should meet surd top {:.2}",
                rule.y0,
                surd.y0
            );
        }
    }

    /// Display-style `\sum` stacks its scripts as over/under limits, so it is
    /// far taller than the same operator with inline side-scripts.
    #[test]
    fn display_sum_uses_limits() {
        let (m, b) = fonts();
        let inline = measure(&m, &b, "$\\sum_{i=1}^{N} x$", 22.0);
        let display = measure(&m, &b, "$\\displaystyle\\sum_{i=1}^{N} x$", 22.0);
        let (h_in, h_disp) = (inline.1 + inline.2, display.1 + display.2);
        assert!(
            h_disp > h_in + 6.0,
            "display sum height {h_disp:.1} should exceed inline {h_in:.1}"
        );
    }

    /// A `pmatrix` lays out all cells (real editable glyphs) and stretches its
    /// fences around them.
    #[test]
    fn matrix_lays_out_cells() {
        let (m, b) = fonts();
        let (nodes, (w, _, _)) = render(
            &m,
            &b,
            "$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$",
            22.0,
            0.0,
            0.0,
            Color::rgba(0, 0, 0, 255),
        );
        assert!(w > 0.0);
        let mut text = String::new();
        for n in &nodes {
            if let Node::Text(t) = n {
                for r in &t.runs {
                    text.push_str(&r.source_text);
                }
            }
        }
        // cells are math-italic (a→U+1D44E, b, c, d)
        for v in ['\u{1D44E}', '\u{1D44F}', '\u{1D450}', '\u{1D451}'] {
            assert!(text.contains(v), "matrix cell {v:?} missing from {text:?}");
        }
    }

    /// A radical over taller content must reserve more height (the surd
    /// stretches) — the old engine kept a fixed-size glyph.
    #[test]
    fn radical_stretches_with_content() {
        let (m, b) = fonts();
        let (_, (_, a_short, d_short)) =
            render(&m, &b, "$\\sqrt{x}$", 24.0, 0.0, 0.0, Color::rgba(0, 0, 0, 255));
        let (_, (_, a_tall, d_tall)) = render(
            &m,
            &b,
            "$\\sqrt{\\frac{a}{b}}$",
            24.0,
            0.0,
            0.0,
            Color::rgba(0, 0, 0, 255),
        );
        assert!(
            a_tall + d_tall > a_short + d_short + 4.0,
            "tall radical {:.1} should exceed short {:.1}",
            a_tall + d_tall,
            a_short + d_short
        );
    }
}
