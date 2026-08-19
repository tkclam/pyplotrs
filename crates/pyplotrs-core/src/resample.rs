//! Per-axis image resampling.
//!
//! An image node is drawn into a rect whose size has nothing to do with its
//! source pixel grid, so each axis is independently magnified or reduced - and
//! the two directions want opposite filters. Reducing 1000 rows onto 215
//! device pixels has to *average*, or four rows in five are simply dropped and
//! the plot shows a moire pattern rather than the field. Magnifying 4 columns
//! across 280 device pixels must *not* average, or the four bands smear into
//! one gradient and the sharpest thing in the data reads as the blurriest
//! thing on the page.
//!
//! No backend can express that, because each offers exactly one filter for the
//! whole image: tiny-skia's `FilterQuality`, SVG's `image-rendering`, PDF's
//! `/Interpolate`. Whichever a backend picks is wrong along one axis of a tall
//! or wide image, and measurably so - rendered from the same 1000x4 figure,
//! the raster backend (nearest) left *every* output pixel pure black or white,
//! averaging nothing at all, while librsvg and ghostscript (smooth) spread
//! each column boundary over 85 and 284 pixels respectively. It is also
//! matplotlib's bug: its `imshow` picks `nearest` only when *both* axes are
//! magnified, so one long axis forces the smoothing filter onto the short one.
//!
//! So the choice is made here instead, before any backend sees the image, by
//! resampling onto the pixel grid the image will actually occupy. The filter
//! is a **separable box (area) filter**, which needs no per-axis mode decision
//! because it already is one:
//!
//! - Reducing an axis, a destination sample spans several source samples and
//!   averages them by how much of each it covers - the correct area average,
//!   so nothing is dropped.
//! - Magnifying an axis, a destination sample falls inside a single source
//!   sample and copies it, exactly like nearest - except at a block boundary,
//!   where the one sample straddling it gets the two blocks' weighted mix.
//!   That is a hard edge carrying one pixel of antialiasing: as sharp as
//!   nearest, minus the jitter. (Nearest has to round each boundary to a whole
//!   pixel, which renders equal source rows as runs of 1, 2 and 3 pixels; a
//!   box filter puts every boundary at its exact fractional position.)
//!
//! Afterwards the grid maps about 1:1 onto the output, which leaves the
//! backend's own filter with nothing left to get wrong - and is what makes the
//! three formats agree with each other.
//!
//! Resampling is not free, though, in time or in bytes, so each backend picks
//! its target through its own rule - [`target_grid`] for a raster backend,
//! [`vector_grid`] for a vector one. Both always resample a *reduced* axis,
//! since that is the aliasing fix; they differ on when magnifying is worth it,
//! because a raster backend's own filter is nearest (already sharp, so it can
//! decline) while a vector backend's viewer smooths (so it cannot).

use crate::ImageData;

/// Default resolution embedded images are resampled to in the **vector**
/// backends, in pixels per inch.
///
/// A vector backend has no device grid to resample onto: the page is
/// resolution-independent, but the raster it embeds is not, so a resolution
/// has to be chosen. 200 ppi matches `Figure.save`'s default `dpi`, so an SVG
/// and a PNG of one figure carry the same image detail; it is also well above
/// screen resolution, which keeps the single pixel of antialiasing at a block
/// boundary under one device pixel at ordinary zoom - i.e. the short axis
/// reads as sharp, which is the whole point.
///
/// It is only the *default*: `Figure.save(dpi=...)` overrides it, which is
/// what lets a heatmap meet a journal's 300-600 dpi minimum in the vector
/// deliverable. Fixing it here meant a PDF's images always carried a third of
/// a 600-dpi PNG's detail no matter what was asked for, and `dpi` was
/// documented as simply ignored for PDF and SVG.
pub const VECTOR_IMAGE_PPI: f64 = 200.0;

/// Largest grid [`vector_grid`] will return, in pixels.
///
/// Only the vector backends need a cap: their target comes from
/// [`VECTOR_IMAGE_PPI`] and a page size, where a raster backend's comes from a
/// canvas that is already bounded. 16 Mpx is a 200 ppi grid over roughly
/// 20 x 20 inches; past that the resample and the encode cost more than the
/// sharpness is worth, so the target is scaled back, keeping the aspect ratio.
const MAX_GRID_PIXELS: f64 = 16.0e6;

/// Round a target to whole pixels, capping the total, and report `None` when
/// it lands back on the source grid and there is nothing to do.
fn settle(src_w: u32, src_h: u32, w: f64, h: f64) -> Option<(u32, u32)> {
    if src_w == 0 || src_h == 0 {
        return None;
    }
    if !(w.is_finite() && h.is_finite() && w > 0.0 && h > 0.0) {
        return None;
    }
    let (mut w, mut h) = (w.round().max(1.0), h.round().max(1.0));
    let pixels = w * h;
    if pixels > MAX_GRID_PIXELS {
        let k = (MAX_GRID_PIXELS / pixels).sqrt();
        w = (w * k).round().max(1.0);
        h = (h * k).round().max(1.0);
    }
    let (w, h) = (w as u32, h as u32);
    (w != src_w || h != src_h).then_some((w, h))
}

/// Magnification past which a raster backend stops resampling and lets
/// nearest-neighbor have the axis.
///
/// Nearest places a block boundary within half a device pixel of the truth;
/// what a box filter adds is that half pixel back, as an exact fractional
/// edge. That matters while a block is a few pixels wide - at 2.15 px per
/// block, nearest renders equal source rows as runs of 1, 2 and 3 pixels - and
/// stops mattering once a block is wide enough that half a pixel is nothing.
/// At 8x it is a 6% wobble on a block, invisible, and skipping the resample
/// there is what keeps a small image on a poster-sized canvas cheap.
const RASTER_MAGNIFY_LIMIT: f64 = 8.0;

/// How many samples one axis should carry in a raster backend.
fn raster_axis(src: u32, dst_px: f64) -> f64 {
    if f64::from(src) >= dst_px {
        // Reducing. Never skipped: this is what stops rows being dropped.
        return dst_px;
    }
    if dst_px / f64::from(src) > RASTER_MAGNIFY_LIMIT {
        return f64::from(src);
    }
    dst_px
}

/// The pixel grid an image with a `src_w` x `src_h` source should be resampled
/// onto when it is drawn into a rect `dst_w` x `dst_h` **device pixels**
/// across, or `None` when there is nothing worth doing.
///
/// For a raster backend, which knows exactly what grid it is drawing onto -
/// and whose own filter is nearest, so an axis it hands back unresampled stays
/// sharp rather than smearing (which is why this can skip work
/// [`vector_grid`] cannot).
pub fn target_grid(src_w: u32, src_h: u32, dst_w: f64, dst_h: f64) -> Option<(u32, u32)> {
    settle(
        src_w,
        src_h,
        raster_axis(src_w, dst_w),
        raster_axis(src_h, dst_h),
    )
}

/// How many samples one axis should carry in a vector backend, for a source of
/// `src` samples drawn across `dst_pt` points.
fn vector_axis(src: u32, dst_pt: f64, ppi: f64) -> f64 {
    let grid = dst_pt * ppi / 72.0;
    if f64::from(src) > grid {
        // Reducing. Always worth it: it is what stops the viewer decimating,
        // and it makes the embedded image smaller rather than larger.
        return grid;
    }
    // Magnifying, which costs file size, so it has to buy something. What it
    // buys is a shorter smear from the viewer's own filter, which spans one
    // source sample - i.e. `dst_pt / src` points. Once the source carries a
    // sample per point that smear is already under a point, thinner than any
    // rule the page draws, and paying several times the bytes to shrink it
    // further is not a trade worth making. A single sample has no neighbor to
    // blend with and cannot smear at all.
    if src <= 1 || f64::from(src) >= dst_pt {
        return f64::from(src);
    }
    grid
}

/// The pixel grid a **vector** backend should embed for an image drawn across
/// `dst_w` x `dst_h` **points**, or `None` to embed the source unchanged.
///
/// Each axis decides for itself, so the tall case this module exists for -
/// hundreds of rows reduced onto a short page span, four columns stretched
/// across a wide one - reduces one axis and magnifies the other in one pass.
pub fn vector_grid(src_w: u32, src_h: u32, dst_w: f64, dst_h: f64, ppi: f64) -> Option<(u32, u32)> {
    let ppi = if ppi.is_finite() && ppi > 0.0 {
        ppi
    } else {
        VECTOR_IMAGE_PPI
    };
    settle(
        src_w,
        src_h,
        vector_axis(src_w, dst_w, ppi),
        vector_axis(src_h, dst_h, ppi),
    )
}

/// The source samples feeding each destination sample along one axis, with
/// their weights.
struct AxisTaps {
    /// `taps[offsets[j]..offsets[j + 1]]` feeds destination sample `j`.
    offsets: Vec<u32>,
    /// `(source index, weight)`, the weights for one destination summing to 1.
    taps: Vec<(u32, f32)>,
}

impl AxisTaps {
    /// Box-filter weights mapping `src` samples onto `dst`: destination sample
    /// `j` covers the source interval `[j*s, (j+1)*s)` for `s = src/dst`, and
    /// each source sample is weighted by how much of that interval it holds.
    fn box_filter(src: u32, dst: u32) -> Self {
        let s = f64::from(src) / f64::from(dst);
        let mut offsets = Vec::with_capacity(dst as usize + 1);
        let mut taps = Vec::with_capacity((dst as usize) * (s.ceil() as usize + 1));
        offsets.push(0);
        for j in 0..dst {
            let lo = f64::from(j) * s;
            let hi = lo + s;
            let first = (lo.floor() as u32).min(src - 1);
            let last = (hi.ceil() as u32).clamp(first + 1, src);
            let start = taps.len();
            let mut total = 0.0;
            for i in first..last {
                let overlap = hi.min(f64::from(i) + 1.0) - lo.max(f64::from(i));
                if overlap > 0.0 {
                    taps.push((i, overlap as f32));
                    total += overlap;
                }
            }
            if total > 0.0 {
                let inv = (1.0 / total) as f32;
                for tap in &mut taps[start..] {
                    tap.1 *= inv;
                }
            } else {
                // Unreachable for a positive scale, but a degenerate tap list
                // would silently blank the sample rather than fail loudly.
                taps.push((first, 1.0));
            }
            offsets.push(taps.len() as u32);
        }
        Self { offsets, taps }
    }

    fn of(&self, j: usize) -> &[(u32, f32)] {
        &self.taps[self.offsets[j] as usize..self.offsets[j + 1] as usize]
    }
}

/// Read pixel `i` as premultiplied RGBA, with alpha kept on a 0..255 scale.
///
/// Averaging has to happen in premultiplied space: a colormapped image makes
/// its non-finite samples fully transparent *black*, and blending that
/// straight would drag the neighboring colors toward black instead of just
/// lowering their coverage.
fn premultiplied(src: &[u8], i: usize) -> [f32; 4] {
    let p = &src[i * 4..i * 4 + 4];
    let a = f32::from(p[3]);
    let k = a * (1.0 / 255.0);
    [
        f32::from(p[0]) * k,
        f32::from(p[1]) * k,
        f32::from(p[2]) * k,
        a,
    ]
}

fn plane_pixel(plane: &[f32], i: usize) -> [f32; 4] {
    [
        plane[i * 4],
        plane[i * 4 + 1],
        plane[i * 4 + 2],
        plane[i * 4 + 3],
    ]
}

fn store_plane(plane: &mut [f32], i: usize, p: [f32; 4]) {
    plane[i * 4..i * 4 + 4].copy_from_slice(&p);
}

/// Undo [`premultiplied`], writing the straight RGBA8 the IR carries.
///
/// The *last* pass writes through this rather than filling another `f32`
/// plane for a whole separate conversion sweep: at 16 bytes a pixel that plane
/// is the largest allocation in the resample (288 MB for a small image blown
/// up onto a poster-sized canvas), and it exists only to be read once.
fn store_straight(out: &mut [u8], i: usize, p: [f32; 4]) {
    let a = p[3];
    if a <= 0.0 {
        return; // fully transparent stays RGBA = 0
    }
    let inv = 255.0 / a;
    let o = &mut out[i * 4..i * 4 + 4];
    o[0] = (p[0] * inv + 0.5).clamp(0.0, 255.0) as u8;
    o[1] = (p[1] * inv + 0.5).clamp(0.0, 255.0) as u8;
    o[2] = (p[2] * inv + 0.5).clamp(0.0, 255.0) as u8;
    o[3] = (a + 0.5).clamp(0.0, 255.0) as u8;
}

/// One separable pass along x: `w` columns in, `dw` out, `h` rows untouched.
///
/// Reads through `get` and writes through `put` so one implementation serves
/// both passes - the first reading RGBA8 and filling an `f32` plane, the last
/// reading that plane and writing RGBA8 straight out.
fn scale_x<F, W>(get: F, w: u32, h: u32, dw: u32, taps: &AxisTaps, mut put: W)
where
    F: Fn(usize) -> [f32; 4],
    W: FnMut(usize, [f32; 4]),
{
    let (w, h, dw) = (w as usize, h as usize, dw as usize);
    for y in 0..h {
        for x in 0..dw {
            let mut acc = [0.0f32; 4];
            for &(i, weight) in taps.of(x) {
                let p = get(y * w + i as usize);
                for (a, v) in acc.iter_mut().zip(p) {
                    *a += v * weight;
                }
            }
            put(y * dw + x, acc);
        }
    }
}

/// One separable pass along y: rows in, `dh` out, `w` columns untouched.
fn scale_y<F, W>(get: F, w: u32, dh: u32, taps: &AxisTaps, mut put: W)
where
    F: Fn(usize) -> [f32; 4],
    W: FnMut(usize, [f32; 4]),
{
    let (w, dh) = (w as usize, dh as usize);
    for y in 0..dh {
        let row = taps.of(y);
        for x in 0..w {
            let mut acc = [0.0f32; 4];
            for &(i, weight) in row {
                let p = get(i as usize * w + x);
                for (a, v) in acc.iter_mut().zip(p) {
                    *a += v * weight;
                }
            }
            put(y * w + x, acc);
        }
    }
}

/// Resample straight RGBA8 `src` (`sw` x `sh`) onto a `dw` x `dh` grid with a
/// separable box filter - see the module docs for why that filter.
///
/// Returns the source unchanged if any dimension is zero or `src` is not
/// `sw * sh * 4` bytes, so a malformed node degrades to today's behavior
/// rather than panicking inside a renderer.
pub fn resample_rgba(src: &[u8], sw: u32, sh: u32, dw: u32, dh: u32) -> Vec<u8> {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 {
        return src.to_vec();
    }
    if src.len() != (sw as usize) * (sh as usize) * 4 {
        return src.to_vec();
    }
    let tx = AxisTaps::box_filter(sw, dw);
    let ty = AxisTaps::box_filter(sh, dh);
    let mut out = vec![0u8; (dw as usize) * (dh as usize) * 4];
    // Run whichever pass shrinks the buffer first, so the intermediate plane
    // is the smaller of the two it could be.
    let x_first = u64::from(dw) * u64::from(sh) <= u64::from(sw) * u64::from(dh);
    if x_first {
        let mut mid = vec![0.0f32; (dw as usize) * (sh as usize) * 4];
        scale_x(
            |i| premultiplied(src, i),
            sw,
            sh,
            dw,
            &tx,
            |i, p| store_plane(&mut mid, i, p),
        );
        scale_y(
            |i| plane_pixel(&mid, i),
            dw,
            dh,
            &ty,
            |i, p| store_straight(&mut out, i, p),
        );
    } else {
        let mut mid = vec![0.0f32; (sw as usize) * (dh as usize) * 4];
        scale_y(
            |i| premultiplied(src, i),
            sw,
            dh,
            &ty,
            |i, p| store_plane(&mut mid, i, p),
        );
        scale_x(
            |i| plane_pixel(&mid, i),
            sw,
            dh,
            dw,
            &tx,
            |i, p| store_straight(&mut out, i, p),
        );
    }
    out
}

/// Resample a normalized colormap-position field and look the result up.
///
/// The averaging happens on `t` - the position on the color axis - and the
/// colormap is applied afterwards, so every output pixel is a color the map
/// actually assigns to some value. Averaging the RGBA instead produces colors
/// between two entries of the table, which is to say colors that appear
/// nowhere on the figure's own colorbar. See [`pyplotrs_core::ColorField`].
///
/// Masked samples (`NaN`) contribute nothing. Coverage is tracked alongside
/// the sum, exactly as premultiplied alpha is in [`resample_rgba`], so a
/// destination sample straddling the edge of the data comes out partly
/// transparent rather than dragged toward an arbitrary value.
pub fn resample_field(
    t: &[f32],
    sw: u32,
    sh: u32,
    dw: u32,
    dh: u32,
    lut: &[u8],
) -> Option<Vec<u8>> {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 {
        return None;
    }
    if t.len() != (sw as usize) * (sh as usize) || lut.len() != 256 * 4 {
        return None;
    }
    // Channel 0 carries `t` weighted by coverage, channel 1 the coverage.
    let load = |v: f32| -> [f32; 4] {
        if v.is_finite() {
            [v, 1.0, 0.0, 0.0]
        } else {
            [0.0; 4]
        }
    };
    let xt = AxisTaps::box_filter(sw, dw);
    let yt = AxisTaps::box_filter(sh, dh);
    let mut mid = vec![0.0f32; (dw as usize) * (sh as usize) * 4];
    scale_x(
        |i| load(t[i]),
        sw,
        sh,
        dw,
        &xt,
        |i, p| store_plane(&mut mid, i, p),
    );
    let mut out = vec![0u8; (dw as usize) * (dh as usize) * 4];
    scale_y(
        |i| plane_pixel(&mid, i),
        dw,
        dh,
        &yt,
        |i, p| {
            let cov = p[1];
            let o = i * 4;
            if cov <= 0.0 {
                return; // fully masked: leave it clear
            }
            let tv = (p[0] / cov).clamp(0.0, 1.0);
            let k = ((tv * 255.0).round() as usize).min(255) * 4;
            out[o] = lut[k];
            out[o + 1] = lut[k + 1];
            out[o + 2] = lut[k + 2];
            out[o + 3] = (f32::from(lut[k + 3]) * cov + 0.5).clamp(0.0, 255.0) as u8;
        },
    );
    Some(out)
}

impl ImageData {
    /// This image resampled onto a `w` x `h` grid. A colormapped image (one
    /// carrying a [`pyplotrs_core::ColorField`]) resamples its **data** and
    /// re-applies the colormap; anything else falls back to [`resample_rgba`]
    /// on the pixels. Pair it with [`target_grid`] or [`vector_grid`] to pick
    /// that grid.
    pub fn resampled_to(&self, w: u32, h: u32) -> ImageData {
        if let Some(field) = &self.field {
            if let Some(rgba) = resample_field(&field.t, self.width, self.height, w, h, &field.lut)
            {
                let mut out = ImageData::from_rgba8(rgba, w, h);
                // The resampled field travels with the pixels, so a second
                // resample (raster caches one grid, vector another) still
                // averages data rather than the colors of the first pass.
                if let Some(t) = resample_field_plane(&field.t, self.width, self.height, w, h) {
                    out = out.with_field(t, (*field.lut).clone());
                }
                return out;
            }
        }
        ImageData::from_rgba8(
            resample_rgba(&self.rgba, self.width, self.height, w, h),
            w,
            h,
        )
    }
}

/// The `t` plane alone, resampled the same way [`resample_field`] does, with
/// fully-masked destination samples staying `NaN`.
fn resample_field_plane(t: &[f32], sw: u32, sh: u32, dw: u32, dh: u32) -> Option<Vec<f32>> {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 || t.len() != (sw as usize) * (sh as usize) {
        return None;
    }
    let load = |v: f32| -> [f32; 4] {
        if v.is_finite() {
            [v, 1.0, 0.0, 0.0]
        } else {
            [0.0; 4]
        }
    };
    let xt = AxisTaps::box_filter(sw, dw);
    let yt = AxisTaps::box_filter(sh, dh);
    let mut mid = vec![0.0f32; (dw as usize) * (sh as usize) * 4];
    scale_x(
        |i| load(t[i]),
        sw,
        sh,
        dw,
        &xt,
        |i, p| store_plane(&mut mid, i, p),
    );
    let mut out = vec![f32::NAN; (dw as usize) * (dh as usize)];
    scale_y(
        |i| plane_pixel(&mid, i),
        dw,
        dh,
        &yt,
        |i, p| {
            if p[1] > 0.0 {
                out[i] = (p[0] / p[1]).clamp(0.0, 1.0);
            }
        },
    );
    Some(out)
}

/// The device lengths of `rect`'s own x and y edges under `transform`.
///
/// Not the transformed bounding box: under a 90-degree rotation a bbox's width
/// is the rect's *height*, which would hand each axis the other one's target
/// and resample both the wrong way. These stay paired with the image's axes.
pub fn device_extent(rect: crate::Rect, transform: crate::Affine) -> (f64, f64) {
    let [a, b, c, d, _, _] = transform.as_coeffs();
    let (w, h) = (rect.width(), rect.height());
    ((a * w).hypot(b * w), (c * h).hypot(d * h))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a `w` x `h` opaque image from a per-pixel gray value.
    fn gray(w: u32, h: u32, f: impl Fn(u32, u32) -> u8) -> Vec<u8> {
        let mut v = Vec::with_capacity((w * h * 4) as usize);
        for y in 0..h {
            for x in 0..w {
                let g = f(x, y);
                v.extend_from_slice(&[g, g, g, 255]);
            }
        }
        v
    }

    fn red(px: &[u8], w: u32, x: u32, y: u32) -> u8 {
        px[((y * w + x) * 4) as usize]
    }

    #[test]
    fn box_weights_sum_to_one() {
        for (src, dst) in [(1, 1), (4, 300), (1000, 215), (7, 7), (3, 1000), (999, 1)] {
            let taps = AxisTaps::box_filter(src, dst);
            for j in 0..dst as usize {
                let total: f32 = taps.of(j).iter().map(|t| t.1).sum();
                assert!(
                    (total - 1.0).abs() < 1e-5,
                    "src {src} dst {dst} sample {j} weights sum to {total}"
                );
                assert!(taps.of(j).iter().all(|t| t.0 < src));
            }
        }
    }

    /// The defect this module exists for: reducing an axis must average, not
    /// drop. 1000 alternating rows onto 215 must come out uniformly mid-gray.
    #[test]
    fn reducing_an_axis_averages_instead_of_dropping() {
        let src = gray(4, 1000, |_, y| if y % 2 == 0 { 0 } else { 255 });
        let out = resample_rgba(&src, 4, 1000, 4, 215);
        // Skip the outermost rows: they cover a fractional span of the source
        // and legitimately land off 50%.
        for y in 2..213 {
            for x in 0..4 {
                let v = red(&out, 4, x, y);
                assert!(
                    (100..=155).contains(&v),
                    "row {y} col {x} came out {v}, not an average of black and white"
                );
            }
        }
    }

    /// The other half: magnifying an axis must stay sharp. Four alternating
    /// columns across 280 pixels must stay four flat blocks, with at most one
    /// pixel of antialiasing at each boundary.
    #[test]
    fn magnifying_an_axis_stays_sharp() {
        let src = gray(4, 8, |x, _| if x % 2 == 0 { 0 } else { 255 });
        let out = resample_rgba(&src, 4, 8, 280, 8);
        let row: Vec<u8> = (0..280).map(|x| red(&out, 280, x, 3)).collect();
        let blurred = row.iter().filter(|&&v| (8..247).contains(&v)).count();
        assert!(
            blurred <= 3,
            "{blurred} intermediate pixels across 3 boundaries: the columns smeared"
        );
        // Block interiors are flat and exact.
        for (x, want) in [(10u32, 0u8), (80, 255), (150, 0), (250, 255)] {
            assert_eq!(red(&out, 280, x, 3), want, "block interior at x={x}");
        }
    }

    /// Nearest has to round each block boundary to a whole pixel, which is why
    /// it renders equal source rows as runs of 1, 2 and 3 pixels. A box filter
    /// puts each boundary at its exact fractional position and encodes the
    /// remainder in the single pixel straddling it.
    ///
    /// Three columns across 100 pixels puts the boundaries at 33.33 and 66.67,
    /// so pixel 33 must be 2/3 of the way to the next color (not a whole pixel
    /// either side of it) and pixel 34 must already be flat.
    #[test]
    fn magnified_block_edges_land_at_their_exact_position() {
        let src = gray(3, 4, |x, _| if x == 1 { 255 } else { 0 });
        let out = resample_rgba(&src, 3, 4, 100, 4);
        let row: Vec<u8> = (0..100).map(|x| red(&out, 100, x, 1)).collect();
        let two_thirds = (255.0_f64 * 2.0 / 3.0).round() as u8;
        assert_eq!(row[33], two_thirds, "left edge is not at 33.33");
        assert_eq!(row[66], two_thirds, "right edge is not at 66.67");
        assert!(row[..33].iter().all(|&v| v == 0), "left block is not flat");
        assert!(
            row[34..66].iter().all(|&v| v == 255),
            "middle block is not flat"
        );
        assert!(row[67..].iter().all(|&v| v == 0), "right block is not flat");
    }

    /// A box filter conserves the total: reducing must move the average onto
    /// the output, which is exactly what dropping rows fails to do.
    #[test]
    fn reducing_conserves_the_average() {
        let src = gray(1, 1000, |_, y| ((y * 37) % 256) as u8);
        let want: f64 = (0..1000)
            .map(|y| f64::from((y * 37 % 256) as u8))
            .sum::<f64>()
            / 1000.0;
        let out = resample_rgba(&src, 1, 1000, 1, 215);
        let got: f64 = (0..215).map(|y| f64::from(red(&out, 1, 0, y))).sum::<f64>() / 215.0;
        assert!(
            (got - want).abs() < 1.0,
            "mean drifted from {want:.2} to {got:.2}"
        );
    }

    #[test]
    fn a_transparent_neighbor_does_not_darken_its_neighbors() {
        // Left half opaque red, right half fully transparent black - what a
        // colormapped image looks like next to a NaN sample.
        let mut src = Vec::new();
        for _ in 0..8 {
            src.extend_from_slice(&[255, 0, 0, 255]);
            src.extend_from_slice(&[0, 0, 0, 0]);
        }
        let out = resample_rgba(&src, 2, 8, 1, 8);
        for y in 0..8 {
            let p = &out[(y * 4) as usize..(y * 4 + 4) as usize];
            assert_eq!(p[0], 255, "row {y} red channel was dragged toward black");
            assert_eq!(
                p[3], 128,
                "row {y} should be half covered, got alpha {}",
                p[3]
            );
        }
    }

    #[test]
    fn resampling_to_the_same_grid_is_a_no_op() {
        let src = gray(5, 7, |x, y| (x * 31 + y * 7) as u8);
        assert_eq!(resample_rgba(&src, 5, 7, 5, 7), src);
    }

    #[test]
    fn target_grid_skips_a_matching_source() {
        assert_eq!(target_grid(300, 200, 300.4, 199.6), None);
        assert_eq!(target_grid(4, 1000, 0.0, 215.0), None);
        assert_eq!(target_grid(4, 1000, f64::NAN, 215.0), None);
    }

    /// A reduced axis is always resampled - that is the aliasing fix. A
    /// magnified one only while the gain is small enough that nearest's
    /// half-pixel rounding would show; past that nearest is already sharp and
    /// resampling a small image onto a poster is pure cost.
    #[test]
    fn target_grid_reduces_always_but_magnifies_only_when_it_shows() {
        // 1000 rows down onto 215 px: reduced, so resampled.
        assert_eq!(target_grid(1000, 1000, 1000.0, 215.0), Some((1000, 215)));
        // 100 rows up onto 215 px (2.15x): the runs-of-1-2-3 case, resampled.
        assert_eq!(target_grid(100, 100, 100.0, 215.0), Some((100, 215)));
        // 200 rows up onto 3670 px (18x): nearest is already sharp, skipped.
        assert_eq!(target_grid(200, 200, 200.0, 3670.0), None);
        // Mixed: reduce one axis, leave the hugely magnified one to nearest.
        assert_eq!(target_grid(4, 1000, 592.0, 481.0), Some((4, 481)));
    }

    /// The requested dpi drives the embedded resolution, so a 600-dpi save
    /// really does put 600-dpi pixels in the PDF rather than the 200-dpi
    /// default the constant names.
    #[test]
    fn a_higher_ppi_asks_for_a_denser_grid() {
        let at200 = vector_grid(4000, 4000, 200.0, 200.0, 200.0).unwrap();
        let at600 = vector_grid(4000, 4000, 200.0, 200.0, 600.0).unwrap();
        assert_eq!(at200.0, (200.0f64 * 200.0 / 72.0).round() as u32);
        assert_eq!(at600.0, (200.0f64 * 600.0 / 72.0).round() as u32);
        assert!(at600.0 > at200.0 * 2);
        // A nonsense ppi falls back to the default rather than producing a
        // zero-pixel or absurd grid.
        for bad in [0.0, -10.0, f64::NAN] {
            assert_eq!(vector_grid(4000, 4000, 200.0, 200.0, bad), Some(at200));
        }
    }

    #[test]
    fn a_huge_vector_grid_is_capped() {
        let (w, h) = vector_grid(10, 10, 20_000.0, 20_000.0, VECTOR_IMAGE_PPI).unwrap();
        assert!(f64::from(w) * f64::from(h) <= MAX_GRID_PIXELS);
        assert_eq!(w, h, "the cap must keep the aspect ratio");
    }

    /// The tall case, in a vector backend: 4 columns across 213 pt magnify to
    /// the 200 ppi grid so they stay sharp, while 1000 rows down 173 pt reduce
    /// onto it so they stop aliasing - opposite directions, one pass.
    #[test]
    fn vector_grid_magnifies_a_coarse_axis_and_reduces_a_dense_one() {
        let (w, h) = vector_grid(4, 1000, 213.0, 173.0, VECTOR_IMAGE_PPI).unwrap();
        assert_eq!(w, (213.0 * VECTOR_IMAGE_PPI / 72.0).round() as u32);
        assert_eq!(h, (173.0 * VECTOR_IMAGE_PPI / 72.0).round() as u32);
        assert!(w > 4 && h < 1000);
    }

    /// Magnifying costs file size, so an axis already carrying a sample per
    /// point is left alone: the viewer's own smear is under a point there, and
    /// paying 3x the bytes to shorten it is not a trade worth making.
    #[test]
    fn vector_grid_leaves_a_dense_enough_axis_alone() {
        assert_eq!(vector_grid(500, 500, 400.0, 300.0, VECTOR_IMAGE_PPI), None);
        // One sample has no neighbor to blend with, so it cannot smear.
        assert_eq!(vector_grid(1, 256, 10.0, 250.0, VECTOR_IMAGE_PPI), None);
        // ...but a coarse axis still gets magnified.
        let (w, _) = vector_grid(40, 256, 400.0, 250.0, VECTOR_IMAGE_PPI).unwrap();
        assert!(w > 40);
    }

    /// A viridis-like table: two far-apart entries whose RGB midpoint is not
    /// itself in the table.
    fn two_tone_lut() -> Vec<u8> {
        let mut lut = vec![0u8; 256 * 4];
        for i in 0..256 {
            // A hard step at the middle, so an averaged *color* lands on a
            // gray that the table contains nowhere.
            let (r, g, b) = if i < 128 {
                (0u8, 0u8, 255u8)
            } else {
                (255, 255, 0)
            };
            lut[i * 4] = r;
            lut[i * 4 + 1] = g;
            lut[i * 4 + 2] = b;
            lut[i * 4 + 3] = 255;
        }
        lut
    }

    /// Reducing a colormapped image must produce colors the colormap actually
    /// assigns. Averaging the RGBA instead gives the mean of two table entries,
    /// which for a stepped map is a color that appears nowhere on the colorbar
    /// - so a reader matching a pixel against the bar gets no answer.
    #[test]
    fn reducing_a_field_stays_on_the_colormap() {
        let lut = two_tone_lut();
        // Two source samples straddling the step, reduced onto one pixel.
        let t = vec![0.0f32, 1.0];
        let out = resample_field(&t, 2, 1, 1, 1, &lut).expect("resampled");
        assert_eq!(out.len(), 4);
        let px = (out[0], out[1], out[2]);
        // Mean t = 0.5 -> index 128 -> the upper entry, which is on the map.
        assert_eq!(
            px,
            (255, 255, 0),
            "resampled pixel {px:?} is not a table entry"
        );

        // What averaging the *colors* would have given, for contrast.
        let rgba = [0u8, 0, 255, 255, 255, 255, 0, 255];
        let naive = resample_rgba(&rgba, 2, 1, 1, 1);
        assert_eq!(
            (naive[0], naive[1], naive[2]),
            (128, 128, 128),
            "the color-space average is the gray this test exists to avoid"
        );
    }

    /// A masked sample lowers coverage instead of pulling its neighbours
    /// toward an arbitrary value.
    #[test]
    fn a_masked_field_sample_only_lowers_coverage() {
        let lut = two_tone_lut();
        let t = vec![1.0f32, f32::NAN];
        let out = resample_field(&t, 2, 1, 1, 1, &lut).expect("resampled");
        assert_eq!((out[0], out[1], out[2]), (255, 255, 0), "value was dragged");
        assert!(
            (120..=134).contains(&out[3]),
            "half-masked pixel should be about half covered, got alpha {}",
            out[3]
        );

        // Fully masked stays clear.
        let all_nan = vec![f32::NAN; 2];
        let out = resample_field(&all_nan, 2, 1, 1, 1, &lut).expect("resampled");
        assert_eq!(out[3], 0, "a fully masked pixel must stay transparent");
    }

    /// The field travels with the pixels, so a second resample still averages
    /// data rather than the colors the first pass produced.
    #[test]
    fn a_resampled_image_keeps_its_field() {
        let lut = two_tone_lut();
        let img =
            ImageData::from_rgba8(vec![0u8; 4 * 4 * 4], 4, 4).with_field(vec![0.5f32; 16], lut);
        let once = img.resampled_to(2, 2);
        assert!(once.field.is_some(), "the field was dropped on resample");
        let twice = once.resampled_to(1, 1);
        assert!(twice.field.is_some());
        let t = twice.field.as_ref().unwrap().t[0];
        assert!((t - 0.5).abs() < 1e-6, "field drifted to {t}");
    }

    #[test]
    fn device_extent_keeps_axes_paired_under_rotation() {
        use crate::kurbo::{Affine, Rect};
        let rect = Rect::new(0.0, 0.0, 200.0, 50.0);
        let (x, y) = device_extent(rect, Affine::scale(2.0));
        assert!((x - 400.0).abs() < 1e-9 && (y - 100.0).abs() < 1e-9);
        // Rotated a quarter turn, the x edge is 200 long *on screen* still.
        let (x, y) = device_extent(rect, Affine::rotate(std::f64::consts::FRAC_PI_2));
        assert!((x - 200.0).abs() < 1e-9 && (y - 50.0).abs() < 1e-9);
    }
}
