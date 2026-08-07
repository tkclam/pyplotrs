//! pyplotrs-render-raster: renders a [`pyplotrs_core::Scene`] to a raster image
//! using `tiny-skia`, rasterizing glyph outlines via `skrifa`.
//!
//! tiny-skia has no state stack of its own, so groups are handled by carrying
//! an accumulated [`Affine`] transform and an optional device-space clip
//! [`Mask`] down the recursive walk; opacity groups are composited via an
//! offscreen layer.

use pyplotrs_core::kurbo::{Affine, PathEl, Point, Vec2};
use pyplotrs_core::{
    Color, FillRule as CoreFillRule, Group, ImageNode, LineCap as CoreLineCap,
    LineJoin as CoreLineJoin, MarkerNode, Node, PathNode, Scene, Stroke as CoreStroke, TextNode,
};
use skrifa::instance::Size as GlyphSize;
use skrifa::outline::OutlinePen;
use skrifa::{FontRef, GlyphId, MetadataProvider};
use tiny_skia::{
    FillRule, IntSize, LineCap, LineJoin, Mask, Paint, PathBuilder, Pixmap, PixmapPaint,
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

fn render_path(pixmap: &mut Pixmap, p: &PathNode, transform: Affine, clip: Option<&Mask>) {
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

fn render_text(pixmap: &mut Pixmap, text: &TextNode, transform: Affine, clip: Option<&Mask>) {
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

/// Sub-pixel phases per axis for marker sprite stamping. P=4 keeps every
/// stamped marker within 0.125px of its true position (sub-pixel, imperceptible)
/// while avoiding a per-marker path scan-conversion.
const STAMP_PHASES: i32 = 8;
/// Only stamp when there are enough markers to amortize the per-phase tile
/// setup, and each marker is small enough that a tile blit beats a path fill.
const STAMP_MIN_COUNT: usize = 64;
const STAMP_MAX_PX: f32 = 96.0;

/// Largest raster we will try to allocate, in bytes (4 GB - about a 32000 x
/// 32000 px image). Past this the request is almost certainly a units or dpi
/// mistake, and honouring it would abort the process instead of raising.
const MAX_RASTER_BYTES: f64 = 4.0e9;

fn render_markers(pixmap: &mut Pixmap, m: &MarkerNode, transform: Affine, clip: Option<&Mask>) {
    let Some(path) = to_tiny_skia_path(&m.marker) else {
        return;
    };
    let fill_paint = m.fill.map(solid_paint);
    let stroke_paint = m
        .stroke
        .as_ref()
        .map(|s| (solid_paint(s.color), to_ts_stroke(s)));
    let fill_rule = to_ts_fill_rule(m.fill_rule);

    // Colormapped scatter: one fill per point, so the single-color stamp tile
    // can't be shared. Fill the shared outline with each point's own paint.
    if let Some(colors) = &m.colors {
        for (pos, c) in m.positions.iter().zip(colors) {
            let ts = to_ts_transform(transform * Affine::translate(Vec2::new(pos.x, pos.y)));
            pixmap.fill_path(&path, &solid_paint(*c), fill_rule, ts, clip);
            if let Some((paint, stroke)) = &stroke_paint {
                pixmap.stroke_path(&path, paint, stroke, ts, clip);
            }
        }
        return;
    }

    // Fast path: rasterize the marker once per sub-pixel phase into a small
    // tile, then alpha-blit that tile at each position - the raster analog of
    // the PDF Form-XObject / SVG <use> instancing, and what makes a 1e6-point
    // scatter quick. Falls back to per-point path filling for few/large markers
    // or a degenerate transform.
    if m.positions.len() >= STAMP_MIN_COUNT
        && stamp_markers(
            pixmap,
            &path,
            &fill_paint,
            &stroke_paint,
            fill_rule,
            &m.positions,
            transform,
            clip,
        )
        .is_some()
    {
        return;
    }

    for pos in &m.positions {
        let ts = to_ts_transform(transform * Affine::translate(Vec2::new(pos.x, pos.y)));
        if let Some(paint) = &fill_paint {
            pixmap.fill_path(&path, paint, fill_rule, ts, clip);
        }
        if let Some((paint, stroke)) = &stroke_paint {
            pixmap.stroke_path(&path, paint, stroke, ts, clip);
        }
    }
}

/// Stamp `path` at every position by pre-rasterizing it into `P x P` sub-pixel
/// phase tiles and alpha-compositing the nearest-phase tile at each point.
/// Returns `None` (so the caller falls back to per-point path filling) when the
/// marker is too large or the tiles can't be allocated.
#[allow(clippy::too_many_arguments)]
fn stamp_markers(
    pixmap: &mut Pixmap,
    path: &tiny_skia::Path,
    fill_paint: &Option<Paint<'static>>,
    stroke_paint: &Option<(Paint<'static>, Stroke)>,
    fill_rule: FillRule,
    positions: &[Point],
    transform: Affine,
    clip: Option<&Mask>,
) -> Option<()> {
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
    let anchor_x = -x0; // tile-local pixel of the marker origin at phase 0
    let anchor_y = -y0;

    // One tile per (pi, pj) sub-pixel phase.
    let p = STAMP_PHASES;
    let mut tiles: Vec<Pixmap> = Vec::with_capacity((p * p) as usize);
    for pj in 0..p {
        for pi in 0..p {
            let mut tile = Pixmap::new(tw as u32, th as u32)?;
            let ax = anchor_x + pi as f32 / p as f32;
            let ay = anchor_y + pj as f32 / p as f32;
            let ts = to_ts_transform(Affine::translate(Vec2::new(ax as f64, ay as f64)) * lin);
            if let Some(paint) = fill_paint {
                tile.fill_path(path, paint, fill_rule, ts, None);
            }
            if let Some((paint, stroke)) = stroke_paint {
                tile.stroke_path(path, paint, stroke, ts, None);
            }
            tiles.push(tile);
        }
    }

    let pw = pixmap.width() as i32;
    let ph = pixmap.height() as i32;
    for pos in positions {
        let dpt = transform * *pos;
        let (cx, cy) = (dpt.x as f32, dpt.y as f32);
        // Nearest sub-pixel phase; the residual is absorbed by rounding the
        // integer destination, so the placement error stays <= 0.5/P px.
        let pi = (((cx - cx.floor()) * p as f32).round() as i32 % p).max(0);
        let pj = (((cy - cy.floor()) * p as f32).round() as i32 % p).max(0);
        let dest_x = (cx - anchor_x - pi as f32 / p as f32).round() as i32;
        let dest_y = (cy - anchor_y - pj as f32 / p as f32).round() as i32;
        blit_tile(
            pixmap,
            pw,
            ph,
            &tiles[(pj * p + pi) as usize],
            tw,
            dest_x,
            dest_y,
            clip,
        );
    }
    Some(())
}

/// Source-over alpha-composite a premultiplied `tile` onto `pixmap` at
/// `(dest_x, dest_y)`, clipped to the pixmap bounds and (if present) the device
/// clip mask. This is a tight hand-rolled blit rather than `Pixmap::draw_pixmap`
/// because the latter sets up a pattern shader per call - far too slow when
/// stamping ~1e6 tiny tiles. Source-over is associative, so compositing the
/// pre-rendered fill+stroke tile gives the same result as the per-point
/// `fill_path`/`stroke_path` fallback (verified by pixel diff). The clip mask
/// shares the pixmap's dimensions (see `render_group`).
#[allow(clippy::too_many_arguments)]
fn blit_tile(
    pixmap: &mut Pixmap,
    pw: i32,
    ph: i32,
    tile: &Pixmap,
    tw: i32,
    dest_x: i32,
    dest_y: i32,
    clip: Option<&Mask>,
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
            let (mut sr, mut sg, mut sb) = (s.red() as u32, s.green() as u32, s.blue() as u32);
            if let Some(cd) = clip_data {
                let k = cd[dst_row + dx as usize] as u32;
                if k == 0 {
                    continue;
                }
                if k != 255 {
                    sa = (sa * k + 127) / 255;
                    sr = (sr * k + 127) / 255;
                    sg = (sg * k + 127) / 255;
                    sb = (sb * k + 127) / 255;
                }
            }
            let idx = dst_row + dx as usize;
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

fn render_image(pixmap: &mut Pixmap, im: &ImageNode, transform: Affine, clip: Option<&Mask>) {
    let (w, h) = (im.data.width, im.data.height);
    let Some(size) = IntSize::from_wh(w, h) else {
        return;
    };
    // tiny-skia stores premultiplied RGBA; our IR carries straight RGBA.
    let mut data = (*im.data.rgba).clone();
    for px in data.chunks_exact_mut(4) {
        let a = px[3] as u16;
        px[0] = (px[0] as u16 * a / 255) as u8;
        px[1] = (px[1] as u16 * a / 255) as u8;
        px[2] = (px[2] as u16 * a / 255) as u8;
    }
    let Some(src) = Pixmap::from_vec(data, size) else {
        return;
    };
    // Map the image's pixel grid to fill the destination rect.
    let img_tf = transform
        * Affine::translate(Vec2::new(im.rect.x0, im.rect.y0))
        * Affine::scale_non_uniform(im.rect.width() / w as f64, im.rect.height() / h as f64);
    pixmap.draw_pixmap(
        0,
        0,
        src.as_ref(),
        &PixmapPaint::default(),
        to_ts_transform(img_tf),
        clip,
    );
}

fn render_group(pixmap: &mut Pixmap, g: &Group, transform: Affine, clip: Option<&Mask>) {
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
        let Some(mut layer) = Pixmap::new(pixmap.width(), pixmap.height()) else {
            return;
        };
        for child in &g.children {
            render_node(&mut layer, child, child_tf, effective_clip);
        }
        let paint = PixmapPaint {
            opacity: g.opacity.clamp(0.0, 1.0),
            ..Default::default()
        };
        pixmap.draw_pixmap(0, 0, layer.as_ref(), &paint, Transform::identity(), None);
    } else {
        for child in &g.children {
            render_node(pixmap, child, child_tf, effective_clip);
        }
    }
}

fn render_node(pixmap: &mut Pixmap, node: &Node, transform: Affine, clip: Option<&Mask>) {
    match node {
        Node::Path(p) => render_path(pixmap, p, transform, clip),
        Node::Text(t) => render_text(pixmap, t, transform, clip),
        Node::Image(im) => render_image(pixmap, im, transform, clip),
        Node::Markers(m) => render_markers(pixmap, m, transform, clip),
        Node::Group(g) => render_group(pixmap, g, transform, clip),
    }
}

/// Render `scene` to a [`Pixmap`] (RGBA8, white background) at `scale`
/// device-pixels per scene-point.
pub fn render_pixmap(scene: &Scene, scale: f64) -> Result<Pixmap, String> {
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
    // `Pixmap::new` returning `None` is not a defence we can rely on. Check the
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
    let mut pixmap = Pixmap::new(width, height)
        .ok_or_else(|| format!("cannot allocate a {width} x {height} px raster"))?;
    pixmap.fill(tiny_skia::Color::WHITE);

    let root = Affine::scale(scale);
    for node in &scene.nodes {
        render_node(&mut pixmap, node, root, None);
    }

    Ok(pixmap)
}

/// Render `scene` to PNG-encoded bytes at `dpi` (dots per inch). The output
/// carries a `pHYs` chunk recording its physical size, so consumers such as
/// LaTeX `\includegraphics` place it at the intended dimensions.
pub fn render_png(scene: &Scene, dpi: f64) -> Result<Vec<u8>, String> {
    let dpi = if dpi.is_finite() && dpi > 0.0 {
        dpi
    } else {
        72.0
    };
    let pixmap = render_pixmap(scene, dpi / 72.0)?;
    encode_png_with_dpi(&pixmap, dpi)
}

/// Encode an (opaque) pixmap to PNG bytes, tagging it with a `pHYs` density
/// chunk derived from `dpi`. The final pixmap is fully opaque (white fill
/// composited under everything), so its premultiplied buffer equals straight
/// RGBA and can be written directly.
fn encode_png_with_dpi(pixmap: &Pixmap, dpi: f64) -> Result<Vec<u8>, String> {
    let ppu = (dpi / 0.0254).round() as u32; // pixels per metre
    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, pixmap.width(), pixmap.height());
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_pixel_dims(Some(png::PixelDimensions {
            xppu: ppu,
            yppu: ppu,
            unit: png::Unit::Meter,
        }));
        let mut writer = encoder
            .write_header()
            .map_err(|e| format!("PNG header write failed: {e}"))?;
        writer
            .write_image_data(pixmap.data())
            .map_err(|e| format!("PNG data write failed: {e}"))?;
    }
    Ok(out)
}

/// Render a sequence of equally-sized scenes to an animated GIF.
///
/// `scale` is device-pixels per scene-point (dpi/72); `delay_cs` is the
/// per-frame delay in centiseconds (GIF's native unit); `infinite` selects
/// looping vs. play-once. Each frame is quantized to its own ≤256-colour
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
    let pixmaps: Vec<Pixmap> = scenes
        .iter()
        .map(|s| render_pixmap(s, scale))
        .collect::<Result<_, _>>()?;
    let (w, h) = (pixmaps[0].width() as u16, pixmaps[0].height() as u16);

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
        for pm in &pixmaps {
            let mut rgba = pm.data().to_vec();
            // speed 10: a balance between NeuQuant quality (1) and speed (30) —
            // plots have few distinct colours so quantization is near-lossless.
            let mut frame = gif::Frame::from_rgba_speed(w, h, &mut rgba, 10);
            frame.delay = delay_cs;
            encoder
                .write_frame(&frame)
                .map_err(|e| format!("GIF frame write failed: {e}"))?;
        }
    }
    Ok(out)
}

/// Render a sequence of equally-sized scenes to an animated PNG (APNG).
///
/// Unlike GIF, APNG keeps full 8-bit-per-channel colour (no palette
/// quantization), so it's the high-fidelity animation format. `delay_num`/
/// `delay_den` give the per-frame delay as a fraction of a second; `infinite`
/// loops forever (`num_plays = 0`) vs. play-once (`num_plays = 1`). The output
/// carries a `pHYs` density chunk like the still-PNG path.
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
    let pixmaps: Vec<Pixmap> = scenes
        .iter()
        .map(|s| render_pixmap(s, dpi / 72.0))
        .collect::<Result<_, _>>()?;
    let (w, h) = (pixmaps[0].width(), pixmaps[0].height());
    let ppu = (dpi / 0.0254).round() as u32;

    let mut out = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut out, w, h);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_pixel_dims(Some(png::PixelDimensions {
            xppu: ppu,
            yppu: ppu,
            unit: png::Unit::Meter,
        }));
        encoder
            .set_animated(pixmaps.len() as u32, u32::from(!infinite))
            .map_err(|e| format!("APNG animation control write failed: {e}"))?;
        encoder
            .set_frame_delay(delay_num, delay_den)
            .map_err(|e| format!("APNG frame delay write failed: {e}"))?;
        let mut writer = encoder
            .write_header()
            .map_err(|e| format!("APNG header write failed: {e}"))?;
        for pm in &pixmaps {
            writer
                .write_image_data(pm.data())
                .map_err(|e| format!("APNG frame write failed: {e}"))?;
        }
    }
    Ok(out)
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
        let reference = render_pixmap(&clip_group(per_path), 2.0).unwrap();

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
