//! `MathFont`: a thin wrapper over a `ttf_parser::Face` that exposes the
//! OpenType **MATH** table (positioning constants, per-glyph italic
//! corrections, and the glyph variants/assembly used to grow radicals and
//! delimiters), with every value already scaled from font design units to
//! points. This is the data the old hand-tuned engine ignored.

use pyplotrs_core::kurbo::BezPath;
use ttf_parser::math::Table as MathTable;
use ttf_parser::{Face, GlyphId};

/// A corner of a glyph for MATH cut-in (per-glyph script) kerning.
#[derive(Clone, Copy)]
pub enum Corner {
    TopRight,
    TopLeft,
    BottomRight,
    BottomLeft,
}

/// Tight ink box of a glyph, in points, baseline at y=0, **y-up**
/// (`y1` above baseline is positive).
#[derive(Clone, Copy, Debug, Default)]
#[allow(dead_code)] // x0/x1 complete the bbox; only y-extents are needed today
pub struct Ink {
    pub x0: f32,
    pub y0: f32,
    pub x1: f32,
    pub y1: f32,
}

impl Ink {
    pub fn height(&self) -> f32 {
        self.y1.max(0.0)
    }
    pub fn depth(&self) -> f32 {
        (-self.y0).max(0.0)
    }
}

pub struct MathFont<'a> {
    face: Face<'a>,
    math: Option<MathTable<'a>>,
    upem: f32,
}

/// Collects a glyph outline into a `BezPath` in *layout space*: the glyph is
/// drawn with its left edge at `gx` and baseline-shift `s` (y-down, so font
/// y-up maps to `s - y`).
struct Outliner {
    path: BezPath,
    gx: f64,
    s: f64,
    scale: f64,
}

impl ttf_parser::OutlineBuilder for Outliner {
    fn move_to(&mut self, x: f32, y: f32) {
        self.path
            .move_to((self.gx + x as f64 * self.scale, self.s - y as f64 * self.scale));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.path
            .line_to((self.gx + x as f64 * self.scale, self.s - y as f64 * self.scale));
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        self.path.quad_to(
            (self.gx + x1 as f64 * self.scale, self.s - y1 as f64 * self.scale),
            (self.gx + x as f64 * self.scale, self.s - y as f64 * self.scale),
        );
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        self.path.curve_to(
            (self.gx + x1 as f64 * self.scale, self.s - y1 as f64 * self.scale),
            (self.gx + x2 as f64 * self.scale, self.s - y2 as f64 * self.scale),
            (self.gx + x as f64 * self.scale, self.s - y as f64 * self.scale),
        );
    }
    fn close(&mut self) {
        self.path.close_path();
    }
}

impl<'a> MathFont<'a> {
    pub fn new(data: &'a [u8], index: u32) -> Option<Self> {
        let face = Face::parse(data, index).ok()?;
        let upem = face.units_per_em() as f32;
        let math = face.tables().math;
        Some(Self { face, math, upem })
    }

    fn scale(&self, size: f32) -> f32 {
        size / self.upem
    }

    /// Glyph id for a character (`None` if the font has no glyph).
    pub fn glyph(&self, c: char) -> Option<u16> {
        self.face.glyph_index(c).map(|g| g.0)
    }

    /// Horizontal advance of a glyph, in points.
    pub fn advance(&self, gid: u16, size: f32) -> f32 {
        self.face
            .glyph_hor_advance(GlyphId(gid))
            .map(|a| a as f32 * self.scale(size))
            .unwrap_or(0.0)
    }

    /// Tight ink box of a glyph, in points (y-up, baseline 0).
    pub fn ink(&self, gid: u16, size: f32) -> Ink {
        let s = self.scale(size);
        match self.face.glyph_bounding_box(GlyphId(gid)) {
            Some(r) => Ink {
                x0: r.x_min as f32 * s,
                y0: r.y_min as f32 * s,
                x1: r.x_max as f32 * s,
                y1: r.y_max as f32 * s,
            },
            None => Ink::default(),
        }
    }

    /// MATH per-glyph cut-in kern (points) for `corner`, looked up at the
    /// script `height` (points, signed: above baseline positive). Refines
    /// super/subscript attachment beyond plain italic correction; 0 if absent.
    pub fn math_kern(&self, gid: u16, corner: Corner, height: f32, size: f32) -> f32 {
        let s = self.scale(size);
        let ki = self
            .math
            .and_then(|m| m.glyph_info)
            .and_then(|gi| gi.kern_infos)
            .and_then(|k| k.get(GlyphId(gid)));
        let Some(ki) = ki else { return 0.0 };
        let kern = match corner {
            Corner::TopRight => ki.top_right,
            Corner::TopLeft => ki.top_left,
            Corner::BottomRight => ki.bottom_right,
            Corner::BottomLeft => ki.bottom_left,
        };
        let Some(kern) = kern else { return 0.0 };
        // Kern records: `count` correction heights and `count+1` kern values.
        // Use the first value whose correction height exceeds `height`.
        let n = kern.count();
        let mut idx = n;
        for i in 0..n {
            let h = kern.height(i).map(|v| v.value as f32 * s).unwrap_or(0.0);
            if height < h {
                idx = i;
                break;
            }
        }
        kern.kern(idx).map(|v| v.value as f32 * s).unwrap_or(0.0)
    }

    /// Per-glyph italic correction (MATH table), in points; 0 if absent.
    pub fn italic(&self, gid: u16, size: f32) -> f32 {
        self.math
            .and_then(|m| m.glyph_info)
            .and_then(|gi| gi.italic_corrections)
            .and_then(|ic| ic.get(GlyphId(gid)))
            .map(|v| v.value as f32 * self.scale(size))
            .unwrap_or(0.0)
    }

    /// Outline a glyph into a `BezPath` in layout space (left edge `gx`,
    /// baseline shift `s`, y-down). Used for stretchy variant glyphs that have
    /// no plain codepoint.
    pub fn outline(&self, gid: u16, size: f32, gx: f32, s: f32) -> BezPath {
        let mut o = Outliner {
            path: BezPath::new(),
            gx: gx as f64,
            s: s as f64,
            scale: self.scale(size) as f64,
        };
        self.face.outline_glyph(GlyphId(gid), &mut o);
        o.path
    }

    /// Pick the smallest vertical glyph variant of `gid` whose height is at
    /// least `target` points. Returns `(variant_gid, height_pts)`. Falls back
    /// to the base glyph if there is no MATH variant list.
    pub fn vertical_variant(&self, gid: u16, size: f32, target: f32) -> (u16, f32) {
        let s = self.scale(size);
        let base_h = self.ink(gid, size).height() + self.ink(gid, size).depth();
        let cons = self
            .math
            .and_then(|m| m.variants)
            .and_then(|v| v.vertical_constructions.get(GlyphId(gid)));
        let Some(cons) = cons else {
            return (gid, base_h);
        };
        let mut best: Option<(u16, f32)> = None;
        for var in cons.variants {
            let h = var.advance_measurement as f32 * s;
            best = Some((var.variant_glyph.0, h));
            if h >= target {
                break;
            }
        }
        best.unwrap_or((gid, base_h))
    }

    // --- MATH positioning constants (points) ----------------------------
    // Each falls back to a fraction of the size when the font lacks a MATH
    // table (STIX Two Math always has one, so the fallback is only a guard).

    fn cval(&self, size: f32, getter: impl Fn(ttf_parser::math::Constants<'a>) -> i16, default_em: f32) -> f32 {
        match self.math.and_then(|m| m.constants) {
            Some(c) => getter(c) as f32 * self.scale(size),
            None => default_em * size,
        }
    }

    pub fn axis_height(&self, size: f32) -> f32 {
        self.cval(size, |c| c.axis_height().value, 0.25)
    }
    pub fn fraction_rule_thickness(&self, size: f32) -> f32 {
        self.cval(size, |c| c.fraction_rule_thickness().value, 0.04)
    }
    pub fn fraction_num_shift(&self, size: f32) -> f32 {
        self.cval(size, |c| c.fraction_numerator_shift_up().value, 0.4)
    }
    pub fn fraction_denom_shift(&self, size: f32) -> f32 {
        self.cval(size, |c| c.fraction_denominator_shift_down().value, 0.4)
    }
    pub fn fraction_num_gap(&self, size: f32) -> f32 {
        self.cval(size, |c| c.fraction_numerator_gap_min().value, 0.04)
    }
    pub fn fraction_denom_gap(&self, size: f32) -> f32 {
        self.cval(size, |c| c.fraction_denominator_gap_min().value, 0.04)
    }
    pub fn sup_shift_up(&self, size: f32) -> f32 {
        self.cval(size, |c| c.superscript_shift_up().value, 0.45)
    }
    pub fn sup_bottom_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.superscript_bottom_min().value, 0.125)
    }
    pub fn sup_drop_max(&self, size: f32) -> f32 {
        self.cval(size, |c| c.superscript_baseline_drop_max().value, 0.3)
    }
    pub fn sub_shift_down(&self, size: f32) -> f32 {
        self.cval(size, |c| c.subscript_shift_down().value, 0.15)
    }
    pub fn sub_top_max(&self, size: f32) -> f32 {
        self.cval(size, |c| c.subscript_top_max().value, 0.4)
    }
    pub fn sub_drop_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.subscript_baseline_drop_min().value, 0.05)
    }
    pub fn sub_sup_gap_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.sub_superscript_gap_min().value, 0.2)
    }
    pub fn sup_bottom_max_with_sub(&self, size: f32) -> f32 {
        self.cval(size, |c| c.superscript_bottom_max_with_subscript().value, 0.35)
    }
    pub fn space_after_script(&self, size: f32) -> f32 {
        self.cval(size, |c| c.space_after_script().value, 0.04)
    }
    pub fn radical_vertical_gap(&self, size: f32) -> f32 {
        self.cval(size, |c| c.radical_vertical_gap().value, 0.05)
    }
    pub fn radical_rule_thickness(&self, size: f32) -> f32 {
        self.cval(size, |c| c.radical_rule_thickness().value, 0.04)
    }
    pub fn radical_extra_ascender(&self, size: f32) -> f32 {
        self.cval(size, |c| c.radical_extra_ascender().value, 0.04)
    }
    pub fn radical_kern_before(&self, size: f32) -> f32 {
        self.cval(size, |c| c.radical_kern_before_degree().value, 0.05)
    }
    pub fn radical_kern_after(&self, size: f32) -> f32 {
        self.cval(size, |c| c.radical_kern_after_degree().value, -0.1)
    }
    pub fn upper_limit_gap_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.upper_limit_gap_min().value, 0.1)
    }
    pub fn upper_limit_baseline_rise_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.upper_limit_baseline_rise_min().value, 0.15)
    }
    pub fn lower_limit_gap_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.lower_limit_gap_min().value, 0.1)
    }
    pub fn lower_limit_baseline_drop_min(&self, size: f32) -> f32 {
        self.cval(size, |c| c.lower_limit_baseline_drop_min().value, 0.3)
    }

    /// Minimum height (points) of n-ary operators in display style.
    pub fn display_operator_min_height(&self, size: f32) -> f32 {
        self.math
            .and_then(|m| m.constants)
            .map(|c| c.display_operator_min_height() as f32 * self.scale(size))
            .filter(|&h| h > 0.0)
            .unwrap_or(size * 1.4)
    }

    /// `radicalDegreeBottomRaisePercent` as a fraction (e.g. 0.6).
    pub fn radical_degree_raise(&self) -> f32 {
        self.math
            .and_then(|m| m.constants)
            .map(|c| c.radical_degree_bottom_raise_percent() as f32 / 100.0)
            .unwrap_or(0.6)
    }

    /// `scriptPercentScaleDown` as a fraction (e.g. 0.7).
    pub fn script_percent(&self) -> f32 {
        self.math
            .and_then(|m| m.constants)
            .map(|c| c.script_percent_scale_down() as f32 / 100.0)
            .filter(|&p| p > 0.0)
            .unwrap_or(0.7)
    }
    /// `scriptScriptPercentScaleDown` as a fraction.
    pub fn script_script_percent(&self) -> f32 {
        self.math
            .and_then(|m| m.constants)
            .map(|c| c.script_script_percent_scale_down() as f32 / 100.0)
            .filter(|&p| p > 0.0)
            .unwrap_or(0.5)
    }
}
