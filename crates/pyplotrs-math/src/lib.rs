//! pyplotrs-math: a faithful (LaTeX/MathJax-grade) math typesetter.
//!
//! Parses the TeX `$...$` subset and lays it out with Knuth's boxes-and-glue
//! model, driven by the **OpenType MATH table** of the math font (STIX Two
//! Math) rather than hand-tuned constants. Output is ordinary pyplotrs IR — real,
//! editable glyph runs plus filled/stroked vector paths for rules and stretchy
//! glyphs — so math stays selectable text in PDF/SVG.
//!
//! Public API: [`measure`] returns `(width, ascent, depth)`; [`render`] returns
//! the positioned [`pyplotrs_core::Node`]s plus those metrics. Both take a
//! [`MathFonts`] naming the faces a span may draw from. Plain strings with no
//! `$` are shaped as a single body-font run, so callers route every label
//! through here unconditionally.

mod font;
mod layout;
mod tables;

use pyplotrs_core::kurbo::Point;
use pyplotrs_core::{
    Color, FillRule, FontData, LineCap, LineJoin, Node, PathNode, Stroke, TextNode,
};

use font::MathFont;
use layout::{DrawKind, Layout};

/// One face of the body family: which of the four the text is set in.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Default)]
pub struct FaceStyle {
    pub bold: bool,
    pub italic: bool,
}

impl FaceStyle {
    /// Index into [`MathFonts`]'s face array.
    fn index(self) -> usize {
        (self.bold as usize) << 1 | self.italic as usize
    }
}

/// Which family a math span is set in — the analog of matplotlib's
/// `rcParams["mathtext.fontset"]`.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum FontSet {
    /// Body-face first: letters, Greek, digits and the common operators come
    /// from the figure's own (sans) family, and the math font draws only what a
    /// text face cannot — big operators, radicals, stretchy fences, and the
    /// symbols and alphabets it has no glyph for. Math then matches the labels
    /// around it, which is what matplotlib's default `dejavusans` set does.
    #[default]
    Sans,
    /// Every atom from the math font (STIX Two Math), so a span is uniformly
    /// serif. Pair it with a serif body family, or the math will not match the
    /// text beside it.
    Stix,
}

/// The faces a math span may draw from.
///
/// Four body faces rather than one because a span uses more than one at a time:
/// `$\mathbf{v} = v_x$` wants bold upright, italic, and the ambient face for
/// its digits, and resolving them all up front is what lets the layout pass
/// pick per character.
pub struct MathFonts<'a> {
    math: &'a FontData,
    /// Indexed by [`FaceStyle::index`].
    body: [&'a FontData; 4],
    /// A sans face consulted for symbols the body family lacks, before the
    /// math font. See [`Self::with_symbols`].
    symbols: Option<&'a FontData>,
    /// A second math font for what the primary one has no glyph for. See
    /// [`Self::with_math_fallback`].
    fallback: Option<&'a FontData>,
    ambient: FaceStyle,
    fontset: FontSet,
}

impl<'a> MathFonts<'a> {
    /// The math font plus the four body faces. `ambient` defaults to regular
    /// and `fontset` to [`FontSet::Sans`]; see [`Self::with_ambient`] and
    /// [`Self::with_fontset`].
    pub fn new(
        math: &'a FontData,
        regular: &'a FontData,
        bold: &'a FontData,
        italic: &'a FontData,
        bold_italic: &'a FontData,
    ) -> Self {
        // Placed by `index()` rather than written out in argument order, so the
        // slot each face lands in cannot drift from the one lookups compute.
        let style = |bold, italic| FaceStyle { bold, italic };
        let mut body = [regular; 4];
        for (face, data) in [
            (style(false, false), regular),
            (style(true, false), bold),
            (style(false, true), italic),
            (style(true, true), bold_italic),
        ] {
            body[face.index()] = data;
        }
        Self {
            math,
            body,
            symbols: None,
            fallback: None,
            ambient: FaceStyle::default(),
            fontset: FontSet::default(),
        }
    }

    /// A second math font, asked for anything the primary one has no glyph for.
    ///
    /// A sans math font is the point of the default font set, and no sans one
    /// is complete: Fira Math has no Script or Fraktur alphabet and is missing
    /// three dozen symbols. Rather than give those up — or give up sans
    /// radicals and operators to keep them — the primary draws what it has and
    /// this draws the rest.
    ///
    /// Positioning constants always come from the **primary** font, whichever
    /// face ends up supplying a glyph, so one span is laid out to one font's
    /// metrics rather than to a blend of two.
    pub fn with_math_fallback(mut self, fallback: &'a FontData) -> Self {
        self.fallback = Some(fallback);
        self
    }

    /// A sans face to try for *symbols* the body family does not carry, before
    /// falling back to the math font.
    ///
    /// It exists because coverage of the symbol blocks is ragged: a text family
    /// typically has `→ ← ↔` but not `⇒ ↦`, `∩` but not `∪`, `±` but not `∓`.
    /// Falling straight to a serif math font therefore splits families down the
    /// middle — a sans `$A \cap B$` beside a serif `$A \cup B$`. This face
    /// closes the gap in the same sans idiom.
    ///
    /// It supplies **shapes only**: glyph id, advance and ink box. Everything
    /// positional still comes from the math font's MATH table, and anything
    /// that must stretch — big operators, radicals, fences — is never asked of
    /// it. Nor are the math alphabets, whose distinct designs are the point.
    pub fn with_symbols(mut self, symbols: &'a FontData) -> Self {
        self.symbols = Some(symbols);
        self
    }

    /// The face the surrounding label is set in. Upright atoms and `\text` runs
    /// use it directly; variables use its italic companion.
    pub fn with_ambient(mut self, ambient: FaceStyle) -> Self {
        self.ambient = ambient;
        self
    }

    pub fn with_fontset(mut self, fontset: FontSet) -> Self {
        self.fontset = fontset;
        self
    }

    fn face(&self, style: FaceStyle) -> &'a FontData {
        self.body[style.index()]
    }

    pub(crate) fn face_at(&self, index: usize) -> &'a FontData {
        self.body[index]
    }

    pub(crate) fn math_font(&self) -> &'a FontData {
        self.math
    }

    pub(crate) fn symbol_font(&self) -> Option<&'a FontData> {
        self.symbols
    }

    pub(crate) fn ambient(&self) -> FaceStyle {
        self.ambient
    }

    pub(crate) fn fontset(&self) -> FontSet {
        self.fontset
    }
}

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

fn build_layout(fonts: &MathFonts, s: &str, size: f32) -> Layout {
    let ambient = fonts.face(fonts.ambient);
    let mf = MathFont::new(&fonts.math.data[..], fonts.math.index);
    let segs = split_segments(s);
    // Fast path: no math at all -> one shaped body run (kept kerned/editable).
    if !s.contains('$') || mf.is_none() {
        return layout::shaped_text_layout(ambient, s, size);
    }
    let mf = mf.unwrap();
    let fallback = fonts
        .fallback
        .and_then(|f| MathFont::new(&f.data[..], f.index).map(|face| (face, f)));
    let mut parts: Vec<Layout> = Vec::new();
    for (is_math, seg) in segs {
        if seg.is_empty() {
            continue;
        }
        if is_math {
            let engine = layout::Engine::new(&mf, fallback.as_ref(), fonts, &seg);
            parts.push(engine.layout(size));
        } else {
            parts.push(layout::shaped_text_layout(ambient, &seg, size));
        }
    }
    if parts.len() == 1 {
        parts.pop().unwrap()
    } else {
        layout::hcat(parts)
    }
}

/// Measure `s` at `size`, returning `(width, ascent, depth)` in points.
pub fn measure(fonts: &MathFonts, s: &str, size: f32) -> (f32, f32, f32) {
    let l = build_layout(fonts, s, size);
    (l.width, l.ascent, l.depth)
}

/// Lay out `s` with its left edge at `x` and baseline at `baseline`, returning
/// the scene nodes plus `(width, ascent, depth)`.
pub fn render(
    fonts: &MathFonts,
    s: &str,
    size: f32,
    x: f32,
    baseline: f32,
    color: Color,
) -> (Vec<Node>, (f32, f32, f32)) {
    let l = build_layout(fonts, s, size);
    let metrics = (l.width, l.ascent, l.depth);
    let mut nodes = Vec::with_capacity(l.draws.len());
    for d in l.draws {
        // `color` is the label's color; a draw overrides it only if a
        // `\textcolor`/`\colorbox` claimed it during layout.
        let ink = d.color.unwrap_or(color);
        match d.kind {
            DrawKind::Text { x: dx, y: dy, run } => nodes.push(Node::Text(TextNode {
                origin: Point::new((x + dx) as f64, (baseline + dy) as f64),
                runs: vec![run],
                color: ink,
            })),
            DrawKind::Fill { path } => {
                let geometry = layout::translate_path(&path, x as f64, baseline as f64);
                nodes.push(Node::Path(PathNode {
                    geometry,
                    fill: Some(ink),
                    fill_rule: FillRule::NonZero,
                    stroke: None,
                }));
            }
            DrawKind::Stroke { path, width } => {
                let geometry = layout::translate_path(&path, x as f64, baseline as f64);
                nodes.push(Node::Path(PathNode {
                    geometry,
                    fill: None,
                    fill_rule: FillRule::NonZero,
                    stroke: Some(Stroke {
                        color: ink,
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

    const BLACK: Color = Color::rgba(0, 0, 0, 255);

    /// The bundled math font plus all four Liberation Sans faces, in the order
    /// [`MathFonts::new`] wants them.
    /// Index of the sans symbol face in [`faces`].
    const SYM: usize = 5;

    fn faces() -> [FontData; 6] {
        [
            &include_bytes!("../../../assets/fonts/STIXTwoMath-Regular.ttf")[..],
            &include_bytes!("../../../assets/fonts/LiberationSans-Regular.ttf")[..],
            &include_bytes!("../../../assets/fonts/LiberationSans-Bold.ttf")[..],
            &include_bytes!("../../../assets/fonts/LiberationSans-Italic.ttf")[..],
            &include_bytes!("../../../assets/fonts/LiberationSans-BoldItalic.ttf")[..],
            &include_bytes!("../../../assets/fonts/DejaVuSans-MathSymbols.ttf")[..],
        ]
        .map(|b| FontData::from_bytes(b.to_vec(), 0))
    }

    fn fonts(f: &[FontData; 6]) -> MathFonts<'_> {
        MathFonts::new(&f[0], &f[1], &f[2], &f[3], &f[4]).with_symbols(&f[SYM])
    }

    /// The Unicode scalars of every glyph run in `nodes`, concatenated.
    fn drawn_text(nodes: &[Node]) -> String {
        let mut text = String::new();
        for n in nodes {
            if let Node::Text(t) = n {
                for r in &t.runs {
                    text.push_str(&r.source_text);
                }
            }
        }
        text
    }

    /// Which font each glyph run in `nodes` came from, as `true` for the math
    /// font. Keyed on the buffer identity, so it is exact rather than inferred.
    fn from_math_font(fonts: &MathFonts, nodes: &[Node]) -> Vec<(String, bool)> {
        let mut out = Vec::new();
        for n in nodes {
            if let Node::Text(t) = n {
                for r in &t.runs {
                    out.push((r.source_text.clone(), r.font.key() == fonts.math.key()));
                }
            }
        }
        out
    }

    /// Binary minus must be a real U+2212, never an ASCII hyphen.
    #[test]
    fn minus_is_u2212() {
        let f = faces();
        let (nodes, _) = render(&fonts(&f), "$a - b$", 20.0, 0.0, 0.0, BLACK);
        let text = drawn_text(&nodes);
        assert!(
            text.contains('\u{2212}'),
            "expected U+2212 minus in {text:?}"
        );
        assert!(
            !text.contains('-'),
            "must not contain ASCII hyphen in {text:?}"
        );
    }

    /// The radical rule must connect to the surd: its left edge meets the
    /// surd's top-right tip, and its top sits at the surd's ink top. This is
    /// the defect the old engine could not fix (fixed-size glyph + floating
    /// rule). Checked for short *and* tall content.
    #[test]
    fn radical_rule_connects_to_surd() {
        let f = faces();
        for expr in ["$\\sqrt{x}$", "$\\sqrt{\\frac{a+b}{2}}$"] {
            let l = build_layout(&fonts(&f), expr, 24.0);
            // Collect filled-path bounding boxes (surd outline + rule rect).
            let mut boxes: Vec<pyplotrs_core::kurbo::Rect> = Vec::new();
            for d in &l.draws {
                if let DrawKind::Fill { path } = &d.kind {
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
        let f = faces();
        let inline = measure(&fonts(&f), "$\\sum_{i=1}^{N} x$", 22.0);
        let display = measure(&fonts(&f), "$\\displaystyle\\sum_{i=1}^{N} x$", 22.0);
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
        let f = faces();
        let (nodes, (w, _, _)) = render(
            &fonts(&f),
            "$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$",
            22.0,
            0.0,
            0.0,
            BLACK,
        );
        assert!(w > 0.0);
        let text = drawn_text(&nodes);
        for v in ['a', 'b', 'c', 'd'] {
            assert!(text.contains(v), "matrix cell {v:?} missing from {text:?}");
        }
    }

    /// A radical over taller content must reserve more height (the surd
    /// stretches) — the old engine kept a fixed-size glyph.
    #[test]
    fn radical_stretches_with_content() {
        let f = faces();
        let (_, a_short, d_short) = measure(&fonts(&f), "$\\sqrt{x}$", 24.0);
        let (_, a_tall, d_tall) = measure(&fonts(&f), "$\\sqrt{\\frac{a}{b}}$", 24.0);
        assert!(
            a_tall + d_tall > a_short + d_short + 4.0,
            "tall radical {:.1} should exceed short {:.1}",
            a_tall + d_tall,
            a_short + d_short
        );
    }

    /// The whole point of the sans font set: one expression, one family. Every
    /// letter, Greek letter, digit and plain operator of a typical label comes
    /// from the body face — only the radical and the big operator, which need
    /// the MATH table's variant chains, are left to the math font.
    #[test]
    fn sans_fontset_draws_letters_and_greek_from_the_body_face() {
        let f = faces();
        let fonts = fonts(&f);
        let (nodes, _) = render(
            &fonts,
            "$\\sigma = \\sqrt{(x_i - \\mu)^2 / N}$",
            22.0,
            0.0,
            0.0,
            BLACK,
        );
        for (text, is_math) in from_math_font(&fonts, &nodes) {
            assert!(
                !is_math,
                "{text:?} should come from the body face, not the math font"
            );
        }
    }

    /// Variables are the *plain* letters in an italic face, not the Mathematical
    /// Alphanumeric codepoints — which is what keeps copied text readable, and
    /// what lets the body family draw them at all.
    #[test]
    fn variables_are_plain_letters_in_the_sans_fontset() {
        let f = faces();
        let (nodes, _) = render(&fonts(&f), "$E = mc^2$", 20.0, 0.0, 0.0, BLACK);
        let text = drawn_text(&nodes);
        assert_eq!(text.replace(' ', ""), "E=mc2", "got {text:?}");
    }

    /// The stix font set is the opposite promise: every atom from the math font,
    /// so a span is uniformly serif rather than uniformly sans.
    #[test]
    fn stix_fontset_draws_everything_from_the_math_font() {
        let f = faces();
        let fonts = fonts(&f).with_fontset(FontSet::Stix);
        let (nodes, _) = render(&fonts, "$E = mc^2 + \\sigma$", 20.0, 0.0, 0.0, BLACK);
        for (text, is_math) in from_math_font(&fonts, &nodes) {
            assert!(
                is_math,
                "{text:?} should come from the math font under Stix"
            );
        }
        // ...and there it is the Mathematical-Italic codepoint again.
        assert!(
            drawn_text(&nodes).contains('\u{1D438}'),
            "expected italic E"
        );
    }

    /// A bold label's math is bold throughout. Before the body faces were
    /// plumbed through, the digits and operators picked up the weight and the
    /// variables did not, so `$E = mc^2$` came out half-bold.
    #[test]
    fn bold_ambient_face_carries_into_variables() {
        let f = faces();
        let bold = fonts(&f).with_ambient(FaceStyle {
            bold: true,
            italic: false,
        });
        let (nodes, _) = render(&bold, "$E = mc^2$", 20.0, 0.0, 0.0, BLACK);
        let runs: Vec<_> = nodes
            .iter()
            .filter_map(|n| match n {
                Node::Text(t) => Some(t),
                _ => None,
            })
            .flat_map(|t| t.runs.iter())
            .collect();
        assert!(!runs.is_empty());
        for r in &runs {
            let expected = if r.source_text.chars().all(|c| c.is_ascii_alphabetic()) {
                // variables: bold italic
                f[4].key()
            } else {
                // digits and operators: bold upright
                f[2].key()
            };
            assert_eq!(
                r.font.key(),
                expected,
                "{:?} landed on the wrong face of a bold label",
                r.source_text
            );
        }
    }

    /// A body glyph carries no MATH table, so its italic correction has to come
    /// from its own ink. Without it a superscript on a leaning letter sits on
    /// top of the letter instead of clear of it.
    #[test]
    fn body_italics_report_an_italic_correction() {
        let f = faces();
        let fonts = fonts(&f);
        // `f` leans furthest, so its superscript must start further right than
        // an upright digit's does.
        let leaning = measure(&fonts, "$f^2$", 24.0).0;
        let upright = measure(&fonts, "$\\mathrm{f}^2$", 24.0).0;
        assert!(
            leaning > upright,
            "italic f^2 ({leaning:.2}) should be wider than upright f^2 ({upright:.2})"
        );
    }

    /// The face each glyph run actually came from, by buffer identity.
    fn faces_used(f: &[FontData; 6], nodes: &[Node]) -> Vec<(String, usize)> {
        let mut out = Vec::new();
        for n in nodes {
            if let Node::Text(t) = n {
                for r in &t.runs {
                    let i = f.iter().position(|d| d.key() == r.font.key()).unwrap();
                    out.push((r.source_text.clone(), i));
                }
            }
        }
        out
    }

    /// A symbol the body family lacks comes from the sans symbol face, not the
    /// serif math font. Liberation Sans has no `ℏ` and no `∇`; without this
    /// tier they arrived as Times-shaped marks in the middle of sans text.
    #[test]
    fn missing_symbols_come_from_the_sans_symbol_face() {
        let f = faces();
        let (nodes, _) = render(&fonts(&f), "$\\nabla\\hbar\\omega$", 20.0, 0.0, 0.0, BLACK);
        let used = faces_used(&f, &nodes);
        for sym in ["\u{2207}", "\u{210F}"] {
            assert!(
                used.iter().any(|(t, i)| t == sym && *i == SYM),
                "{sym:?} should come from the symbol face: {used:?}"
            );
        }
        assert!(
            used.iter().any(|(t, i)| t == "\u{03C9}" && *i == 3),
            "omega should still come from the body italic: {used:?}"
        );
    }

    /// The symbol face is asked for *symbols*, never for a math alphabet: the
    /// whole point of `\mathbb{R}` is a letterform only the math font has.
    #[test]
    fn math_alphabets_skip_the_symbol_face() {
        let f = faces();
        let (nodes, _) = render(
            &fonts(&f),
            "$\\mathbb{R}\\mathfrak{g}$",
            20.0,
            0.0,
            0.0,
            BLACK,
        );
        let used = faces_used(&f, &nodes);
        assert!(!used.is_empty());
        for (text, i) in &used {
            assert_eq!(*i, 0, "{text:?} should come from the math font");
        }
    }

    /// Big operators always come from the math font, whatever else a face may
    /// have: only its MATH table can grow them in display style, and an inline
    /// `∑` drawn from one font beside a display `∑` from another would be worse
    /// than either alone.
    #[test]
    fn big_operators_stay_in_the_math_font() {
        let f = faces();
        let (nodes, _) = render(&fonts(&f), "$\\sum_i x_i + \\int f$", 20.0, 0.0, 0.0, BLACK);
        let used = faces_used(&f, &nodes);
        for op in ["\u{2211}", "\u{222B}"] {
            assert!(
                used.iter().any(|(t, i)| t == op && *i == 0),
                "{op:?} should come from the math font: {used:?}"
            );
        }
    }

    /// Under `stix` the symbol face is not consulted either — that font set
    /// promises one face for the whole span.
    #[test]
    fn the_stix_fontset_skips_the_symbol_face() {
        let f = faces();
        let fonts = fonts(&f).with_fontset(FontSet::Stix);
        let (nodes, _) = render(&fonts, "$\\nabla\\hbar$", 20.0, 0.0, 0.0, BLACK);
        for (text, i) in faces_used(&f, &nodes) {
            assert_eq!(i, 0, "{text:?} should come from the math font under Stix");
        }
    }

    /// The primary math font draws what it has; the fallback draws the rest.
    /// Here the roles are reversed on purpose — Liberation Sans stands in as a
    /// "math font" with no `∑` — so the test states the mechanism rather than
    /// any one font's coverage.
    #[test]
    fn the_math_fallback_supplies_what_the_primary_lacks() {
        let f = faces();
        // f[1] (Liberation Sans Regular) has no U+2207; f[0] (STIX) does. No
        // symbol face here, so the fallback is the only thing that can answer.
        let fonts = MathFonts::new(&f[1], &f[1], &f[2], &f[3], &f[4]).with_math_fallback(&f[0]);
        let (nodes, _) = render(&fonts, "$\\nabla x$", 20.0, 0.0, 0.0, BLACK);
        let used = faces_used(&f, &nodes);
        assert!(
            used.iter().any(|(t, i)| t == "\u{2207}" && *i == 0),
            "nabla should fall back to the face that has it: {used:?}"
        );
    }

    /// With no fallback the primary answers everything, including with
    /// `.notdef` — the behavior every embedder that supplies one font relies on.
    #[test]
    fn the_math_fallback_is_optional() {
        let f = faces();
        let fonts = fonts(&f);
        let (nodes, _) = render(&fonts, "$\\sum x$", 20.0, 0.0, 0.0, BLACK);
        assert!(faces_used(&f, &nodes)
            .iter()
            .any(|(t, i)| t == "\u{2211}" && *i == 0));
    }

    /// With no symbol face configured the chain still ends at the math font,
    /// which is what every embedder that does not supply one relies on.
    #[test]
    fn the_symbol_face_is_optional() {
        let f = faces();
        let bare = MathFonts::new(&f[0], &f[1], &f[2], &f[3], &f[4]);
        let (nodes, _) = render(&bare, "$\\nabla\\hbar$", 20.0, 0.0, 0.0, BLACK);
        for (text, i) in faces_used(&f, &nodes) {
            assert_eq!(i, 0, "{text:?} should fall through to the math font");
        }
    }

    /// The color of every node in `nodes`, in draw order: fills and strokes
    /// report their paint, glyph runs their text color.
    fn colors(nodes: &[Node]) -> Vec<Color> {
        nodes
            .iter()
            .filter_map(|n| match n {
                Node::Text(t) => Some(t.color),
                Node::Path(p) => p.fill.or(p.stroke.as_ref().map(|s| s.color)),
                _ => None,
            })
            .collect()
    }

    /// `\textcolor` paints one sub-expression and leaves the rest of the label
    /// in the color the *caller* asked for — the whole point of pushing color
    /// down to the individual draw.
    #[test]
    fn textcolor_paints_only_its_own_subexpression() {
        let f = faces();
        let (nodes, _) = render(
            &fonts(&f),
            "$a + \\textcolor{#ff0000}{b}$",
            20.0,
            0.0,
            0.0,
            BLACK,
        );
        let seen = colors(&nodes);
        assert!(
            seen.contains(&Color::rgba(255, 0, 0, 255)),
            "expected a red draw among {seen:?}"
        );
        assert!(
            seen.contains(&BLACK),
            "the rest of the expression should stay black: {seen:?}"
        );
    }

    /// Nesting resolves innermost-first: the inner color claims its draws
    /// before the outer one gets to paint what is left.
    #[test]
    fn the_innermost_textcolor_wins() {
        let f = faces();
        let (nodes, _) = render(
            &fonts(&f),
            "$\\textcolor{#0000ff}{x + \\textcolor{#00ff00}{y}}$",
            20.0,
            0.0,
            0.0,
            BLACK,
        );
        let seen = colors(&nodes);
        assert!(
            seen.contains(&Color::rgba(0, 255, 0, 255)),
            "inner green should survive the outer blue: {seen:?}"
        );
        assert!(
            seen.contains(&Color::rgba(0, 0, 255, 255)),
            "outer blue should still paint the rest: {seen:?}"
        );
        assert!(
            !seen.contains(&BLACK),
            "nothing should be left in the ambient color: {seen:?}"
        );
    }

    /// Non-glyph draws take the color too: a fraction bar inside a
    /// `\textcolor` must not stay black while its numerator turns red.
    #[test]
    fn textcolor_reaches_rules_not_just_glyphs() {
        let f = faces();
        let (nodes, _) = render(
            &fonts(&f),
            "$\\textcolor{#ff0000}{\\frac{a}{b}}$",
            24.0,
            0.0,
            0.0,
            BLACK,
        );
        let red = Color::rgba(255, 0, 0, 255);
        let bars: Vec<_> = nodes
            .iter()
            .filter_map(|n| match n {
                Node::Path(p) => p.fill,
                _ => None,
            })
            .collect();
        assert!(
            !bars.is_empty(),
            "expected the fraction bar as a filled path"
        );
        for c in bars {
            assert_eq!(c, red, "the fraction bar kept the ambient color");
        }
    }

    /// `\colorbox` puts its panel *behind* the content: same expression, but
    /// the fill is emitted before the glyphs it sits under, and the content
    /// keeps the label's own color.
    #[test]
    fn colorbox_draws_a_panel_behind_untouched_content() {
        let f = faces();
        let (nodes, _) = render(
            &fonts(&f),
            "$\\colorbox{#ffff00}{x}$",
            20.0,
            0.0,
            0.0,
            BLACK,
        );
        let yellow = Color::rgba(255, 255, 0, 255);
        assert!(
            matches!(&nodes[0], Node::Path(p) if p.fill == Some(yellow)),
            "the panel must be the first node, so it lands under the glyphs"
        );
        assert!(
            colors(&nodes[1..]).iter().all(|c| *c == BLACK),
            "colorbox should tint the background, not the text"
        );
    }

    /// A malformed spec must not swallow the term it wraps. Losing `x` to a
    /// typo in a color would be a far worse failure than drawing it black.
    #[test]
    fn an_unparseable_color_still_draws_its_content() {
        let f = faces();
        let (nodes, _) = render(&fonts(&f), "$\\textcolor{nope}{x}$", 20.0, 0.0, 0.0, BLACK);
        assert_eq!(drawn_text(&nodes), "x");
        assert!(colors(&nodes).iter().all(|c| *c == BLACK));
    }

    /// Short hex doubles each nibble (`#f00` is red, not near-black), and the
    /// 4/8-digit forms carry alpha.
    #[test]
    fn hex_color_forms_all_parse() {
        let f = faces();
        for (spec, want) in [
            ("#f00", Color::rgba(255, 0, 0, 255)),
            ("#ff0000", Color::rgba(255, 0, 0, 255)),
            ("#f008", Color::rgba(255, 0, 0, 136)),
            ("#ff000080", Color::rgba(255, 0, 0, 128)),
        ] {
            let src = format!("$\\textcolor{{{spec}}}{{x}}$");
            let (nodes, _) = render(&fonts(&f), &src, 20.0, 0.0, 0.0, BLACK);
            assert!(
                colors(&nodes).contains(&want),
                "{spec} should parse to {want:?}, got {:?}",
                colors(&nodes)
            );
        }
    }

    /// `\mathrm` is upright in every alphabet it can reach, Greek included —
    /// `$\mathrm{\pi}$` is the constant, `$\pi$` the variable.
    #[test]
    fn mathrm_uprights_greek() {
        let f = faces();
        let fonts = fonts(&f);
        let upright = render(&fonts, "$\\mathrm{\\pi}$", 20.0, 0.0, 0.0, BLACK).0;
        let italic = render(&fonts, "$\\pi$", 20.0, 0.0, 0.0, BLACK).0;
        let face_of = |nodes: &[Node]| match &nodes[0] {
            Node::Text(t) => t.runs[0].font.key(),
            _ => panic!("expected a glyph run"),
        };
        assert_eq!(face_of(&upright), f[1].key(), "\\mathrm{{\\pi}} upright");
        assert_eq!(face_of(&italic), f[3].key(), "\\pi italic");
    }
}
