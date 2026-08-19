//! pyplotrs-core: the backend-agnostic Scene IR.
//!
//! The IR is a small tree of nodes (paths, pre-shaped text runs, images, and
//! transform/clip groups). All three backends (PDF, raster, SVG) walk this
//! same tree, so a figure is described exactly once and rendered identically
//! everywhere. Text is kept as pre-shaped glyph runs - never collapsed to
//! outlines - which is what makes "real, editable text" a property of the
//! whole pipeline rather than a PDF-only trick.

pub use kurbo;

pub mod resample;

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

/// Raw font bytes shared (by reference) across the scene and renderers.
///
/// Keeping this in `pyplotrs-core` lets every backend (PDF embedding, raster
/// rasterization, SVG font-family lookup) refer to the *same* underlying
/// bytes that were used for shaping/measurement during layout.
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

/// A run of glyphs that have already been shaped (via `pyplotrs-text`) against
/// a single font at a single size.
///
/// Pre-shaping upstream means every backend draws *exactly* the same glyphs
/// at the same positions - the PDF backend embeds them as real text, the
/// raster backend rasterizes their outlines, and the SVG backend emits a
/// `<text>` element using `source_text`.
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

/// Raw RGBA8 pixel data for an image, shared by reference.
#[derive(Debug, Clone)]
pub struct ImageData {
    /// `width * height * 4` bytes, row-major, non-premultiplied RGBA.
    pub rgba: Arc<Vec<u8>>,
    pub width: u32,
    pub height: u32,
}

impl ImageData {
    pub fn from_rgba8(rgba: Vec<u8>, width: u32, height: u32) -> Self {
        debug_assert_eq!(rgba.len(), (width as usize) * (height as usize) * 4);
        Self {
            rgba: Arc::new(rgba),
            width,
            height,
        }
    }

    pub fn key(&self) -> *const Vec<u8> {
        Arc::as_ptr(&self.rgba)
    }
}

/// An image composited into the destination `rect` (in the current local
/// coordinate space). The image's pixel grid is scaled to fill `rect`.
///
/// The two axes scale independently, and a backend has only one filter to
/// cover both - so each backend resamples the pixel grid onto the one it will
/// actually draw first, via [`resample`]. Read that module before touching an
/// image path in a renderer: handing the source grid straight to a rasterizer
/// is what makes a tall image alias and a wide one smear.
///
/// `rect` is **always normalized** (`x0 <= x1`, `y0 <= y1`) - build one with
/// [`ImageNode::new`], which does that for you. A denormalized rect is not a
/// way to request a flip; it is a bug, and one each backend used to answer
/// differently. An inverted y axis produced `y1 < y0`, and the raster backend
/// flipped the blit (right picture, by accident) while the PDF backend's
/// `Size::from_wh` returned `None` and dropped the image entirely and the SVG
/// backend wrote `height="-174"`, which SVG declares an error - so the same
/// figure rendered its heatmap in the PNG and omitted it from both vector
/// formats. Orientation is now decided once, where the pixels are laid out,
/// and the rect only ever says *where*.
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

/// A reusable marker outline stamped (by pure translation) at many positions -
/// the instanced form of a scatter plot.
///
/// Instead of one giant [`PathNode`] carrying a separate copy of the marker
/// geometry per point, the outline is described **once** (centered at the local
/// origin, already at its final size) and each backend places it at every
/// center as cheaply as it can: the PDF backend as a single reused Form XObject
/// (`draw_graphic`), the SVG backend as one `<defs>` path with a `<use>` per
/// point, and the raster backend by re-filling one prebuilt path at each
/// translated position. Fill/stroke are identical for every instance, and
/// positions translate only (never scale), so stroke widths are preserved.
///
/// This is what keeps large scatters (1e5-1e6 points) fast and the resulting
/// PDF/SVG small, instead of megabytes of duplicated bezier data.
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

/// A complete figure, ready to be handed to a renderer backend.
///
/// # Coordinate convention
///
/// The scene uses a **y-down** coordinate system with the origin at the
/// **top-left** of the canvas (matching SVG, raster images, and most "screen"
/// coordinate systems) and units of points (1/72 inch). This is the natural
/// convention for layout code (row 0 is the top row) and matches all three
/// backends directly: SVG and raster are natively y-down/top-left, and the
/// PDF backend's `krilla::Surface` applies its own page-root transform that
/// likewise exposes a y-down/top-left coordinate space, so no extra flip is
/// needed in `pyplotrs-render-pdf`.
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
