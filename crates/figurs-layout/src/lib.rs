//! figurs-layout: figure/axes/legend/colorbar arrangement and axis ticking.
//!
//! Two responsibilities, both feeding the "measure once, solve once" layout
//! strategy that replaces matplotlib's draw-measure-adjust loops:
//!
//! - [`ticks`]: choose round tick values + labels so their extents can be
//!   measured *before* layout runs.
//! - [`solve`]: arrange a figure's subplot grid and each axes' surrounding
//!   bands (title / axis labels / tick labels / plot area) in a single pass,
//!   given pre-measured band sizes.

pub mod solve;
pub mod ticks;

pub use solve::{AxesBands, FigureSpec, LayoutResult, Rect};
pub use ticks::{format_tick, nice_step, tick_values, ticks, Tick};
