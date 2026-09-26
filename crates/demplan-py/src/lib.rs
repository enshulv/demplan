//! Python extension module `demplan._core`.
//!
//! The module hands the Rust data model to Python as plain dictionaries of numpy
//! arrays. Keys match the column names of the data model, so the Python package
//! can build its own immutable data classes without a second naming scheme.

use std::collections::BTreeMap;

use demplan_core::{Economy, ExtraArray, LoadError as CoreLoadError};
use numpy::ndarray::{ArrayD, IxDyn};
use numpy::{Element, IntoPyArray, PyArrayDyn};
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

create_exception!(
    _core,
    LoadError,
    PyValueError,
    "A scenario file that cannot be turned into an economy."
);
create_exception!(
    _core,
    SchemaError,
    PyValueError,
    "An economy that breaches the data model."
);

/// Returns the version of the Rust core.
#[pyfunction]
fn core_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Reads a dep1ex scenario file and returns its economy as a dictionary.
///
/// `endowment` is the quantity of every natural resource and every kind of
/// labour available in the period; the file does not carry it.
///
/// Raises `LoadError` when the file cannot be read, decompressed or parsed, and
/// `SchemaError` when the economy it describes breaches the data model.
#[pyfunction]
fn load_dep1ex<'py>(py: Python<'py>, path: &str, endowment: f64) -> PyResult<Bound<'py, PyDict>> {
    let economy = py
        .detach(|| demplan_core::load_dep1ex(path, endowment))
        .map_err(to_py_error)?;
    economy_to_dict(py, economy)
}

/// Maps a load failure onto the matching Python exception.
///
/// A schema breach keeps its own type and message, because the caller acts on it
/// differently from a malformed file.
fn to_py_error(error: CoreLoadError) -> PyErr {
    match error {
        CoreLoadError::Schema(schema) => SchemaError::new_err(schema.to_string()),
        other => LoadError::new_err(other.to_string()),
    }
}

fn economy_to_dict(py: Python<'_>, economy: Economy) -> PyResult<Bound<'_, PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("period", economy.period)?;

    dict.set_item("commodity_id", economy.commodity_id.into_pyarray(py))?;
    dict.set_item("commodity_kind", economy.commodity_kind.into_pyarray(py))?;
    dict.set_item("endowment", economy.endowment.into_pyarray(py))?;
    dict.set_item(
        "commodity_extra",
        extra_to_dict(py, economy.commodity_extra)?,
    )?;

    dict.set_item("unit_id", economy.unit_id.into_pyarray(py))?;
    dict.set_item("unit_group", economy.unit_group.into_pyarray(py))?;
    dict.set_item(
        "output_commodity",
        economy.output_commodity.into_pyarray(py),
    )?;
    dict.set_item("technology_kind", economy.technology_kind.into_pyarray(py))?;
    dict.set_item(
        "technology_scale",
        economy.technology_scale.into_pyarray(py),
    )?;
    dict.set_item("input_offsets", economy.input_offsets.into_pyarray(py))?;
    dict.set_item("input_commodity", economy.input_commodity.into_pyarray(py))?;
    dict.set_item(
        "input_coefficient",
        economy.input_coefficient.into_pyarray(py),
    )?;
    dict.set_item("unit_extra", extra_to_dict(py, economy.unit_extra)?)?;

    dict.set_item("consumer_id", economy.consumer_id.into_pyarray(py))?;
    dict.set_item("consumer_group", economy.consumer_group.into_pyarray(py))?;
    dict.set_item("consumer_extra", extra_to_dict(py, economy.consumer_extra)?)?;

    Ok(dict)
}

/// Turns one extra bag into a dictionary of numpy arrays, restoring the stored
/// shape so a two-dimensional array arrives two-dimensional.
fn extra_to_dict(py: Python<'_>, bag: BTreeMap<String, ExtraArray>) -> PyResult<Bound<'_, PyDict>> {
    let dict = PyDict::new(py);
    for (key, array) in bag {
        let value = match array {
            ExtraArray::F64 { shape, data } => reshape(py, &key, shape, data)?.into_any(),
            ExtraArray::I64 { shape, data } => reshape(py, &key, shape, data)?.into_any(),
        };
        dict.set_item(key, value)?;
    }
    Ok(dict)
}

fn reshape<'py, T: Element>(
    py: Python<'py>,
    key: &str,
    shape: Vec<usize>,
    data: Vec<T>,
) -> PyResult<Bound<'py, PyArrayDyn<T>>> {
    let array = ArrayD::from_shape_vec(IxDyn(&shape), data)
        .map_err(|error| SchemaError::new_err(format!("extra array `{key}`: {error}")))?;
    Ok(array.into_pyarray(py))
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(core_version, m)?)?;
    m.add_function(wrap_pyfunction!(load_dep1ex, m)?)?;
    m.add("LoadError", m.py().get_type::<LoadError>())?;
    m.add("SchemaError", m.py().get_type::<SchemaError>())?;
    Ok(())
}
