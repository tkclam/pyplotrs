//! The scene: a backend-agnostic tree of paths, shaped text runs, images and
//! transform/clip groups. All renderers walk the same tree, and text stays as
//! shaped glyph runs (never outlines), so it remains real text in every format.

use kurbo::{Affine, BezPath, Point, Rect, Size};
use std::sync::Arc;

/// An 8-bit RGBA color.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: u8,
}

impl Color {
    pub const fn rgb(r: u8, g: u8, b: u8) -> Self {
        Self { r, g, b, a: 255 }
    }

    pub const fn rgba(r: u8, g: u8, b: u8, a: u8) -> Self {
        Self { r, g, b, a }
    }

    pub const BLACK: Color = Color::rgb(0, 0, 0);
    pub const WHITE: Color = Color::rgb(255, 255, 255);
}

/// How the ends of an open stroked subpath are drawn.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum LineCap {
    #[default]
    Butt,
    Round,
    Square,
}

/// How corners between stroked segments are drawn.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum LineJoin {
    Miter,
    #[default]
    Round,
    Bevel,
}

/// A stroke style for a path.
#[derive(Debug, Clone)]
pub struct Stroke {
    pub color: Color,
    pub width: f64,
    pub cap: LineCap,
    pub join: LineJoin,
    /// Dash pattern (on/off lengths, in points). `None` = solid.
    pub dash: Option<Vec<f32>>,
}

impl Default for Stroke {
    fn default() -> Self {
        Self {
            color: Color::BLACK,
            width: 1.0,
            cap: LineCap::default(),
            join: LineJoin::default(),
            dash: None,
        }
    }
}

impl Stroke {
    /// A solid stroke of the given color and width, with default cap/join.
    pub fn new(color: Color, width: f64) -> Self {
        Self {
            color,
            width,
            ..Default::default()
        }
    }
}

/// The winding rule used to fill a path.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum FillRule {
    #[default]
    NonZero,
    EvenOdd,
}

/// A filled and/or stroked vector path.
#[derive(Debug, Clone)]
pub struct PathNode {
    pub geometry: BezPath,
    pub fill: Option<Color>,
    pub fill_rule: FillRule,
    pub stroke: Option<Stroke>,
}

impl PathNode {
    pub fn new(geometry: BezPath) -> Self {
        Self {
            geometry,
            fill: None,
            fill_rule: FillRule::NonZero,
            stroke: None,
        }
    }
}

/// Font bytes shared by reference between layout and every renderer.
#[derive(Debug, Clone)]
pub struct FontData {
    pub data: Arc<Vec<u8>>,
    pub index: u32,
}

impl FontData {
    pub fn from_bytes(data: Vec<u8>, index: u32) -> Self {
        Self {
            data: Arc::new(data),
            index,
        }
    }

    /// A stable identity for this font's underlying buffer, usable as a map
    /// key so each distinct font is parsed/embedded only once.
    pub fn key(&self) -> *const Vec<u8> {
        Arc::as_ptr(&self.data)
    }
}

/// A single glyph, already shaped and positioned relative to the text run's origin.
#[derive(Debug, Clone, Copy)]
pub struct PositionedGlyph {
    pub glyph_id: u16,
    /// Offset from the run origin to where this glyph should be drawn.
    pub x: f32,
    pub y: f32,
    /// Horizontal advance to the next glyph (cumulative positions are
    /// already baked into `x`/`y`; `advance` is kept for text-extent math).
    pub advance: f32,
    /// Byte offset into `GlyphRun::source_text` where this glyph's cluster
    /// begins - lets backends map glyphs back to source text (e.g. for a
    /// PDF ToUnicode/ActualText mapping so copy-paste yields real text).
    pub cluster: u32,
}

/// Glyphs shaped against one font at one size. Every backend draws exactly
/// these glyphs at these positions; `source_text` is the text they came from.
#[derive(Debug, Clone)]
pub struct GlyphRun {
    pub font: FontData,
    pub size: f32,
    pub glyphs: Vec<PositionedGlyph>,
    pub source_text: String,
}

/// A positioned block of text (one or more shaped runs, e.g. for font fallback).
#[derive(Debug, Clone)]
pub struct TextNode {
    pub origin: Point,
    pub runs: Vec<GlyphRun>,
    pub color: Color,
}

/// The normalized color-axis positions a colormapped image was built from,
/// kept so resampling can average data rather than colors (which would produce
/// colors that are not on the colorbar). NaN entries are masked.
#[derive(Debug, Clone)]
pub struct ColorField {
    /// `width * height` normalized positions in `[0, 1]`; NaN = masked.
    pub t: Arc<Vec<f32>>,
    /// The 256-entry RGBA lookup table `t` is read through.
    pub lut: Arc<Vec<u8>>,
}

/// Raw RGBA8 pixel data for an image, shared by reference.
#[derive(Debug, Clone)]
pub struct ImageData {
    /// `width * height * 4` bytes, row-major, non-premultiplied RGBA.
    pub rgba: Arc<Vec<u8>>,
    pub width: u32,
    pub height: u32,
    /// Present for a colormapped image; see [`ColorField`]. `None` for a raw
    /// RGBA image (a contour fill, an embedded bitmap), which has no data
    /// behind its pixels to average instead.
    pub field: Option<ColorField>,
}

impl ImageData {
    pub fn from_rgba8(rgba: Vec<u8>, width: u32, height: u32) -> Self {
        debug_assert_eq!(rgba.len(), (width as usize) * (height as usize) * 4);
        Self {
            rgba: Arc::new(rgba),
            width,
            height,
            field: None,
        }
    }

    /// Same pixels, plus the field they were colormapped from.
    pub fn with_field(mut self, t: Vec<f32>, lut: Vec<u8>) -> Self {
        debug_assert_eq!(t.len(), (self.width as usize) * (self.height as usize));
        debug_assert_eq!(lut.len(), 256 * 4);
        self.field = Some(ColorField {
            t: Arc::new(t),
            lut: Arc::new(lut),
        });
        self
    }

    pub fn key(&self) -> *const Vec<u8> {
        Arc::as_ptr(&self.rgba)
    }
}

/// An image scaled to fill `rect` (local coordinates). Backends resample it
/// first; see [`crate::resample`].
///
/// `rect` is always normalized (`x0 <= x1`, `y0 <= y1`); flips are applied to
/// the pixels, never expressed through the rect. Build with [`ImageNode::new`].
#[derive(Debug, Clone)]
pub struct ImageNode {
    pub data: ImageData,
    pub rect: Rect,
}

impl ImageNode {
    /// An image filling `rect`, normalized so the two corners are ordered.
    pub fn new(data: ImageData, rect: Rect) -> Self {
        Self {
            data,
            rect: rect.abs(),
        }
    }
}

/// One marker outline (centered on the origin, at final size) stamped at many
/// positions: a Form XObject in PDF, `<use>` in SVG, cached tiles in PNG. This
/// keeps big scatters fast and their files small.
#[derive(Debug, Clone)]
pub struct MarkerNode {
    /// The marker outline, centered at the origin, at final size. Closed
    /// subpaths are filled; open subpaths (`+`/`x`) are stroked.
    pub marker: BezPath,
    pub fill: Option<Color>,
    pub fill_rule: FillRule,
    pub stroke: Option<Stroke>,
    /// Center positions in the current local coordinate space.
    pub positions: Vec<Point>,
    /// Optional per-position fill colors (e.g. a colormapped scatter). When
    /// `Some`, it is parallel to `positions` and overrides `fill` per point; the
    /// shared `marker` outline and `stroke` (edge) still apply to every point.
    pub colors: Option<Vec<Color>>,
}

/// A path used to clip a [`Group`]'s contents.
#[derive(Debug, Clone)]
pub struct ClipPath {
    pub geometry: BezPath,
    pub rule: FillRule,
}

impl ClipPath {
    /// A rectangular clip - the common case (clipping marks to a plot area).
    pub fn rect(rect: Rect) -> Self {
        let mut geometry = BezPath::new();
        geometry.move_to((rect.x0, rect.y0));
        geometry.line_to((rect.x1, rect.y0));
        geometry.line_to((rect.x1, rect.y1));
        geometry.line_to((rect.x0, rect.y1));
        geometry.close_path();
        Self {
            geometry,
            rule: FillRule::NonZero,
        }
    }
}

/// A grouping node carrying a transform, optional clip, and opacity that
/// apply to all of its `children`.
///
/// Transforms compose down the tree (child transforms are pre-multiplied by
/// ancestor transforms), clips intersect, and opacity is applied to the group
/// as a single composited layer.
#[derive(Debug, Clone)]
pub struct Group {
    pub transform: Affine,
    pub clip: Option<ClipPath>,
    pub opacity: f32,
    pub children: Vec<Node>,
}

impl Default for Group {
    fn default() -> Self {
        Self {
            transform: Affine::IDENTITY,
            clip: None,
            opacity: 1.0,
            children: Vec::new(),
        }
    }
}

impl Group {
    pub fn new() -> Self {
        Self::default()
    }

    /// A group that applies `transform` to its children.
    pub fn with_transform(transform: Affine) -> Self {
        Self {
            transform,
            ..Default::default()
        }
    }

    pub fn push(&mut self, node: impl Into<Node>) {
        self.children.push(node.into());
    }
}

/// A node in the scene tree.
#[derive(Debug, Clone)]
pub enum Node {
    Path(PathNode),
    Text(TextNode),
    Image(ImageNode),
    Markers(MarkerNode),
    Group(Group),
}

impl From<PathNode> for Node {
    fn from(n: PathNode) -> Self {
        Node::Path(n)
    }
}
impl From<MarkerNode> for Node {
    fn from(n: MarkerNode) -> Self {
        Node::Markers(n)
    }
}
impl From<TextNode> for Node {
    fn from(n: TextNode) -> Self {
        Node::Text(n)
    }
}
impl From<ImageNode> for Node {
    fn from(n: ImageNode) -> Self {
        Node::Image(n)
    }
}
impl From<Group> for Node {
    fn from(n: Group) -> Self {
        Node::Group(n)
    }
}

/// A figure ready to render. Coordinates are points, y down, origin top-left.
#[derive(Debug, Clone)]
pub struct Scene {
    /// Canvas size in points (1/72 inch) - PDF's native unit.
    pub size: Size,
    pub nodes: Vec<Node>,
}

impl Scene {
    pub fn new(size: Size) -> Self {
        Self {
            size,
            nodes: Vec::new(),
        }
    }

    pub fn push(&mut self, node: impl Into<Node>) {
        self.nodes.push(node.into());
    }
}
