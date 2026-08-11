//! pyplotrs-text: a thin wrapper around `rustybuzz` for shaping text into
//! [`pyplotrs_core::GlyphRun`]s.
//!
//! Shaping happens once, here, producing exact glyph IDs and positions that
//! every backend (PDF, raster, SVG) consumes identically.

use pyplotrs_core::{FontData, GlyphRun, PositionedGlyph};
use rustybuzz::{Direction, Face, UnicodeBuffer};
use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex, OnceLock};

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

/// The four raw (unscaled, font-units) header fields `font_vmetrics` needs -
/// cheap to store, and all that's needed to answer any `size` query without
/// re-parsing the font.
#[derive(Clone, Copy)]
struct RawVMetrics {
    units_per_em: f32,
    ascender: f32,
    descender: f32,
    line_gap: f32,
}

/// Per-font-buffer cache of [`RawVMetrics`], so a layout pass that asks for
/// vertical metrics repeatedly (once per label band, per axes - a multi-panel
/// figure repeats this many times over the same one or two fonts) parses the
/// font file once rather than on every call. Keyed by buffer identity
/// (`FontData::key()`) but also *holds* a clone of the `Arc`, not just the
/// pointer: since this cache is process-lifetime (unlike the equivalent
/// per-render `HashMap<*const Vec<u8>, _>` caches used elsewhere, e.g.
/// `PdfRenderer::fonts`), a pointer-only key could alias a since-freed,
/// unrelated font's buffer reusing the same address. Holding the `Arc` pins
/// that address for as long as the cache entry lives, so the key stays
/// unambiguous.
type RawVMetricsCache = Mutex<HashMap<usize, (Arc<Vec<u8>>, RawVMetrics)>>;

/// Ceiling on live cache entries before the whole map is dropped.
///
/// Holding the `Arc` keeps the key unambiguous, but it also keeps the entire
/// font file alive - and the entry count is not bounded by the number of
/// *fonts*, it is bounded by the number of `Arc`s ever handed here.
/// `set_sans_serif` clears the body-font cache, so the next resolve mints a
/// fresh `Arc` over the same file at a new address, which is a new key and a
/// new retained copy. Measured at ~0.44 MB per `set_font_family` + `save`
/// cycle, monotonic: 300 cycles grew the process by 132 MB.
///
/// A process legitimately uses a handful of faces - four body variants plus a
/// math face is a busy figure - so anything past this is churn rather than
/// working set. Dropping the whole map rather than evicting one entry is
/// deliberate: this is pure memoization, so the only cost of being wrong is
/// re-parsing a font header, and a wholesale clear has no ordering to get
/// subtly wrong.
const MAX_VMETRICS_ENTRIES: usize = 64;

fn raw_vmetrics_cache() -> &'static RawVMetricsCache {
    static CACHE: OnceLock<RawVMetricsCache> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Vertical metrics for `font` at `size` (points). These are font-global (not
/// dependent on any particular string), so the layout engine can reserve
/// label band heights before knowing the exact text. `descent` is returned as
/// a positive magnitude.
pub fn font_vmetrics(font: &FontData, size: f32) -> VMetrics {
    let key = font.key() as usize;
    let mut cache = raw_vmetrics_cache().lock().unwrap();
    if cache.len() >= MAX_VMETRICS_ENTRIES && !cache.contains_key(&key) {
        cache.clear();
    }
    let (_, raw) = cache.entry(key).or_insert_with(|| {
        let face = Face::from_slice(&font.data, font.index).expect("invalid font data");
        let raw = RawVMetrics {
            units_per_em: face.units_per_em() as f32,
            ascender: face.ascender() as f32,
            descender: face.descender() as f32,
            line_gap: face.line_gap() as f32,
        };
        (font.data.clone(), raw)
    });
    let scale = size / raw.units_per_em;
    VMetrics {
        ascent: raw.ascender * scale,
        descent: -raw.descender * scale,
        line_gap: raw.line_gap * scale,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The bundled Liberation Sans, so the parse in `font_vmetrics` succeeds.
    fn liberation() -> Vec<u8> {
        include_bytes!("../../../assets/fonts/LiberationSans-Regular.ttf").to_vec()
    }

    #[test]
    fn the_vmetrics_cache_does_not_grow_without_bound() {
        // Every iteration builds a *fresh* `Arc` over the same bytes, which is
        // exactly what `set_sans_serif` causes: it clears the body-font cache,
        // so the next resolve allocates a new buffer at a new address, which is
        // a new key. Before the bound, each one retained a full copy of the
        // font file forever - 0.44 MB a time, 132 MB over 300 figures.
        let bytes = liberation();
        for _ in 0..(MAX_VMETRICS_ENTRIES * 4) {
            let font = FontData::from_bytes(bytes.clone(), 0);
            let m = font_vmetrics(&font, 12.0);
            assert!(
                m.ascent > 0.0,
                "metrics should still be correct after a clear"
            );
        }
        let entries = raw_vmetrics_cache().lock().unwrap().len();
        assert!(
            entries <= MAX_VMETRICS_ENTRIES,
            "cache holds {entries} entries, above the {MAX_VMETRICS_ENTRIES} ceiling"
        );
    }

    #[test]
    fn repeated_lookups_of_one_font_reuse_its_entry() {
        // The cache has to still *work*: the common case is one `Arc` asked for
        // metrics once per label band, many times per figure.
        //
        // Asserted as key presence rather than as a count. The cache is
        // process-global and `cargo test` runs these concurrently, so any
        // arithmetic on `len()` races with the bound test clearing the map.
        let font = FontData::from_bytes(liberation(), 0);
        let key = font.key() as usize;
        let first = font_vmetrics(&font, 10.0);
        assert!(
            raw_vmetrics_cache().lock().unwrap().contains_key(&key),
            "the first lookup did not populate the cache"
        );
        for _ in 0..50 {
            let m = font_vmetrics(&font, 10.0);
            assert_eq!(m.ascent, first.ascent, "a cached lookup changed the answer");
            assert_eq!(m.descent, first.descent);
        }
    }

    #[test]
    fn metrics_scale_linearly_with_size() {
        let font = FontData::from_bytes(liberation(), 0);
        let a = font_vmetrics(&font, 10.0);
        let b = font_vmetrics(&font, 20.0);
        assert!((b.ascent - a.ascent * 2.0).abs() < 1e-3);
        assert!((b.descent - a.descent * 2.0).abs() < 1e-3);
    }
}
