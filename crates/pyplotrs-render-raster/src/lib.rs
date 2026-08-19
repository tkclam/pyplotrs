//! pyplotrs-render-raster: renders a [`pyplotrs_core::Scene`] to a raster image
//! using `tiny-skia`, rasterizing glyph outlines via `skrifa`.
//!
//! tiny-skia has no state stack of its own, so groups are handled by carrying
//! an accumulated [`Affine`] transform and an optional device-space clip
//! [`Mask`] down the recursive walk; opacity groups are composited via an
//! offscreen layer.
//!
//! Big rasters are drawn in **horizontal bands in parallel** (see
//! [`render_pixmap`]): every band is a [`PixmapMut`] view over its own rows of
//! one canvas allocation, and each replays the whole scene with the root
//! transform shifted up by the band's top. Source-over compositing is
//! per-pixel, so bands never interact and the decomposition is exact in the
//! compositing sense; what it does perturb, very slightly, is antialiasing and
//! image resampling at the seams - `banded_render_matches_single_band` measures
//! by how much and says why. Because that difference is not quite nothing, the
//! band count is a function of the canvas alone and never of the core count,
//! and cheap scenes skip banding entirely and keep the exact single-pass path.

mod png_encode;

use std::collections::HashMap;

use pyplotrs_core::kurbo::{Affine, PathEl, Point, Vec2};
use pyplotrs_core::resample;
use pyplotrs_core::{
    Color, FillRule as CoreFillRule, Group, ImageNode, LineCap as CoreLineCap,
    LineJoin as CoreLineJoin, MarkerNode, Node, PathNode, Scene, Stroke as CoreStroke, TextNode,
};
use rayon::prelude::*;
use skrifa::instance::Size as GlyphSize;
use skrifa::outline::OutlinePen;
use skrifa::{FontRef, GlyphId, MetadataProvider};
use tiny_skia::{
    FillRule, IntSize, LineCap, LineJoin, Mask, Paint, PathBuilder, Pixmap, PixmapMut, PixmapPaint,
    PremultipliedColorU8, Stroke, StrokeDash, Transform,
};

fn to_tiny_skia_path(geometry: &pyplotrs_core::kurbo::BezPath) -> Option<tiny_skia::Path> {
    let mut pb = PathBuilder::new();
    for el in geometry.elements() {
        match *el {
            PathEl::MoveTo(p) => pb.move_to(p.x as f32, p.y as f32),
            PathEl::LineTo(p) => pb.line_to(p.x as f32, p.y as f32),
            PathEl::QuadTo(p1, p2) => {
                pb.quad_to(p1.x as f32, p1.y as f32, p2.x as f32, p2.y as f32)
            }
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

fn solid_paint(color: Color) -> Paint<'static> {
    let mut paint = Paint::default();
    paint.set_color_rgba8(color.r, color.g, color.b, color.a);
    paint.anti_alias = true;
    paint
}

fn to_ts_transform(a: Affine) -> Transform {
    let [a, b, c, d, e, f] = a.as_coeffs();
    Transform::from_row(a as f32, b as f32, c as f32, d as f32, e as f32, f as f32)
}

fn to_ts_fill_rule(rule: CoreFillRule) -> FillRule {
    match rule {
        CoreFillRule::NonZero => FillRule::Winding,
        CoreFillRule::EvenOdd => FillRule::EvenOdd,
    }
}

fn to_ts_stroke(s: &CoreStroke) -> Stroke {
    Stroke {
        width: s.width as f32,
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
        dash: s
            .dash
            .as_ref()
            .and_then(|array| StrokeDash::new(array.clone(), 0.0)),
        ..Default::default()
    }
}

/// Collects glyph outline commands into a [`PathBuilder`], translating from
/// font space (y-up, origin at baseline) into local scene space (y-down) and
/// positioning the glyph at `(origin_x, origin_y)`. The resulting path is then
/// mapped to device space by the caller's accumulated transform.
struct GlyphPen {
    builder: PathBuilder,
    origin_x: f32,
    origin_y: f32,
}

impl GlyphPen {
    fn new(origin_x: f32, origin_y: f32) -> Self {
        Self {
            builder: PathBuilder::new(),
            origin_x,
            origin_y,
        }
    }
}

impl OutlinePen for GlyphPen {
    fn move_to(&mut self, x: f32, y: f32) {
        self.builder.move_to(self.origin_x + x, self.origin_y - y);
    }

    fn line_to(&mut self, x: f32, y: f32) {
        self.builder.line_to(self.origin_x + x, self.origin_y - y);
    }

    fn quad_to(&mut self, cx0: f32, cy0: f32, x: f32, y: f32) {
        self.builder.quad_to(
            self.origin_x + cx0,
            self.origin_y - cy0,
            self.origin_x + x,
            self.origin_y - y,
        );
    }

    fn curve_to(&mut self, cx0: f32, cy0: f32, cx1: f32, cy1: f32, x: f32, y: f32) {
        self.builder.cubic_to(
            self.origin_x + cx0,
            self.origin_y - cy0,
            self.origin_x + cx1,
            self.origin_y - cy1,
            self.origin_x + x,
            self.origin_y - y,
        );
    }

    fn close(&mut self) {
        self.builder.close();
    }
}

fn render_path(pixmap: &mut PixmapMut, p: &PathNode, transform: Affine, clip: Option<&Mask>) {
    let Some(path) = to_tiny_skia_path(&p.geometry) else {
        return;
    };
    let ts = to_ts_transform(transform);
    if let Some(fill) = p.fill {
        pixmap.fill_path(
            &path,
            &solid_paint(fill),
            to_ts_fill_rule(p.fill_rule),
            ts,
            clip,
        );
    }
    if let Some(stroke) = &p.stroke {
        pixmap.stroke_path(
            &path,
            &solid_paint(stroke.color),
            &to_ts_stroke(stroke),
            ts,
            clip,
        );
    }
}

fn render_text(pixmap: &mut PixmapMut, text: &TextNode, transform: Affine, clip: Option<&Mask>) {
    let paint = solid_paint(text.color);
    let ts = to_ts_transform(transform);
    for run in &text.runs {
        let font = FontRef::from_index(&run.font.data, run.font.index).expect("invalid font data");
        let outlines = font.outline_glyphs();
        let size = GlyphSize::new(run.size);
        for glyph in &run.glyphs {
            let gx = text.origin.x as f32 + glyph.x;
            let gy = text.origin.y as f32 + glyph.y;
            if let Some(outline) = outlines.get(GlyphId::from(glyph.glyph_id)) {
                let mut pen = GlyphPen::new(gx, gy);
                let _ = outline.draw(size, &mut pen);
                if let Some(glyph_path) = pen.builder.finish() {
                    pixmap.fill_path(&glyph_path, &paint, FillRule::Winding, ts, clip);
                }
            }
        }
    }
}

/// Sub-pixel phases per axis for marker sprite stamping. At 8 phases every
/// stamped marker lands within 1/16 px of its true position - sub-pixel, and
/// well inside a rasterizer's own antialiasing - while avoiding a per-marker
/// path scan-conversion. (The comment here used to describe P=4 and a 0.125 px
/// bound, neither of which matched the value below.)
const STAMP_PHASES: i32 = 8;
/// Only stamp when there are enough markers to amortize the per-phase tile
/// setup, and each marker is small enough that a tile blit beats a path fill.
const STAMP_MIN_COUNT: usize = 64;
const STAMP_MAX_PX: f32 = 96.0;

/// Largest raster we will try to allocate, in bytes (4 GB - about a 32000 x
/// 32000 px image). Past this the request is almost certainly a units or dpi
/// mistake, and honoring it would abort the process instead of raising.
const MAX_RASTER_BYTES: f64 = 4.0e9;

fn render_markers(
    pixmap: &mut PixmapMut,
    m: &MarkerNode,
    transform: Affine,
    clip: Option<&Mask>,
    stamps: Option<&StampCache>,
) {
    let Some(path) = to_tiny_skia_path(&m.marker) else {
        return;
    };
    let fill_paint = m.fill.map(solid_paint);
    let stroke_paint = m
        .stroke
        .as_ref()
        .map(|s| (solid_paint(s.color), to_ts_stroke(s)));
    let fill_rule = to_ts_fill_rule(m.fill_rule);

    // Fast path: rasterize the marker once per sub-pixel phase into a small
    // tile, then alpha-blit that tile at each position - the raster analog of
    // the PDF Form-XObject / SVG <use> instancing, and what makes a 1e6-point
    // scatter quick. Colormapped scatter takes the same route: its tiles hold
    // pure coverage and are tinted per point at blit time. Falls back to
    // per-point path filling for few/large markers or a degenerate transform.
    //
    // When rendering in bands, `stamps` holds the tile set built once for the
    // whole canvas (see [`StampCache`]); without it each call builds its own,
    // which is what the single-band path does.
    if m.positions.len() >= STAMP_MIN_COUNT {
        let built;
        let tiles = match stamps.and_then(|c| c.get(&stamp_key(m))) {
            Some(t) => Some(t),
            None if stamps.is_some() => None, // pre-pass judged it ineligible
            None => {
                built = build_stamp_tiles(
                    &path,
                    &fill_paint,
                    &stroke_paint,
                    fill_rule,
                    m.colors.is_some(),
                    transform,
                );
                built.as_ref()
            }
        };
        if let Some(tiles) = tiles {
            blit_stamps(
                pixmap,
                tiles,
                &m.positions,
                m.colors.as_deref(),
                transform,
                clip,
            );
            return;
        }
    }

    for (i, pos) in m.positions.iter().enumerate() {
        let ts = to_ts_transform(transform * Affine::translate(Vec2::new(pos.x, pos.y)));
        // A per-point color overrides the shared fill; the stroke stays uniform.
        let paint = match &m.colors {
            Some(colors) => colors.get(i).copied().map(solid_paint),
            None => fill_paint.clone(),
        };
        if let Some(paint) = &paint {
            pixmap.fill_path(&path, paint, fill_rule, ts, clip);
        }
        if let Some((paint, stroke)) = &stroke_paint {
            pixmap.stroke_path(&path, paint, stroke, ts, clip);
        }
    }
}

/// One marker pre-rasterized at every sub-pixel phase, ready to be stamped.
///
/// The tiles depend only on the marker outline and the **linear** part of the
/// transform, never on the translation, so one set serves every position - and,
/// because a band only shifts the translation, every band too.
struct StampTiles {
    tiles: Vec<Pixmap>,
    /// Separate uniform-stroke tiles, used only for a tinted (colormapped)
    /// marker where fill and stroke must stay separable. Empty otherwise.
    stroke_tiles: Vec<Pixmap>,
    tw: i32,
    /// Tile-local pixel of the marker origin at phase 0.
    anchor_x: f32,
    anchor_y: f32,
}

/// Tile sets for the whole scene, built once before a banded render and shared
/// by every band. Keyed by node identity: the scene is immutable for the
/// duration of the render, so a `&MarkerNode`'s address uniquely names it. The
/// key is the address as a `usize` rather than a raw pointer so the map stays
/// `Sync` and can be shared across the band threads.
type StampCache = HashMap<usize, StampTiles>;

/// Images already resampled onto their device grid and premultiplied, ready to
/// blit. Same rationale as [`StampCache`]: both steps depend only on the linear
/// part of the transform, which a band shift leaves alone, so doing them once
/// beats redoing them in all ~30 bands of a tall figure.
///
/// Keyed by the pixel buffer's address plus the grid, so one image drawn at two
/// sizes gets an entry each.
type ImageCache = HashMap<(usize, u32, u32), Pixmap>;

/// Everything a banded render can compute once up front and share, because it
/// depends on the root transform's linear part alone.
#[derive(Default)]
struct RenderCache {
    stamps: StampCache,
    images: ImageCache,
}

fn stamp_key(m: &MarkerNode) -> usize {
    m as *const MarkerNode as usize
}

/// Rasterize `path` into `P x P` sub-pixel phase tiles. Returns `None` (so the
/// caller falls back to per-point path filling) when the marker is too large or
/// the tiles can't be allocated.
///
/// When `tinted` is set (a colormapped scatter), the fill tiles are rasterized
/// in opaque white so their alpha channel is pure coverage, and each point tints
/// that coverage with its own color at blit time. Fill and stroke are then
/// blitted as two separate passes, which is exactly the order the per-point
/// fallback draws them in, so the two paths agree.
fn build_stamp_tiles(
    path: &tiny_skia::Path,
    fill_paint: &Option<Paint<'static>>,
    stroke_paint: &Option<(Paint<'static>, Stroke)>,
    fill_rule: FillRule,
    tinted: bool,
    transform: Affine,
) -> Option<StampTiles> {
    // Linear part of the transform (translation dropped): it scales/rotates the
    // marker shape; per-instance translation comes from `positions`.
    let [a, b, c, d, _, _] = transform.as_coeffs();
    let lin = Affine::new([a, b, c, d, 0.0, 0.0]);
    let dev = path.clone().transform(to_ts_transform(lin))?;
    let bounds = dev.bounds();
    let margin = 1.5_f32;
    let x0 = (bounds.left() - margin).floor();
    let y0 = (bounds.top() - margin).floor();
    let tw = ((bounds.right() + margin).ceil() - x0) as i32;
    let th = ((bounds.bottom() + margin).ceil() - y0) as i32;
    if tw <= 0 || th <= 0 || tw as f32 > STAMP_MAX_PX || th as f32 > STAMP_MAX_PX {
        return None;
    }
    let anchor_x = -x0;
    let anchor_y = -y0;

    let coverage_paint = tinted.then(|| solid_paint(Color::rgba(255, 255, 255, 255)));

    let p = STAMP_PHASES;
    let n_tiles = (p * p) as usize;
    let mut tiles: Vec<Pixmap> = Vec::with_capacity(n_tiles);
    let mut stroke_tiles: Vec<Pixmap> = Vec::with_capacity(if tinted { n_tiles } else { 0 });
    for pj in 0..p {
        for pi in 0..p {
            let mut tile = Pixmap::new(tw as u32, th as u32)?;
            let ax = anchor_x + pi as f32 / p as f32;
            let ay = anchor_y + pj as f32 / p as f32;
            let ts = to_ts_transform(Affine::translate(Vec2::new(ax as f64, ay as f64)) * lin);
            if let Some(paint) = coverage_paint.as_ref().or(fill_paint.as_ref()) {
                tile.fill_path(path, paint, fill_rule, ts, None);
            }
            if let Some((paint, stroke)) = stroke_paint {
                if tinted {
                    let mut st = Pixmap::new(tw as u32, th as u32)?;
                    st.stroke_path(path, paint, stroke, ts, None);
                    stroke_tiles.push(st);
                } else {
                    tile.stroke_path(path, paint, stroke, ts, None);
                }
            }
            tiles.push(tile);
        }
    }
    Some(StampTiles {
        tiles,
        stroke_tiles,
        tw,
        anchor_x,
        anchor_y,
    })
}

/// Alpha-composite the nearest-phase tile at every position.
fn blit_stamps(
    pixmap: &mut PixmapMut,
    t: &StampTiles,
    positions: &[Point],
    colors: Option<&[Color]>,
    transform: Affine,
    clip: Option<&Mask>,
) {
    let p = STAMP_PHASES;
    let pw = pixmap.width() as i32;
    let ph = pixmap.height() as i32;
    for (i, pos) in positions.iter().enumerate() {
        let dpt = transform * *pos;
        let (cx, cy) = (dpt.x as f32, dpt.y as f32);
        // Nearest sub-pixel phase; the residual is absorbed by rounding the
        // integer destination, so the placement error stays <= 0.5/P px.
        let pi = (((cx - cx.floor()) * p as f32).round() as i32 % p).max(0);
        let pj = (((cy - cy.floor()) * p as f32).round() as i32 % p).max(0);
        let dest_x = (cx - t.anchor_x - pi as f32 / p as f32).round() as i32;
        let dest_y = (cy - t.anchor_y - pj as f32 / p as f32).round() as i32;
        let phase = (pj * p + pi) as usize;
        let tint = colors.map(|cs| cs.get(i).copied().unwrap_or(Color::rgba(0, 0, 0, 255)));
        blit_tile(
            pixmap,
            pw,
            ph,
            &t.tiles[phase],
            t.tw,
            dest_x,
            dest_y,
            clip,
            tint,
        );
        if let Some(st) = t.stroke_tiles.get(phase) {
            blit_tile(pixmap, pw, ph, st, t.tw, dest_x, dest_y, clip, None);
        }
    }
}

/// Source-over alpha-composite a premultiplied `tile` onto `pixmap` at
/// `(dest_x, dest_y)`, clipped to the pixmap bounds and (if present) the device
/// clip mask. This is a tight hand-rolled blit rather than `Pixmap::draw_pixmap`
/// because the latter sets up a pattern shader per call - far too slow when
/// stamping ~1e6 tiny tiles. Source-over is associative, so compositing the
/// pre-rendered fill+stroke tile gives the same result as the per-point
/// `fill_path`/`stroke_path` fallback (verified by pixel diff). The clip mask
/// shares the pixmap's dimensions (see `render_group`).
///
/// With `tint`, the tile is read as a **coverage mask** - it was rasterized in
/// opaque white, so its alpha channel is the antialiased coverage - and the
/// source color is synthesized per pixel as `tint * coverage`. That is what lets
/// a colormapped scatter reuse one set of tiles for every point instead of
/// scan-converting the outline once per point.
#[allow(clippy::too_many_arguments)]
fn blit_tile(
    pixmap: &mut PixmapMut,
    pw: i32,
    ph: i32,
    tile: &Pixmap,
    tw: i32,
    dest_x: i32,
    dest_y: i32,
    clip: Option<&Mask>,
    tint: Option<Color>,
) {
    let th = tile.height() as i32;
    let sx0 = (-dest_x).max(0);
    let sy0 = (-dest_y).max(0);
    let sx1 = (pw - dest_x).min(tw);
    let sy1 = (ph - dest_y).min(th);
    if sx0 >= sx1 || sy0 >= sy1 {
        return;
    }
    let src = tile.pixels();
    let clip_data = clip.map(|c| c.data());
    let dst = pixmap.pixels_mut();
    for sy in sy0..sy1 {
        let dy = dest_y + sy;
        let src_row = (sy * tw) as usize;
        let dst_row = (dy * pw) as usize;
        for sx in sx0..sx1 {
            let s = src[src_row + sx as usize];
            let mut sa = s.alpha() as u32;
            if sa == 0 {
                continue;
            }
            let dx = dest_x + sx;
            let idx = dst_row + dx as usize;

            // Resolve the clip coverage up front: `k = 255` (full coverage)
            // is the common case away from the clip mask's own edge, and
            // knowing it here lets the opaque fast path below apply under a
            // clip too, not just when there is none.
            let k = match clip_data {
                Some(cd) => {
                    let k = cd[idx] as u32;
                    if k == 0 {
                        continue;
                    }
                    k
                }
                None => 255,
            };

            // Fast path: an opaque, untinted source pixel under full clip
            // coverage source-over-composites to exactly itself (`inv` below
            // would be 0, so every blended channel reduces to the source
            // one). That's the interior of every filled marker, so skipping
            // the divide-by-255 blend arithmetic there is most of the win.
            if tint.is_none() && sa == 255 && k == 255 {
                dst[idx] = s;
                continue;
            }

            let (mut sr, mut sg, mut sb) = match tint {
                // Coverage mask: `sa` is the antialiased coverage. Fold in the
                // tint's own alpha, then premultiply its channels by the result.
                Some(c) => {
                    sa = (sa * c.a as u32 + 127) / 255;
                    if sa == 0 {
                        continue;
                    }
                    (
                        (c.r as u32 * sa + 127) / 255,
                        (c.g as u32 * sa + 127) / 255,
                        (c.b as u32 * sa + 127) / 255,
                    )
                }
                None => (s.red() as u32, s.green() as u32, s.blue() as u32),
            };
            if k != 255 {
                sa = (sa * k + 127) / 255;
                sr = (sr * k + 127) / 255;
                sg = (sg * k + 127) / 255;
                sb = (sb * k + 127) / 255;
            }
            let bg = dst[idx];
            let inv = 255 - sa;
            let oa = (sa + (bg.alpha() as u32 * inv + 127) / 255).min(255);
            let or = (sr + (bg.red() as u32 * inv + 127) / 255).min(oa);
            let og = (sg + (bg.green() as u32 * inv + 127) / 255).min(oa);
            let ob = (sb + (bg.blue() as u32 * inv + 127) / 255).min(oa);
            dst[idx] = PremultipliedColorU8::from_rgba(or as u8, og as u8, ob as u8, oa as u8)
                .unwrap_or(bg);
        }
    }
}

/// The pixel grid `im` should carry when drawn under `transform` - its own,
/// where [`resample::target_grid`] judges a resample not worth its cost.
fn image_grid(im: &ImageNode, transform: Affine) -> (u32, u32) {
    let (dx, dy) = resample::device_extent(im.rect, transform);
    resample::target_grid(im.data.width, im.data.height, dx, dy)
        .unwrap_or((im.data.width, im.data.height))
}

/// Resample `im` onto `grid` and premultiply it, ready for `draw_pixmap`.
///
/// tiny-skia offers one `FilterQuality` for both axes, and its default is
/// `Nearest` - right for the magnified axis of a tall image, and wrong for the
/// reduced one, where it drops rows instead of averaging them. So the grid is
/// resampled per axis first (see [`resample`]) and the blit that follows is
/// about a 1:1 copy, where the filter has nothing left to get wrong.
fn image_pixmap(im: &ImageNode, grid: (u32, u32)) -> Option<Pixmap> {
    let resampled =
        (grid != (im.data.width, im.data.height)).then(|| im.data.resampled_to(grid.0, grid.1));
    let data = resampled.as_ref().unwrap_or(&im.data);
    let size = IntSize::from_wh(data.width, data.height)?;
    // tiny-skia stores premultiplied RGBA; our IR carries straight RGBA.
    //
    // Rounded, not truncated. `c * a / 255` in integers throws away the
    // remainder, so every semi-transparent image pixel came out up to one
    // level darker here than the same pixel in the PDF or SVG, where the
    // viewer does the multiply in floating point. One level is invisible on
    // its own and is still a difference between backends of the same figure -
    // and `+ 127` costs nothing.
    let mut px = (*data.rgba).clone();
    for p in px.chunks_exact_mut(4) {
        let a = p[3] as u16;
        p[0] = ((p[0] as u16 * a + 127) / 255) as u8;
        p[1] = ((p[1] as u16 * a + 127) / 255) as u8;
        p[2] = ((p[2] as u16 * a + 127) / 255) as u8;
    }
    Pixmap::from_vec(px, size)
}

fn render_image(
    pixmap: &mut PixmapMut,
    im: &ImageNode,
    transform: Affine,
    clip: Option<&Mask>,
    images: Option<&ImageCache>,
) {
    let grid = image_grid(im, transform);
    let built;
    // When rendering in bands, this pixmap was built once for the whole canvas
    // (see [`ImageCache`]); without a cache this call builds its own.
    let key = (im.data.key() as usize, grid.0, grid.1);
    let src = match images.and_then(|c| c.get(&key)) {
        Some(p) => p,
        None => {
            built = image_pixmap(im, grid);
            let Some(p) = &built else { return };
            p
        }
    };
    // Map the image's pixel grid to fill the destination rect.
    let img_tf = transform
        * Affine::translate(Vec2::new(im.rect.x0, im.rect.y0))
        * Affine::scale_non_uniform(
            im.rect.width() / src.width() as f64,
            im.rect.height() / src.height() as f64,
        );
    pixmap.draw_pixmap(
        0,
        0,
        src.as_ref(),
        &PixmapPaint::default(),
        to_ts_transform(img_tf),
        clip,
    );
}

fn render_group(
    pixmap: &mut PixmapMut,
    g: &Group,
    transform: Affine,
    clip: Option<&Mask>,
    cache: Option<&RenderCache>,
) {
    let child_tf = transform * g.transform;

    // Resolve the effective clip: intersect this group's clip path (in the
    // child coordinate space) with any inherited clip.
    let new_clip: Option<Mask> = g.clip.as_ref().and_then(|cp| {
        let path = to_tiny_skia_path(&cp.geometry)?;
        let ts = to_ts_transform(child_tf);
        let rule = to_ts_fill_rule(cp.rule);
        let mask = match clip {
            Some(parent) => {
                let mut m = parent.clone();
                m.intersect_path(&path, rule, true, ts);
                m
            }
            None => {
                let mut m = Mask::new(pixmap.width(), pixmap.height())?;
                m.fill_path(&path, rule, true, ts);
                m
            }
        };
        Some(mask)
    });
    let effective_clip = new_clip.as_ref().or(clip);

    if g.opacity < 1.0 {
        // Band-local layer: an opacity group composites per pixel, so doing it
        // over the band's rows alone gives the same result as over the canvas.
        let Some(mut layer) = Pixmap::new(pixmap.width(), pixmap.height()) else {
            return;
        };
        let mut layer_view = layer.as_mut();
        for child in &g.children {
            render_node(&mut layer_view, child, child_tf, effective_clip, cache);
        }
        let paint = PixmapPaint {
            opacity: g.opacity.clamp(0.0, 1.0),
            ..Default::default()
        };
        pixmap.draw_pixmap(0, 0, layer.as_ref(), &paint, Transform::identity(), None);
    } else {
        for child in &g.children {
            render_node(pixmap, child, child_tf, effective_clip, cache);
        }
    }
}

fn render_node(
    pixmap: &mut PixmapMut,
    node: &Node,
    transform: Affine,
    clip: Option<&Mask>,
    cache: Option<&RenderCache>,
) {
    match node {
        Node::Path(p) => render_path(pixmap, p, transform, clip),
        Node::Text(t) => render_text(pixmap, t, transform, clip),
        Node::Image(im) => render_image(pixmap, im, transform, clip, cache.map(|c| &c.images)),
        Node::Markers(m) => render_markers(pixmap, m, transform, clip, cache.map(|c| &c.stamps)),
        Node::Group(g) => render_group(pixmap, g, transform, clip, cache),
    }
}

/// Estimated rasterization work in a node tree, in scanline-touches.
///
/// Counting *primitives* is not enough to tell a slow raster from a fast one:
/// a 99k-point scatter renders in 11 ms while an 11k-segment noisy polyline
/// takes 900 ms, because a scan converter costs roughly (edges x scanlines each
/// edge spans), and a scribble's segments each span most of the panel. So paths
/// are weighted by the device height of their bounding box, which is what
/// separates a busy figure from an expensive one by a wide enough margin to put
/// a threshold between them. Only ever compared against [`BAND_MIN_WORK`].
fn scene_work(nodes: &[Node], transform: Affine) -> u64 {
    let mut work = 0u64;
    for node in nodes {
        work += match node {
            Node::Path(p) => {
                // `control_box` is the hull of the control points - a cheap
                // over-estimate of the true bounds, which is all this needs.
                let rows = (transform
                    .transform_rect_bbox(p.geometry.control_box())
                    .height())
                .max(1.0) as u64;
                p.geometry.elements().len() as u64 * rows
            }
            Node::Text(t) => t
                .runs
                .iter()
                .map(|r| {
                    let rows = (f64::from(r.size) * transform.as_coeffs()[3].abs()).max(1.0) as u64;
                    r.glyphs.len() as u64 * rows
                })
                .sum(),
            // A stamped marker blits its whole sprite, so it costs per pixel
            // rather than per scanline. Left undiscounted against the path
            // terms: it errs towards banding marker-heavy scenes, which is the
            // safe direction, since stamping comes out bit-identical banded.
            Node::Markers(m) => {
                let b = transform.transform_rect_bbox(m.marker.control_box());
                let px = (b.width().max(1.0) * b.height().max(1.0)) as u64;
                m.positions.len() as u64 * px
            }
            Node::Image(im) => {
                // Device area the image covers, discounted: a pixel copy is far
                // cheaper than scan-converting a path segment.
                let r = transform.transform_rect_bbox(im.rect);
                ((r.width() * r.height()).max(0.0) as u64) / 32
            }
            Node::Group(g) => scene_work(&g.children, transform * g.transform),
        };
    }
    work
}

/// Build the work a banded render shares across its bands: marker tile sets
/// (see [`StampTiles`]) and resampled image pixmaps (see [`ImageCache`]).
///
/// The marker half mirrors the eligibility test in `render_markers`, so a node
/// missing from the cache is exactly one the bands will draw per-point instead.
fn build_render_cache(nodes: &[Node], transform: Affine, out: &mut RenderCache) {
    for node in nodes {
        match node {
            Node::Image(im) => {
                let grid = image_grid(im, transform);
                if let Some(pm) = image_pixmap(im, grid) {
                    out.images
                        .insert((im.data.key() as usize, grid.0, grid.1), pm);
                }
            }
            Node::Markers(m) if m.positions.len() >= STAMP_MIN_COUNT => {
                let Some(path) = to_tiny_skia_path(&m.marker) else {
                    continue;
                };
                let fill_paint = m.fill.map(solid_paint);
                let stroke_paint = m
                    .stroke
                    .as_ref()
                    .map(|s| (solid_paint(s.color), to_ts_stroke(s)));
                if let Some(tiles) = build_stamp_tiles(
                    &path,
                    &fill_paint,
                    &stroke_paint,
                    to_ts_fill_rule(m.fill_rule),
                    m.colors.is_some(),
                    transform,
                ) {
                    out.stamps.insert(stamp_key(m), tiles);
                }
            }
            Node::Group(g) => build_render_cache(&g.children, transform * g.transform, out),
            _ => {}
        }
    }
}

/// Canvas area (device px) below which banding is never worth its overhead.
const BAND_MIN_PIXELS: u64 = 250_000;
/// Scene work (see [`scene_work`]) below which banding is never worth it.
///
/// Calibrated by measuring both sides. Ordinary figures score well under this -
/// a two-line 400x300 pt plot is 78k at 100 dpi and 233k at 300 dpi, a
/// four-panel figure 157k - and rasterize in under 10 ms, so there is nothing
/// to win. The cases above it are the ones that hurt: a 99k-point scatter
/// (1.1M) and an 11k-segment noisy polyline (9.3M, 0.92 s unbanded).
///
/// Keeping ordinary figures out is not only about overhead. Banding perturbs
/// antialiasing slightly, and forcing it on for everything spends 10-65% of the
/// golden suite's comparison tolerance - budget that exists to catch real
/// regressions. Below this threshold the output stays byte-identical.
const BAND_MIN_WORK: u64 = 400_000;
/// Rows per band. Short enough that even a modest canvas yields more bands than
/// there are cores (which is what lets rayon balance uneven ones - a band over
/// a dense panel costs far more than one over white space), long enough that
/// per-band setup stays amortized.
const BAND_ROWS: u32 = 32;

/// How many horizontal bands to split this render into. `1` means the exact
/// serial path.
///
/// Deliberately a function of the canvas alone, **not** of the core count: the
/// band count perturbs antialiasing and image resampling very slightly (see
/// [`render_pixmap_banded`]), and a figure must not render differently on a
/// different machine.
fn band_count(width: u32, height: u32, work: u64) -> u32 {
    let pixels = width as u64 * height as u64;
    if pixels < BAND_MIN_PIXELS || work < BAND_MIN_WORK {
        return 1;
    }
    height.div_ceil(BAND_ROWS).max(1)
}

/// Render `scene` to a [`Pixmap`] (RGBA8, white background unless
/// `transparent`) at `scale` device-pixels per scene-point.
///
/// Expensive rasters are split into horizontal bands rendered in parallel; see
/// the module docs. Small ones take the single-band path, which is
/// byte-for-byte what this function did before banding existed.
pub fn render_pixmap(scene: &Scene, scale: f64, transparent: bool) -> Result<Pixmap, String> {
    render_pixmap_banded(scene, scale, transparent, None)
}

/// [`render_pixmap`], with the band count forced rather than chosen by
/// [`band_count`]. Only the tests need this: it is how the banded output is
/// checked against the single-band reference.
fn render_pixmap_banded(
    scene: &Scene,
    scale: f64,
    transparent: bool,
    force_bands: Option<u32>,
) -> Result<Pixmap, String> {
    // `scale` is device-pixels per scene-point (i.e. dpi / 72). Geometry,
    // glyph outlines, images and clips are all mapped by a single root scale,
    // so text is *re-rasterized* crisply at the target resolution rather than
    // upscaled.
    let scale = if scale.is_finite() && scale > 0.0 {
        scale
    } else {
        1.0
    };
    // Round (not ceil) to the nearest pixel so exact cases land exactly, e.g.
    // a 4x3in figure at 300dpi is 1200x900, not 1200x901 from f64 creep.
    let width = (scene.size.width * scale).round().max(1.0) as u32;
    let height = (scene.size.height * scale).round().max(1.0) as u32;
    // Bound the raster *before* allocating. A big figure at a big dpi is an
    // easy mistake (a 4000x3000 in poster at 2400 dpi asks for 276 TB), and
    // Rust's allocator aborts the process on OOM rather than returning - so
    // `Pixmap::new` returning `None` is not a defense we can rely on. Check the
    // arithmetic in f64 to avoid overflowing the multiply itself.
    let bytes = (width as f64) * (height as f64) * 4.0;
    if bytes > MAX_RASTER_BYTES {
        return Err(format!(
            "raster would be {width} x {height} px ({:.1} GB, limit {:.0} GB); \
             reduce the figure size or the dpi",
            bytes / 1e9,
            MAX_RASTER_BYTES / 1e9
        ));
    }
    let size = IntSize::from_wh(width, height)
        .ok_or_else(|| format!("cannot allocate a {width} x {height} px raster"))?;
    let mut data = vec![0u8; (width as usize) * (height as usize) * 4];

    let background = if transparent {
        tiny_skia::Color::TRANSPARENT
    } else {
        tiny_skia::Color::WHITE
    };
    let root = Affine::scale(scale);

    let bands = force_bands
        .map(|b| b.clamp(1, height.max(1)))
        .unwrap_or_else(|| band_count(width, height, scene_work(&scene.nodes, root)));
    // Marker sprite tiles and resampled images depend only on the linear part
    // of the transform, which a band shift leaves alone - so build them once
    // here rather than once per band.
    let cache = (bands > 1).then(|| {
        let mut cache = RenderCache::default();
        build_render_cache(&scene.nodes, root, &mut cache);
        cache
    });

    let band_rows = height.div_ceil(bands);
    let stride = (width as usize) * 4;
    data.par_chunks_mut(band_rows as usize * stride)
        .enumerate()
        .for_each(|(i, chunk)| {
            let rows = (chunk.len() / stride) as u32;
            let Some(mut view) = PixmapMut::from_bytes(chunk, width, rows) else {
                return;
            };
            view.fill(background);
            // Shift the scene up so this band's first row is device row 0.
            let band_tf =
                Affine::translate(Vec2::new(0.0, -((i as u32 * band_rows) as f64))) * root;
            for node in &scene.nodes {
                render_node(&mut view, node, band_tf, None, cache.as_ref());
            }
        });

    Pixmap::from_vec(data, size)
        .ok_or_else(|| format!("cannot allocate a {width} x {height} px raster"))
}

/// Render `scene` to PNG-encoded bytes at `dpi` (dots per inch). The output
/// carries a `pHYs` chunk recording its physical size, so consumers such as
/// LaTeX `\includegraphics` place it at the intended dimensions. `transparent`
/// drops the white page fill in favor of an alpha channel.
pub fn render_png(scene: &Scene, dpi: f64, transparent: bool) -> Result<Vec<u8>, String> {
    let dpi = if dpi.is_finite() && dpi > 0.0 {
        dpi
    } else {
        72.0
    };
    let pixmap = render_pixmap(scene, dpi / 72.0, transparent)?;
    encode_png_with_dpi(pixmap, dpi, transparent)
}

/// Encode a pixmap to PNG bytes, tagging it with a `pHYs` density chunk
/// derived from `dpi`. An opaque pixmap (white fill composited under
/// everything) has premultiplied bytes equal to straight RGBA and is written
/// directly; a `transparent` one is demultiplied first, since tiny-skia's
/// internal buffer is premultiplied and PNG expects straight alpha.
///
/// Both halves of the encode - scanline filtering and DEFLATE - run in
/// parallel; see [`png_encode`].
fn encode_png_with_dpi(pixmap: Pixmap, dpi: f64, transparent: bool) -> Result<Vec<u8>, String> {
    let ppu = (dpi / 0.0254).round() as u32; // pixels per metre
    let (width, height) = (pixmap.width(), pixmap.height());
    let data = if transparent {
        pixmap.take_demultiplied()
    } else {
        pixmap.take()
    };
    png_encode::encode_rgba8(&data, width, height, ppu)
}

/// Render a sequence of equally-sized scenes to an animated GIF.
///
/// `scale` is device-pixels per scene-point (dpi/72); `delay_cs` is the
/// per-frame delay in centiseconds (GIF's native unit); `infinite` selects
/// looping vs. play-once. Each frame is quantized to its own ≤256-color
/// palette via NeuQuant (`gif`'s `from_rgba_speed`). All frames share frame 0's
/// canvas size — the caller (Python `Animation`) guarantees a uniform figsize.
///
/// The pixmap buffer is premultiplied RGBA, but the rendered scene is always
/// opaque (white fill under everything), so it equals straight RGBA and GIF's
/// 1-bit alpha is never exercised.
pub fn render_gif(
    scenes: &[&Scene],
    scale: f64,
    delay_cs: u16,
    infinite: bool,
) -> Result<Vec<u8>, String> {
    if scenes.is_empty() {
        return Err("animation needs at least one frame".to_string());
    }
    // Frames are independent all the way through quantization - which is the
    // expensive half - so render and quantize them in parallel and keep only
    // the write ordered. `collect` preserves frame order.
    let pixmaps: Vec<Pixmap> = scenes
        .par_iter()
        .map(|s| render_pixmap(s, scale, false))
        .collect::<Result<_, String>>()?;
    // GIF stores dimensions as u16, so anything past 65535 px cannot be
    // represented at all. Checked *before* the truncation below, because the
    // truncation is what made the old size check unable to fire: it compared
    // `pm.width() as u16` against a `w` that was already `as u16`, so a 70000
    // px frame and a 4464 px frame both read as 4464 and matched. The
    // mismatch then reached `from_rgba_speed`, which asserts - a panic across
    // the FFI boundary, from a figure size the caller chose.
    let (full_w, full_h) = (pixmaps[0].width(), pixmaps[0].height());
    if full_w > u16::MAX as u32 || full_h > u16::MAX as u32 {
        return Err(format!(
            "a GIF frame can be at most {max} x {max} px; this animation is \
             {full_w} x {full_h}. Reduce the figure size or the dpi, or save \
             an APNG (`.png`), which has no such limit.",
            max = u16::MAX
        ));
    }
    let (w, h) = (full_w as u16, full_h as u16);
    let frames: Vec<gif::Frame<'static>> = pixmaps
        .par_iter()
        .map(|pm| {
            // `from_rgba_speed` asserts on a size mismatch; report it instead.
            if (pm.width(), pm.height()) != (full_w, full_h) {
                return Err(format!(
                    "every animation frame must be {full_w} x {full_h} px, got {} x {}",
                    pm.width(),
                    pm.height()
                ));
            }
            let mut rgba = pm.data().to_vec();
            // speed 10: a balance between NeuQuant quality (1) and speed (30) —
            // plots have few distinct colors so quantization is near-lossless.
            let mut frame = gif::Frame::from_rgba_speed(w, h, &mut rgba, 10);
            frame.delay = delay_cs;
            Ok(frame)
        })
        .collect::<Result<_, String>>()?;

    let mut out = Vec::new();
    {
        let mut encoder = gif::Encoder::new(&mut out, w, h, &[])
            .map_err(|e| format!("GIF encoder init failed: {e}"))?;
        encoder
            .set_repeat(if infinite {
                gif::Repeat::Infinite
            } else {
                gif::Repeat::Finite(0)
            })
            .map_err(|e| format!("GIF repeat write failed: {e}"))?;
        for frame in &frames {
            encoder
                .write_frame(frame)
                .map_err(|e| format!("GIF frame write failed: {e}"))?;
        }
    }
    Ok(out)
}

/// Render a sequence of equally-sized scenes to an animated PNG (APNG).
///
/// Unlike GIF, APNG keeps full 8-bit-per-channel color (no palette
/// quantization), so it's the high-fidelity animation format. `delay_num`/
/// `delay_den` give the per-frame delay as a fraction of a second; `infinite`
/// loops forever (`num_plays = 0`) vs. play-once (`num_plays = 1`). The output
/// carries a `pHYs` density chunk like the still-PNG path.
///
/// Both halves are parallel: the frames rasterize against each other, then
/// [`png_encode::encode_apng`] filters and deflates them against each other too.
/// Going through the `png` crate's writer instead left the whole encode on one
/// thread, which cost more than the rasterization on any ink-heavy animation.
pub fn render_apng(
    scenes: &[&Scene],
    dpi: f64,
    delay_num: u16,
    delay_den: u16,
    infinite: bool,
) -> Result<Vec<u8>, String> {
    if scenes.is_empty() {
        return Err("animation needs at least one frame".to_string());
    }
    let dpi = if dpi.is_finite() && dpi > 0.0 {
        dpi
    } else {
        72.0
    };
    // Frames are independent; render them in parallel, write them in order.
    let pixmaps: Vec<Pixmap> = scenes
        .par_iter()
        .map(|s| render_pixmap(s, dpi / 72.0, false))
        .collect::<Result<_, String>>()?;
    let (w, h) = (pixmaps[0].width(), pixmaps[0].height());
    // The size check `render_gif` carries, which this path used to leave to the
    // encoder: `encode_apng` would reject a short buffer, but naming the frame
    // and its size here says what actually went wrong. Python's `Animation`
    // enforces a uniform figsize, so this only fires through the Rust API or
    // when a dpi lands two figsizes on different pixel counts.
    if let Some((i, pm)) = pixmaps
        .iter()
        .enumerate()
        .find(|(_, pm)| (pm.width(), pm.height()) != (w, h))
    {
        return Err(format!(
            "every animation frame must be {w} x {h} px, got {} x {} at frame {i}",
            pm.width(),
            pm.height()
        ));
    }
    let ppu = (dpi / 0.0254).round() as u32;
    let frames: Vec<&[u8]> = pixmaps.iter().map(|pm| pm.data()).collect();
    png_encode::encode_apng(
        &frames,
        w,
        h,
        ppu,
        delay_num,
        delay_den,
        u32::from(!infinite),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyplotrs_core::kurbo::{Circle, Point, Rect, Shape, Size};
    use pyplotrs_core::{ClipPath, Color, FillRule, Group, MarkerNode, PathNode, Scene};

    /// Positions on a deliberately non-integer grid, so the stamped markers
    /// exercise a spread of sub-pixel phases (and a few land past the clip
    /// rect, exercising partial-tile clipping in `blit_tile`).
    fn positions() -> Vec<Point> {
        let mut v = Vec::new();
        for i in 0..12 {
            for j in 0..10 {
                v.push(Point::new(8.0 + i as f64 * 7.31, 6.0 + j as f64 * 7.07));
            }
        }
        v
    }

    fn marker_path() -> pyplotrs_core::kurbo::BezPath {
        Circle::new((0.0, 0.0), 3.5).to_path(0.05)
    }

    fn clip_group(children: Vec<Node>) -> Scene {
        let mut scene = Scene::new(Size::new(100.0, 80.0));
        let mut g = Group::new();
        g.clip = Some(ClipPath::rect(Rect::new(4.0, 4.0, 92.0, 74.0)));
        g.children = children;
        scene.push(g);
        scene
    }

    fn avg_and_content(a: &Pixmap, b: &Pixmap) -> (f64, usize) {
        let (da, db) = (a.data(), b.data());
        assert_eq!(da.len(), db.len());
        let mut total = 0u64;
        let mut non_white = 0usize;
        for (pa, pb) in da.chunks_exact(4).zip(db.chunks_exact(4)) {
            let d = (0..3)
                .map(|k| (pa[k] as i32 - pb[k] as i32).unsigned_abs())
                .max()
                .unwrap();
            total += d as u64;
            if pa[0] != 255 || pa[1] != 255 || pa[2] != 255 {
                non_white += 1;
            }
        }
        (total as f64 / (da.len() / 4) as f64, non_white)
    }

    /// Stamping a filled marker at every position must match rendering an
    /// equivalent per-point `PathNode` for each position to within a sub-pixel
    /// average difference - this is the invariant the sprite fast path relies on.
    #[test]
    fn stamped_markers_match_per_path_fill() {
        let fill = Color::rgb(0, 110, 200);
        let pos = positions();
        assert!(
            pos.len() >= STAMP_MIN_COUNT,
            "must trigger the stamp fast path"
        );

        let stamped = render_pixmap(
            &clip_group(vec![Node::Markers(MarkerNode {
                marker: marker_path(),
                fill: Some(fill),
                fill_rule: FillRule::NonZero,
                stroke: None,
                positions: pos.clone(),
                colors: None,
            })]),
            2.0,
            false,
        )
        .unwrap();

        // Reference: one PathNode per position (the per-point fallback path).
        let per_path: Vec<Node> = pos
            .iter()
            .map(|p| {
                Node::Path(PathNode {
                    geometry: Circle::new((p.x, p.y), 3.5).to_path(0.05),
                    fill: Some(fill),
                    fill_rule: FillRule::NonZero,
                    stroke: None,
                })
            })
            .collect();
        let reference = render_pixmap(&clip_group(per_path), 2.0, false).unwrap();

        let (avg, non_white) = avg_and_content(&stamped, &reference);
        assert!(
            non_white > 2000,
            "expected substantial marker coverage, got {non_white}px"
        );
        assert!(
            avg < 2.0,
            "stamped vs per-path avg diff too high: {avg:.3}/255"
        );
    }

    /// The same invariant for a *colormapped* scatter, where the tiles carry
    /// coverage only and each point tints them. Without this, the tinting math
    /// (premultiplying by the point's color and its alpha) could be wrong in a
    /// way no other test would notice - the previous code sidestepped the whole
    /// fast path here and filled one path per point.
    #[test]
    fn tinted_stamped_markers_match_per_path_fill() {
        let pos = positions();
        assert!(
            pos.len() >= STAMP_MIN_COUNT,
            "must trigger the stamp fast path"
        );
        // A per-point ramp, including a translucent entry so the alpha term is
        // exercised rather than always being 255.
        let colors: Vec<Color> = (0..pos.len())
            .map(|i| {
                let t = (i * 255 / pos.len().max(1)) as u8;
                Color::rgba(t, 255 - t, 128, if i % 4 == 0 { 128 } else { 255 })
            })
            .collect();

        let stamped = render_pixmap(
            &clip_group(vec![Node::Markers(MarkerNode {
                marker: marker_path(),
                fill: Some(Color::rgb(0, 0, 0)),
                fill_rule: FillRule::NonZero,
                stroke: None,
                positions: pos.clone(),
                colors: Some(colors.clone()),
            })]),
            2.0,
            false,
        )
        .unwrap();

        let per_path: Vec<Node> = pos
            .iter()
            .zip(&colors)
            .map(|(p, c)| {
                Node::Path(PathNode {
                    geometry: Circle::new((p.x, p.y), 3.5).to_path(0.05),
                    fill: Some(*c),
                    fill_rule: FillRule::NonZero,
                    stroke: None,
                })
            })
            .collect();
        let reference = render_pixmap(&clip_group(per_path), 2.0, false).unwrap();

        let (avg, non_white) = avg_and_content(&stamped, &reference);
        assert!(
            non_white > 2000,
            "expected substantial marker coverage, got {non_white}px"
        );
        assert!(
            avg < 2.0,
            "tinted stamp vs per-path avg diff too high: {avg:.3}/255"
        );
    }

    /// A scene touching every node kind banding has to carry across a seam:
    /// stroked and filled paths, text, an image, stamped markers, a clip group
    /// and a nested opacity group.
    fn mixed_scene() -> Scene {
        let mut scene = Scene::new(Size::new(200.0, 160.0));

        let mut wave = pyplotrs_core::kurbo::BezPath::new();
        wave.move_to((5.0, 80.0));
        for i in 1..400 {
            let x = 5.0 + i as f64 * 0.475;
            wave.line_to((x, 80.0 + 60.0 * (x * 0.21).sin()));
        }
        let mut g = Group::new();
        g.clip = Some(ClipPath::rect(Rect::new(2.0, 2.0, 198.0, 158.0)));
        g.children = vec![
            Node::Path(PathNode {
                geometry: Rect::new(10.0, 10.0, 190.0, 150.0).to_path(0.05),
                fill: Some(Color::rgba(240, 245, 250, 255)),
                fill_rule: FillRule::NonZero,
                stroke: None,
            }),
            Node::Image(pyplotrs_core::ImageNode {
                data: pyplotrs_core::ImageData::from_rgba8(
                    (0..32 * 24 * 4)
                        .map(|i| if i % 4 == 3 { 255 } else { (i % 251) as u8 })
                        .collect(),
                    32,
                    24,
                ),
                rect: Rect::new(20.0, 20.0, 100.0, 90.0),
            }),
            Node::Path(PathNode {
                geometry: wave,
                fill: None,
                fill_rule: FillRule::NonZero,
                stroke: Some(pyplotrs_core::Stroke::new(Color::rgb(200, 40, 40), 1.7)),
            }),
            Node::Markers(MarkerNode {
                marker: marker_path(),
                fill: Some(Color::rgb(0, 110, 200)),
                fill_rule: FillRule::NonZero,
                stroke: Some(pyplotrs_core::Stroke::new(Color::rgb(255, 255, 255), 0.8)),
                positions: positions(),
                colors: None,
            }),
        ];

        let mut faded = Group::new();
        faded.opacity = 0.45;
        faded.children = vec![Node::Markers(MarkerNode {
            marker: marker_path(),
            fill: Some(Color::rgb(20, 160, 90)),
            fill_rule: FillRule::NonZero,
            stroke: None,
            positions: positions().iter().map(|p| Point::new(p.y, p.x)).collect(),
            colors: Some(
                (0..positions().len())
                    .map(|i| Color::rgba((i * 3 % 256) as u8, 120, 200, 255))
                    .collect(),
            ),
        })];
        g.children.push(Node::Group(faded));

        scene.push(g);
        scene
    }

    /// Rendering in bands must agree with rendering in one pass. It cannot be
    /// bit-exact, for two reasons found by measuring each node kind separately:
    ///
    /// - **Stroked and filled outlines.** tiny-skia's antialiasing takes a
    ///   different code path once a path is no longer wholly inside the clip
    ///   (`path_contained_in_clip` in its scan converter), so a shape crossing a
    ///   seam picks up sub-pixel coverage differences (worst seen: 14/255 on a
    ///   handful of pixels).
    /// - **Images.** A band shifts the transform, and tiny-skia inverts it in
    ///   `f32` to sample the pattern, so a destination row whose source
    ///   coordinate sits almost exactly on a source-pixel boundary can round to
    ///   the neighboring row. That costs one destination row per seam, and the
    ///   error is bounded by how much adjacent source rows differ - a few units
    ///   out of 255 for the colormapped images plots actually contain.
    ///
    /// Filled paths, stamped markers and opacity groups come out bit-identical.
    /// This test pins the total: comfortably sub-perceptual, and not growing
    /// without bound as bands multiply.
    #[test]
    fn banded_render_matches_single_band() {
        let scene = mixed_scene();
        let reference = render_pixmap_banded(&scene, 2.0, false, Some(1)).unwrap();
        for bands in [2u32, 3, 7, 16, 64] {
            let banded = render_pixmap_banded(&scene, 2.0, false, Some(bands)).unwrap();
            assert_eq!(
                (banded.width(), banded.height()),
                (reference.width(), reference.height())
            );
            let (avg, non_white) = avg_and_content(&banded, &reference);
            assert!(
                non_white > 5000,
                "expected substantial content, got {non_white}px"
            );
            assert!(
                avg < 0.5,
                "{bands} bands differ from a single band by {avg:.4}/255 on average"
            );
        }
    }

    /// The band count must depend on the canvas alone. If it were derived from
    /// the core count, the same figure would render differently on a different
    /// machine - the AA and resampling differences above are small, but they
    /// are not nothing, and reproducibility is the point of the golden suite.
    #[test]
    fn band_count_is_machine_independent() {
        let heavy = (2000u32, 1500u32, 500_000u64);
        let expected = band_count(heavy.0, heavy.1, heavy.2);
        assert!(expected > 1);
        // Re-derive it under pools of different sizes; nothing may change.
        for threads in [1usize, 3, 32] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            let got = pool.install(|| band_count(heavy.0, heavy.1, heavy.2));
            assert_eq!(got, expected, "band count changed with {threads} threads");
        }
    }

    /// The band decomposition is fixed, so a banded render must be repeatable
    /// byte for byte - the golden suite compares whole PNG files.
    #[test]
    fn banded_render_is_deterministic() {
        let scene = mixed_scene();
        let a = render_pixmap_banded(&scene, 2.0, false, Some(16)).unwrap();
        for _ in 0..4 {
            let b = render_pixmap_banded(&scene, 2.0, false, Some(16)).unwrap();
            assert_eq!(a.data(), b.data(), "banded render is not deterministic");
        }
    }

    /// Ordinary figures must keep the exact single-pass path: banding trades a
    /// little antialiasing fidelity for speed, and there is nothing to win on a
    /// raster that takes a millisecond.
    #[test]
    fn small_figures_are_not_banded() {
        // A typical single-panel figure at 200 dpi: ~1 Mpx, a few hundred
        // primitives.
        assert_eq!(
            band_count(1000, 722, 400),
            1,
            "typical figure must not band"
        );
        assert_eq!(band_count(1556, 1167, 5_000), 1, "golden-sized figure");
        // Too small to matter however busy it is.
        assert_eq!(band_count(300, 200, 10_000_000), 1, "tiny canvas");
        // A big, busy raster is what banding is for.
        assert!(
            band_count(2000, 1500, 500_000) > 1,
            "a heavy raster must band"
        );
    }

    /// A few distinct frames -> a valid 89a GIF with the canvas size of frame 0,
    /// one Graphic Control Extension per frame, and a NETSCAPE loop block iff
    /// `infinite`. (0x21F904 is unambiguous as a GCE introducer + block size.)
    #[test]
    fn render_gif_structure() {
        let frames: Vec<Scene> = (0..4).map(frame_scene).collect();
        let refs: Vec<&Scene> = frames.iter().collect();

        let looping = render_gif(&refs, 1.0, 5, true).unwrap();
        assert_eq!(&looping[..6], b"GIF89a");
        let w = u16::from_le_bytes([looping[6], looping[7]]);
        let h = u16::from_le_bytes([looping[8], looping[9]]);
        assert_eq!((w, h), (40, 30), "canvas = frame 0 size at scale 1.0");
        let gce = looping.windows(3).filter(|w| w == b"\x21\xf9\x04").count();
        assert_eq!(gce, 4, "one Graphic Control Extension per frame");
        assert!(
            looping.windows(11).any(|w| w == b"NETSCAPE2.0"),
            "infinite loop must emit a NETSCAPE2.0 application extension"
        );

        let once = render_gif(&refs, 1.0, 5, false).unwrap();
        assert!(
            !once.windows(11).any(|w| w == b"NETSCAPE2.0"),
            "play-once must not emit a loop block"
        );
    }

    /// A few frames -> a valid APNG: PNG signature, an `acTL` recording the
    /// frame count and play count, and one frame chunk-group per frame
    /// (frame 0 = `IDAT`, the rest = `fdAT`).
    #[test]
    fn render_apng_structure() {
        let frames: Vec<Scene> = (0..3).map(frame_scene).collect();
        let refs: Vec<&Scene> = frames.iter().collect();
        let png = render_apng(&refs, 96.0, 1, 20, true).unwrap();
        assert_eq!(&png[..8], b"\x89PNG\r\n\x1a\n");

        // Walk the chunk stream: [len:4][type:4][data:len][crc:4].
        let (mut i, mut actl, mut idat, mut fdat, mut fctl) = (8usize, None, 0, 0, 0);
        while i + 8 <= png.len() {
            let len = u32::from_be_bytes(png[i..i + 4].try_into().unwrap()) as usize;
            let typ = &png[i + 4..i + 8];
            match typ {
                b"acTL" => {
                    let d = &png[i + 8..i + 16];
                    actl = Some((
                        u32::from_be_bytes(d[0..4].try_into().unwrap()),
                        u32::from_be_bytes(d[4..8].try_into().unwrap()),
                    ));
                }
                b"IDAT" => idat += 1,
                b"fdAT" => fdat += 1,
                b"fcTL" => fctl += 1,
                _ => {}
            }
            i += 12 + len;
        }
        assert_eq!(actl, Some((3, 0)), "acTL: 3 frames, num_plays=0 (infinite)");
        assert_eq!(fctl, 3, "one fcTL per frame");
        assert_eq!(idat, 1, "frame 0 is encoded as IDAT");
        assert_eq!(fdat, 2, "frames 1..n are encoded as fdAT");
    }

    /// A small scene whose content depends on `i`, for animation tests.
    fn frame_scene(i: u32) -> Scene {
        let mut scene = Scene::new(Size::new(40.0, 30.0));
        scene.push(Node::Path(PathNode {
            geometry: Circle::new((6.0 + i as f64 * 8.0, 15.0), 4.0).to_path(0.05),
            fill: Some(Color::rgb(20, 120, 200)),
            fill_rule: FillRule::NonZero,
            stroke: None,
        }));
        scene
    }
}
