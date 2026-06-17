//! figurs-text: a thin wrapper around `rustybuzz` for shaping text into
//! [`figurs_core::GlyphRun`]s.
//!
//! Shaping happens once, here, producing exact glyph IDs and positions that
//! every backend (PDF, raster, SVG) consumes identically.

use figurs_core::{FontData, GlyphRun, PositionedGlyph};
use rustybuzz::{Direction, Face, UnicodeBuffer};
use std::path::Path;

/// Load a font file from disk into [`FontData`] (face index 0).
pub fn load_font_file(path: &Path) -> std::io::Result<FontData> {
    let data = std::fs::read(path)?;
    Ok(FontData::from_bytes(data, 0))
}

/// Shape `text` at the given `size` (in points) using `font`, returning a
/// [`GlyphRun`] with absolute glyph positions/advances scaled to `size`.
pub fn shape_text(font: &FontData, text: &str, size: f32) -> GlyphRun {
    let face = Face::from_slice(&font.data, font.index).expect("invalid font data");
    let units_per_em = face.units_per_em() as f32;
    let scale = size / units_per_em;

    let mut buffer = UnicodeBuffer::new();
    buffer.push_str(text);
    buffer.set_direction(Direction::LeftToRight);
    buffer.guess_segment_properties();

    let glyph_buffer = rustybuzz::shape(&face, &[], buffer);

    let mut glyphs = Vec::new();
    let mut cursor_x: f32 = 0.0;
    let mut cursor_y: f32 = 0.0;
    for (info, pos) in glyph_buffer
        .glyph_infos()
        .iter()
        .zip(glyph_buffer.glyph_positions())
    {
        let x = cursor_x + pos.x_offset as f32 * scale;
        let y = cursor_y + pos.y_offset as f32 * scale;
        let advance = pos.x_advance as f32 * scale;
        glyphs.push(PositionedGlyph {
            glyph_id: info.glyph_id as u16,
            x,
            y,
            advance,
            cluster: info.cluster,
        });
        cursor_x += advance;
        cursor_y += pos.y_advance as f32 * scale;
    }

    GlyphRun {
        font: font.clone(),
        size,
        glyphs,
        source_text: text.to_string(),
    }
}

/// Total horizontal advance of a shaped run, in points.
pub fn run_width(run: &GlyphRun) -> f32 {
    run.glyphs.iter().map(|g| g.advance).sum()
}

/// Vertical font metrics, scaled to a given size (points).
#[derive(Debug, Clone, Copy)]
pub struct VMetrics {
    /// Distance from baseline up to the top of the ascenders (positive).
    pub ascent: f32,
    /// Distance from baseline down to the bottom of the descenders (positive).
    pub descent: f32,
    /// Recommended extra leading between lines.
    pub line_gap: f32,
}

impl VMetrics {
    /// Total line height: ascent + descent + line gap.
    pub fn line_height(&self) -> f32 {
        self.ascent + self.descent + self.line_gap
    }
}

/// Vertical metrics for `font` at `size` (points). These are font-global (not
/// dependent on any particular string), so the layout engine can reserve
/// label band heights before knowing the exact text. `descent` is returned as
/// a positive magnitude.
pub fn font_vmetrics(font: &FontData, size: f32) -> VMetrics {
    let face = Face::from_slice(&font.data, font.index).expect("invalid font data");
    let upem = face.units_per_em() as f32;
    let scale = size / upem;
    VMetrics {
        ascent: face.ascender() as f32 * scale,
        descent: -(face.descender() as f32) * scale,
        line_gap: face.line_gap() as f32 * scale,
    }
}
