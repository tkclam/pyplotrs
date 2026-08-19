//! Single-pass figure layout.
//!
//! The whole point of this module is to fix matplotlib's `tight_layout` /
//! `constrained_layout` instability by construction: every band around an
//! axes (title, axis labels, tick labels, colorbar) and every figure-level
//! region (suptitle, legend) is given **reserved space sized from real,
//! pre-measured text extents**, and the plot areas get whatever is left.
//! Nothing is ever drawn as an overlay, so labels/legends/colorbars can never
//! overlap the data - there is no draw-measure-adjust loop.
//!
//! The public [`FigureSpec`] / [`LayoutResult`] types are engine-agnostic: the
//! current implementation is a direct deterministic solve (a uniform subplot
//! grid with per-axes bands), and a flexbox/grid engine could be slotted under
//! [`solve`] later without changing callers.

/// An axis-aligned rectangle in figure space (points, y-down, origin top-left).
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

impl Rect {
    pub fn new(x: f64, y: f64, w: f64, h: f64) -> Self {
        Self { x, y, w, h }
    }
    pub fn x1(&self) -> f64 {
        self.x + self.w
    }
    pub fn y1(&self) -> f64 {
        self.y + self.h
    }
}

/// Pre-measured band thicknesses (points) around a single axes' plot area.
///
/// A zero band means "not present" (e.g. no title, no colorbar). These come
/// from shaping real strings via `pyplotrs-text`, so they are exact.
#[derive(Debug, Clone, Copy, Default)]
pub struct AxesBands {
    /// Height reserved above the plot area for the axes title.
    pub title_h: f64,
    /// Height reserved below for the x-axis label.
    pub xlabel_h: f64,
    /// Width reserved at the left for the (rotated) y-axis label.
    pub ylabel_w: f64,
    /// Height reserved below the plot for x tick marks + tick labels.
    pub x_tick_h: f64,
    /// Horizontal room the first and last x tick labels need *beside* the plot
    /// area, being centered on ticks that sit at its very edges.
    ///
    /// The x tick band reserves thickness but has no length of its own - it is
    /// as wide as the plot - so a tick label centered on the last tick hangs
    /// half its width past the plot's right edge. Inside a grid that lands on
    /// the neighbouring cell; on the outermost column it lands off the page,
    /// and the label was simply cut there, silently, mid-glyph. These two say
    /// how far the overhang reaches so the plot can be inset enough to keep it
    /// on the canvas.
    pub x_tick_overhang_l: f64,
    pub x_tick_overhang_r: f64,
    /// Width reserved at the left (right of the y-axis label) for y tick
    /// marks + tick labels.
    pub y_tick_w: f64,
    /// Width reserved at the right for this axes' colorbar (0 if none).
    pub cbar_w: f64,
    /// Height reserved at the bottom for a *horizontal* colorbar (0 if none).
    /// Exactly one of `cbar_w`/`cbar_h` is non-zero: a colorbar is either
    /// beside the plot or beneath it, never both.
    pub cbar_h: f64,
}

/// A complete description of a figure to lay out.
#[derive(Debug, Clone)]
pub struct FigureSpec {
    pub width: f64,
    pub height: f64,
    pub nrows: usize,
    pub ncols: usize,
    /// Padding (points) around the entire figure.
    pub outer_margin: f64,
    /// Vertical gap (points) between subplot rows.
    pub hspace: f64,
    /// Horizontal gap (points) between subplot columns.
    pub wspace: f64,
    /// Height reserved at the very top of the figure for a suptitle (0 = none).
    pub suptitle_h: f64,
    /// Width reserved at the right of the figure for a shared legend (0 = none).
    pub legend_w: f64,
    /// Per-cell bands. Row-major `nrows * ncols` when `spans` is `None`; one per
    /// axes (aligned with `spans`) when spanning cells are used.
    pub cells: Vec<AxesBands>,
    /// Optional spanning placement: one `(row, col, rowspan, colspan)` per axes
    /// (in `cells` order). `None` = a plain uniform grid (the default).
    pub spans: Option<Vec<(usize, usize, usize, usize)>>,
    /// Relative column widths, one per column. `None` = all equal. Values are
    /// normalized, so `[2.0, 1.0]` and `[0.5, 0.25]` mean the same thing; the
    /// ratios apply to the *cell* including its label bands, matching
    /// matplotlib's `width_ratios`.
    pub width_ratios: Option<Vec<f64>>,
    /// Relative row heights, one per row. `None` = all equal.
    pub height_ratios: Option<Vec<f64>>,
}

/// The computed rectangles for one axes.
#[derive(Debug, Clone, Copy, Default)]
pub struct AxesLayout {
    /// The full grid cell allotted to this axes.
    pub cell: Rect,
    /// The data/plot area (where marks are drawn and clipped).
    pub plot: Rect,
    /// Band where the title is centered (above the plot area).
    pub title: Rect,
    /// Band for the x-axis label (below tick labels).
    pub xlabel: Rect,
    /// Band for the rotated y-axis label (left of tick labels).
    pub ylabel: Rect,
    /// Band for x tick marks + tick labels.
    pub x_tick: Rect,
    /// Band for y tick marks + tick labels.
    pub y_tick: Rect,
    /// Band for a colorbar to the right of the plot area (zero-size if none).
    pub cbar: Rect,
}

/// The full solved layout.
#[derive(Debug, Clone, Default)]
pub struct LayoutResult {
    /// Per-axes rects, row-major (same order as [`FigureSpec::cells`]).
    pub axes: Vec<AxesLayout>,
    /// Reserved suptitle band (zero-size if `suptitle_h == 0`).
    pub suptitle: Rect,
    /// Reserved figure-legend band (zero-size if `legend_w == 0`).
    pub legend: Rect,
}

/// Lay out `spec` in a single pass and return all rectangles.
pub fn solve(spec: &FigureSpec) -> LayoutResult {
    let nrows = spec.nrows.max(1);
    let ncols = spec.ncols.max(1);

    // 1. Inner figure area after the outer margin.
    let inner = Rect::new(
        spec.outer_margin,
        spec.outer_margin,
        (spec.width - 2.0 * spec.outer_margin).max(0.0),
        (spec.height - 2.0 * spec.outer_margin).max(0.0),
    );

    // 2. Carve a suptitle band off the top and a legend column off the right.
    let suptitle = Rect::new(inner.x, inner.y, inner.w, spec.suptitle_h);
    let legend = Rect::new(
        inner.x1() - spec.legend_w,
        inner.y + spec.suptitle_h,
        spec.legend_w,
        (inner.h - spec.suptitle_h).max(0.0),
    );

    // 3. The grid occupies what's left.
    let grid = Rect::new(
        inner.x,
        inner.y + spec.suptitle_h,
        (inner.w - spec.legend_w).max(0.0),
        (inner.h - spec.suptitle_h).max(0.0),
    );

    // Track/offset tables rather than a single cell size, so columns and rows
    // can differ in extent. `offsets[i]` is the start of track `i` relative to
    // the grid origin; `sizes[i]` its extent, gaps excluded.
    let (col_w, col_x) = tracks(grid.w, ncols, spec.wspace, spec.width_ratios.as_deref());
    let (row_h, row_y) = tracks(grid.h, nrows, spec.hspace, spec.height_ratios.as_deref());

    // Grid cell at (row, col) spanning (rowspan, colspan) whole cells, including
    // the inter-cell gaps it swallows.
    let span_rect = |row: usize, col: usize, rowspan: usize, colspan: usize| {
        let r0 = row.min(nrows - 1);
        let c0 = col.min(ncols - 1);
        let r1 = (r0 + rowspan.max(1)).min(nrows) - 1;
        let c1 = (c0 + colspan.max(1)).min(ncols) - 1;
        Rect::new(
            grid.x + col_x[c0],
            grid.y + row_y[r0],
            (col_x[c1] + col_w[c1] - col_x[c0]).max(0.0),
            (row_y[r1] + row_h[r1] - row_y[r0]).max(0.0),
        )
    };

    let mut axes = Vec::new();
    if let Some(spans) = &spec.spans {
        // Explicit spanning placement (GridSpec / subplot_mosaic).
        for (idx, &(row, col, rowspan, colspan)) in spans.iter().enumerate() {
            let bands = spec.cells.get(idx).copied().unwrap_or_default();
            axes.push(layout_cell(span_rect(row, col, rowspan, colspan), &bands));
        }
    } else {
        for row in 0..nrows {
            for col in 0..ncols {
                let idx = row * ncols + col;
                let bands = spec.cells.get(idx).copied().unwrap_or_default();
                axes.push(layout_cell(span_rect(row, col, 1, 1), &bands));
            }
        }
    }

    LayoutResult {
        axes,
        suptitle,
        legend,
    }
}

/// Split `total` into `n` tracks separated by `gap`, weighted by `ratios`.
///
/// Returns `(sizes, offsets)`. Gaps are taken out first so they stay a fixed
/// number of points regardless of the weighting - a 3:1 split should change the
/// panels, not the gutter between them. A missing, wrong-length, or
/// non-positive `ratios` falls back to equal tracks rather than erroring: a
/// layout hint is not worth failing a render over.
fn tracks(total: f64, n: usize, gap: f64, ratios: Option<&[f64]>) -> (Vec<f64>, Vec<f64>) {
    let n = n.max(1);
    let usable = (total - (n as f64 - 1.0) * gap).max(0.0);

    let weights: Vec<f64> = match ratios {
        Some(r) if r.len() == n && r.iter().all(|v| v.is_finite() && *v > 0.0) => r.to_vec(),
        _ => vec![1.0; n],
    };
    let sum: f64 = weights.iter().sum();

    let sizes: Vec<f64> = weights.iter().map(|w| usable * w / sum).collect();
    let mut offsets = Vec::with_capacity(n);
    let mut at = 0.0;
    for size in &sizes {
        offsets.push(at);
        at += size + gap;
    }
    (sizes, offsets)
}

/// Reserve the bands within one cell and return the plot area + band rects.
fn layout_cell(cell: Rect, b: &AxesBands) -> AxesLayout {
    // Left-to-right reservations: y-axis label, then y tick labels.
    let left = cell.x;
    let ylabel = Rect::new(left, cell.y, b.ylabel_w, cell.h);
    let y_tick_x = left + b.ylabel_w;

    // Top reservation: title. Bottom: x tick labels, x-axis label, then a
    // horizontal colorbar underneath both (it is the outermost bottom band, so
    // its own tick labels never collide with the axis's).
    let title = Rect::new(cell.x, cell.y, cell.w, b.title_h);

    // Plot area is what remains after all bands.
    //
    // The left overhang is usually swallowed by the y tick band, which is
    // wider than half an x tick label whenever there are y labels at all -
    // only the part that sticks out beyond it costs anything.
    let left_pad = (b.x_tick_overhang_l - b.y_tick_w).max(0.0);
    let plot_x = y_tick_x + b.y_tick_w + left_pad;
    let plot_y = cell.y + b.title_h;
    let plot_w = (cell.x1() - b.cbar_w - b.x_tick_overhang_r - plot_x).max(0.0);
    let plot_h = (cell.y1() - b.xlabel_h - b.x_tick_h - b.cbar_h - plot_y).max(0.0);
    let plot = Rect::new(plot_x, plot_y, plot_w, plot_h);

    let y_tick = Rect::new(y_tick_x, plot_y, b.y_tick_w, plot_h);
    let x_tick = Rect::new(plot_x, plot.y1(), plot_w, b.x_tick_h);
    let xlabel = Rect::new(plot_x, plot.y1() + b.x_tick_h, plot_w, b.xlabel_h);

    // The colorbar band: beside the plot when vertical, beneath it when
    // horizontal. Spanning the plot's extent (not the cell's) keeps the strip
    // aligned with the data it describes.
    let cbar = if b.cbar_h > 0.0 {
        Rect::new(
            plot_x,
            plot.y1() + b.x_tick_h + b.xlabel_h,
            plot_w,
            b.cbar_h,
        )
    } else {
        Rect::new(cell.x1() - b.cbar_w, cell.y, b.cbar_w, cell.h)
    };

    AxesLayout {
        cell,
        plot,
        title,
        xlabel,
        ylabel,
        x_tick,
        y_tick,
        cbar,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn approx(a: f64, b: f64) {
        assert!((a - b).abs() < 1e-6, "{a} != {b}");
    }

    #[test]
    fn single_axes_reserves_all_bands() {
        let spec = FigureSpec {
            width: 400.0,
            height: 300.0,
            nrows: 1,
            ncols: 1,
            outer_margin: 5.0,
            hspace: 0.0,
            wspace: 0.0,
            suptitle_h: 0.0,
            legend_w: 0.0,
            cells: vec![AxesBands {
                title_h: 20.0,
                xlabel_h: 12.0,
                ylabel_w: 12.0,
                x_tick_h: 14.0,
                y_tick_w: 24.0,
                x_tick_overhang_l: 0.0,
                x_tick_overhang_r: 0.0,
                cbar_w: 0.0,
                cbar_h: 0.0,
            }],
            spans: None,
            width_ratios: None,
            height_ratios: None,
        };
        let out = solve(&spec);
        let ax = out.axes[0];
        // Plot area starts after left margin + ylabel + y_tick.
        approx(ax.plot.x, 5.0 + 12.0 + 24.0);
        approx(ax.plot.y, 5.0 + 20.0);
        // Right edge reaches inner right (no colorbar).
        approx(ax.plot.x1(), 395.0);
        // Bottom leaves room for x ticks + xlabel.
        approx(ax.plot.y1(), 295.0 - 14.0 - 12.0);
    }

    /// A 2:1 width ratio must make the first column exactly twice the second,
    /// and must not change the gutter between them - gaps are a fixed number of
    /// points, not a share of the figure.
    #[test]
    fn width_ratios_weight_columns_but_not_gaps() {
        let equal = solve(&spec_with_ratios(None));
        let weighted = solve(&spec_with_ratios(Some(vec![2.0, 1.0])));

        let (a, b) = (weighted.axes[0].cell, weighted.axes[1].cell);
        assert!(
            (a.w - 2.0 * b.w).abs() < 1e-9,
            "expected a 2:1 split, got {} and {}",
            a.w,
            b.w
        );
        // Total extent, and therefore the gutter, is unchanged.
        let equal_span = equal.axes[1].cell.x1() - equal.axes[0].cell.x;
        let weighted_span = b.x1() - a.x;
        assert!((equal_span - weighted_span).abs() < 1e-9);
        assert!((b.x - a.x1() - 12.0).abs() < 1e-9, "gutter changed");
    }

    /// Ratios are normalized, so only their proportions matter.
    #[test]
    fn width_ratios_are_scale_invariant() {
        let a = solve(&spec_with_ratios(Some(vec![3.0, 1.0])));
        let b = solve(&spec_with_ratios(Some(vec![0.75, 0.25])));
        assert!((a.axes[0].cell.w - b.axes[0].cell.w).abs() < 1e-9);
    }

    /// A malformed hint falls back to equal tracks rather than erroring - a
    /// layout preference is not worth failing a render over.
    #[test]
    fn malformed_ratios_fall_back_to_equal() {
        let equal = solve(&spec_with_ratios(None));
        for bad in [
            vec![1.0],
            vec![1.0, 0.0],
            vec![1.0, f64::NAN],
            vec![-1.0, 2.0],
        ] {
            let got = solve(&spec_with_ratios(Some(bad.clone())));
            assert!(
                (got.axes[0].cell.w - equal.axes[0].cell.w).abs() < 1e-9,
                "ratios {bad:?} should have fallen back to equal tracks"
            );
        }
    }

    fn spec_with_ratios(width_ratios: Option<Vec<f64>>) -> FigureSpec {
        FigureSpec {
            width: 400.0,
            height: 200.0,
            nrows: 1,
            ncols: 2,
            outer_margin: 5.0,
            hspace: 10.0,
            wspace: 12.0,
            suptitle_h: 0.0,
            legend_w: 0.0,
            cells: vec![AxesBands::default(); 2],
            spans: None,
            width_ratios,
            height_ratios: None,
        }
    }

    #[test]
    fn grid_cells_tile_without_overlap() {
        let spec = FigureSpec {
            width: 600.0,
            height: 400.0,
            nrows: 1,
            ncols: 2,
            outer_margin: 10.0,
            hspace: 0.0,
            wspace: 20.0,
            suptitle_h: 0.0,
            legend_w: 0.0,
            cells: vec![AxesBands::default(), AxesBands::default()],
            spans: None,
            width_ratios: None,
            height_ratios: None,
        };
        let out = solve(&spec);
        // Two equal cells with a 20pt gap inside a 580pt-wide inner area.
        approx(out.axes[0].cell.w, (580.0 - 20.0) / 2.0);
        approx(out.axes[1].cell.x, 10.0 + (580.0 - 20.0) / 2.0 + 20.0);
        // No overlap: cell0 right edge < cell1 left edge.
        assert!(out.axes[0].cell.x1() <= out.axes[1].cell.x + 1e-9);
    }
}
