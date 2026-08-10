//! pyplotrs-py: PyO3 bindings exposing the pyplotrs Rust core as `_pyplotrs_core`.
//!
//! This crate is a thin shell over the Rust core. It exposes:
//!
//! - a stateful [`Scene`] builder (paths / text / images / transform+clip
//!   groups) that the Python layer drives to construct a `pyplotrs_core::Scene`,
//!   then renders via the three backend crates;
//! - [`nice_ticks`] and [`solve_layout`], so axis ticking and the single-pass
//!   figure layout (both in `pyplotrs-layout`) are the one source of truth,
//!   shared by the Python API rather than reimplemented there.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use fontdb::{Database, Family, Query, Stretch, Style, Weight};

use pyo3::buffer::PyBuffer;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use pyplotrs_core::kurbo::{Affine, BezPath, Circle, Point, Rect as KRect, Shape, Size};
use pyplotrs_core::{
    ClipPath, Color, FillRule, FontData, Group, ImageData, ImageNode, LineCap, LineJoin,
    MarkerNode, Node, PathNode, Scene as CoreScene, Stroke as CoreStroke, TextNode,
};
use pyplotrs_layout::solve::{AxesBands, FigureSpec};

/// The bundled body fallback (Liberation Sans Regular, SIL OFL): metrically
/// compatible with Arial/Helvetica, so figures laid out against it line-break
/// and size identically to the real fonts. This is what the resolver lands on
/// when the host has none of the preferred sans-serif families installed, and
/// it guarantees rendering never fails for lack of a system font.
const BUNDLED_SANS: &[u8] = include_bytes!("../../../assets/fonts/LiberationSans-Regular.ttf");
const BUNDLED_SANS_BOLD: &[u8] = include_bytes!("../../../assets/fonts/LiberationSans-Bold.ttf");
const BUNDLED_SANS_ITALIC: &[u8] =
    include_bytes!("../../../assets/fonts/LiberationSans-Italic.ttf");
const BUNDLED_SANS_BOLD_ITALIC: &[u8] =
    include_bytes!("../../../assets/fonts/LiberationSans-BoldItalic.ttf");

/// All four bundled body faces, as `(FaceStyle, bytes, PostScript name)`.
///
/// Shipping the emphasis faces and not just Regular is what makes bold and
/// italic hold the same promise as everything else: a figure looks the same on
/// any machine. Resolving them from the host alone would work on a desktop but
/// silently render upright inside a minimal container, which is exactly where
/// figures get built in bulk.
fn bundled_faces() -> [(FaceStyle, &'static [u8], &'static str); 4] {
    [
        (
            FaceStyle {
                bold: false,
                italic: false,
            },
            BUNDLED_SANS,
            "LiberationSans-Regular",
        ),
        (
            FaceStyle {
                bold: true,
                italic: false,
            },
            BUNDLED_SANS_BOLD,
            "LiberationSans-Bold",
        ),
        (
            FaceStyle {
                bold: false,
                italic: true,
            },
            BUNDLED_SANS_ITALIC,
            "LiberationSans-Italic",
        ),
        (
            FaceStyle {
                bold: true,
                italic: true,
            },
            BUNDLED_SANS_BOLD_ITALIC,
            "LiberationSans-BoldItalic",
        ),
    ]
}

/// System font database, built once. We load the host's fonts (honouring its
/// fontconfig setup on Unix) and also register the bundled Liberation Sans, so
/// the preferred-family lookup can always find a metric-compatible sans-serif
/// even on a machine with no fonts of its own.
fn font_db() -> &'static Database {
    static DB: OnceLock<Database> = OnceLock::new();
    DB.get_or_init(|| {
        let mut db = Database::new();
        db.load_system_fonts();
        // Register every bundled face, not just Regular, so a family query for
        // Liberation Sans can find a real bold/italic even with no host fonts.
        for (_, bytes, _) in bundled_faces() {
            db.load_font_data(bytes.to_vec());
        }
        db
    })
}

/// One resolved font face: how to name it and the bytes to shape and embed.
#[derive(Clone)]
struct ResolvedFace {
    /// Family as the font names itself (a Helvetica query may land on
    /// "Nimbus Sans"). Identical across the four faces of a family.
    family: String,
    /// PostScript name, e.g. `ArialMT` vs `Arial-BoldMT`. This is what tells the
    /// faces apart, and so whether a bold request actually found a bold face.
    postscript: String,
    data: FontData,
}

/// The bundled body face for `face`, used directly (no host lookup). This is the
/// last resort when none of the preferred families resolves.
fn bundled_body(face: FaceStyle) -> ResolvedFace {
    let (_, bytes, postscript) = bundled_faces()
        .into_iter()
        .find(|(f, _, _)| *f == face)
        .unwrap_or(bundled_faces()[0]);
    ResolvedFace {
        family: "Liberation Sans".to_string(),
        postscript: postscript.to_string(),
        data: FontData::from_bytes(bytes.to_vec(), 0),
    }
}

/// The default preferred sans-serif families: the host's Arial, then
/// Helvetica, then the bundled (Arial-metric-compatible) Liberation Sans.
/// Whichever is chosen is embedded into every saved figure, so a saved file
/// always *views* identically across machines regardless of this choice.
fn default_sans_serif() -> Vec<String> {
    ["Arial", "Helvetica", "Liberation Sans"]
        .into_iter()
        .map(String::from)
        .collect()
}

/// User-configured preferred sans-serif families (matplotlib's
/// `rcParams["font.sans-serif"]` analogue). `None` means "use the default"
/// ([`default_sans_serif`]). Each name is tried in order against the host's
/// installed fonts; the bundled Liberation Sans is always the final fallback.
static SANS_SERIF: Mutex<Option<Vec<String>>> = Mutex::new(None);

/// One face of the body family. Text is drawn in exactly one of these four, so
/// they are resolved and cached independently: a host may have Arial Regular and
/// Arial Bold but no Arial Italic, and each should land on the best face for
/// *that* combination rather than all sharing one lookup.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, Default)]
struct FaceStyle {
    bold: bool,
    italic: bool,
}

impl FaceStyle {
    /// Parse the selector the Python layer sends: `"body"`, `"body-bold"`,
    /// `"body-italic"`, `"body-bolditalic"` (order-insensitive, so
    /// `"body-italic-bold"` works too).
    fn from_selector(kind: &str) -> Self {
        Self {
            bold: kind.contains("bold"),
            italic: kind.contains("italic") || kind.contains("oblique"),
        }
    }

    fn weight(self) -> Weight {
        if self.bold {
            Weight::BOLD
        } else {
            Weight::NORMAL
        }
    }

    fn style(self) -> Style {
        if self.italic {
            Style::Italic
        } else {
            Style::Normal
        }
    }
}

/// Memoised resolution of each body face: the resolved family name plus its
/// bytes, keyed by [`FaceStyle`]. Cleared whenever the preferred families change.
static BODY_CACHE: Mutex<Option<HashMap<FaceStyle, ResolvedFace>>> = Mutex::new(None);

/// Walk a preferred-family list against the host font database, returning the
/// first family that exists (and the name it reports), or the bundled
/// Liberation Sans if none match.
///
/// `face` selects weight and slant. fontdb matches approximately, per the CSS
/// font-matching rules, so a family with no bold face resolves to its regular
/// one rather than failing - text stays legible, it just isn't emboldened.
/// [`resolved_font_variants`] reports what each face actually landed on so that
/// degradation is visible instead of silent.
fn resolve_from_host(families: &[String], face: FaceStyle) -> ResolvedFace {
    let db = font_db();
    families
        .iter()
        .find_map(|fam| {
            let query = Query {
                families: &[Family::Name(fam)],
                weight: face.weight(),
                stretch: Stretch::Normal,
                style: face.style(),
            };
            let id = db.query(&query)?;
            let data = db.with_face_data(id, |bytes, index| {
                FontData::from_bytes(bytes.to_vec(), index)
            })?;
            let info = db.face(id);
            // Report the family as the font itself names it, not the query
            // string (e.g. a Helvetica query may resolve to "Nimbus Sans").
            let name = info
                .and_then(|f| f.families.first().map(|(n, _)| n.clone()))
                .unwrap_or_else(|| fam.clone());
            // The PostScript name is what distinguishes the *faces* of one
            // family (ArialMT vs Arial-BoldMT); the family name is identical
            // across all four, so it cannot show whether bold actually resolved.
            let postscript = info
                .map(|f| f.post_script_name.clone())
                .unwrap_or_else(|| name.clone());
            Some(ResolvedFace {
                family: name,
                postscript,
                data,
            })
        })
        .unwrap_or_else(|| bundled_body(face))
}

/// Resolve the body font (family name + bytes), memoised. Walks the preferred
/// families (default: Arial, Helvetica, then bundled Liberation Sans) against
/// the host's installed fonts, falling back to the bundled font when none
/// match. The resolved font is embedded into saved figures, so the choice
/// never affects how a saved file views on another machine.
fn resolve_body(face: FaceStyle) -> ResolvedFace {
    let mut guard = BODY_CACHE.lock().unwrap();
    let cache = guard.get_or_insert_with(HashMap::new);
    if let Some(hit) = cache.get(&face) {
        return hit.clone();
    }
    let families = SANS_SERIF
        .lock()
        .unwrap()
        .clone()
        .unwrap_or_else(default_sans_serif);
    let resolved = resolve_from_host(&families, face);
    cache.insert(face, resolved.clone());
    resolved
}

/// The resolved regular body font (see [`resolve_body`]).
fn body_font() -> FontData {
    resolve_body(FaceStyle::default()).data
}

/// The bundled math font (STIX Two Math, SIL OFL): full coverage of Greek,
/// operators, radicals and the Mathematical Alphanumeric Symbols block, used
/// for `$...$` spans by the `mathtext` layer. Always bundled (it has no common
/// system equivalent) so math typesetting is identical everywhere.
fn math_font() -> &'static FontData {
    static FONT: OnceLock<FontData> = OnceLock::new();
    FONT.get_or_init(|| {
        let bytes: &[u8] = include_bytes!("../../../assets/fonts/STIXTwoMath-Regular.ttf");
        FontData::from_bytes(bytes.to_vec(), 0)
    })
}

/// Resolve a font selector string (`"body"` / `"math"`) to font data. Unknown
/// selectors fall back to the body font.
fn font_for_kind(kind: &str) -> FontData {
    match kind {
        "math" => math_font().clone(),
        "body" => body_font(),
        other => resolve_body(FaceStyle::from_selector(other)).data,
    }
}

fn color_from_rgba(rgba: (u8, u8, u8, u8)) -> Color {
    Color::rgba(rgba.0, rgba.1, rgba.2, rgba.3)
}

fn parse_cap(s: &str) -> LineCap {
    match s {
        "round" => LineCap::Round,
        "square" => LineCap::Square,
        _ => LineCap::Butt,
    }
}

fn parse_join(s: &str) -> LineJoin {
    match s {
        "miter" => LineJoin::Miter,
        "bevel" => LineJoin::Bevel,
        _ => LineJoin::Round,
    }
}

fn parse_fill_rule(s: &str) -> FillRule {
    match s {
        "evenodd" => FillRule::EvenOdd,
        _ => FillRule::NonZero,
    }
}

/// Bulk `f64` input from Python, extracted through the **buffer protocol** when
/// the caller can offer one.
///
/// This is the seam that decides how fast a large plot is. PyO3's stock
/// `Vec<f64>` extraction walks the object as a generic sequence and calls
/// `__float__` on every element, so a million-point array costs a million
/// interpreter round-trips. Anything exposing a 1-D contiguous `f64` buffer -
/// `array.array('d')` (what `Axes._coords` now produces) or a NumPy
/// `float64` array - is instead copied out at memcpy speed.
///
/// The fallback keeps plain Python lists working, so this is a pure speedup
/// with no API change and no new dependency: NumPy is fast here because it
/// speaks the buffer protocol, not because pyplotrs imports it.
pub struct F64Data(Vec<f64>);

impl F64Data {
    #[inline]
    fn as_slice(&self) -> &[f64] {
        &self.0
    }
}

impl std::ops::Deref for F64Data {
    type Target = [f64];
    #[inline]
    fn deref(&self) -> &[f64] {
        &self.0
    }
}

impl<'a, 'py> FromPyObject<'a, 'py> for F64Data {
    type Error = PyErr;

    fn extract(obj: pyo3::Borrowed<'a, 'py, PyAny>) -> Result<Self, Self::Error> {
        if let Ok(buf) = PyBuffer::<f64>::get(&obj) {
            // `to_vec` is a straight copy out of the exporter's memory. Reject
            // non-contiguous or multi-dimensional views rather than silently
            // reading them in the wrong order.
            if buf.dimensions() == 1 && buf.is_c_contiguous() {
                return Ok(F64Data(buf.to_vec(obj.py())?));
            }
        }
        Ok(F64Data(obj.extract::<Vec<f64>>()?))
    }
}

/// Finite minimum and maximum of `values`, or `None` when nothing is finite.
///
/// Autoscaling ignores `NaN`/`inf` the way matplotlib does. Doing that scan here
/// rather than in Python is worth a lot: it used to be
/// `[v for v in values if math.isfinite(v)]` followed by `min()`/`max()`, i.e.
/// three passes plus a full intermediate list, and it dominated the profile of a
/// large save - 79% of a one-million-point PNG export.
#[pyfunction]
fn data_range(values: F64Data) -> Option<(f64, f64)> {
    finite_range(values.as_slice())
}

/// Finite min/max over a slice; the shared body behind [`data_range`].
fn finite_range(values: &[f64]) -> Option<(f64, f64)> {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    let mut any = false;
    for &v in values {
        if v.is_finite() {
            any = true;
            if v < lo {
                lo = v;
            }
            if v > hi {
                hi = v;
            }
        }
    }
    if any {
        Some((lo, hi))
    } else {
        None
    }
}

/// Finite min/max restricted to **strictly positive** values, for log-family
/// scales whose domain excludes zero and negatives. `None` when nothing
/// qualifies.
#[pyfunction]
fn positive_range(values: F64Data) -> Option<(f64, f64)> {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    let mut any = false;
    for &v in values.as_slice() {
        if v > 0.0 && v.is_finite() {
            any = true;
            if v < lo {
                lo = v;
            }
            if v > hi {
                hi = v;
            }
        }
    }
    if any {
        Some((lo, hi))
    } else {
        None
    }
}

/// Finite min/max over `values[i] + offsets[i]`, and - when `two_sided` -
/// `values[i] - offsets[i]` as well, without materializing either sequence.
///
/// `two_sided` distinguishes the two callers, and getting it wrong is not
/// visible in a crash: **errorbars** extend both ways from the datum, while a
/// **bar** runs from its base to `base + height` only. Treating a bar as
/// two-sided invents a mirrored negative bound and silently rescales the axis.
#[pyfunction]
#[pyo3(signature = (values, offsets, two_sided=true))]
fn offset_range(values: F64Data, offsets: F64Data, two_sided: bool) -> Option<(f64, f64)> {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    let mut any = false;
    let n = values.len().min(offsets.len());
    for i in 0..n {
        let (v, e) = (values[i], offsets[i]);
        let candidates: &[f64] = if two_sided { &[v - e, v + e] } else { &[v + e] };
        for &candidate in candidates {
            if candidate.is_finite() {
                any = true;
                if candidate < lo {
                    lo = candidate;
                }
                if candidate > hi {
                    hi = candidate;
                }
            }
        }
    }
    if any {
        Some((lo, hi))
    } else {
        None
    }
}

/// Bin `values` into `bins` equal-width bins, returning `(edges, counts)`.
///
/// The 1-D counterpart of [`hist2d`], which was already in Rust while this ran
/// as a `for v in vals:` loop in Python. Semantics match that loop exactly:
/// values outside `[lo, hi]` are dropped, the top edge is inclusive (it lands in
/// the last bin), and `density` divides by `n * width`.
///
/// `range` is the explicit `(lo, hi)`; when `None` the finite data range is used.
/// A degenerate range is widened by 1.0, as an all-equal sample otherwise has
/// nowhere to go.
#[pyfunction]
#[pyo3(signature = (values, bins, range=None, density=false))]
fn histogram(
    values: F64Data,
    bins: usize,
    range: Option<(f64, f64)>,
    density: bool,
) -> (Vec<f64>, Vec<f64>) {
    let vals = values.as_slice();
    let bins = bins.max(1);
    let (mut lo, mut hi) = range.or_else(|| finite_range(vals)).unwrap_or((0.0, 1.0));
    if !(lo.is_finite() && hi.is_finite()) {
        lo = 0.0;
        hi = 1.0;
    }
    if lo == hi {
        hi = lo + 1.0;
    }
    let width = (hi - lo) / bins as f64;
    let edges: Vec<f64> = (0..=bins).map(|i| lo + width * i as f64).collect();

    let mut counts = vec![0.0f64; bins];
    for &v in vals {
        if v < lo || v > hi {
            continue;
        }
        let idx = (((v - lo) / width) as usize).min(bins - 1);
        counts[idx] += 1.0;
    }
    if density {
        let total = vals.len() as f64 * width;
        if total != 0.0 {
            for c in counts.iter_mut() {
                *c /= total;
            }
        }
    }
    (edges, counts)
}

/// A normalization plus a 256-entry RGBA lookup table: the shared machinery
/// behind both colormapped scatter and colormapped images.
///
/// Normalizing happens in *transformed* space so `norm="log"` matches `LogNorm`:
/// `t = (scale(v) - scale(vmin)) / (scale(vmax) - scale(vmin))`.
struct ColorMapper<'a> {
    lut: &'a [u8],
    norm: &'a str,
    tmin: f64,
    span: f64,
}

impl<'a> ColorMapper<'a> {
    fn new(lut: &'a [u8], norm: &'a str, vmin: f64, vmax: f64) -> Self {
        let tmin = apply_scale(norm, vmin);
        let tmax = apply_scale(norm, vmax);
        let span = if tmax > tmin { tmax - tmin } else { 1.0 };
        Self {
            lut,
            norm,
            tmin,
            span,
        }
    }

    /// RGBA for one value, or `None` when it falls outside the norm's domain
    /// (a non-positive value on a log scale, or a NaN) and should be left clear.
    #[inline]
    fn lookup(&self, v: f64) -> Option<(u8, u8, u8, u8)> {
        let t = apply_scale(self.norm, v);
        if !t.is_finite() {
            return None;
        }
        let frac = ((t - self.tmin) / self.span).clamp(0.0, 1.0);
        let i = ((frac * 255.0).round() as usize) * 4;
        Some((
            self.lut[i],
            self.lut[i + 1],
            self.lut[i + 2],
            self.lut[i + 3],
        ))
    }
}

/// Map `values` to per-point RGBA through `lut`, normalized between `vmin` and
/// `vmax` under `norm`.
///
/// Replaces `[cmap(norm(v)) for v in values]`, which was two Python calls per
/// point - so a colormapped scatter of 100k points made 200k interpreter
/// round-trips before any drawing began. Values outside the norm's domain come
/// back fully transparent, matching the image path.
#[pyfunction]
fn map_colors(
    values: F64Data,
    lut: Vec<u8>,
    vmin: f64,
    vmax: f64,
    norm: &str,
) -> Vec<(u8, u8, u8, u8)> {
    let mapper = ColorMapper::new(&lut, norm, vmin, vmax);
    values
        .as_slice()
        .iter()
        .map(|&v| mapper.lookup(v).unwrap_or((0, 0, 0, 0)))
        .collect()
}

// -- colormap/palette registry + color science (pyplotrs-color) -------------
//
// The curated colormap/palette tables and all color-space math live in the
// `pyplotrs-color` crate (matplotlib/colorcet/cmocean-sourced continuous
// maps, matplotlib/ColorBrewer/seaborn-sourced categorical palettes, and
// sRGB/XYZ/Lab/Oklab/CAM16-UCS conversions). These bindings are thin: every
// function below is a direct pass-through, with `u8` triples standing in for
// `pyplotrs_color::Table`'s `[u8; 3]` entries (PyO3 has no fixed-size-array
// conversion, so `Colormap` materializes its 256-entry table as a
// `list[tuple[int,int,int]]` on the Python side).

/// A built-in colormap's exact 256-entry RGB table (`_r` suffix reverses it).
/// `None` if `name` is not registered.
#[pyfunction]
fn colormap_table(name: &str) -> Option<Vec<(u8, u8, u8)>> {
    pyplotrs_color::colormap_table(name).map(|t| t.into_iter().map(|[r, g, b]| (r, g, b)).collect())
}

/// Build a 256-entry RGB table from `(position, color)` stops, interpolated
/// in `space` (`"oklab"` (default/unrecognized), `"lab"`, `"linear"`, or
/// `"srgb"`). Mirrors `Colormap(name, stops=...)`'s construction path.
#[pyfunction]
fn colormap_table_from_stops(stops: Vec<(f64, (u8, u8, u8))>, space: &str) -> Vec<(u8, u8, u8)> {
    let stops: Vec<(f64, [u8; 3])> = stops.into_iter().map(|(p, (r, g, b))| (p, [r, g, b])).collect();
    pyplotrs_color::colormap_table_from_stops(&stops, space)
        .into_iter()
        .map(|[r, g, b]| (r, g, b))
        .collect()
}

/// A built-in categorical/qualitative palette's colors by name (`None` if
/// unregistered).
#[pyfunction]
fn categorical_palette(name: &str) -> Option<Vec<(u8, u8, u8)>> {
    pyplotrs_color::categorical_palette(name).map(|colors| colors.iter().map(|&[r, g, b]| (r, g, b)).collect())
}

/// Names of built-in continuous colormaps, optionally filtered to one
/// category (`"sequential"`, `"diverging"`, `"cyclic"`,
/// `"perceptually_uniform"`, `"miscellaneous"`).
#[pyfunction]
#[pyo3(signature = (category=None))]
fn list_colormaps(category: Option<&str>) -> Vec<String> {
    pyplotrs_color::list_colormaps(category).into_iter().map(String::from).collect()
}

/// Names of built-in categorical/qualitative palettes.
#[pyfunction]
fn list_palettes() -> Vec<String> {
    pyplotrs_color::list_palettes().into_iter().map(String::from).collect()
}

/// Alpha-scale a 256-entry RGB table into a draw-ready 1024-byte RGBA LUT
/// (replaces the 256-iteration Python loop `_draw.py::_colormap_lut` used to
/// do). Errors if `table` is not exactly 256 entries.
#[pyfunction]
fn colormap_rgba_lut(table: Vec<(u8, u8, u8)>, alpha: f64) -> PyResult<Vec<u8>> {
    let table: [[u8; 3]; 256] = table
        .into_iter()
        .map(|(r, g, b)| [r, g, b])
        .collect::<Vec<_>>()
        .try_into()
        .map_err(|_| PyValueError::new_err("colormap_rgba_lut needs exactly 256 entries"))?;
    Ok(pyplotrs_color::rgba_lut(&table, alpha).to_vec())
}

/// sRGB (as `(r, g, b)` bytes 0-255) -> Oklab (`L` in `[0, 1]`, `a`/`b`
/// roughly `[-0.4, 0.4]`).
#[pyfunction]
fn srgb_to_oklab(rgb: (u8, u8, u8)) -> (f64, f64, f64) {
    let [l, a, b] = pyplotrs_color::colorspace::srgb_to_oklab([rgb.0, rgb.1, rgb.2]);
    (l, a, b)
}

/// Oklab -> sRGB bytes (out-of-gamut input is clipped per channel).
#[pyfunction]
fn oklab_to_srgb(lab: (f64, f64, f64)) -> (u8, u8, u8) {
    let [r, g, b] = pyplotrs_color::colorspace::oklab_to_srgb([lab.0, lab.1, lab.2]);
    (r, g, b)
}

/// sRGB -> Oklch (`L` in `[0, 1]`, `chroma` >= 0, `hue` degrees).
#[pyfunction]
fn srgb_to_oklch(rgb: (u8, u8, u8)) -> (f64, f64, f64) {
    let [l, c, h] = pyplotrs_color::colorspace::srgb_to_oklch([rgb.0, rgb.1, rgb.2]);
    (l, c, h)
}

/// Oklch -> sRGB bytes.
#[pyfunction]
fn oklch_to_srgb(lch: (f64, f64, f64)) -> (u8, u8, u8) {
    let [r, g, b] = pyplotrs_color::colorspace::oklch_to_srgb([lch.0, lch.1, lch.2]);
    (r, g, b)
}

/// sRGB -> CIELAB (D65), `L*` in `[0, 100]`.
#[pyfunction]
fn srgb_to_lab(rgb: (u8, u8, u8)) -> (f64, f64, f64) {
    let [l, a, b] = pyplotrs_color::colorspace::srgb_to_lab([rgb.0, rgb.1, rgb.2]);
    (l, a, b)
}

/// CIELAB (D65) -> sRGB bytes.
#[pyfunction]
fn lab_to_srgb(lab: (f64, f64, f64)) -> (u8, u8, u8) {
    let [r, g, b] = pyplotrs_color::colorspace::lab_to_srgb([lab.0, lab.1, lab.2]);
    (r, g, b)
}

/// sRGB -> CIE 1931 XYZ (D65 white point, `Y` in `[0, 1]`).
#[pyfunction]
fn srgb_to_xyz(rgb: (u8, u8, u8)) -> (f64, f64, f64) {
    let [x, y, z] = pyplotrs_color::colorspace::srgb_to_xyz([rgb.0, rgb.1, rgb.2]);
    (x, y, z)
}

/// CIE 1931 XYZ (D65) -> sRGB bytes.
#[pyfunction]
fn xyz_to_srgb(xyz: (f64, f64, f64)) -> (u8, u8, u8) {
    let [r, g, b] = pyplotrs_color::colorspace::xyz_to_srgb([xyz.0, xyz.1, xyz.2]);
    (r, g, b)
}

/// Encoded (gamma) sRGB -> linear-light sRGB (each component `[0, 1]`).
#[pyfunction]
fn srgb_to_linear(rgb: (u8, u8, u8)) -> (f64, f64, f64) {
    let [r, g, b] = pyplotrs_color::colorspace::srgb_to_linear([rgb.0, rgb.1, rgb.2]);
    (r, g, b)
}

/// Linear-light sRGB -> encoded (gamma) sRGB bytes.
#[pyfunction]
fn linear_to_srgb(rgb: (f64, f64, f64)) -> (u8, u8, u8) {
    let [r, g, b] = pyplotrs_color::colorspace::linear_to_srgb([rgb.0, rgb.1, rgb.2]);
    (r, g, b)
}

/// sRGB -> CAM16-UCS (Jmh form: lightness, colorfulness, hue-degrees) under
/// pyplotrs' fixed viewing conditions (see `pyplotrs_color::colorspace`).
#[pyfunction]
fn srgb_to_cam16ucs(rgb: (u8, u8, u8)) -> (f64, f64, f64) {
    let [j, m, h] = pyplotrs_color::colorspace::srgb_to_cam16ucs([rgb.0, rgb.1, rgb.2]);
    (j, m, h)
}

/// CAM16-UCS (Jmh form) -> sRGB bytes.
#[pyfunction]
fn cam16ucs_to_srgb(ucs: (f64, f64, f64)) -> (u8, u8, u8) {
    let [r, g, b] = pyplotrs_color::colorspace::cam16ucs_to_srgb([ucs.0, ucs.1, ucs.2]);
    (r, g, b)
}

/// Perceptual (CAM16-UCS) distance between two sRGB colors.
#[pyfunction]
fn cam16ucs_distance(a: (u8, u8, u8), b: (u8, u8, u8)) -> f64 {
    pyplotrs_color::colorspace::cam16ucs_distance([a.0, a.1, a.2], [b.0, b.1, b.2])
}

/// Simulate `rgb` as seen under a color-vision deficiency (`"protanopia"`,
/// `"deuteranopia"`, or `"tritanopia"`), via the Machado/Oliveira/Fernandes
/// (2009) model.
#[pyfunction]
fn simulate_cvd(rgb: (u8, u8, u8), kind: &str) -> PyResult<(u8, u8, u8)> {
    let [r, g, b] = pyplotrs_color::simulate_cvd([rgb.0, rgb.1, rgb.2], kind)
        .ok_or_else(|| PyValueError::new_err(format!("unknown CVD kind {kind:?}")))?;
    Ok((r, g, b))
}

/// Worst-case distinguishability of a 256-entry colormap table under a CVD
/// kind: `1.0` = unaffected, near `0.0` = some pair of its colors becomes
/// indistinguishable. Takes a table (not a name) so it works for *any*
/// `Colormap`, built-in or custom - `color.py` passes `cmap._table`.
#[pyfunction]
fn cvd_safety_ratio(table: Vec<(u8, u8, u8)>, kind: &str) -> PyResult<f64> {
    let kind = pyplotrs_color::CvdKind::parse(kind)
        .ok_or_else(|| PyValueError::new_err(format!("unknown CVD kind {kind:?}")))?;
    let table: Vec<[u8; 3]> = table.into_iter().map(|(r, g, b)| [r, g, b]).collect();
    Ok(pyplotrs_color::cvd::cvd_safety_ratio(&table, kind))
}

/// Perceptual-uniformity roughness of a 256-entry colormap table: `0.0`
/// means every step along it looks equally large; larger values mean some
/// regions compress more visual change into less data range than others.
#[pyfunction]
fn perceptual_uniformity(table: Vec<(u8, u8, u8)>) -> f64 {
    let table: Vec<[u8; 3]> = table.into_iter().map(|(r, g, b)| [r, g, b]).collect();
    pyplotrs_color::cvd::perceptual_uniformity(&table)
}

/// Symlog parameters (matplotlib defaults: linthresh=1, linscale=1, base=10).
/// `linscale_adj = linscale / (1 - 1/base)`; `log_base = ln(base)`.
const SYMLOG_LINTHRESH: f64 = 1.0;
const SYMLOG_LINSCALE_ADJ: f64 = 1.0 / (1.0 - 1.0 / 10.0);
const LN10: f64 = std::f64::consts::LN_10;

/// Apply an axis scale's non-linear transform to a single data value, **in
/// Rust**, so the polyline/marker fast paths stay off the per-point Python path
/// (see `scales.py`). The result feeds the affine device map; values outside a
/// scale's domain (e.g. x<=0 on a log axis) return `NaN`, which the callers
/// already treat as a gap/skip. Must stay numerically identical to the matching
/// `Scale.transform` in `scales.py`.
#[inline]
fn apply_scale(code: &str, v: f64) -> f64 {
    match code {
        "log" => {
            if v > 0.0 {
                v.log10()
            } else {
                f64::NAN
            }
        }
        "symlog" => {
            let a = v.abs();
            if a <= SYMLOG_LINTHRESH {
                v * SYMLOG_LINSCALE_ADJ
            } else {
                v.signum()
                    * SYMLOG_LINTHRESH
                    * (SYMLOG_LINSCALE_ADJ + (a / SYMLOG_LINTHRESH).ln() / LN10)
            }
        }
        "logit" => {
            if v > 0.0 && v < 1.0 {
                (v / (1.0 - v)).log10()
            } else {
                f64::NAN
            }
        }
        // "linear" and anything unknown: identity.
        _ => v,
    }
}

/// Collapse runs of near-collinear vertices in a device-space polyline
/// (matplotlib's `path.simplify`). Within a run, each point's perpendicular
/// deviation is measured against the run's *initial* direction; the run is cut
/// as soon as the signed spread (max deviation either side of that direction)
/// exceeds `tol` device points, or the path doubles back. Dropped points lie
/// within ~`tol` of the retained polyline, so the stroke is visually identical
/// while the vertex count - and thus PDF/SVG size and draw time - falls sharply
/// on smooth or axis-aligned data. Endpoints are always preserved exactly.
fn simplify_polyline(pts: &[Point], tol: f64) -> Vec<Point> {
    if pts.len() < 3 || tol <= 0.0 {
        return pts.to_vec();
    }
    let tol2 = tol * tol;
    let mut out: Vec<Point> = Vec::with_capacity(pts.len() / 2 + 2);
    out.push(pts[0]);

    let mut anchor = pts[0];
    let mut have_ref = false; // a reference direction has been established
    let (mut rdx, mut rdy, mut rnorm2) = (0.0_f64, 0.0_f64, 0.0_f64);
    let mut dmax = 0.0_f64; // largest +side perpendicular distance^2 seen
    let mut dmin = 0.0_f64; // largest -side perpendicular distance^2 seen
    let mut cand = pts[0]; // last point that still fit the current run

    for &p in &pts[1..] {
        let dx = p.x - anchor.x;
        let dy = p.y - anchor.y;
        if !have_ref {
            let n2 = dx * dx + dy * dy;
            if n2 <= tol2 {
                // Within tol of the anchor: hold as candidate, no direction yet.
                cand = p;
                continue;
            }
            rdx = dx;
            rdy = dy;
            rnorm2 = n2;
            have_ref = true;
            cand = p;
            continue;
        }
        let totdot = rdx * dx + rdy * dy;
        let perp2 = (dx * dx + dy * dy - totdot * totdot / rnorm2).max(0.0);
        if rdx * dy - rdy * dx >= 0.0 {
            dmax = dmax.max(perp2);
        } else {
            dmin = dmin.max(perp2);
        }
        if dmax.sqrt() + dmin.sqrt() > tol || totdot < 0.0 {
            // Run can no longer be one segment: emit it, restart from `cand`.
            out.push(cand);
            anchor = cand;
            dmax = 0.0;
            dmin = 0.0;
            let ndx = p.x - anchor.x;
            let ndy = p.y - anchor.y;
            let n2 = ndx * ndx + ndy * ndy;
            have_ref = n2 > tol2;
            if have_ref {
                rdx = ndx;
                rdy = ndy;
                rnorm2 = n2;
            }
        }
        cand = p;
    }

    let last = pts[pts.len() - 1];
    if *out.last().unwrap() != last {
        out.push(last);
    }
    out
}

/// Append one marker of radius `r` centered at `(cx, cy)` to `path`. Filled
/// shapes are closed subpaths; `+`/`x` are open stroked subpaths.
fn append_marker(path: &mut BezPath, marker: &str, cx: f64, cy: f64, r: f64) {
    match marker {
        "s" => {
            path.move_to((cx - r, cy - r));
            path.line_to((cx + r, cy - r));
            path.line_to((cx + r, cy + r));
            path.line_to((cx - r, cy + r));
            path.close_path();
        }
        "^" => {
            let s = r * 0.95;
            path.move_to((cx, cy - r));
            path.line_to((cx + s, cy + r * 0.8));
            path.line_to((cx - s, cy + r * 0.8));
            path.close_path();
        }
        "v" => {
            let s = r * 0.95;
            path.move_to((cx, cy + r));
            path.line_to((cx - s, cy - r * 0.8));
            path.line_to((cx + s, cy - r * 0.8));
            path.close_path();
        }
        "D" => {
            path.move_to((cx, cy - r));
            path.line_to((cx + r * 0.8, cy));
            path.line_to((cx, cy + r));
            path.line_to((cx - r * 0.8, cy));
            path.close_path();
        }
        "+" => {
            path.move_to((cx - r, cy));
            path.line_to((cx + r, cy));
            path.move_to((cx, cy - r));
            path.line_to((cx, cy + r));
        }
        "x" => {
            path.move_to((cx - r, cy - r));
            path.line_to((cx + r, cy + r));
            path.move_to((cx - r, cy + r));
            path.line_to((cx + r, cy - r));
        }
        _ => {
            // "o" and unknown -> exact Bezier circle.
            path.extend(Circle::new(Point::new(cx, cy), r).path_elements(0.2));
        }
    }
}

/// A scene under construction.
///
/// Drawing calls append to the *current group* if one is open (see
/// [`Scene::begin_group`] / [`Scene::end_group`]), else to the scene root.
#[pyclass]
struct Scene {
    inner: CoreScene,
    /// Stack of groups currently being built (innermost last).
    stack: Vec<Group>,
}

impl Scene {
    /// Append a node to the innermost open group, or the root if none.
    fn push_node(&mut self, node: Node) {
        match self.stack.last_mut() {
            Some(group) => group.children.push(node),
            None => self.inner.push(node),
        }
    }
}

#[pymethods]
impl Scene {
    /// Create a new scene of the given size, in points (1/72 inch).
    #[new]
    fn new(width: f64, height: f64) -> Self {
        Self {
            inner: CoreScene::new(Size::new(width, height)),
            stack: Vec::new(),
        }
    }

    /// Add a (poly)line path. `points` is a list of `(x, y)` tuples in the
    /// current local coordinate space (points, y-down, origin top-left).
    #[pyo3(signature = (
        points,
        stroke_color=None,
        stroke_width=1.0,
        fill_color=None,
        close=false,
        dash=None,
        cap="butt",
        join="round",
        fill_rule="nonzero",
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_path(
        &mut self,
        points: Vec<(f64, f64)>,
        stroke_color: Option<(u8, u8, u8, u8)>,
        stroke_width: f64,
        fill_color: Option<(u8, u8, u8, u8)>,
        close: bool,
        dash: Option<Vec<f32>>,
        cap: &str,
        join: &str,
        fill_rule: &str,
    ) {
        let mut geometry = BezPath::new();
        let mut iter = points.into_iter();
        if let Some((x, y)) = iter.next() {
            geometry.move_to(Point::new(x, y));
            for (x, y) in iter {
                geometry.line_to(Point::new(x, y));
            }
            if close {
                geometry.close_path();
            }
        }

        self.push_node(Node::Path(PathNode {
            geometry,
            fill: fill_color.map(color_from_rgba),
            fill_rule: parse_fill_rule(fill_rule),
            stroke: stroke_color.map(|c| CoreStroke {
                color: color_from_rgba(c),
                width: stroke_width,
                cap: parse_cap(cap),
                join: parse_join(join),
                dash: dash.filter(|d| d.len() >= 2),
            }),
        }));
    }

    /// Fast path: add a polyline straight from raw data arrays, mapping each
    /// point through the linear data->device transform
    /// `(dx, dy) = (ax·x + bx, ay·y + by)` **in Rust**. This avoids building a
    /// Python list of `(x, y)` tuples and doing per-point arithmetic in Python,
    /// which is the bottleneck for large (1e5-1e6 point) line plots.
    #[pyo3(signature = (
        xs, ys, ax, bx, ay, by,
        stroke_color, stroke_width=1.0, dash=None, cap="round", join="round",
        simplify=true, simplify_threshold=0.1, x_scale="linear", y_scale="linear",
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_line_xform(
        &mut self,
        xs: F64Data,
        ys: F64Data,
        ax: f64,
        bx: f64,
        ay: f64,
        by: f64,
        stroke_color: (u8, u8, u8, u8),
        stroke_width: f64,
        dash: Option<Vec<f32>>,
        cap: &str,
        join: &str,
        simplify: bool,
        simplify_threshold: f64,
        x_scale: &str,
        y_scale: &str,
    ) {
        let n = xs.len().min(ys.len());
        // Split into maximal runs of finite points: a non-finite (NaN/inf) point
        // breaks the polyline into separate subpaths. This matches matplotlib's
        // treatment of missing data as a gap, and keeps non-finite coordinates -
        // which are undefined for the rasterizer - out of the path entirely.
        let mut geometry = BezPath::new();
        let mut run: Vec<Point> = Vec::new();
        let flush = |run: &mut Vec<Point>, geometry: &mut BezPath| {
            if run.is_empty() {
                return;
            }
            let seg = if simplify && run.len() >= 3 {
                let s = simplify_polyline(run, simplify_threshold);
                run.clear();
                s
            } else {
                std::mem::take(run)
            };
            if let Some((first, rest)) = seg.split_first() {
                geometry.move_to(*first);
                for p in rest {
                    geometry.line_to(*p);
                }
            }
        };
        for i in 0..n {
            // Scale transform (identity for linear) then affine device map, both
            // in Rust; a non-finite result (e.g. x<=0 on a log axis) cuts the run.
            let dx = ax * apply_scale(x_scale, xs[i]) + bx;
            let dy = ay * apply_scale(y_scale, ys[i]) + by;
            if dx.is_finite() && dy.is_finite() {
                run.push(Point::new(dx, dy));
            } else {
                flush(&mut run, &mut geometry);
            }
        }
        flush(&mut run, &mut geometry);
        self.push_node(Node::Path(PathNode {
            geometry,
            fill: None,
            fill_rule: FillRule::NonZero,
            stroke: Some(CoreStroke {
                color: color_from_rgba(stroke_color),
                width: stroke_width,
                cap: parse_cap(cap),
                join: parse_join(join),
                dash: dash.filter(|d| d.len() >= 2),
            }),
        }));
    }

    /// Fast path: add many identical markers from raw data arrays, mapped
    /// through the linear data->device transform in Rust and emitted as one
    /// `PathNode` (a single fill, or a single stroke for `+`/`x`).
    #[pyo3(signature = (
        xs, ys, ax, bx, ay, by,
        marker, diameter, fill_color, edge_color=None, edge_width=1.0,
        x_scale="linear", y_scale="linear",
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_markers_xform(
        &mut self,
        xs: F64Data,
        ys: F64Data,
        ax: f64,
        bx: f64,
        ay: f64,
        by: f64,
        marker: &str,
        diameter: f64,
        fill_color: (u8, u8, u8, u8),
        edge_color: Option<(u8, u8, u8, u8)>,
        edge_width: f64,
        x_scale: &str,
        y_scale: &str,
    ) {
        let n = xs.len().min(ys.len());
        let r = diameter / 2.0;

        // Describe the marker outline *once*, centered at the origin; the
        // backends stamp it at each position (PDF XObject / SVG <use> / raster
        // path reuse) instead of duplicating the geometry per point.
        let mut marker_path = BezPath::new();
        append_marker(&mut marker_path, marker, 0.0, 0.0, r);

        // Skip non-finite positions (matplotlib draws no marker at NaN/inf);
        // the scale transform (identity for linear) runs in Rust before the
        // affine, so out-of-domain points (x<=0 on log) drop out here.
        let positions: Vec<Point> = (0..n)
            .map(|i| {
                Point::new(
                    ax * apply_scale(x_scale, xs[i]) + bx,
                    ay * apply_scale(y_scale, ys[i]) + by,
                )
            })
            .filter(|p| p.x.is_finite() && p.y.is_finite())
            .collect();

        let stroke_only = marker == "+" || marker == "x";
        let node = if stroke_only {
            MarkerNode {
                marker: marker_path,
                fill: None,
                fill_rule: FillRule::NonZero,
                stroke: Some(CoreStroke {
                    color: color_from_rgba(edge_color.unwrap_or(fill_color)),
                    width: edge_width.max(1.0),
                    cap: LineCap::Round,
                    join: LineJoin::Round,
                    dash: None,
                }),
                positions,
                colors: None,
            }
        } else {
            MarkerNode {
                marker: marker_path,
                fill: Some(color_from_rgba(fill_color)),
                fill_rule: FillRule::NonZero,
                stroke: edge_color.map(|c| CoreStroke {
                    color: color_from_rgba(c),
                    width: edge_width,
                    cap: LineCap::Round,
                    join: LineJoin::Round,
                    dash: None,
                }),
                positions,
                colors: None,
            }
        };
        self.push_node(Node::Markers(node));
    }

    /// Fast path for a **colormapped** scatter: like `add_markers_xform` but with
    /// one fill color per point (`colors`, parallel to `xs`/`ys`). The scale
    /// transform runs in Rust; non-finite positions are dropped along with their
    /// color. A single uniform edge (`edge_color`/`edge_width`) applies to all.
    #[pyo3(signature = (
        xs, ys, ax, bx, ay, by,
        marker, diameter, colors, edge_color=None, edge_width=1.0,
        x_scale="linear", y_scale="linear",
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_markers_xform_colored(
        &mut self,
        xs: F64Data,
        ys: F64Data,
        ax: f64,
        bx: f64,
        ay: f64,
        by: f64,
        marker: &str,
        diameter: f64,
        colors: Vec<(u8, u8, u8, u8)>,
        edge_color: Option<(u8, u8, u8, u8)>,
        edge_width: f64,
        x_scale: &str,
        y_scale: &str,
    ) {
        let n = xs.len().min(ys.len()).min(colors.len());
        let r = diameter / 2.0;
        let mut marker_path = BezPath::new();
        append_marker(&mut marker_path, marker, 0.0, 0.0, r);

        // Keep positions and their colors aligned while dropping non-finite points.
        let mut positions: Vec<Point> = Vec::with_capacity(n);
        let mut pt_colors: Vec<Color> = Vec::with_capacity(n);
        for i in 0..n {
            let p = Point::new(
                ax * apply_scale(x_scale, xs[i]) + bx,
                ay * apply_scale(y_scale, ys[i]) + by,
            );
            if p.x.is_finite() && p.y.is_finite() {
                positions.push(p);
                pt_colors.push(color_from_rgba(colors[i]));
            }
        }
        self.push_node(Node::Markers(MarkerNode {
            marker: marker_path,
            fill: pt_colors.first().copied(),
            fill_rule: FillRule::NonZero,
            stroke: edge_color.map(|c| CoreStroke {
                color: color_from_rgba(c),
                width: edge_width,
                cap: LineCap::Round,
                join: LineJoin::Round,
                dash: None,
            }),
            positions,
            colors: Some(pt_colors),
        }));
    }

    /// Fast path: colormap a 2D field and add it as an image, doing the
    /// per-pixel value->color lookup **in Rust**. `values` is the field in
    /// row-major data order (length `width*height`); `lut` is a 256-entry RGBA
    /// table (1024 bytes). Non-finite values become transparent. `origin_upper`
    /// places data row 0 at the top of the destination rect `(x, y, w, h)`.
    #[pyo3(signature = (
        values, width, height, vmin, vmax, lut, origin_upper, x, y, w, h,
        norm="linear",
    ))]
    #[allow(clippy::too_many_arguments)]
    fn add_colormapped_image(
        &mut self,
        values: F64Data,
        width: u32,
        height: u32,
        vmin: f64,
        vmax: f64,
        lut: Vec<u8>,
        origin_upper: bool,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
        norm: &str,
    ) {
        let wi = width as usize;
        let hi = height as usize;
        let mapper = ColorMapper::new(&lut, norm, vmin, vmax);
        let mut buf = vec![0u8; wi * hi * 4];
        for row in 0..hi {
            let drow = if origin_upper { row } else { hi - 1 - row };
            let src = drow * wi;
            let dst = row * wi * 4;
            for col in 0..wi {
                // Out-of-domain samples keep RGBA = 0, i.e. transparent.
                if let Some((r, g, b, a)) = mapper.lookup(values[src + col]) {
                    let o = dst + col * 4;
                    buf[o] = r;
                    buf[o + 1] = g;
                    buf[o + 2] = b;
                    buf[o + 3] = a;
                }
            }
        }
        self.push_node(Node::Image(ImageNode {
            data: ImageData::from_rgba8(buf, width, height),
            rect: KRect::new(x, y, x + w, y + h),
        }));
    }

    /// Add a run of text with its baseline origin at `(x, y)`. `font` selects
    /// the face: `"body"` (the resolved sans-serif - Arial/Helvetica if present
    /// on the host, else bundled Liberation Sans) or `"math"` (STIX Two Math).
    #[pyo3(signature = (x, y, text, size, color=(0, 0, 0, 255), font="body"))]
    fn add_text(
        &mut self,
        x: f64,
        y: f64,
        text: &str,
        size: f64,
        color: (u8, u8, u8, u8),
        font: &str,
    ) {
        let run = pyplotrs_text::shape_text(&font_for_kind(font), text, size as f32);
        self.push_node(Node::Text(TextNode {
            origin: Point::new(x, y),
            runs: vec![run],
            color: color_from_rgba(color),
        }));
    }

    /// Lay out and add a (LaTeX) math/text string with its left edge at `x`
    /// and baseline at `y`. Plain strings (no `$`) are shaped as a single
    /// body-font run; `$...$` spans are typeset by `pyplotrs-math` using the
    /// math font's OpenType MATH table (real editable glyphs + vector rules),
    /// then appended to the current group/scene.
    #[pyo3(signature = (x, y, text, size, color=(0, 0, 0, 255), font="body"))]
    fn add_math(
        &mut self,
        x: f64,
        y: f64,
        text: &str,
        size: f64,
        color: (u8, u8, u8, u8),
        font: &str,
    ) {
        // `font` selects the *upright body* face used for non-math runs and for
        // \text{...} spans. Math italics come from the math font's alphanumeric
        // blocks and are unaffected by it.
        let body = font_for_kind(font);
        let (nodes, _m) = pyplotrs_math::render(
            math_font(),
            &body,
            text,
            size as f32,
            x as f32,
            y as f32,
            color_from_rgba(color),
        );
        for node in nodes {
            self.push_node(node);
        }
    }

    /// Measure a math/text string: `(width, ascent, depth)` in points.
    #[pyo3(signature = (text, size, font="body"))]
    fn measure_math(&self, text: &str, size: f64, font: &str) -> (f64, f64, f64) {
        // Must use the same face `add_math` will draw with, or the layout
        // solver reserves the wrong band and bold labels clip or float.
        let body = font_for_kind(font);
        let (w, a, d) = pyplotrs_math::measure(math_font(), &body, text, size as f32);
        (w as f64, a as f64, d as f64)
    }

    /// Add an RGBA8 image filling the destination rect `(x, y, w, h)`.
    #[pyo3(signature = (rgba, width, height, x, y, w, h))]
    #[allow(clippy::too_many_arguments)]
    fn add_image(
        &mut self,
        rgba: Vec<u8>,
        width: u32,
        height: u32,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
    ) {
        self.push_node(Node::Image(ImageNode {
            data: ImageData::from_rgba8(rgba, width, height),
            rect: KRect::new(x, y, x + w, y + h),
        }));
    }

    /// Open a group applying the affine matrix `[a b c d e f]` (mapping
    /// `(x, y) -> (a·x + c·y + e, b·x + d·y + f)`), an optional rectangular
    /// clip `(x, y, w, h)` in the group's local space, and `opacity`.
    /// Subsequent draw calls go into this group until [`Scene::end_group`].
    #[pyo3(signature = (a, b, c, d, e, f, clip=None, opacity=1.0))]
    #[allow(clippy::too_many_arguments)]
    fn begin_group(
        &mut self,
        a: f64,
        b: f64,
        c: f64,
        d: f64,
        e: f64,
        f: f64,
        clip: Option<(f64, f64, f64, f64)>,
        opacity: f32,
    ) {
        self.stack.push(Group {
            transform: Affine::new([a, b, c, d, e, f]),
            clip: clip.map(|(x, y, w, h)| ClipPath::rect(KRect::new(x, y, x + w, y + h))),
            opacity,
            children: Vec::new(),
        });
    }

    /// Close the most recently opened group, appending it to its parent.
    fn end_group(&mut self) {
        if let Some(group) = self.stack.pop() {
            self.push_node(Node::Group(group));
        }
    }

    /// Total horizontal advance of `text` at `size` (points) - for layout.
    /// `font` selects the bundled face (`"body"` / `"math"`).
    #[pyo3(signature = (text, size, font="body"))]
    fn measure_text(&self, text: &str, size: f64, font: &str) -> f64 {
        let run = pyplotrs_text::shape_text(&font_for_kind(font), text, size as f32);
        pyplotrs_text::run_width(&run) as f64
    }

    /// Vertical font metrics `(ascent, descent, line_gap)` at `size` (points).
    /// `font` selects the bundled face (`"body"` / `"math"`).
    #[pyo3(signature = (size, font="body"))]
    fn font_vmetrics(&self, size: f64, font: &str) -> (f64, f64, f64) {
        let m = pyplotrs_text::font_vmetrics(&font_for_kind(font), size as f32);
        (m.ascent as f64, m.descent as f64, m.line_gap as f64)
    }

    /// Render to PDF bytes (real, embedded/subsetted, editable text). When
    /// `tagged` is set, emit a tagged/accessible PDF whose content is one
    /// `Figure` structure element carrying `alt` text, plus document metadata.
    #[pyo3(signature = (tagged=false, title=None, alt=None))]
    fn to_pdf<'py>(
        &self,
        py: Python<'py>,
        tagged: bool,
        title: Option<&str>,
        alt: Option<&str>,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let bytes = if tagged {
            pyplotrs_render_pdf::render_pdf_tagged(&self.inner, title, alt.unwrap_or("figure"))
        } else {
            pyplotrs_render_pdf::render_pdf(&self.inner)
        }
        .map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, &bytes))
    }

    /// Render to an SVG document string (real `<text>` elements).
    fn to_svg(&self) -> String {
        pyplotrs_render_svg::render_svg(&self.inner)
    }

    /// Render to PNG bytes at `dpi` dots per inch (the PNG carries a `pHYs`
    /// chunk recording its physical size). PDF/SVG are resolution-independent
    /// and ignore dpi.
    #[pyo3(signature = (dpi=200.0))]
    fn to_png<'py>(&self, py: Python<'py>, dpi: f64) -> PyResult<Bound<'py, PyBytes>> {
        let bytes =
            pyplotrs_render_raster::render_png(&self.inner, dpi).map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, &bytes))
    }
}

/// An axis-aligned rectangle `(x, y, w, h)` returned by [`solve_layout`].
#[pyclass(skip_from_py_object)]
#[derive(Clone, Copy)]
struct Rect {
    #[pyo3(get)]
    x: f64,
    #[pyo3(get)]
    y: f64,
    #[pyo3(get)]
    w: f64,
    #[pyo3(get)]
    h: f64,
}

impl From<pyplotrs_layout::solve::Rect> for Rect {
    fn from(r: pyplotrs_layout::solve::Rect) -> Self {
        Self {
            x: r.x,
            y: r.y,
            w: r.w,
            h: r.h,
        }
    }
}

#[pymethods]
impl Rect {
    #[getter]
    fn x1(&self) -> f64 {
        self.x + self.w
    }
    #[getter]
    fn y1(&self) -> f64 {
        self.y + self.h
    }
    fn __repr__(&self) -> String {
        format!(
            "Rect(x={:.2}, y={:.2}, w={:.2}, h={:.2})",
            self.x, self.y, self.w, self.h
        )
    }
}

/// Computed rectangles for one axes.
#[pyclass(skip_from_py_object)]
#[derive(Clone, Copy)]
struct AxesLayout {
    #[pyo3(get)]
    cell: Rect,
    #[pyo3(get)]
    plot: Rect,
    #[pyo3(get)]
    title: Rect,
    #[pyo3(get)]
    xlabel: Rect,
    #[pyo3(get)]
    ylabel: Rect,
    #[pyo3(get)]
    x_tick: Rect,
    #[pyo3(get)]
    y_tick: Rect,
    #[pyo3(get)]
    cbar: Rect,
}

/// The full solved figure layout.
#[pyclass]
struct Layout {
    #[pyo3(get)]
    axes: Vec<AxesLayout>,
    #[pyo3(get)]
    suptitle: Rect,
    #[pyo3(get)]
    legend: Rect,
}

/// Locate "nice" axis ticks for `[vmin, vmax]`, returning `(value, label)`
/// pairs. Backed by `pyplotrs_layout::ticks`.
#[pyfunction]
#[pyo3(signature = (vmin, vmax, max_ticks=7))]
fn nice_ticks(vmin: f64, vmax: f64, max_ticks: usize) -> Vec<(f64, String)> {
    pyplotrs_layout::ticks::ticks(vmin, vmax, max_ticks)
        .into_iter()
        .map(|t| (t.value, t.label))
        .collect()
}

/// Solve a figure layout in one pass. `cells` is a row-major list of
/// `(title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w)` band sizes
/// (points). Returns a [`Layout`] with every reserved rectangle.
#[pyfunction]
#[pyo3(signature = (
    width, height, nrows, ncols,
    cells,
    outer_margin=5.0, hspace=0.0, wspace=0.0, suptitle_h=0.0, legend_w=0.0,
    spans=None, width_ratios=None, height_ratios=None,
))]
#[allow(clippy::too_many_arguments)]
fn solve_layout(
    width: f64,
    height: f64,
    nrows: usize,
    ncols: usize,
    cells: Vec<(f64, f64, f64, f64, f64, f64)>,
    outer_margin: f64,
    hspace: f64,
    wspace: f64,
    suptitle_h: f64,
    legend_w: f64,
    spans: Option<Vec<(usize, usize, usize, usize)>>,
    width_ratios: Option<Vec<f64>>,
    height_ratios: Option<Vec<f64>>,
) -> Layout {
    let spec = FigureSpec {
        width,
        height,
        nrows,
        ncols,
        outer_margin,
        hspace,
        wspace,
        suptitle_h,
        legend_w,
        spans,
        width_ratios,
        height_ratios,
        cells: cells
            .into_iter()
            .map(
                |(title_h, xlabel_h, ylabel_w, x_tick_h, y_tick_w, cbar_w)| AxesBands {
                    title_h,
                    xlabel_h,
                    ylabel_w,
                    x_tick_h,
                    y_tick_w,
                    cbar_w,
                },
            )
            .collect(),
    };
    let result = pyplotrs_layout::solve::solve(&spec);
    Layout {
        axes: result
            .axes
            .into_iter()
            .map(|a| AxesLayout {
                cell: a.cell.into(),
                plot: a.plot.into(),
                title: a.title.into(),
                xlabel: a.xlabel.into(),
                ylabel: a.ylabel.into(),
                x_tick: a.x_tick.into(),
                y_tick: a.y_tick.into(),
                cbar: a.cbar.into(),
            })
            .collect(),
        suptitle: result.suptitle.into(),
        legend: result.legend.into(),
    }
}

/// Encode a sequence of equally-sized [`Scene`]s as an animated GIF. `scale` =
/// dpi/72 (device pixels per point); `delay_cs` = per-frame delay in
/// centiseconds; `infinite` loops forever vs. plays once.
#[pyfunction]
#[pyo3(signature = (scenes, scale, delay_cs, infinite=true))]
fn scenes_to_gif<'py>(
    py: Python<'py>,
    scenes: Vec<Py<Scene>>,
    scale: f64,
    delay_cs: u16,
    infinite: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    if scenes.is_empty() {
        return Err(PyValueError::new_err("animation needs at least one frame"));
    }
    // `guards` keeps each Scene borrowed; `refs` borrows from `guards`; both
    // outlive the render call, so no copying or unsafe is needed.
    let guards: Vec<PyRef<Scene>> = scenes.iter().map(|s| s.borrow(py)).collect();
    let refs: Vec<&CoreScene> = guards.iter().map(|g| &g.inner).collect();
    let bytes = pyplotrs_render_raster::render_gif(&refs, scale, delay_cs, infinite)
        .map_err(PyValueError::new_err)?;
    Ok(PyBytes::new(py, &bytes))
}

/// Encode a sequence of equally-sized [`Scene`]s as an animated PNG (full
/// colour, no palette quantization). `delay_num`/`delay_den` give the per-frame
/// delay in seconds; `infinite` loops forever vs. plays once.
#[pyfunction]
#[pyo3(signature = (scenes, dpi, delay_num, delay_den, infinite=true))]
fn scenes_to_apng<'py>(
    py: Python<'py>,
    scenes: Vec<Py<Scene>>,
    dpi: f64,
    delay_num: u16,
    delay_den: u16,
    infinite: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    if scenes.is_empty() {
        return Err(PyValueError::new_err("animation needs at least one frame"));
    }
    let guards: Vec<PyRef<Scene>> = scenes.iter().map(|s| s.borrow(py)).collect();
    let refs: Vec<&CoreScene> = guards.iter().map(|g| &g.inner).collect();
    let bytes = pyplotrs_render_raster::render_apng(&refs, dpi, delay_num, delay_den, infinite)
        .map_err(PyValueError::new_err)?;
    Ok(PyBytes::new(py, &bytes))
}

/// Set the ordered list of preferred sans-serif family names used for body
/// text (matplotlib's `rcParams["font.sans-serif"]`). Each name is tried in
/// order against the host's installed fonts; the first that exists wins, and
/// the bundled Liberation Sans is the guaranteed final fallback. Passing an
/// empty list restores the default (`Arial`, `Helvetica`, `Liberation Sans`).
#[pyfunction]
fn set_sans_serif(families: Vec<String>) {
    *SANS_SERIF.lock().unwrap() = if families.is_empty() {
        None
    } else {
        Some(families)
    };
    *BODY_CACHE.lock().unwrap() = None;
}

/// The currently configured preferred sans-serif families, in order. When
/// unset, reports the default (`Arial`, `Helvetica`, `Liberation Sans`).
#[pyfunction]
fn get_sans_serif() -> Vec<String> {
    SANS_SERIF
        .lock()
        .unwrap()
        .clone()
        .unwrap_or_else(default_sans_serif)
}

/// The family name of the font the body selector actually resolves to right
/// now (e.g. `"Arial"` if installed, else `"Liberation Sans"`). Useful for
/// confirming which physical font a figure was rendered with.
#[pyfunction]
fn resolved_font_name() -> String {
    resolve_body(FaceStyle::default()).family
}

/// What each of the four body faces resolves to on this host, as
/// `[(selector, family_name), ...]` for `body`, `body-bold`, `body-italic`,
/// `body-bolditalic`.
///
/// Font matching is approximate: a family with no italic face resolves to its
/// regular one, so asking for italic can quietly give you upright text. This
/// makes that visible - if two selectors report the same family, the host has no
/// distinct face for one of them.
#[pyfunction]
fn resolved_font_variants() -> Vec<(String, String)> {
    [
        ("body", FaceStyle::default()),
        (
            "body-bold",
            FaceStyle {
                bold: true,
                italic: false,
            },
        ),
        (
            "body-italic",
            FaceStyle {
                bold: false,
                italic: true,
            },
        ),
        (
            "body-bolditalic",
            FaceStyle {
                bold: true,
                italic: true,
            },
        ),
    ]
    .into_iter()
    .map(|(name, face)| (name.to_string(), resolve_body(face).postscript))
    .collect()
}

/// The raw bytes of the currently resolved body font. Lets the HTML backends
/// embed the *same* font they were laid out with as a webfont, so interactive
/// (canvas-drawn) text views identically across machines.
#[pyfunction]
fn body_font_bytes(py: Python<'_>) -> Bound<'_, PyBytes> {
    PyBytes::new(py, &resolve_body(FaceStyle::default()).data.data)
}

// ---------------------------------------------------------------------------
// Numeric kernels for statistical / field plot types (Phase E). These are pure
// number-crunchers kept in Rust so the hot per-cell / per-sample loops never run
// in Python: contouring, 2D histograms, KDE, and hex binning.
// ---------------------------------------------------------------------------

/// Linear interpolation of the crossing position where `va..vb` equals `level`.
#[inline]
fn _iso_t(va: f64, vb: f64, level: f64) -> f64 {
    let d = vb - va;
    if d == 0.0 {
        0.5
    } else {
        (level - va) / d
    }
}

/// Marching-squares contour lines. `values` is a row-major `w*h` grid (index =
/// `row*w + col`). Returns `(level_idx, x0, y0, x1, y1)` line segments in
/// fractional grid coordinates (`x` = column in `0..w-1`, `y` = row in `0..h-1`);
/// the caller maps those to data space against its coordinate vectors.
#[pyfunction]
fn contour_lines(
    values: F64Data,
    w: usize,
    h: usize,
    levels: F64Data,
) -> Vec<(u32, f64, f64, f64, f64)> {
    let mut out = Vec::new();
    if w < 2 || h < 2 {
        return out;
    }
    for (li, &level) in levels.iter().enumerate() {
        let li = li as u32;
        for r in 0..h - 1 {
            for c in 0..w - 1 {
                let a = values[r * w + c]; // A: (c,   r)
                let b = values[r * w + c + 1]; // B: (c+1, r)
                let cc = values[(r + 1) * w + c + 1]; // C: (c+1, r+1)
                let d = values[(r + 1) * w + c]; // D: (c,   r+1)
                if !(a.is_finite() && b.is_finite() && cc.is_finite() && d.is_finite()) {
                    continue;
                }
                let (fc, fr) = (c as f64, r as f64);
                // Edge crossing points (top AB, right BC, bottom CD, left DA).
                let p_ab = (fc + _iso_t(a, b, level), fr);
                let p_bc = (fc + 1.0, fr + _iso_t(b, cc, level));
                let p_cd = (fc + _iso_t(d, cc, level), fr + 1.0);
                let p_da = (fc, fr + _iso_t(a, d, level));
                let case = ((a >= level) as u8) << 3
                    | ((b >= level) as u8) << 2
                    | ((cc >= level) as u8) << 1
                    | (d >= level) as u8;
                let center = (a + b + cc + d) * 0.25;
                let mut seg = |p: (f64, f64), q: (f64, f64)| {
                    out.push((li, p.0, p.1, q.0, q.1));
                };
                match case {
                    1 | 14 => seg(p_cd, p_da),
                    2 | 13 => seg(p_bc, p_cd),
                    3 | 12 => seg(p_bc, p_da),
                    4 | 11 => seg(p_ab, p_bc),
                    6 | 9 => seg(p_ab, p_cd),
                    7 | 8 => seg(p_ab, p_da),
                    5 => {
                        // b,d inside; a,cc outside (saddle).
                        if center >= level {
                            seg(p_da, p_ab);
                            seg(p_bc, p_cd);
                        } else {
                            seg(p_ab, p_bc);
                            seg(p_cd, p_da);
                        }
                    }
                    10 => {
                        // a,cc inside; b,d outside (saddle).
                        if center >= level {
                            seg(p_ab, p_bc);
                            seg(p_cd, p_da);
                        } else {
                            seg(p_da, p_ab);
                            seg(p_bc, p_cd);
                        }
                    }
                    _ => {}
                }
            }
        }
    }
    out
}

/// Filled contour bands as an RGBA image. The field is bilinearly upsampled by
/// `upsample` and each pixel colored by the band its value falls in (`edges` has
/// `nbands+1` monotone entries; `band_lut` is `nbands*4` RGBA bytes). Values
/// outside `edges[0]..edges[last]` (and non-finite) are transparent. Returns
/// `(rgba, out_w, out_h)` with buffer row 0 = grid row `h-1` (largest data y at
/// the top), matching `add_image`'s top-down placement.
#[pyfunction]
fn contourf_image(
    values: F64Data,
    w: usize,
    h: usize,
    edges: F64Data,
    band_lut: Vec<u8>,
    upsample: usize,
) -> (Vec<u8>, usize, usize) {
    let up = upsample.max(1);
    if w < 2 || h < 2 || edges.len() < 2 {
        return (Vec::new(), 0, 0);
    }
    let ow = (w - 1) * up + 1;
    let oh = (h - 1) * up + 1;
    let nbands = edges.len() - 1;
    let mut buf = vec![0u8; ow * oh * 4];
    for oy in 0..oh {
        // Flip so buffer row 0 corresponds to the largest-y grid row (h-1).
        let gy = (oh - 1 - oy) as f64 / up as f64;
        let r0 = gy.floor() as usize;
        let r1 = (r0 + 1).min(h - 1);
        let fy = gy - r0 as f64;
        for ox in 0..ow {
            let gx = ox as f64 / up as f64;
            let c0 = gx.floor() as usize;
            let c1 = (c0 + 1).min(w - 1);
            let fx = gx - c0 as f64;
            let v00 = values[r0 * w + c0];
            let v10 = values[r0 * w + c1];
            let v01 = values[r1 * w + c0];
            let v11 = values[r1 * w + c1];
            if !(v00.is_finite() && v10.is_finite() && v01.is_finite() && v11.is_finite()) {
                continue;
            }
            let top = v00 + (v10 - v00) * fx;
            let bot = v01 + (v11 - v01) * fx;
            let val = top + (bot - top) * fy;
            if val < edges[0] || val > edges[nbands] {
                continue;
            }
            // Band index: largest b with edges[b] <= val.
            let mut band = 0;
            while band + 1 < nbands && val >= edges[band + 1] {
                band += 1;
            }
            let li = band * 4;
            let o = (oy * ow + ox) * 4;
            buf[o] = band_lut[li];
            buf[o + 1] = band_lut[li + 1];
            buf[o + 2] = band_lut[li + 2];
            buf[o + 3] = band_lut[li + 3];
        }
    }
    (buf, ow, oh)
}

/// 2D histogram: count `(xs, ys)` into `ny * nx` equal bins over
/// `[xlo,xhi] x [ylo,yhi]`. Returns row-major counts (`iy*nx + ix`), `iy=0` the
/// lowest-y row. Points outside the range are dropped.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn hist2d(
    xs: F64Data,
    ys: F64Data,
    nx: usize,
    ny: usize,
    xlo: f64,
    xhi: f64,
    ylo: f64,
    yhi: f64,
) -> Vec<f64> {
    let mut counts = vec![0.0f64; nx * ny];
    let xspan = if xhi > xlo { xhi - xlo } else { 1.0 };
    let yspan = if yhi > ylo { yhi - ylo } else { 1.0 };
    for (&x, &y) in xs.iter().zip(ys.iter()) {
        if !(x.is_finite() && y.is_finite()) || x < xlo || x > xhi || y < ylo || y > yhi {
            continue;
        }
        let mut ix = ((x - xlo) / xspan * nx as f64) as usize;
        let mut iy = ((y - ylo) / yspan * ny as f64) as usize;
        if ix >= nx {
            ix = nx - 1;
        }
        if iy >= ny {
            iy = ny - 1;
        }
        counts[iy * nx + ix] += 1.0;
    }
    counts
}

/// Evaluate a 1D Gaussian kernel density estimate of `samples` at each point of
/// `grid`. `bandwidth <= 0` selects Scott's rule (`n^(-1/5) * std`). Used by
/// `violinplot`.
#[pyfunction]
fn gaussian_kde(samples: Vec<f64>, grid: Vec<f64>, bandwidth: f64) -> Vec<f64> {
    let n = samples.len();
    if n == 0 {
        return vec![0.0; grid.len()];
    }
    let mean = samples.iter().sum::<f64>() / n as f64;
    let var = samples.iter().map(|s| (s - mean).powi(2)).sum::<f64>() / n as f64;
    let std = var.sqrt();
    let bw = if bandwidth > 0.0 {
        bandwidth
    } else {
        let b = (n as f64).powf(-0.2) * std;
        if b > 0.0 {
            b
        } else {
            1.0
        }
    };
    let norm = 1.0 / (n as f64 * bw * (2.0 * std::f64::consts::PI).sqrt());
    grid.iter()
        .map(|&g| {
            let s: f64 = samples
                .iter()
                .map(|&x| {
                    let z = (g - x) / bw;
                    (-0.5 * z * z).exp()
                })
                .sum();
            s * norm
        })
        .collect()
}

/// Hexagonal binning (matplotlib's two-offset-grid algorithm). Returns occupied
/// hexagons as `(center_x, center_y, count)` in data coordinates. `gridsize` is
/// the number of hexagons across x; the y count is derived for regular hexagons.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn hexbin(
    xs: F64Data,
    ys: F64Data,
    gridsize: usize,
    xlo: f64,
    xhi: f64,
    ylo: f64,
    yhi: f64,
) -> Vec<(f64, f64, f64)> {
    let nx = gridsize.max(1);
    let ny = ((nx as f64 / 3.0_f64.sqrt()).round() as usize).max(1);
    let sx = if xhi > xlo {
        (xhi - xlo) / nx as f64
    } else {
        1.0
    };
    let sy = if yhi > ylo {
        (yhi - ylo) / ny as f64
    } else {
        1.0
    };
    // Two interleaved grids: full (n1) and half-offset (n2).
    let mut n1 = std::collections::HashMap::<(i64, i64), f64>::new();
    let mut n2 = std::collections::HashMap::<(i64, i64), f64>::new();
    for (&px, &py) in xs.iter().zip(ys.iter()) {
        if !(px.is_finite() && py.is_finite()) {
            continue;
        }
        let x = (px - xlo) / sx;
        let y = (py - ylo) / sy;
        let ix1 = x.round();
        let iy1 = y.round();
        let ix2 = x.floor();
        let iy2 = y.floor();
        let d1 = (x - ix1).powi(2) + 3.0 * (y - iy1).powi(2);
        let d2 = (x - ix2 - 0.5).powi(2) + 3.0 * (y - iy2 - 0.5).powi(2);
        if d1 <= d2 {
            *n1.entry((ix1 as i64, iy1 as i64)).or_insert(0.0) += 1.0;
        } else {
            *n2.entry((ix2 as i64, iy2 as i64)).or_insert(0.0) += 1.0;
        }
    }
    let mut out = Vec::new();
    for ((ix, iy), c) in n1 {
        out.push((xlo + ix as f64 * sx, ylo + iy as f64 * sy, c));
    }
    for ((ix, iy), c) in n2 {
        out.push((
            xlo + (ix as f64 + 0.5) * sx,
            ylo + (iy as f64 + 0.5) * sy,
            c,
        ));
    }
    out
}

#[pymodule]
fn _pyplotrs_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Scene>()?;
    m.add_class::<Rect>()?;
    m.add_class::<AxesLayout>()?;
    m.add_class::<Layout>()?;
    m.add_function(wrap_pyfunction!(nice_ticks, m)?)?;
    m.add_function(wrap_pyfunction!(solve_layout, m)?)?;
    m.add_function(wrap_pyfunction!(data_range, m)?)?;
    m.add_function(wrap_pyfunction!(positive_range, m)?)?;
    m.add_function(wrap_pyfunction!(offset_range, m)?)?;
    m.add_function(wrap_pyfunction!(histogram, m)?)?;
    m.add_function(wrap_pyfunction!(map_colors, m)?)?;
    m.add_function(wrap_pyfunction!(scenes_to_gif, m)?)?;
    m.add_function(wrap_pyfunction!(scenes_to_apng, m)?)?;
    m.add_function(wrap_pyfunction!(set_sans_serif, m)?)?;
    m.add_function(wrap_pyfunction!(get_sans_serif, m)?)?;
    m.add_function(wrap_pyfunction!(resolved_font_name, m)?)?;
    m.add_function(wrap_pyfunction!(resolved_font_variants, m)?)?;
    m.add_function(wrap_pyfunction!(body_font_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(contour_lines, m)?)?;
    m.add_function(wrap_pyfunction!(contourf_image, m)?)?;
    m.add_function(wrap_pyfunction!(hist2d, m)?)?;
    m.add_function(wrap_pyfunction!(gaussian_kde, m)?)?;
    m.add_function(wrap_pyfunction!(hexbin, m)?)?;
    m.add_function(wrap_pyfunction!(colormap_table, m)?)?;
    m.add_function(wrap_pyfunction!(colormap_table_from_stops, m)?)?;
    m.add_function(wrap_pyfunction!(categorical_palette, m)?)?;
    m.add_function(wrap_pyfunction!(list_colormaps, m)?)?;
    m.add_function(wrap_pyfunction!(list_palettes, m)?)?;
    m.add_function(wrap_pyfunction!(colormap_rgba_lut, m)?)?;
    m.add_function(wrap_pyfunction!(srgb_to_oklab, m)?)?;
    m.add_function(wrap_pyfunction!(oklab_to_srgb, m)?)?;
    m.add_function(wrap_pyfunction!(srgb_to_oklch, m)?)?;
    m.add_function(wrap_pyfunction!(oklch_to_srgb, m)?)?;
    m.add_function(wrap_pyfunction!(srgb_to_lab, m)?)?;
    m.add_function(wrap_pyfunction!(lab_to_srgb, m)?)?;
    m.add_function(wrap_pyfunction!(srgb_to_xyz, m)?)?;
    m.add_function(wrap_pyfunction!(xyz_to_srgb, m)?)?;
    m.add_function(wrap_pyfunction!(srgb_to_linear, m)?)?;
    m.add_function(wrap_pyfunction!(linear_to_srgb, m)?)?;
    m.add_function(wrap_pyfunction!(srgb_to_cam16ucs, m)?)?;
    m.add_function(wrap_pyfunction!(cam16ucs_to_srgb, m)?)?;
    m.add_function(wrap_pyfunction!(cam16ucs_distance, m)?)?;
    m.add_function(wrap_pyfunction!(simulate_cvd, m)?)?;
    m.add_function(wrap_pyfunction!(cvd_safety_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(perceptual_uniformity, m)?)?;
    Ok(())
}
