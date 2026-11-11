//! Python bindings for the pyplotrs engine, imported as `pyplotrs._core`.
//!
//! Keep `python/pyplotrs/_core.pyi` in step with this crate.

mod convert;
mod scene;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use pyplotrs_engine::geometry::Scale;
use pyplotrs_engine::render::raster;
use pyplotrs_engine::{color, kernels, threed};

use convert::{Bytes, F64s, Transform, value_err};
use scene::Scene;

/// `(min, max)` of the finite values that `scale` can place (positive values
/// for `"log"`), or `None` if there are none.
#[pyfunction]
#[pyo3(signature = (values, scale="linear"))]
fn finite_range(values: F64s, scale: &str) -> Option<(f64, f64)> {
    kernels::scaled_range(&values, Scale::parse(scale))
}

/// `(min, max)` of `values + offsets` (and `values - offsets` if `two_sided`).
#[pyfunction]
#[pyo3(signature = (values, offsets, two_sided=true))]
fn offset_range(values: F64s, offsets: F64s, two_sided: bool) -> Option<(f64, f64)> {
    kernels::offset_range(&values, &offsets, two_sided)
}

/// `(edges, counts)` of a fixed-width histogram.
#[pyfunction]
#[pyo3(signature = (values, bins, range=None, density=false))]
fn histogram(
    py: Python<'_>,
    values: F64s,
    bins: usize,
    range: Option<(f64, f64)>,
    density: bool,
) -> (Vec<f64>, Vec<f64>) {
    py.detach(|| kernels::histogram(&values, bins, range, density))
}

/// Row-major `ny x nx` counts of points binned over the given ranges.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn hist2d(
    py: Python<'_>,
    xs: F64s,
    ys: F64s,
    nx: usize,
    ny: usize,
    xlo: f64,
    xhi: f64,
    ylo: f64,
    yhi: f64,
) -> PyResult<Vec<f64>> {
    py.detach(|| kernels::hist2d(&xs, &ys, nx, ny, xlo, xhi, ylo, yhi))
        .map_err(value_err)
}

/// Gaussian kernel density of `samples` evaluated at `grid`.
#[pyfunction]
fn gaussian_kde(py: Python<'_>, samples: F64s, grid: F64s, bandwidth: f64) -> Vec<f64> {
    py.detach(|| kernels::gaussian_kde(&samples, &grid, bandwidth))
}

/// `([(x, y, count), ...], cell_width, cell_height)` for hexagonal bins.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn hexbin(
    py: Python<'_>,
    xs: F64s,
    ys: F64s,
    gridsize: usize,
    xlo: f64,
    xhi: f64,
    ylo: f64,
    yhi: f64,
) -> (Vec<(f64, f64, f64)>, f64, f64) {
    py.detach(|| kernels::hexbin(&xs, &ys, gridsize, xlo, xhi, ylo, yhi))
}

/// Iso-lines of a row-major `w x h` grid as `(level index, closed, points)`,
/// points in fractional grid coordinates.
#[pyfunction]
fn contour_lines(
    py: Python<'_>,
    values: F64s,
    w: usize,
    h: usize,
    levels: F64s,
) -> PyResult<Vec<kernels::ContourLine>> {
    py.detach(|| kernels::contour_lines(&values, w, h, &levels))
        .map_err(value_err)
}

/// Filled contours as `(rgba, width, height)`, `upsample` pixels per cell.
#[pyfunction]
fn contourf_image<'py>(
    py: Python<'py>,
    values: F64s,
    w: usize,
    h: usize,
    edges: F64s,
    band_lut: Bytes,
    upsample: usize,
) -> PyResult<(Bound<'py, PyBytes>, usize, usize)> {
    let (buf, ow, oh) = py
        .detach(|| kernels::contourf_image(&values, w, h, &edges, &band_lut.0, upsample))
        .map_err(value_err)?;
    Ok((PyBytes::new(py, &buf), ow, oh))
}

/// One RGBA quadruple per value (flat bytes) through `norm` and a 256-entry
/// RGBA `lut`. Non-finite values come out transparent.
#[pyfunction]
#[pyo3(signature = (values, lut, vmin, vmax, norm="linear"))]
fn map_colors<'py>(
    py: Python<'py>,
    values: F64s,
    lut: Bytes,
    vmin: f64,
    vmax: f64,
    norm: &str,
) -> PyResult<Bound<'py, PyBytes>> {
    if lut.0.len() != 1024 {
        return Err(PyValueError::new_err(
            "lut must be 256 RGBA entries (1024 bytes)",
        ));
    }
    let norm = Scale::parse(norm);
    let out = py.detach(|| kernels::map_colors(&values, &lut.0, norm, vmin, vmax));
    Ok(PyBytes::new(py, &out))
}

fn table_bytes(table: color::Table) -> Vec<u8> {
    table.iter().flatten().copied().collect()
}

/// A built-in colormap's 256 RGB entries as 768 bytes, or `None`.
#[pyfunction]
fn colormap_table(py: Python<'_>, name: &str) -> Option<Py<PyBytes>> {
    color::colormap_table(name).map(|t| PyBytes::new(py, &table_bytes(t)).unbind())
}

/// 256 RGB entries (768 bytes) interpolated between `(position, rgb)` stops in
/// `space` (`"oklab"`, `"lab"`, `"linear"` or `"srgb"`).
#[pyfunction]
fn colormap_from_stops<'py>(
    py: Python<'py>,
    stops: Vec<(f64, (u8, u8, u8))>,
    space: &str,
) -> PyResult<Bound<'py, PyBytes>> {
    if color::InterpSpace::parse(space).is_none() {
        return Err(PyValueError::new_err(format!(
            "unknown color space {space:?}"
        )));
    }
    let stops: Vec<(f64, [u8; 3])> = stops
        .into_iter()
        .map(|(p, (r, g, b))| (p, [r, g, b]))
        .collect();
    Ok(PyBytes::new(
        py,
        &table_bytes(color::colormap_table_from_stops(&stops, space)),
    ))
}

/// A built-in categorical palette's colors, or `None`.
#[pyfunction]
fn palette(name: &str) -> Option<Vec<(u8, u8, u8)>> {
    color::categorical_palette(name).map(|c| c.iter().map(|&[r, g, b]| (r, g, b)).collect())
}

/// Names of built-in colormaps, optionally only one category.
#[pyfunction]
#[pyo3(signature = (category=None))]
fn colormap_names(category: Option<&str>) -> Vec<&'static str> {
    color::list_colormaps(category)
}

/// Names of built-in categorical palettes.
#[pyfunction]
fn palette_names() -> Vec<&'static str> {
    color::list_palettes()
}

/// Device `(xs, ys, depths)` for 3D points seen from `(elev, azim)` degrees.
/// `frame` is `(xmin, xspan, ymin, yspan, zmin, zspan, cx, cy, sx, sy, scale)`.
#[pyfunction]
#[allow(clippy::type_complexity)]
fn project3d(
    xs: F64s,
    ys: F64s,
    zs: F64s,
    elev: f64,
    azim: f64,
    frame: (f64, f64, f64, f64, f64, f64, f64, f64, f64, f64, f64),
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let (xmin, xspan, ymin, yspan, zmin, zspan, ccx, ccy, scx, scy, scale) = frame;
    let frame = threed::Frame {
        xmin,
        xspan,
        ymin,
        yspan,
        zmin,
        zspan,
        ccx,
        ccy,
        scx,
        scy,
        scale,
    };
    threed::project_batch(&xs, &ys, &zs, &threed::Camera3D::new(elev, azim), &frame)
}

/// Screen-space `(xmin, xmax, ymin, ymax)` of the unit cube seen from
/// `(elev, azim)` degrees.
#[pyfunction]
fn cube_bounds(elev: f64, azim: f64) -> (f64, f64, f64, f64) {
    threed::cube_screen_bbox(&threed::Camera3D::new(elev, azim))
}

fn frames<'py>(
    py: Python<'py>,
    scenes: &[Py<Scene>],
) -> PyResult<Vec<pyplotrs_engine::scene::Scene>> {
    if scenes.is_empty() {
        return Err(PyValueError::new_err(
            "an animation needs at least one frame",
        ));
    }
    Ok(scenes
        .iter()
        .map(|s| s.borrow(py).with_scene(Clone::clone))
        .collect())
}

/// An animated GIF of `scenes`, each shown `delay_cs` hundredths of a second.
#[pyfunction]
#[pyo3(signature = (scenes, scale, delay_cs, loop_forever=true))]
fn render_gif<'py>(
    py: Python<'py>,
    scenes: Vec<Py<Scene>>,
    scale: f64,
    delay_cs: u16,
    loop_forever: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    let frames = frames(py, &scenes)?;
    let refs: Vec<_> = frames.iter().collect();
    let bytes = py
        .detach(|| raster::render_gif(&refs, scale, delay_cs, loop_forever))
        .map_err(value_err)?;
    Ok(PyBytes::new(py, &bytes))
}

/// An animated PNG of `scenes`, each shown `delay_num / delay_den` seconds.
#[pyfunction]
#[pyo3(signature = (scenes, dpi, delay_num, delay_den, loop_forever=true))]
fn render_apng<'py>(
    py: Python<'py>,
    scenes: Vec<Py<Scene>>,
    dpi: f64,
    delay_num: u16,
    delay_den: u16,
    loop_forever: bool,
) -> PyResult<Bound<'py, PyBytes>> {
    let frames = frames(py, &scenes)?;
    let refs: Vec<_> = frames.iter().collect();
    let bytes = py
        .detach(|| raster::render_apng(&refs, dpi, delay_num, delay_den, loop_forever))
        .map_err(value_err)?;
    Ok(PyBytes::new(py, &bytes))
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Scene>()?;
    m.add_class::<Transform>()?;
    m.add_function(wrap_pyfunction!(finite_range, m)?)?;
    m.add_function(wrap_pyfunction!(offset_range, m)?)?;
    m.add_function(wrap_pyfunction!(histogram, m)?)?;
    m.add_function(wrap_pyfunction!(hist2d, m)?)?;
    m.add_function(wrap_pyfunction!(gaussian_kde, m)?)?;
    m.add_function(wrap_pyfunction!(hexbin, m)?)?;
    m.add_function(wrap_pyfunction!(contour_lines, m)?)?;
    m.add_function(wrap_pyfunction!(contourf_image, m)?)?;
    m.add_function(wrap_pyfunction!(map_colors, m)?)?;
    m.add_function(wrap_pyfunction!(colormap_table, m)?)?;
    m.add_function(wrap_pyfunction!(colormap_from_stops, m)?)?;
    m.add_function(wrap_pyfunction!(palette, m)?)?;
    m.add_function(wrap_pyfunction!(colormap_names, m)?)?;
    m.add_function(wrap_pyfunction!(palette_names, m)?)?;
    m.add_function(wrap_pyfunction!(project3d, m)?)?;
    m.add_function(wrap_pyfunction!(cube_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(render_gif, m)?)?;
    m.add_function(wrap_pyfunction!(render_apng, m)?)?;
    Ok(())
}
