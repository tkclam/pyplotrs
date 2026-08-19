//! Parser + boxes-and-glue layout for the TeX math subset.
//!
//! Coordinate convention (*layout space*): x to the right, **y down**, the math
//! baseline at y=0. A box reports `ascent` (extent above the baseline, a
//! positive number) and `depth` (extent below). Sub-boxes are positioned with a
//! *baseline shift* `dy` (positive = lower). Everything is driven by the
//! OpenType MATH constants exposed by [`crate::font::MathFont`].

use std::cell::RefCell;

use pyplotrs_core::kurbo::{BezPath, PathEl, Point};
use pyplotrs_core::{Color, FontData, GlyphRun, PositionedGlyph};

use crate::font::MathFont;
use crate::tables::{self, Class, Style};
use crate::MathFonts;

const MIN_SIZE: f32 = 4.0;

/// A one-glyph text run — the draw primitive behind every math atom that is a
/// plain glyph rather than a grown or assembled one.
fn single_glyph_run(font: &FontData, gid: u16, advance: f32, size: f32, ch: char) -> GlyphRun {
    GlyphRun {
        font: font.clone(),
        size,
        glyphs: vec![PositionedGlyph {
            glyph_id: gid,
            x: 0.0,
            y: 0.0,
            advance,
            cluster: 0,
        }],
        source_text: ch.to_string(),
    }
}

/// What a [`Draw`] puts on the page, in layout space.
pub enum DrawKind {
    /// An editable text run (one or more shaped glyphs) at baseline `(x, y)`.
    Text { x: f32, y: f32, run: GlyphRun },
    /// A filled vector path (fraction bars, radical rule, stretchy glyph
    /// outlines, accent dots).
    Fill { path: BezPath },
    /// A stroked vector path (accent marks).
    Stroke { path: BezPath, width: f32 },
}

/// One drawing primitive in layout space, plus the color to draw it in.
///
/// `color` is almost always `None`, meaning *inherit* - take whatever color the
/// label as a whole is being drawn in, which [`crate::render`] supplies. Only
/// `\textcolor`/`\colorbox` fill it in, and [`recolor`] only ever writes into a
/// `None`, so the innermost `\textcolor` around a draw is the one that wins.
pub struct Draw {
    pub kind: DrawKind,
    pub color: Option<Color>,
}

impl Draw {
    /// A draw that inherits the label's color - what every primitive the
    /// typesetter emits starts out as.
    fn inherit(kind: DrawKind) -> Self {
        Draw { kind, color: None }
    }

    fn text(x: f32, y: f32, run: GlyphRun) -> Self {
        Draw::inherit(DrawKind::Text { x, y, run })
    }

    fn fill(path: BezPath) -> Self {
        Draw::inherit(DrawKind::Fill { path })
    }

    fn stroke(path: BezPath, width: f32) -> Self {
        Draw::inherit(DrawKind::Stroke { path, width })
    }
}

/// Paint `color` onto every draw in `draws` that has not already been colored.
///
/// The `is_none` guard is what makes nesting behave: by the time an outer
/// `\textcolor` runs, an inner one has already claimed its own draws, and they
/// must survive. It also means an uncolored span stays `None` all the way out
/// to [`crate::render`], so a plain label still takes its color from the call.
pub(crate) fn recolor(draws: &mut [Draw], color: Color) {
    for d in draws {
        if d.color.is_none() {
            d.color = Some(color);
        }
    }
}

/// A laid-out box.
#[derive(Default)]
pub struct Layout {
    pub width: f32,
    pub ascent: f32,
    pub depth: f32,
    /// Trailing italic correction (used to shift a following superscript).
    pub italic: f32,
    /// Leading / trailing math glyph `(id, size)`, when the box begins/ends in
    /// a single math glyph — used for MATH cut-in (script) kerning.
    pub lead: Option<(u16, f32)>,
    pub trail: Option<(u16, f32)>,
    pub draws: Vec<Draw>,
}

impl Layout {
    fn empty() -> Self {
        Layout::default()
    }
}

pub(crate) fn translate_path(p: &BezPath, dx: f64, dy: f64) -> BezPath {
    let mut out = BezPath::new();
    let t = |pt: Point| Point::new(pt.x + dx, pt.y + dy);
    for el in p.elements() {
        match *el {
            PathEl::MoveTo(a) => out.move_to(t(a)),
            PathEl::LineTo(a) => out.line_to(t(a)),
            PathEl::QuadTo(a, b) => out.quad_to(t(a), t(b)),
            PathEl::CurveTo(a, b, c) => out.curve_to(t(a), t(b), t(c)),
            PathEl::ClosePath => out.close_path(),
        }
    }
    out
}

/// Append `src`'s draws into `dst`, shifted by `(dx, dy)` in layout space.
fn place(dst: &mut Vec<Draw>, src: Vec<Draw>, dx: f32, dy: f32) {
    for d in src {
        // Whatever color the draw already carries rides along untouched: a
        // `\textcolor` inside a fraction must survive being placed into the
        // fraction, and then into whatever encloses that.
        let color = d.color;
        let kind = match d.kind {
            DrawKind::Text { x, y, run } => DrawKind::Text {
                x: x + dx,
                y: y + dy,
                run,
            },
            DrawKind::Fill { path } => DrawKind::Fill {
                path: translate_path(&path, dx as f64, dy as f64),
            },
            DrawKind::Stroke { path, width } => DrawKind::Stroke {
                path: translate_path(&path, dx as f64, dy as f64),
                width,
            },
        };
        dst.push(Draw { kind, color });
    }
}

/// Horizontal box builder.
struct Hbuild {
    draws: Vec<Draw>,
    x: f32,
    ascent: f32,
    depth: f32,
    italic: f32,
    lead: Option<(u16, f32)>,
    trail: Option<(u16, f32)>,
    started: bool,
}

impl Hbuild {
    fn new() -> Self {
        Hbuild {
            draws: Vec::new(),
            x: 0.0,
            ascent: 0.0,
            depth: 0.0,
            italic: 0.0,
            lead: None,
            trail: None,
            started: false,
        }
    }
    fn add(&mut self, l: Layout, dy: f32) {
        self.ascent = self.ascent.max(l.ascent - dy);
        self.depth = self.depth.max(l.depth + dy);
        self.italic = l.italic;
        if !self.started {
            self.lead = l.lead;
            self.started = true;
        }
        self.trail = l.trail;
        let w = l.width;
        place(&mut self.draws, l.draws, self.x, dy);
        self.x += w;
    }
    fn kern(&mut self, w: f32) {
        self.x += w;
        self.italic = 0.0;
        self.trail = None;
    }
    fn finish(self) -> Layout {
        Layout {
            width: self.x,
            ascent: self.ascent,
            depth: self.depth,
            italic: self.italic,
            lead: self.lead,
            trail: self.trail,
            draws: self.draws,
        }
    }
}

/// A closed rectangle in layout space `[x0,x1] × [y0,y1]` (y-down).
fn rect_path(x0: f32, y0: f32, x1: f32, y1: f32) -> BezPath {
    let mut p = BezPath::new();
    p.move_to((x0 as f64, y0 as f64));
    p.line_to((x1 as f64, y0 as f64));
    p.line_to((x1 as f64, y1 as f64));
    p.line_to((x0 as f64, y1 as f64));
    p.close_path();
    p
}

/// A filled rectangle in layout space `[x0,x1] × [y0,y1]` (y-down).
fn fill_rect(x0: f32, y0: f32, x1: f32, y1: f32) -> Draw {
    Draw::fill(rect_path(x0, y0, x1, y1))
}

/// Parse `#rgb` / `#rgba` / `#rrggbb` / `#rrggbbaa` into a [`Color`].
///
/// Deliberately the *only* spelling the typesetter understands - see the
/// `\textcolor` branch for why names and palette indices are resolved upstream
/// instead. The leading `#` is optional so a caller that strips it still works.
fn parse_hex_color(spec: &str) -> Option<Color> {
    let h = spec.trim().strip_prefix('#').unwrap_or(spec.trim());
    if !h.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let nyb = |i: usize| u8::from_str_radix(&h[i..i + 1], 16).ok();
    let byte = |i: usize| u8::from_str_radix(&h[i..i + 2], 16).ok();
    match h.len() {
        // Short form doubles each nibble, so `#f00` is `#ff0000`, not `#0f0000`.
        3 | 4 => {
            let c = |i: usize| nyb(i).map(|v| v << 4 | v);
            Some(Color::rgba(
                c(0)?,
                c(1)?,
                c(2)?,
                if h.len() == 4 { c(3)? } else { 255 },
            ))
        }
        6 | 8 => Some(Color::rgba(
            byte(0)?,
            byte(2)?,
            byte(4)?,
            if h.len() == 8 { byte(6)? } else { 255 },
        )),
        _ => None,
    }
}

fn stroke_poly(pts: &[(f32, f32)], width: f32, closed: bool) -> Draw {
    let mut p = BezPath::new();
    if let Some(&(x, y)) = pts.first() {
        p.move_to((x as f64, y as f64));
        for &(x, y) in &pts[1..] {
            p.line_to((x as f64, y as f64));
        }
        if closed {
            p.close_path();
        }
    }
    Draw::stroke(p, width)
}

// -- inter-atom spacing (the TeXbook table; negative = display/text only) ----

#[rustfmt::skip]
const SPACE: [[i8; 8]; 8] = [
    // r: Ord  Op  Bin  Rel Open Close Punct Inner
    [0,  1, -2, -3,  0,  0,  0, -1], // Ord
    [1,  1,  0, -3,  0,  0,  0, -1], // Op
    [-2,-2,  0,  0, -2,  0,  0, -2], // Bin
    [-3,-3,  0,  0, -3,  0,  0, -3], // Rel
    [0,  0,  0,  0,  0,  0,  0,  0], // Open
    [0,  1, -2, -3,  0,  0,  0, -1], // Close
    [-1,-1,  0, -1, -1, -1, -1, -1], // Punct
    [-1, 1, -2, -3, -1,  0, -1, -1], // Inner
];

fn class_idx(c: Class) -> usize {
    match c {
        Class::Ord => 0,
        Class::Op => 1,
        Class::Bin => 2,
        Class::Rel => 3,
        Class::Open => 4,
        Class::Close => 5,
        Class::Punct => 6,
        Class::Inner => 7,
    }
}

/// Inter-atom space (points) between classes `l` and `r` at script `level`.
fn atom_space(l: Class, r: Class, size: f32, level: usize) -> f32 {
    let v = SPACE[class_idx(l)][class_idx(r)];
    if v == 0 {
        return 0.0;
    }
    let display_only = v < 0;
    if display_only && level > 0 {
        return 0.0; // parenthesized entries vanish in script styles
    }
    // 1→thin(3mu), 2→med(4mu), 3→thick(5mu); 1mu = size/18.
    (v.unsigned_abs() as f32 + 2.0) * size / 18.0
}

struct Item {
    class: Class,
    layout: Layout,
    space: bool,
    /// `\limits`/`\nolimits` override for an operator's scripts (`None` = auto).
    limits: Option<bool>,
}

/// One body face, wrapped the same way the math font is so that an atom routed
/// to it is measured from its own outlines. It carries no MATH table, which
/// costs nothing: the only values read through it are the glyph id, advance and
/// ink box. `None` if the face fails to parse, which sends its atoms back to
/// the math font.
struct BodyFace<'a> {
    data: &'a FontData,
    face: Option<MathFont<'a>>,
}

/// Parsing + layout state.
pub struct Engine<'a> {
    mf: &'a MathFont<'a>,
    fonts: &'a MathFonts<'a>,
    /// The four body faces, indexed by [`FaceStyle::index`].
    body: [BodyFace<'a>; 4],
    /// The sans symbol face, tried between the body faces and the math font.
    symbols: Option<BodyFace<'a>>,
    /// A second math font for glyphs the primary one does not have.
    fallback: Option<(&'a MathFont<'a>, &'a FontData)>,
    chars: Vec<char>,
    /// Command names this engine did not recognize, in source order.
    ///
    /// An unknown macro is *typeset*, not refused - see the fallthrough in
    /// [`Engine::parse_command`] - because refusing mid-layout would mean
    /// threading a `Result` through every level of the builder. Recording it
    /// costs nothing and lets the caller say something, which is the part that
    /// was missing: `$\sfrac{1}{2}$` silently became the characters
    /// "sfrac12", so a reader saw the number 12 where the author meant one
    /// half, and nothing anywhere reported a problem.
    unknown: RefCell<Vec<String>>,
}

impl<'a> Engine<'a> {
    /// Command names this engine did not recognize while laying out, in source
    /// order. Meaningful only after `layout` has run.
    pub fn unknown_commands(&self) -> Vec<String> {
        self.unknown.borrow().clone()
    }

    pub fn new(
        mf: &'a MathFont<'a>,
        fallback: Option<&'a (MathFont<'a>, &'a FontData)>,
        fonts: &'a MathFonts<'a>,
        src: &str,
    ) -> Self {
        let wrap = |data: &'a FontData| BodyFace {
            data,
            face: MathFont::new(&data.data[..], data.index),
        };
        Engine {
            mf,
            fonts,
            body: std::array::from_fn(|i| wrap(fonts.face_at(i))),
            symbols: fonts.symbol_font().map(wrap),
            fallback: fallback.map(|(f, d)| (f, *d)),
            chars: src.chars().collect(),
            unknown: RefCell::new(Vec::new()),
        }
    }

    /// The math face that will draw `ch`: the primary math font when it has the
    /// glyph, else the fallback.
    ///
    /// Only *glyphs* are sourced this way. Every positioning constant still
    /// comes from `self.mf`, so a span is laid out to one font's metrics even
    /// when two supply its marks — which is what keeps a fallback `\bigcup`
    /// sitting on the same axis as the `\sum` beside it.
    fn math_face(&self, ch: char) -> (&MathFont<'a>, &'a FontData) {
        let primary = (self.mf, self.fonts.math_font());
        if self.mf.glyph(ch).is_some_and(|g| g != 0) {
            return primary;
        }
        match self.fallback {
            Some((face, data)) if face.glyph(ch).is_some_and(|g| g != 0) => (face, data),
            _ => primary,
        }
    }

    /// The ambient body face — what upright atoms and `\text` runs are set in.
    fn ambient(&self) -> &BodyFace<'a> {
        &self.body[self.fonts.ambient().index()]
    }

    /// Lay out the whole (math) source at `size`.
    pub fn layout(&self, size: f32) -> Layout {
        let items = self.parse_items(0, self.chars.len(), size, Style::Default, 0, false);
        self.assemble(items, size, 0)
    }

    // ---- glyph boxes ---------------------------------------------------

    /// The box for `ch` under alphabet `style`.
    ///
    /// [`tables::place_char`] names the codepoint and the preferred face
    /// together; this walks the fallback chain from there, checking coverage at
    /// each step so that a family missing a glyph moves on rather than drawing
    /// `.notdef`:
    ///
    /// 1. the **body face** the style calls for — letters, Greek, digits, and
    ///    the operators a text family reliably carries;
    /// 2. the **sans symbol face**, for a standalone mark the body family
    ///    happens not to have (`∇`, `⇒`, `∪`), so symbol families do not split
    ///    down the middle;
    /// 3. the **math font**, which has everything and is the only face whose
    ///    MATH table can position and grow it.
    fn styled_glyph_box(&self, ch: char, style: Style, size: f32) -> Layout {
        match tables::place_char(ch, style, self.fonts.ambient(), self.fonts.fontset()) {
            tables::Placement::Body {
                ch: body_ch,
                face: body_face,
            } => self
                .plain_glyph_box(
                    &self.body[body_face.index()],
                    body_ch,
                    body_face.italic,
                    size,
                )
                .or_else(|| self.symbol_glyph_box(body_ch, size))
                .unwrap_or_else(|| self.math_glyph_box(tables::styled_char(ch, style), size)),
            tables::Placement::Math { ch, symbol } => symbol
                .then(|| self.symbol_glyph_box(ch, size))
                .flatten()
                .unwrap_or_else(|| self.math_glyph_box(ch, size)),
        }
    }

    /// `ch` from the sans symbol face, if there is one and it has the glyph.
    fn symbol_glyph_box(&self, ch: char, size: f32) -> Option<Layout> {
        self.plain_glyph_box(self.symbols.as_ref()?, ch, false, size)
    }

    /// A glyph drawn from the math font, with its MATH-table metrics.
    fn math_glyph_box(&self, ch: char, size: f32) -> Layout {
        let (face, data) = self.math_face(ch);
        let primary = std::ptr::eq(data, self.fonts.math_font());
        let gid = face.glyph(ch).unwrap_or(0);
        let adv = face.advance(gid, size);
        let ink = face.ink(gid, size);
        Layout {
            width: adv,
            ascent: ink.height(),
            depth: ink.depth(),
            italic: face.italic(gid, size),
            // `lead`/`trail` name a glyph for the *primary* font's MATH cut-in
            // kern lookup, so a fallback glyph reports neither: its id would
            // point at some unrelated glyph in that table.
            lead: primary.then_some((gid, size)),
            trail: primary.then_some((gid, size)),
            draws: vec![Draw::text(
                0.0,
                0.0,
                single_glyph_run(data, gid, adv, size, ch),
            )],
        }
    }

    /// A glyph drawn from a face with no MATH table — a body face or the sans
    /// symbol face. `None` when that face has no glyph for `ch`, which is how
    /// the caller walks to the next tier. `slanted` says whether the face leans,
    /// and so whether an italic correction has to be measured.
    fn plain_glyph_box(
        &self,
        face: &BodyFace<'a>,
        ch: char,
        slanted: bool,
        size: f32,
    ) -> Option<Layout> {
        let bmf = face.face.as_ref()?;
        let gid = bmf.glyph(ch).filter(|&g| g != 0)?;
        let adv = bmf.advance(gid, size);
        let ink = bmf.ink(gid, size);
        // The MATH table's per-glyph italic corrections and cut-in kerns are
        // keyed by *math-font* glyph ids, so a body glyph can report neither -
        // `lead`/`trail` stay `None` and its scripts attach on the plain ink
        // box. What it can report is its own ink: an italic letter's outline
        // leans out past its advance, and that overhang is exactly the quantity
        // TeX calls the italic correction - what a following superscript has to
        // clear. Measuring it beats dropping it, which set the 2 of an italic
        // `f^2` on top of the f's ascender.
        let italic = if slanted {
            (ink.x1 - adv).max(0.0)
        } else {
            0.0
        };
        Some(Layout {
            width: adv,
            ascent: ink.height(),
            depth: ink.depth(),
            italic,
            lead: None,
            trail: None,
            draws: vec![Draw::text(
                0.0,
                0.0,
                single_glyph_run(face.data, gid, adv, size, ch),
            )],
        })
    }

    /// A run of upright glyphs (function names, `\operatorname`, unknown
    /// commands), no inter-letter spacing.
    fn upright_run(&self, s: &str, size: f32) -> Layout {
        let mut hb = Hbuild::new();
        for c in s.chars() {
            hb.add(self.styled_glyph_box(c, Style::Rm, size), 0.0);
        }
        hb.finish()
    }

    /// `\text{...}`: shaped body-font run, upright, kerned.
    fn text_run(&self, s: &str, size: f32) -> Layout {
        let font = self.ambient().data;
        let run = pyplotrs_text::shape_text(font, s, size);
        let w = pyplotrs_text::run_width(&run);
        let vm = pyplotrs_text::font_vmetrics(font, size);
        Layout {
            width: w,
            ascent: vm.ascent,
            depth: vm.descent,
            draws: vec![Draw::text(0.0, 0.0, run)],
            ..Default::default()
        }
    }

    // ---- parsing -------------------------------------------------------

    fn parse_items(
        &self,
        lo: usize,
        hi: usize,
        size: f32,
        style: Style,
        level: usize,
        disp: bool,
    ) -> Vec<Item> {
        let mut items: Vec<Item> = Vec::new();
        let mut disp = disp;
        let mut i = lo;
        while i < hi {
            let c = self.chars[i];
            if c == ' ' {
                i += 1;
                continue;
            }
            // style switches and operator-limit overrides (no atoms produced)
            if c == '\\' {
                let (name, nj) = self.read_command(i);
                match name.as_str() {
                    "displaystyle" => {
                        disp = true;
                        i = nj;
                        continue;
                    }
                    "textstyle" | "scriptstyle" | "scriptscriptstyle" => {
                        disp = false;
                        i = nj;
                        continue;
                    }
                    "limits" => {
                        if let Some(l) = items.last_mut() {
                            l.limits = Some(true);
                        }
                        i = nj;
                        continue;
                    }
                    "nolimits" => {
                        if let Some(l) = items.last_mut() {
                            l.limits = Some(false);
                        }
                        i = nj;
                        continue;
                    }
                    _ => {}
                }
            }
            if c == '^' || c == '_' {
                let (nucleus, ncls, nlim) = match items.pop() {
                    Some(it) => (it.layout, it.class, it.limits),
                    None => (Layout::empty(), Class::Ord, None),
                };
                let (mut sup, mut sub) = (None, None);
                let (csize, clevel) = self.script_child(size, level);
                let (arg_lo, arg_hi, ni) = self.read_arg(i + 1, hi);
                let l = self.assemble(
                    self.parse_items(arg_lo, arg_hi, csize, style, clevel, false),
                    csize,
                    clevel,
                );
                if c == '^' {
                    sup = Some(l)
                } else {
                    sub = Some(l)
                }
                i = ni;
                // optional second script of the other kind
                let mut j = i;
                while j < hi && self.chars[j] == ' ' {
                    j += 1;
                }
                if j < hi && (self.chars[j] == '^' || self.chars[j] == '_') {
                    let other = self.chars[j];
                    let want_other =
                        (other == '^' && sup.is_none()) || (other == '_' && sub.is_none());
                    if want_other {
                        let (a_lo, a_hi, nj) = self.read_arg(j + 1, hi);
                        let l2 = self.assemble(
                            self.parse_items(a_lo, a_hi, csize, style, clevel, false),
                            csize,
                            clevel,
                        );
                        if other == '^' {
                            sup = Some(l2)
                        } else {
                            sub = Some(l2)
                        }
                        i = nj;
                    }
                }
                let use_lim = nlim.unwrap_or(ncls == Class::Op && disp);
                let scripted = if use_lim {
                    self.attach_limits(nucleus, sup, sub, size)
                } else {
                    self.attach_scripts(nucleus, sup, sub, size)
                };
                items.push(Item {
                    class: ncls,
                    layout: scripted,
                    space: false,
                    limits: None,
                });
                continue;
            }
            let (item, ni) = self.parse_atom(i, hi, size, style, level, disp);
            i = ni;
            if let Some(it) = item {
                items.push(it);
            }
        }
        items
    }

    fn parse_atom(
        &self,
        i: usize,
        hi: usize,
        size: f32,
        style: Style,
        level: usize,
        disp: bool,
    ) -> (Option<Item>, usize) {
        let c = self.chars[i];
        if c == '{' {
            let (lo, ghi, ni) = self.read_group(i);
            let l = self.assemble(
                self.parse_items(lo, ghi, size, style, level, disp),
                size,
                level,
            );
            return (
                Some(Item {
                    class: Class::Ord,
                    layout: l,
                    space: false,
                    limits: None,
                }),
                ni,
            );
        }
        if c == '\\' {
            return self.parse_command(i, hi, size, style, level, disp);
        }
        // literal character
        let class = tables::char_class(c);
        (
            Some(Item {
                class,
                layout: self.styled_glyph_box(tables::literal_char(c), style, size),
                space: false,
                limits: None,
            }),
            i + 1,
        )
    }

    fn parse_command(
        &self,
        i: usize,
        hi: usize,
        size: f32,
        style: Style,
        level: usize,
        disp: bool,
    ) -> (Option<Item>, usize) {
        let (name, mut j) = self.read_command(i);
        // structural commands
        match name.as_str() {
            "begin" => return self.parse_environment(j, hi, size, style, level, disp),
            "frac" | "binom" | "tfrac" | "dfrac" => {
                let (n_lo, n_hi, j1) = self.read_arg(j, hi);
                let (d_lo, d_hi, j2) = self.read_arg(j1, hi);
                let (csize, clevel) = self.script_child(size, level);
                let num = self.assemble(
                    self.parse_items(n_lo, n_hi, csize, style, clevel, false),
                    csize,
                    clevel,
                );
                let den = self.assemble(
                    self.parse_items(d_lo, d_hi, csize, style, clevel, false),
                    csize,
                    clevel,
                );
                let bar = name == "frac" || name == "tfrac" || name == "dfrac";
                let frac = self.make_fraction(num, den, bar, size);
                if name == "binom" {
                    let delim = self.make_delim(frac, '(', ')', size);
                    return (
                        Some(Item {
                            class: Class::Inner,
                            layout: delim,
                            space: false,
                            limits: None,
                        }),
                        j2,
                    );
                }
                return (
                    Some(Item {
                        class: Class::Ord,
                        layout: frac,
                        space: false,
                        limits: None,
                    }),
                    j2,
                );
            }
            "sqrt" => {
                // optional [index]
                let mut index = None;
                let mut k = j;
                while k < hi && self.chars[k] == ' ' {
                    k += 1;
                }
                if k < hi && self.chars[k] == '[' {
                    if let Some(close) = (k..hi).find(|&p| self.chars[p] == ']') {
                        let (isize, ilevel) = self.script_child(size, level.max(1));
                        index = Some(self.assemble(
                            self.parse_items(k + 1, close, isize, style, ilevel, false),
                            isize,
                            ilevel,
                        ));
                        j = close + 1;
                    }
                }
                let (a_lo, a_hi, jn) = self.read_arg(j, hi);
                let content = self.assemble(
                    self.parse_items(a_lo, a_hi, size, style, level, disp),
                    size,
                    level,
                );
                let rad = self.make_radical(content, index, size);
                return (
                    Some(Item {
                        class: Class::Ord,
                        layout: rad,
                        space: false,
                        limits: None,
                    }),
                    jn,
                );
            }
            "left" => {
                let (ld, j1) = self.read_delim(j, hi);
                let (inner_lo, inner_hi, rd, j2) = self.read_until_right(j1, hi);
                let content = self.assemble(
                    self.parse_items(inner_lo, inner_hi, size, style, level, disp),
                    size,
                    level,
                );
                let delim = self.make_delim(content, ld, rd, size);
                return (
                    Some(Item {
                        class: Class::Inner,
                        layout: delim,
                        space: false,
                        limits: None,
                    }),
                    j2,
                );
            }
            "right" => {
                // stray \right: skip its delimiter token
                let (_d, jn) = self.read_delim(j, hi);
                return (None, jn);
            }
            "text" => {
                let (lo, ghi, jn) = self.read_arg(j, hi);
                let s: String = self.chars[lo..ghi].iter().collect();
                return (
                    Some(Item {
                        class: Class::Ord,
                        layout: self.text_run(&s, size),
                        space: false,
                        limits: None,
                    }),
                    jn,
                );
            }
            // `\textcolor{#rrggbb}{...}` paints one sub-expression; the
            // enclosing label keeps its own color. `\colorbox{...}{...}` puts
            // that color *behind* the sub-expression instead, for highlighting
            // one term of a formula.
            //
            // The spec is hex only: color names, `"C0"` palette indices and
            // 0-1 float tuples are a theme-dependent question, and the answer
            // lives in `theme.parse_color` - so the Python layer resolves the
            // spec before the string ever reaches here. See
            // `pyplotrs.text._resolve_math_colors`.
            "textcolor" | "colorbox" => {
                let (c_lo, c_hi, j1) = self.read_arg(j, hi);
                let (a_lo, a_hi, j2) = self.read_arg(j1, hi);
                let spec: String = self.chars[c_lo..c_hi].iter().collect();
                let mut inner = self.assemble(
                    self.parse_items(a_lo, a_hi, size, style, level, disp),
                    size,
                    level,
                );
                // An unparseable spec draws the content in the ambient color
                // rather than dropping it - losing a term of an equation to a
                // typo in a color is far worse than getting its color wrong.
                if let Some(c) = parse_hex_color(&spec) {
                    if name == "colorbox" {
                        // Prepended, so the panel cannot cover glyphs that were
                        // already placed, and pre-colored so the `recolor` an
                        // enclosing `\textcolor` might run leaves it alone.
                        let pad = size * 0.1;
                        let mut draws = vec![Draw {
                            kind: DrawKind::Fill {
                                path: rect_path(
                                    -pad,
                                    -inner.ascent - pad,
                                    inner.width + pad,
                                    inner.depth + pad,
                                ),
                            },
                            color: Some(c),
                        }];
                        draws.append(&mut inner.draws);
                        inner.draws = draws;
                    } else {
                        recolor(&mut inner.draws, c);
                    }
                }
                return (
                    Some(Item {
                        class: Class::Ord,
                        layout: inner,
                        space: false,
                        limits: None,
                    }),
                    j2,
                );
            }
            _ => {}
        }
        // accents
        if let Some((kind, wide)) = tables::accent(&name) {
            let (a_lo, a_hi, jn) = self.read_arg(j, hi);
            let content = self.assemble(
                self.parse_items(a_lo, a_hi, size, style, level, disp),
                size,
                level,
            );
            return (
                Some(Item {
                    class: Class::Ord,
                    layout: self.make_accent(content, kind, wide, size),
                    space: false,
                    limits: None,
                }),
                jn,
            );
        }
        // math alphabets (\mathbf ...) and \operatorname
        if let Some(sub_style) = tables::alphabet_style(&name) {
            let (a_lo, a_hi, jn) = self.read_arg(j, hi);
            if name == "operatorname" {
                let s: String = self.chars[a_lo..a_hi].iter().collect();
                return (
                    Some(Item {
                        class: Class::Op,
                        layout: self.upright_run(&s, size),
                        space: false,
                        limits: None,
                    }),
                    jn,
                );
            }
            let l = self.assemble(
                self.parse_items(a_lo, a_hi, size, sub_style, level, disp),
                size,
                level,
            );
            return (
                Some(Item {
                    class: Class::Ord,
                    layout: l,
                    space: false,
                    limits: None,
                }),
                jn,
            );
        }
        // spacing commands
        if let Some(em) = tables::space_em(&name) {
            return (
                Some(Item {
                    class: Class::Ord,
                    layout: kern_layout(em * size),
                    space: true,
                    limits: None,
                }),
                j,
            );
        }
        // function names (upright, \mathop)
        if tables::is_function_name(&name) {
            return (
                Some(Item {
                    class: Class::Op,
                    layout: self.upright_run(&name, size),
                    space: false,
                    limits: None,
                }),
                j,
            );
        }
        // named symbols
        if let Some((ch, class)) = tables::symbol(&name) {
            // Big operators (∑ ∫ ∏ …) are centered on the math axis, enlarged in
            // display style, and always drawn from the math font — a text face
            // has no variant chain to grow them with.
            let layout = if class == Class::Op {
                self.op_glyph(ch, size, disp)
            } else {
                self.styled_glyph_box(ch, style, size)
            };
            // Integrals default to side limits (\nolimits) even in display
            // style, per LaTeX convention; \limits can still override.
            let limits = if matches!(ch, '∫' | '∮' | '∬' | '∭' | '∯' | '∰') {
                Some(false)
            } else {
                None
            };
            return (
                Some(Item {
                    class,
                    layout,
                    space: false,
                    limits,
                }),
                j,
            );
        }
        // Unknown command: render its name upright, and remember that we did.
        self.unknown.borrow_mut().push(name.clone());
        (
            Some(Item {
                class: Class::Ord,
                layout: self.upright_run(&name, size),
                space: false,
                limits: None,
            }),
            j,
        )
    }

    // ---- assembling a list with inter-atom spacing ---------------------

    fn assemble(&self, mut items: Vec<Item>, size: f32, level: usize) -> Layout {
        if items.is_empty() {
            return Layout::empty();
        }
        self.reclassify_bin(&mut items);
        let mut hb = Hbuild::new();
        let mut prev: Option<Class> = None;
        for it in items {
            if it.space {
                hb.add(it.layout, 0.0);
                prev = None;
                continue;
            }
            if let Some(pc) = prev {
                let s = atom_space(pc, it.class, size, level);
                if s != 0.0 {
                    hb.kern(s);
                }
            }
            prev = Some(it.class);
            hb.add(it.layout, 0.0);
        }
        hb.finish()
    }

    /// Reclassify `Bin` atoms to `Ord` where TeX rules require (start of list,
    /// after Op/Bin/Rel/Open/Punct, or before Rel/Close/Punct / at end).
    fn reclassify_bin(&self, items: &mut [Item]) {
        let n = items.len();
        for k in 0..n {
            if items[k].class != Class::Bin || items[k].space {
                continue;
            }
            // previous non-space class
            let prev = (0..k)
                .rev()
                .find(|&p| !items[p].space)
                .map(|p| items[p].class);
            // TeXbook rule 5: a Bin with nothing usable before it - start of
            // list, or another operator/relation/open/punct - is really an Ord.
            let demote_prev = matches!(
                prev,
                None | Some(Class::Bin)
                    | Some(Class::Op)
                    | Some(Class::Rel)
                    | Some(Class::Open)
                    | Some(Class::Punct)
            );
            // next non-space class
            let next = ((k + 1)..n)
                .find(|&p| !items[p].space)
                .map(|p| items[p].class);
            let demote_next = matches!(
                next,
                None | Some(Class::Rel) | Some(Class::Close) | Some(Class::Punct)
            );
            if demote_prev || demote_next {
                items[k].class = Class::Ord;
            }
        }
    }

    // ---- scripts -------------------------------------------------------

    fn script_child(&self, size: f32, level: usize) -> (f32, usize) {
        let sp = self.mf.script_percent();
        let ssp = self.mf.script_script_percent();
        let factor = match level {
            0 => sp,
            1 => ssp / sp,
            _ => 1.0,
        };
        ((size * factor).max(MIN_SIZE), (level + 1).min(2))
    }

    /// MATH cut-in kern (points) at a script attachment: base-corner kern at
    /// the base glyph plus script-corner kern at the script glyph.
    fn cut_in(
        &self,
        base: Option<(u16, f32)>,
        bc: crate::font::Corner,
        scr: Option<(u16, f32)>,
        sc: crate::font::Corner,
        height: f32,
    ) -> f32 {
        let kb = base.map_or(0.0, |(g, s)| self.mf.math_kern(g, bc, height, s));
        let ks = scr.map_or(0.0, |(g, s)| self.mf.math_kern(g, sc, height, s));
        kb + ks
    }

    fn attach_scripts(
        &self,
        nucleus: Layout,
        sup: Option<Layout>,
        sub: Option<Layout>,
        size: f32,
    ) -> Layout {
        use crate::font::Corner::{BottomLeft, BottomRight, TopLeft, TopRight};
        let mut hb = Hbuild::new();
        let nuc_italic = nucleus.italic;
        let nuc_ascent = nucleus.ascent;
        let nuc_depth = nucleus.depth;
        let nuc_trail = nucleus.trail;
        hb.add(nucleus, 0.0);
        let sx = hb.x; // right edge of nucleus
        let space_after = self.mf.space_after_script(size);

        match (sup, sub) {
            (Some(p), Some(b)) => {
                let mut u = self
                    .mf
                    .sup_shift_up(size)
                    .max(nuc_ascent - self.mf.sup_drop_max(size));
                u = u.max(self.mf.sup_bottom_min(size) + p.depth);
                let mut v = self
                    .mf
                    .sub_shift_down(size)
                    .max(nuc_depth + self.mf.sub_drop_min(size));
                // ensure gap between sup bottom and sub top
                let gap_min = self.mf.sub_sup_gap_min(size);
                let gap = (u - p.depth) - (b.ascent - v);
                if gap < gap_min {
                    v += gap_min - gap;
                    let psi = self.mf.sup_bottom_max_with_sub(size) - (u - p.depth);
                    if psi > 0.0 {
                        u += psi;
                        v -= psi;
                    }
                }
                let (pw, pa) = (p.width, p.ascent);
                let (bw, bd) = (b.width, b.depth);
                let ksup = nuc_italic + self.cut_in(nuc_trail, TopRight, p.lead, BottomLeft, u);
                let ksub = self.cut_in(nuc_trail, BottomRight, b.lead, TopLeft, -v);
                place(&mut hb.draws, p.draws, sx + ksup, -u);
                place(&mut hb.draws, b.draws, sx + ksub, v);
                hb.ascent = hb.ascent.max(u + pa).max(nuc_ascent);
                hb.depth = hb.depth.max(v + bd).max(nuc_depth);
                hb.x = sx + (ksup + pw).max(ksub + bw) + space_after;
                hb.finish()
            }
            (Some(p), None) => {
                let mut u = self
                    .mf
                    .sup_shift_up(size)
                    .max(nuc_ascent - self.mf.sup_drop_max(size));
                u = u.max(self.mf.sup_bottom_min(size) + p.depth);
                let pw = p.width;
                let pa = p.ascent;
                let ksup = nuc_italic + self.cut_in(nuc_trail, TopRight, p.lead, BottomLeft, u);
                place(&mut hb.draws, p.draws, sx + ksup, -u);
                hb.ascent = hb.ascent.max(u + pa);
                hb.depth = hb.depth.max(nuc_depth);
                hb.x = sx + ksup + pw + space_after;
                hb.finish()
            }
            (None, Some(b)) => {
                let mut v = self
                    .mf
                    .sub_shift_down(size)
                    .max(nuc_depth + self.mf.sub_drop_min(size));
                v = v.max(b.ascent - self.mf.sub_top_max(size));
                let bw = b.width;
                let bd = b.depth;
                let ksub = self.cut_in(nuc_trail, BottomRight, b.lead, TopLeft, -v);
                place(&mut hb.draws, b.draws, sx + ksub, v);
                hb.depth = hb.depth.max(v + bd);
                hb.ascent = hb.ascent.max(nuc_ascent);
                hb.x = sx + ksub + bw + space_after;
                hb.finish()
            }
            (None, None) => hb.finish(),
        }
    }

    /// A big-operator glyph (∑ ∫ …), centered on the math axis and — in display
    /// style — grown to `displayOperatorMinHeight` via a vertical variant.
    fn op_glyph(&self, ch: char, size: f32, disp: bool) -> Layout {
        let axis = self.mf.axis_height(size);
        // The operator's own face grows it — a variant id means nothing outside
        // the font that declared it — while the target height and the axis stay
        // the primary font's, so operators from either land on the same axis.
        let (face, data) = self.math_face(ch);
        let gid = face.glyph(ch).unwrap_or(0);
        let vgid = if disp {
            face.vertical_variant(gid, size, self.mf.display_operator_min_height(size))
                .0
        } else {
            gid
        };
        let vink = face.ink(vgid, size);
        let adv = face.advance(vgid, size);
        let italic = face.italic(vgid, size);
        let s = (vink.y0 + vink.y1) / 2.0 - axis; // center the glyph on the axis
        let ascent = (vink.y1 - s).max(0.0);
        let depth = (s - vink.y0).max(0.0);
        let (draws, lead, trail) = if vgid != gid {
            (
                vec![Draw::fill(face.outline(vgid, size, 0.0, s))],
                None,
                None,
            )
        } else {
            let run = GlyphRun {
                font: data.clone(),
                size,
                glyphs: vec![PositionedGlyph {
                    glyph_id: gid,
                    x: 0.0,
                    y: 0.0,
                    advance: adv,
                    cluster: 0,
                }],
                source_text: ch.to_string(),
            };
            (
                vec![Draw::text(0.0, s, run)],
                Some((gid, size)),
                Some((gid, size)),
            )
        };
        Layout {
            width: adv,
            ascent,
            depth,
            italic,
            lead,
            trail,
            draws,
        }
    }

    /// Place scripts as over/under *limits* (display-style big operators and
    /// `\limits`), centered above and below the nucleus.
    fn attach_limits(
        &self,
        nucleus: Layout,
        sup: Option<Layout>,
        sub: Option<Layout>,
        size: f32,
    ) -> Layout {
        let width = nucleus
            .width
            .max(sup.as_ref().map_or(0.0, |l| l.width))
            .max(sub.as_ref().map_or(0.0, |l| l.width));
        let (na, nd) = (nucleus.ascent, nucleus.depth);
        let mut draws = Vec::new();
        place(
            &mut draws,
            nucleus.draws,
            (width - nucleus.width) / 2.0,
            0.0,
        );
        let mut ascent = na;
        let mut depth = nd;
        if let Some(p) = sup {
            let shift = (na + self.mf.upper_limit_gap_min(size) + p.depth)
                .max(na + self.mf.upper_limit_baseline_rise_min(size));
            let pa = p.ascent;
            place(&mut draws, p.draws, (width - p.width) / 2.0, -shift);
            ascent = ascent.max(shift + pa);
        }
        if let Some(b) = sub {
            let shift = (nd + self.mf.lower_limit_gap_min(size) + b.ascent)
                .max(nd + self.mf.lower_limit_baseline_drop_min(size));
            let bd = b.depth;
            place(&mut draws, b.draws, (width - b.width) / 2.0, shift);
            depth = depth.max(shift + bd);
        }
        Layout {
            width,
            ascent,
            depth,
            draws,
            ..Default::default()
        }
    }

    // ---- matrices / cases ----------------------------------------------

    fn parse_environment(
        &self,
        after_begin: usize,
        hi: usize,
        size: f32,
        style: Style,
        level: usize,
        disp: bool,
    ) -> (Option<Item>, usize) {
        let (nlo, nhi, j) = self.read_arg(after_begin, hi);
        let env: String = self.chars[nlo..nhi].iter().collect();
        let (blo, bhi, after) = self.read_until_end(j, hi);
        let cells = self.split_matrix(blo, bhi);
        let (left, right, left_align) = match env.as_str() {
            "pmatrix" => ('(', ')', false),
            "bmatrix" => ('[', ']', false),
            "Bmatrix" => ('{', '}', false),
            "vmatrix" => ('|', '|', false),
            "Vmatrix" => ('‖', '‖', false),
            "cases" => ('{', '.', true),
            _ => ('.', '.', false), // matrix, array, smallmatrix, ...
        };
        let rows: Vec<Vec<Layout>> = cells
            .into_iter()
            .map(|row| {
                row.into_iter()
                    .map(|(a, b)| {
                        self.assemble(
                            self.parse_items(a, b, size, style, level, disp),
                            size,
                            level,
                        )
                    })
                    .collect()
            })
            .collect();
        let grid = self.make_matrix(rows, size, left_align);
        let layout = if left == '.' && right == '.' {
            grid
        } else {
            self.make_delim(grid, left, right, size)
        };
        (
            Some(Item {
                class: Class::Inner,
                layout,
                space: false,
                limits: None,
            }),
            after,
        )
    }

    fn make_matrix(&self, rows: Vec<Vec<Layout>>, size: f32, left_align: bool) -> Layout {
        let nrows = rows.len();
        let ncols = rows.iter().map(|r| r.len()).max().unwrap_or(0);
        if nrows == 0 || ncols == 0 {
            return Layout::empty();
        }
        let mut col_w = vec![0f32; ncols];
        for r in &rows {
            for (j, c) in r.iter().enumerate() {
                col_w[j] = col_w[j].max(c.width);
            }
        }
        let row_a: Vec<f32> = rows
            .iter()
            .map(|r| r.iter().map(|c| c.ascent).fold(0.0, f32::max))
            .collect();
        let row_d: Vec<f32> = rows
            .iter()
            .map(|r| r.iter().map(|c| c.depth).fold(0.0, f32::max))
            .collect();
        let colsep = size * 0.6;
        let rowsep = size * 0.35;
        let pad = size * 0.16;
        let axis = self.mf.axis_height(size);
        let total: f32 =
            row_a.iter().chain(row_d.iter()).sum::<f32>() + rowsep * nrows.saturating_sub(1) as f32;
        let width = col_w.iter().sum::<f32>() + colsep * ncols.saturating_sub(1) as f32 + 2.0 * pad;
        let mut draws = Vec::new();
        let mut y = -axis - total / 2.0; // top edge
        for (r, row) in rows.into_iter().enumerate() {
            let baseline = y + row_a[r];
            let mut x = pad;
            for (jcol, cell) in row.into_iter().enumerate() {
                let cx = if left_align {
                    x
                } else {
                    x + (col_w[jcol] - cell.width) / 2.0
                };
                place(&mut draws, cell.draws, cx, baseline);
                x += col_w[jcol] + colsep;
            }
            y += row_a[r] + row_d[r] + rowsep;
        }
        Layout {
            width,
            ascent: axis + total / 2.0,
            depth: (total / 2.0 - axis).max(0.0),
            draws,
            ..Default::default()
        }
    }

    // ---- fractions -----------------------------------------------------

    fn make_fraction(&self, num: Layout, den: Layout, bar: bool, size: f32) -> Layout {
        let axis = self.mf.axis_height(size);
        let t = if bar {
            self.mf.fraction_rule_thickness(size)
        } else {
            0.0
        };
        let num_gap = if bar {
            self.mf.fraction_num_gap(size)
        } else {
            size * 0.05
        };
        let den_gap = if bar {
            self.mf.fraction_denom_gap(size)
        } else {
            size * 0.05
        };
        let u = self
            .mf
            .fraction_num_shift(size)
            .max(num.depth + axis + t / 2.0 + num_gap);
        let v = self
            .mf
            .fraction_denom_shift(size)
            .max(den.ascent - axis + t / 2.0 + den_gap);
        let pad = size * 0.12;
        let inner = num.width.max(den.width);
        let width = inner + 2.0 * pad;
        let num_x = pad + (inner - num.width) / 2.0;
        let den_x = pad + (inner - den.width) / 2.0;
        let mut draws = Vec::new();
        let num_a = num.ascent;
        let den_d = den.depth;
        place(&mut draws, num.draws, num_x, -u);
        place(&mut draws, den.draws, den_x, v);
        if bar {
            draws.push(fill_rect(
                pad * 0.25,
                -axis - t / 2.0,
                width - pad * 0.25,
                -axis + t / 2.0,
            ));
        }
        Layout {
            width,
            ascent: u + num_a,
            depth: v + den_d,
            italic: 0.0,
            draws,
            ..Default::default()
        }
    }

    // ---- radicals ------------------------------------------------------

    fn make_radical(&self, content: Layout, index: Option<Layout>, size: f32) -> Layout {
        let t = self.mf.radical_rule_thickness(size);
        let gap = self.mf.radical_vertical_gap(size);
        let extra = self.mf.radical_extra_ascender(size);
        let hc = content.ascent;
        let dc = content.depth;
        let target = hc + dc + gap + t;
        let (surd_face, _) = self.math_face('√');
        let surd_gid = surd_face.glyph('√').unwrap_or(0);
        let (vgid, _vh) = surd_face.vertical_variant(surd_gid, size, target);
        let vink = surd_face.ink(vgid, size);
        let va = surd_face.advance(vgid, size);
        let glyph_h = vink.y1 - vink.y0;
        // place surd so its ink top sits at the rule top: -(hc + gap + t)
        let s = vink.y1 - (hc + gap + t);
        // index overhang on the left
        let lead = match &index {
            Some(idx) => {
                (idx.width + self.mf.radical_kern_before(size) + self.mf.radical_kern_after(size))
                    .max(0.0)
            }
            None => 0.0,
        };
        let mut draws = Vec::new();
        draws.push(Draw::fill(surd_face.outline(vgid, size, lead, s)));
        // overbar rule, connecting at the surd's advance width
        let rx0 = lead + va;
        draws.push(fill_rect(
            rx0,
            -(hc + gap + t),
            rx0 + content.width,
            -(hc + gap),
        ));
        // content under the bar
        let cw = content.width;
        place(&mut draws, content.draws, rx0, 0.0);
        if let Some(idx) = index {
            // degree sits in the crook, raised by a fraction of the surd height
            let raise = self.mf.radical_degree_raise() * (hc + gap + t) + idx.depth;
            let idx_w = idx.width;
            let ix = (lead - self.mf.radical_kern_after(size).max(0.0) - idx_w).max(0.0);
            place(&mut draws, idx.draws, ix, -raise);
        }
        Layout {
            width: lead + va + cw,
            ascent: hc + gap + t + extra,
            depth: dc.max(glyph_h - (hc + gap + t)),
            italic: 0.0,
            draws,
            ..Default::default()
        }
    }

    // ---- delimiters ----------------------------------------------------

    fn make_delim(&self, content: Layout, left: char, right: char, size: f32) -> Layout {
        let axis = self.mf.axis_height(size);
        let hc = content.ascent;
        let dc = content.depth;
        let delta = (hc - axis).max(dc + axis).max(0.0);
        let target = 2.0 * delta;
        let pad = size * 0.05;
        let mut hb = Hbuild::new();
        if left != '.' {
            hb.add(self.stretchy_delim(left, size, target, axis), 0.0);
            hb.kern(pad);
        }
        hb.add(content, 0.0);
        if right != '.' {
            hb.kern(pad);
            hb.add(self.stretchy_delim(right, size, target, axis), 0.0);
        }
        hb.finish()
    }

    /// A delimiter glyph grown to ~`target` height and centered on the math
    /// `axis`. A genuine size variant is emitted as a filled outline (no plain
    /// codepoint); the base glyph stays editable text.
    fn stretchy_delim(&self, ch: char, size: f32, target: f32, axis: f32) -> Layout {
        let (face, data) = self.math_face(ch);
        let gid = face.glyph(ch).unwrap_or(0);
        let (vgid, _vh) = face.vertical_variant(gid, size, target);
        let vink = face.ink(vgid, size);
        let adv = face.advance(vgid, size);
        let s = (vink.y0 + vink.y1) / 2.0 - axis;
        let ascent = (vink.y1 - s).max(0.0);
        let depth = (s - vink.y0).max(0.0);
        let draws = if vgid != gid {
            vec![Draw::fill(face.outline(vgid, size, 0.0, s))]
        } else {
            let run = GlyphRun {
                font: data.clone(),
                size,
                glyphs: vec![PositionedGlyph {
                    glyph_id: gid,
                    x: 0.0,
                    y: 0.0,
                    advance: adv,
                    cluster: 0,
                }],
                source_text: ch.to_string(),
            };
            vec![Draw::text(0.0, s, run)]
        };
        Layout {
            width: adv,
            ascent,
            depth,
            italic: 0.0,
            draws,
            ..Default::default()
        }
    }

    // ---- accents -------------------------------------------------------

    fn make_accent(&self, content: Layout, kind: &str, wide: bool, size: f32) -> Layout {
        let gap = size * 0.05;
        let th = (size * 0.055).max(0.7);
        let ah = size * 0.16;
        let y_bot = -(content.ascent + gap);
        let y_top = y_bot - ah;
        let y_mid = (y_bot + y_top) / 2.0;
        let cw = content.width;
        let cx = cw / 2.0;
        let aw = if wide {
            cw.max(size * 0.4)
        } else {
            (cw * 0.9).max(size * 0.3).min(size * 0.66)
        };
        let lx = cx - aw / 2.0;
        let rx = cx + aw / 2.0;
        let mut draws = content.draws;
        let mut strokes: Vec<Draw> = Vec::new();
        match kind {
            "bar" => strokes.push(stroke_poly(&[(lx, y_bot), (rx, y_bot)], th, false)),
            "hat" => strokes.push(stroke_poly(
                &[(lx, y_bot), (cx, y_top), (rx, y_bot)],
                th,
                false,
            )),
            "check" => strokes.push(stroke_poly(
                &[(lx, y_top), (cx, y_bot), (rx, y_top)],
                th,
                false,
            )),
            "vec" => {
                let hw = (aw * 0.34).min(size * 0.22);
                let hh = ah * 0.55;
                strokes.push(stroke_poly(&[(lx, y_mid), (rx, y_mid)], th, false));
                strokes.push(stroke_poly(
                    &[(rx - hw, y_mid - hh), (rx, y_mid), (rx - hw, y_mid + hh)],
                    th,
                    false,
                ));
            }
            "tilde" => strokes.push(stroke_poly(
                &[
                    (lx, y_mid),
                    (lx + aw * 0.25, y_top),
                    (cx, y_mid),
                    (rx - aw * 0.25, y_bot),
                    (rx, y_mid),
                ],
                th,
                false,
            )),
            "breve" => strokes.push(stroke_poly(
                &[
                    (lx, y_top),
                    (lx + aw * 0.22, y_bot),
                    (rx - aw * 0.22, y_bot),
                    (rx, y_top),
                ],
                th,
                false,
            )),
            "acute" => strokes.push(stroke_poly(
                &[(cx - aw * 0.28, y_bot), (cx + aw * 0.28, y_top)],
                th,
                false,
            )),
            "grave" => strokes.push(stroke_poly(
                &[(cx - aw * 0.28, y_top), (cx + aw * 0.28, y_bot)],
                th,
                false,
            )),
            "dot" | "ddot" => {
                let r = th * 1.1;
                let centers: &[f32] = if kind == "dot" {
                    &[0.0]
                } else {
                    &[-aw * 0.26, aw * 0.26]
                };
                for &off in centers {
                    let dcx = cx + off;
                    draws.push(fill_rect(dcx - r, y_mid - r, dcx + r, y_mid + r));
                }
            }
            _ => {}
        }
        draws.extend(strokes);
        Layout {
            width: cw,
            ascent: content.ascent + gap + ah,
            depth: content.depth,
            italic: 0.0,
            draws,
            ..Default::default()
        }
    }

    // ---- low-level token reading --------------------------------------

    /// Read `\command` starting at `i` (chars[i] == '\\'); returns (name, next).
    fn read_command(&self, i: usize) -> (String, usize) {
        let n = self.chars.len();
        let j = i + 1;
        if j >= n {
            return (String::new(), j);
        }
        if !self.chars[j].is_ascii_alphabetic() {
            return (self.chars[j].to_string(), j + 1);
        }
        let mut k = j;
        while k < n && self.chars[k].is_ascii_alphabetic() {
            k += 1;
        }
        (self.chars[j..k].iter().collect(), k)
    }

    /// chars[i] == '{'; returns (inner_lo, inner_hi, after_close).
    fn read_group(&self, i: usize) -> (usize, usize, usize) {
        let n = self.chars.len();
        let mut depth = 0;
        let mut j = i;
        while j < n {
            match self.chars[j] {
                '{' => depth += 1,
                '}' => {
                    depth -= 1;
                    if depth == 0 {
                        return (i + 1, j, j + 1);
                    }
                }
                _ => {}
            }
            j += 1;
        }
        (i + 1, n, n)
    }

    /// Read a single required argument; returns (lo, hi, after) into `chars`.
    fn read_arg(&self, i: usize, hi: usize) -> (usize, usize, usize) {
        let mut i = i;
        while i < hi && self.chars[i] == ' ' {
            i += 1;
        }
        if i >= hi {
            return (i, i, i);
        }
        match self.chars[i] {
            '{' => self.read_group(i),
            '\\' => {
                let (_n, j) = self.read_command(i);
                (i, j, j)
            }
            _ => (i, i + 1, i + 1),
        }
    }

    /// Read a delimiter token after `\left`/`\right`.
    fn read_delim(&self, i: usize, hi: usize) -> (char, usize) {
        let mut i = i;
        while i < hi && self.chars[i] == ' ' {
            i += 1;
        }
        if i >= hi {
            return ('.', i);
        }
        if self.chars[i] == '\\' {
            let (name, j) = self.read_command(i);
            return (tables::delimiter(&name).unwrap_or('.'), j);
        }
        let c = self.chars[i];
        (tables::delimiter(&c.to_string()).unwrap_or(c), i + 1)
    }

    /// From after `\left<delim>`, find the matching `\right`, returning
    /// (inner_lo, inner_hi, right_delim, after).
    fn read_until_right(&self, i: usize, hi: usize) -> (usize, usize, char, usize) {
        let mut depth = 0;
        let mut j = i;
        while j < hi {
            if self.chars[j] == '\\' {
                let (name, k) = self.read_command(j);
                if name == "left" {
                    depth += 1;
                } else if name == "right" {
                    if depth == 0 {
                        let (rd, k2) = self.read_delim(k, hi);
                        return (i, j, rd, k2);
                    }
                    depth -= 1;
                }
                j = k;
                continue;
            }
            j += 1;
        }
        (i, hi, '.', hi)
    }

    /// From after `\begin{env}`, return `(body_lo, body_hi, after_end)` for the
    /// matching `\end` (handling nested environments).
    fn read_until_end(&self, i: usize, hi: usize) -> (usize, usize, usize) {
        let mut depth = 0;
        let mut k = i;
        while k < hi {
            if self.chars[k] == '\\' {
                let (n, k2) = self.read_command(k);
                if n == "begin" {
                    let (_a, _b, k3) = self.read_arg(k2, hi);
                    depth += 1;
                    k = k3;
                    continue;
                } else if n == "end" {
                    let (_a, _b, k3) = self.read_arg(k2, hi);
                    if depth == 0 {
                        return (i, k, k3);
                    }
                    depth -= 1;
                    k = k3;
                    continue;
                }
                k = k2;
                continue;
            }
            k += 1;
        }
        (i, hi, hi)
    }

    /// Split a matrix body `[lo, hi)` into rows (`\\`) of cells (`&`), as char
    /// ranges, respecting brace nesting.
    fn split_matrix(&self, lo: usize, hi: usize) -> Vec<Vec<(usize, usize)>> {
        let mut rows: Vec<Vec<(usize, usize)>> = Vec::new();
        let mut row: Vec<(usize, usize)> = Vec::new();
        let mut cell_lo = lo;
        let mut depth = 0;
        let mut k = lo;
        while k < hi {
            let c = self.chars[k];
            if c == '{' {
                depth += 1;
                k += 1;
            } else if c == '}' {
                depth -= 1;
                k += 1;
            } else if depth == 0 && c == '&' {
                row.push((cell_lo, k));
                cell_lo = k + 1;
                k += 1;
            } else if depth == 0 && c == '\\' && k + 1 < hi && self.chars[k + 1] == '\\' {
                row.push((cell_lo, k));
                rows.push(std::mem::take(&mut row));
                k += 2;
                cell_lo = k;
            } else if c == '\\' {
                let (_n, k2) = self.read_command(k);
                k = k2;
            } else {
                k += 1;
            }
        }
        let tail_nonblank = (cell_lo..hi).any(|p| self.chars[p] != ' ');
        if tail_nonblank || !row.is_empty() {
            row.push((cell_lo, hi));
        }
        if !row.is_empty() {
            rows.push(row);
        }
        rows
    }
}

fn kern_layout(w: f32) -> Layout {
    Layout {
        width: w,
        ..Default::default()
    }
}

/// A shaped, kerned body-font run (for non-math segments and `\text`).
/// A plain (non-math) span, shaped with `font` and whatever of `fallbacks`
/// is needed for characters `font` cannot draw.
///
/// One `Draw` per resulting run. `shape_with_fallback` keeps glyph positions
/// absolute across the whole span, so every run is placed at the same origin
/// and the pieces line up without any bookkeeping here. The band is the
/// deepest of the faces actually used - a fallback face is rarely metrically
/// compatible with the body one, and sizing the band from the body alone
/// would clip whatever the fallback drew.
pub(crate) fn shaped_text_layout(
    font: &FontData,
    fallbacks: &[FontData],
    s: &str,
    size: f32,
) -> Layout {
    let runs = pyplotrs_text::shape_with_fallback(font, fallbacks, s, size);
    let w = runs.iter().map(pyplotrs_text::run_width).sum::<f32>();
    let mut ascent = 0.0f32;
    let mut depth = 0.0f32;
    for r in &runs {
        let vm = pyplotrs_text::font_vmetrics(&r.font, size);
        ascent = ascent.max(vm.ascent);
        depth = depth.max(vm.descent);
    }
    Layout {
        width: w,
        ascent,
        depth,
        draws: runs.into_iter().map(|r| Draw::text(0.0, 0.0, r)).collect(),
        ..Default::default()
    }
}

/// Concatenate boxes horizontally on a shared baseline.
pub(crate) fn hcat(parts: Vec<Layout>) -> Layout {
    let mut hb = Hbuild::new();
    for p in parts {
        hb.add(p, 0.0);
    }
    hb.finish()
}
