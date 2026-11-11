//! The pyplotrs engine: a backend-agnostic scene description, the text and math
//! layout that fills it, and the PDF, SVG and PNG renderers that draw it.
//!
//! Nothing here knows about Python. The `pyplotrs-python` crate builds a
//! [`scene::Scene`] through thin bindings and hands it to [`render`].

pub use kurbo;

pub mod color;
pub mod draw;
pub mod fonts;
pub mod geometry;
pub mod kernels;
pub mod math;
pub mod render;
pub mod resample;
pub mod scene;
pub mod text;
pub mod threed;
