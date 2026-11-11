//! Argument conversion between Python and the engine.

use pyo3::buffer::PyBuffer;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use pyplotrs_engine::geometry::{self, Scale};
use pyplotrs_engine::scene::{Color, LineCap, LineJoin, Stroke};

/// A column of floats. Anything exporting a 1-D contiguous float64 buffer
/// (NumPy arrays, `array.array("d")`) is copied in at memcpy speed; other
/// sequences go through the generic per-element path.
pub struct F64s(pub Vec<f64>);

impl std::ops::Deref for F64s {
    type Target = [f64];
    fn deref(&self) -> &[f64] {
        &self.0
    }
}

impl<'a, 'py> FromPyObject<'a, 'py> for F64s {
    type Error = PyErr;

    fn extract(obj: pyo3::Borrowed<'a, 'py, PyAny>) -> PyResult<Self> {
        if let Ok(buf) = PyBuffer::<f64>::get(&obj)
            && buf.dimensions() == 1
            && buf.is_c_contiguous()
        {
            return Ok(F64s(buf.to_vec(obj.py())?));
        }
        Ok(F64s(obj.extract()?))
    }
}

/// Raw bytes from `bytes`, `bytearray` or any byte buffer.
pub struct Bytes(pub Vec<u8>);

impl<'a, 'py> FromPyObject<'a, 'py> for Bytes {
    type Error = PyErr;

    fn extract(obj: pyo3::Borrowed<'a, 'py, PyAny>) -> PyResult<Self> {
        if let Ok(buf) = PyBuffer::<u8>::get(&obj)
            && buf.is_c_contiguous()
        {
            return Ok(Bytes(buf.to_vec(obj.py())?));
        }
        Ok(Bytes(obj.extract()?))
    }
}

pub type Rgba = (u8, u8, u8, u8);

pub fn color(c: Rgba) -> Color {
    Color::rgba(c.0, c.1, c.2, c.3)
}

pub fn cap(name: &str) -> PyResult<LineCap> {
    Ok(match name {
        "butt" => LineCap::Butt,
        "round" => LineCap::Round,
        "square" => LineCap::Square,
        _ => return Err(PyValueError::new_err(format!("unknown cap {name:?}"))),
    })
}

pub fn join(name: &str) -> PyResult<LineJoin> {
    Ok(match name {
        "miter" => LineJoin::Miter,
        "round" => LineJoin::Round,
        "bevel" => LineJoin::Bevel,
        _ => return Err(PyValueError::new_err(format!("unknown join {name:?}"))),
    })
}

pub fn stroke(
    c: Option<Rgba>,
    width: f64,
    dash: Option<Vec<f32>>,
    cap_name: &str,
    join_name: &str,
) -> PyResult<Option<Stroke>> {
    let (cap, join) = (cap(cap_name)?, join(join_name)?);
    Ok(c.map(|c| Stroke {
        color: color(c),
        width,
        cap,
        join,
        dash: dash.filter(|d| d.len() >= 2),
    }))
}

pub fn marker(name: &str) -> PyResult<&str> {
    if geometry::MARKERS.contains(&name) {
        Ok(name)
    } else {
        Err(PyValueError::new_err(format!(
            "unknown marker {name:?}; expected one of {:?}",
            geometry::MARKERS
        )))
    }
}

/// Maps data coordinates to device points: `device = a * scale(v) + b` per
/// axis. The default is the identity, for drawing directly in points.
#[pyclass(frozen, skip_from_py_object, module = "pyplotrs._core")]
#[derive(Clone, Copy)]
pub struct Transform(pub geometry::Transform);

#[pymethods]
impl Transform {
    #[new]
    #[pyo3(signature = (ax=1.0, bx=0.0, ay=1.0, by=0.0, xscale="linear", yscale="linear"))]
    fn new(ax: f64, bx: f64, ay: f64, by: f64, xscale: &str, yscale: &str) -> Self {
        Transform(geometry::Transform {
            ax,
            bx,
            ay,
            by,
            xscale: Scale::parse(xscale),
            yscale: Scale::parse(yscale),
        })
    }

    /// Device x for data `x`.
    fn x(&self, x: f64) -> f64 {
        self.0.x(x)
    }

    /// Device y for data `y`.
    fn y(&self, y: f64) -> f64 {
        self.0.y(y)
    }
}

pub fn transform(tf: Option<&Transform>) -> geometry::Transform {
    tf.map_or(geometry::Transform::IDENTITY, |t| t.0)
}

pub fn value_err(e: String) -> PyErr {
    PyValueError::new_err(e)
}
