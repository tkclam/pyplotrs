//! Parser + boxes-and-glue layout for the TeX math subset.
//!
//! Coordinate convention (*layout space*): x to the right, **y down**, the math
//! baseline at y=0. A box reports `ascent` (extent above the baseline, a
//! positive number) and `depth` (extent below). Sub-boxes are positioned with a
//! *baseline shift* `dy` (positive = lower). Everything is driven by the
//! OpenType MATH constants exposed by [`crate::font::MathFont`].

use pyplotrs_core::kurbo::{BezPath, PathEl, Point};
use pyplotrs_core::{FontData, GlyphRun, PositionedGlyph};

use crate::font::MathFont;
use crate::tables::{self, Class, Style};

const MIN_SIZE: f32 = 4.0;

/// One drawing primitive in layout space.
pub enum Draw {
    /// An editable text run (one or more shaped glyphs) at baseline `(x, y)`.
    Text { x: f32, y: f32, run: GlyphRun },
    /// A filled vector path (fraction bars, radical rule, stretchy glyph
    /// outlines, accent dots), filled with the current text colour.
    Fill { path: BezPath },
    /// A stroked vector path (accent marks), stroked with the text colour.
    Stroke { path: BezPath, width: f32 },
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
        match d {
            Draw::Text { x, y, run } => dst.push(Draw::Text { x: x + dx, y: y + dy, run }),
            Draw::Fill { path } => {
                dst.push(Draw::Fill { path: translate_path(&path, dx as f64, dy as f64) })
            }
            Draw::Stroke { path, width } => dst.push(Draw::Stroke {
                path: translate_path(&path, dx as f64, dy as f64),
                width,
            }),
        }
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

/// A filled rectangle in layout space `[x0,x1] × [y0,y1]` (y-down).
fn fill_rect(x0: f32, y0: f32, x1: f32, y1: f32) -> Draw {
    let mut p = BezPath::new();
    p.move_to((x0 as f64, y0 as f64));
    p.line_to((x1 as f64, y0 as f64));
    p.line_to((x1 as f64, y1 as f64));
    p.line_to((x0 as f64, y1 as f64));
    p.close_path();
    Draw::Fill { path: p }
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
    Draw::Stroke { path: p, width }
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
        Class::Ord => 0, Class::Op => 1, Class::Bin => 2, Class::Rel => 3,
        Class::Open => 4, Class::Close => 5, Class::Punct => 6, Class::Inner => 7,
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
        return 0.0; // parenthesised entries vanish in script styles
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

/// Parsing + layout state.
pub struct Engine<'a> {
    mf: &'a MathFont<'a>,
    math_font: &'a FontData,
    body_font: &'a FontData,
    chars: Vec<char>,
}

impl<'a> Engine<'a> {
    pub fn new(
        mf: &'a MathFont<'a>,
        math_font: &'a FontData,
        body_font: &'a FontData,
        src: &str,
    ) -> Self {
        Engine { mf, math_font, body_font, chars: src.chars().collect() }
    }

    /// Lay out the whole (math) source at `size`.
    pub fn layout(&self, size: f32) -> Layout {
        let items = self.parse_items(0, self.chars.len(), size, Style::Default, 0, false);
        self.assemble(items, size, 0)
    }

    // ---- glyph boxes ---------------------------------------------------

    fn glyph_box(&self, ch: char, size: f32, math: bool) -> Layout {
        let font = if math { self.math_font } else { self.body_font };
        let gid = self.mf.glyph(ch).unwrap_or(0);
        let (adv, ink, italic) = if math {
            (self.mf.advance(gid, size), self.mf.ink(gid, size), self.mf.italic(gid, size))
        } else {
            // body font: shape one char for a correct advance
            let run = pyplotrs_text::shape_text(font, &ch.to_string(), size);
            let w = pyplotrs_text::run_width(&run);
            let vm = pyplotrs_text::font_vmetrics(font, size);
            return Layout {
                width: w,
                ascent: vm.ascent,
                depth: vm.descent,
                draws: vec![Draw::Text { x: 0.0, y: 0.0, run }],
                ..Default::default()
            };
        };
        let run = GlyphRun {
            font: font.clone(),
            size,
            glyphs: vec![PositionedGlyph { glyph_id: gid, x: 0.0, y: 0.0, advance: adv, cluster: 0 }],
            source_text: ch.to_string(),
        };
        Layout {
            width: adv,
            ascent: ink.height(),
            depth: ink.depth(),
            italic,
            lead: Some((gid, size)),
            trail: Some((gid, size)),
            draws: vec![Draw::Text { x: 0.0, y: 0.0, run }],
        }
    }

    /// A run of upright math-font glyphs (function names, `\operatorname`,
    /// unknown commands), no inter-letter spacing.
    fn upright_run(&self, s: &str, size: f32) -> Layout {
        let mut hb = Hbuild::new();
        for c in s.chars() {
            hb.add(self.glyph_box(c, size, true), 0.0);
        }
        hb.finish()
    }

    /// `\text{...}`: shaped body-font run, upright, kerned.
    fn text_run(&self, s: &str, size: f32) -> Layout {
        let run = pyplotrs_text::shape_text(self.body_font, s, size);
        let w = pyplotrs_text::run_width(&run);
        let vm = pyplotrs_text::font_vmetrics(self.body_font, size);
        Layout {
            width: w,
            ascent: vm.ascent,
            depth: vm.descent,
            draws: vec![Draw::Text { x: 0.0, y: 0.0, run }],
            ..Default::default()
        }
    }

    // ---- parsing -------------------------------------------------------

    fn parse_items(&self, lo: usize, hi: usize, size: f32, style: Style, level: usize, disp: bool) -> Vec<Item> {
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
                    "displaystyle" => { disp = true; i = nj; continue; }
                    "textstyle" | "scriptstyle" | "scriptscriptstyle" => { disp = false; i = nj; continue; }
                    "limits" => { if let Some(l) = items.last_mut() { l.limits = Some(true); } i = nj; continue; }
                    "nolimits" => { if let Some(l) = items.last_mut() { l.limits = Some(false); } i = nj; continue; }
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
                let l = self.assemble(self.parse_items(arg_lo, arg_hi, csize, style, clevel, false), csize, clevel);
                if c == '^' { sup = Some(l) } else { sub = Some(l) }
                i = ni;
                // optional second script of the other kind
                let mut j = i;
                while j < hi && self.chars[j] == ' ' { j += 1; }
                if j < hi && (self.chars[j] == '^' || self.chars[j] == '_') {
                    let other = self.chars[j];
                    let want_other = (other == '^' && sup.is_none()) || (other == '_' && sub.is_none());
                    if want_other {
                        let (a_lo, a_hi, nj) = self.read_arg(j + 1, hi);
                        let l2 = self.assemble(self.parse_items(a_lo, a_hi, csize, style, clevel, false), csize, clevel);
                        if other == '^' { sup = Some(l2) } else { sub = Some(l2) }
                        i = nj;
                    }
                }
                let use_lim = nlim.unwrap_or(ncls == Class::Op && disp);
                let scripted = if use_lim {
                    self.attach_limits(nucleus, sup, sub, size)
                } else {
                    self.attach_scripts(nucleus, sup, sub, size)
                };
                items.push(Item { class: ncls, layout: scripted, space: false, limits: None });
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

    fn parse_atom(&self, i: usize, hi: usize, size: f32, style: Style, level: usize, disp: bool) -> (Option<Item>, usize) {
        let c = self.chars[i];
        if c == '{' {
            let (lo, ghi, ni) = self.read_group(i);
            let l = self.assemble(self.parse_items(lo, ghi, size, style, level, disp), size, level);
            return (Some(Item { class: Class::Ord, layout: l, space: false, limits: None }), ni);
        }
        if c == '\\' {
            return self.parse_command(i, hi, size, style, level, disp);
        }
        // literal character
        let displayed = tables::styled_char_for_literal(c, style);
        let class = tables::char_class(c);
        (Some(Item { class, layout: self.glyph_box(displayed, size, true), space: false, limits: None }), i + 1)
    }

    fn parse_command(&self, i: usize, hi: usize, size: f32, style: Style, level: usize, disp: bool) -> (Option<Item>, usize) {
        let (name, mut j) = self.read_command(i);
        // structural commands
        match name.as_str() {
            "begin" => return self.parse_environment(j, hi, size, style, level, disp),
            "frac" | "binom" | "tfrac" | "dfrac" => {
                let (n_lo, n_hi, j1) = self.read_arg(j, hi);
                let (d_lo, d_hi, j2) = self.read_arg(j1, hi);
                let (csize, clevel) = self.script_child(size, level);
                let num = self.assemble(self.parse_items(n_lo, n_hi, csize, style, clevel, false), csize, clevel);
                let den = self.assemble(self.parse_items(d_lo, d_hi, csize, style, clevel, false), csize, clevel);
                let bar = name == "frac" || name == "tfrac" || name == "dfrac";
                let frac = self.make_fraction(num, den, bar, size);
                if name == "binom" {
                    let delim = self.make_delim(frac, '(', ')', size);
                    return (Some(Item { class: Class::Inner, layout: delim, space: false, limits: None }), j2);
                }
                return (Some(Item { class: Class::Ord, layout: frac, space: false, limits: None }), j2);
            }
            "sqrt" => {
                // optional [index]
                let mut index = None;
                let mut k = j;
                while k < hi && self.chars[k] == ' ' { k += 1; }
                if k < hi && self.chars[k] == '[' {
                    if let Some(close) = (k..hi).find(|&p| self.chars[p] == ']') {
                        let (isize, ilevel) = self.script_child(size, level.max(1));
                        index = Some(self.assemble(
                            self.parse_items(k + 1, close, isize, style, ilevel, false), isize, ilevel,
                        ));
                        j = close + 1;
                    }
                }
                let (a_lo, a_hi, jn) = self.read_arg(j, hi);
                let content = self.assemble(self.parse_items(a_lo, a_hi, size, style, level, disp), size, level);
                let rad = self.make_radical(content, index, size);
                return (Some(Item { class: Class::Ord, layout: rad, space: false, limits: None }), jn);
            }
            "left" => {
                let (ld, j1) = self.read_delim(j, hi);
                let (inner_lo, inner_hi, rd, j2) = self.read_until_right(j1, hi);
                let content = self.assemble(self.parse_items(inner_lo, inner_hi, size, style, level, disp), size, level);
                let delim = self.make_delim(content, ld, rd, size);
                return (Some(Item { class: Class::Inner, layout: delim, space: false, limits: None }), j2);
            }
            "right" => {
                // stray \right: skip its delimiter token
                let (_d, jn) = self.read_delim(j, hi);
                return (None, jn);
            }
            "text" => {
                let (lo, ghi, jn) = self.read_arg(j, hi);
                let s: String = self.chars[lo..ghi].iter().collect();
                return (Some(Item { class: Class::Ord, layout: self.text_run(&s, size), space: false, limits: None }), jn);
            }
            _ => {}
        }
        // accents
        if let Some((kind, wide)) = tables::accent(&name) {
            let (a_lo, a_hi, jn) = self.read_arg(j, hi);
            let content = self.assemble(self.parse_items(a_lo, a_hi, size, style, level, disp), size, level);
            return (Some(Item { class: Class::Ord, layout: self.make_accent(content, kind, wide, size), space: false, limits: None }), jn);
        }
        // math alphabets (\mathbf ...) and \operatorname
        if let Some(sub_style) = tables::alphabet_style(&name) {
            let (a_lo, a_hi, jn) = self.read_arg(j, hi);
            if name == "operatorname" {
                let s: String = self.chars[a_lo..a_hi].iter().collect();
                return (Some(Item { class: Class::Op, layout: self.upright_run(&s, size), space: false, limits: None }), jn);
            }
            let l = self.assemble(self.parse_items(a_lo, a_hi, size, sub_style, level, disp), size, level);
            return (Some(Item { class: Class::Ord, layout: l, space: false, limits: None }), jn);
        }
        // spacing commands
        if let Some(em) = tables::space_em(&name) {
            return (Some(Item { class: Class::Ord, layout: kern_layout(em * size), space: true, limits: None }), j);
        }
        // function names (upright, \mathop)
        if tables::is_function_name(&name) {
            return (Some(Item { class: Class::Op, layout: self.upright_run(&name, size), space: false, limits: None }), j);
        }
        // named symbols
        if let Some((ch, class)) = tables::symbol(&name) {
            // Big operators (∑ ∫ ∏ …) are centred on the math axis and enlarged
            // in display style; everything else is an ordinary glyph.
            let layout = if class == Class::Op {
                self.op_glyph(ch, size, disp)
            } else {
                self.glyph_box(tables::math_italic(ch), size, true)
            };
            // Integrals default to side limits (\nolimits) even in display
            // style, per LaTeX convention; \limits can still override.
            let limits = if matches!(ch, '∫' | '∮' | '∬' | '∭' | '∯' | '∰') {
                Some(false)
            } else {
                None
            };
            return (Some(Item { class, layout, space: false, limits }), j);
        }
        // unknown command: render its name upright
        (Some(Item { class: Class::Ord, layout: self.upright_run(&name, size), space: false, limits: None }), j)
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
            let prev = (0..k).rev().find(|&p| !items[p].space).map(|p| items[p].class);
            let demote_prev = match prev {
                None => true,
                Some(Class::Bin) | Some(Class::Op) | Some(Class::Rel) | Some(Class::Open) | Some(Class::Punct) => true,
                _ => false,
            };
            // next non-space class
            let next = ((k + 1)..n).find(|&p| !items[p].space).map(|p| items[p].class);
            let demote_next = matches!(next, None | Some(Class::Rel) | Some(Class::Close) | Some(Class::Punct));
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

    fn attach_scripts(&self, nucleus: Layout, sup: Option<Layout>, sub: Option<Layout>, size: f32) -> Layout {
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
                let mut u = self.mf.sup_shift_up(size).max(nuc_ascent - self.mf.sup_drop_max(size));
                u = u.max(self.mf.sup_bottom_min(size) + p.depth);
                let mut v = self.mf.sub_shift_down(size).max(nuc_depth + self.mf.sub_drop_min(size));
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
                let mut u = self.mf.sup_shift_up(size).max(nuc_ascent - self.mf.sup_drop_max(size));
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
                let mut v = self.mf.sub_shift_down(size).max(nuc_depth + self.mf.sub_drop_min(size));
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

    /// A big-operator glyph (∑ ∫ …), centred on the math axis and — in display
    /// style — grown to `displayOperatorMinHeight` via a vertical variant.
    fn op_glyph(&self, ch: char, size: f32, disp: bool) -> Layout {
        let axis = self.mf.axis_height(size);
        let gid = self.mf.glyph(ch).unwrap_or(0);
        let vgid = if disp {
            self.mf
                .vertical_variant(gid, size, self.mf.display_operator_min_height(size))
                .0
        } else {
            gid
        };
        let vink = self.mf.ink(vgid, size);
        let adv = self.mf.advance(vgid, size);
        let italic = self.mf.italic(vgid, size);
        let s = (vink.y0 + vink.y1) / 2.0 - axis; // centre the glyph on the axis
        let ascent = (vink.y1 - s).max(0.0);
        let depth = (s - vink.y0).max(0.0);
        let (draws, lead, trail) = if vgid != gid {
            (vec![Draw::Fill { path: self.mf.outline(vgid, size, 0.0, s) }], None, None)
        } else {
            let run = GlyphRun {
                font: self.math_font.clone(),
                size,
                glyphs: vec![PositionedGlyph { glyph_id: gid, x: 0.0, y: 0.0, advance: adv, cluster: 0 }],
                source_text: ch.to_string(),
            };
            (vec![Draw::Text { x: 0.0, y: s, run }], Some((gid, size)), Some((gid, size)))
        };
        Layout { width: adv, ascent, depth, italic, lead, trail, draws }
    }

    /// Place scripts as over/under *limits* (display-style big operators and
    /// `\limits`), centred above and below the nucleus.
    fn attach_limits(&self, nucleus: Layout, sup: Option<Layout>, sub: Option<Layout>, size: f32) -> Layout {
        let width = nucleus
            .width
            .max(sup.as_ref().map_or(0.0, |l| l.width))
            .max(sub.as_ref().map_or(0.0, |l| l.width));
        let (na, nd) = (nucleus.ascent, nucleus.depth);
        let mut draws = Vec::new();
        place(&mut draws, nucleus.draws, (width - nucleus.width) / 2.0, 0.0);
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
        Layout { width, ascent, depth, draws, ..Default::default() }
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
                    .map(|(a, b)| self.assemble(self.parse_items(a, b, size, style, level, disp), size, level))
                    .collect()
            })
            .collect();
        let grid = self.make_matrix(rows, size, left_align);
        let layout = if left == '.' && right == '.' {
            grid
        } else {
            self.make_delim(grid, left, right, size)
        };
        (Some(Item { class: Class::Inner, layout, space: false, limits: None }), after)
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
        let row_a: Vec<f32> = rows.iter().map(|r| r.iter().map(|c| c.ascent).fold(0.0, f32::max)).collect();
        let row_d: Vec<f32> = rows.iter().map(|r| r.iter().map(|c| c.depth).fold(0.0, f32::max)).collect();
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
                let cx = if left_align { x } else { x + (col_w[jcol] - cell.width) / 2.0 };
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
        let t = if bar { self.mf.fraction_rule_thickness(size) } else { 0.0 };
        let num_gap = if bar { self.mf.fraction_num_gap(size) } else { size * 0.05 };
        let den_gap = if bar { self.mf.fraction_denom_gap(size) } else { size * 0.05 };
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
            draws.push(fill_rect(pad * 0.25, -axis - t / 2.0, width - pad * 0.25, -axis + t / 2.0));
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
        let surd_gid = self.mf.glyph('√').unwrap_or(0);
        let (vgid, _vh) = self.mf.vertical_variant(surd_gid, size, target);
        let vink = self.mf.ink(vgid, size);
        let va = self.mf.advance(vgid, size);
        let glyph_h = vink.y1 - vink.y0;
        // place surd so its ink top sits at the rule top: -(hc + gap + t)
        let s = vink.y1 - (hc + gap + t);
        // index overhang on the left
        let lead = match &index {
            Some(idx) => (idx.width + self.mf.radical_kern_before(size) + self.mf.radical_kern_after(size)).max(0.0),
            None => 0.0,
        };
        let mut draws = Vec::new();
        draws.push(Draw::Fill { path: self.mf.outline(vgid, size, lead, s) });
        // overbar rule, connecting at the surd's advance width
        let rx0 = lead + va;
        draws.push(fill_rect(rx0, -(hc + gap + t), rx0 + content.width, -(hc + gap)));
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

    /// A delimiter glyph grown to ~`target` height and centred on the math
    /// `axis`. A genuine size variant is emitted as a filled outline (no plain
    /// codepoint); the base glyph stays editable text.
    fn stretchy_delim(&self, ch: char, size: f32, target: f32, axis: f32) -> Layout {
        let gid = self.mf.glyph(ch).unwrap_or(0);
        let (vgid, _vh) = self.mf.vertical_variant(gid, size, target);
        let vink = self.mf.ink(vgid, size);
        let adv = self.mf.advance(vgid, size);
        let s = (vink.y0 + vink.y1) / 2.0 - axis;
        let ascent = (vink.y1 - s).max(0.0);
        let depth = (s - vink.y0).max(0.0);
        let draws = if vgid != gid {
            vec![Draw::Fill { path: self.mf.outline(vgid, size, 0.0, s) }]
        } else {
            let run = GlyphRun {
                font: self.math_font.clone(),
                size,
                glyphs: vec![PositionedGlyph { glyph_id: gid, x: 0.0, y: 0.0, advance: adv, cluster: 0 }],
                source_text: ch.to_string(),
            };
            vec![Draw::Text { x: 0.0, y: s, run }]
        };
        Layout { width: adv, ascent, depth, italic: 0.0, draws, ..Default::default() }
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
            "hat" => strokes.push(stroke_poly(&[(lx, y_bot), (cx, y_top), (rx, y_bot)], th, false)),
            "check" => strokes.push(stroke_poly(&[(lx, y_top), (cx, y_bot), (rx, y_top)], th, false)),
            "vec" => {
                let hw = (aw * 0.34).min(size * 0.22);
                let hh = ah * 0.55;
                strokes.push(stroke_poly(&[(lx, y_mid), (rx, y_mid)], th, false));
                strokes.push(stroke_poly(&[(rx - hw, y_mid - hh), (rx, y_mid), (rx - hw, y_mid + hh)], th, false));
            }
            "tilde" => strokes.push(stroke_poly(
                &[(lx, y_mid), (lx + aw * 0.25, y_top), (cx, y_mid), (rx - aw * 0.25, y_bot), (rx, y_mid)],
                th, false,
            )),
            "breve" => strokes.push(stroke_poly(
                &[(lx, y_top), (lx + aw * 0.22, y_bot), (rx - aw * 0.22, y_bot), (rx, y_top)],
                th, false,
            )),
            "acute" => strokes.push(stroke_poly(&[(cx - aw * 0.28, y_bot), (cx + aw * 0.28, y_top)], th, false)),
            "grave" => strokes.push(stroke_poly(&[(cx - aw * 0.28, y_top), (cx + aw * 0.28, y_bot)], th, false)),
            "dot" | "ddot" => {
                let r = th * 1.1;
                let centers: &[f32] = if kind == "dot" { &[0.0] } else { &[-aw * 0.26, aw * 0.26] };
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
    Layout { width: w, ..Default::default() }
}

/// A shaped, kerned body-font run (for non-math segments and `\text`).
pub(crate) fn shaped_text_layout(font: &FontData, s: &str, size: f32) -> Layout {
    let run = pyplotrs_text::shape_text(font, s, size);
    let w = pyplotrs_text::run_width(&run);
    let vm = pyplotrs_text::font_vmetrics(font, size);
    Layout {
        width: w,
        ascent: vm.ascent,
        depth: vm.descent,
        draws: vec![Draw::Text { x: 0.0, y: 0.0, run }],
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
