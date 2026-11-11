//! Scene renderers. All three walk the same [`crate::scene::Scene`], so a figure
//! looks the same in every format.

pub mod pdf;
pub(crate) mod png;
pub mod raster;
pub mod svg;
