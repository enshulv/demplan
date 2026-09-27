//! Python extension module `demplan._core`.
//!
//! The module hands the Rust data model to Python as plain dictionaries. Numeric
//! columns arrive as numpy arrays; text columns (`technology_kind` and text extra
//! arrays) arrive as a `list` of `str`, which the Python package converts. Keys
//! match the column names of the data model, so the Python package can build its
//! own immutable data classes without a second naming scheme.

use std::collections::BTreeMap;

use demplan_core::{
    Economy, ExtraArray, Labor, LoadError as CoreLoadError, ObservedFlows, WiodError, WiodTable,
};
use numpy::ndarray::{ArrayD, IxDyn};
use numpy::{Element, IntoPyArray, PyArrayDyn};
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

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

/// Labour measure name that reads compensation of employees.
const LABOR_COMPENSATION: &str = "compensation";
/// Labour measure name that reads hours worked by employees.
const LABOR_HOURS: &str = "hours";

/// Reads one year of the WIOD 2016 release and returns a dictionary with three
/// entries: `economy`, keyed like the result of `load_dep1ex`; `observed`, the
/// recorded flows (`output`, `input_use`, `consumption` as a two-dimensional
/// array, `consumption_commodity`, `shared_use`); and `unproduced_inputs`, the
/// products without a producing unit that units use (`commodity`, and `used`,
/// the total units use of each).
///
/// `path` is the release zip or one `.xlsb` workbook. `labor` is `None`,
/// `"compensation"` (which needs `sea` and `exchange_rates`) or `"hours"` (which
/// needs `sea`); any other combination raises `ValueError`.
///
/// Raises `LoadError` when a file cannot be read or does not have the release's
/// layout, and `SchemaError` when the economy it describes breaches the data
/// model.
#[pyfunction]
#[pyo3(signature = (path, year, labor=None, sea=None, exchange_rates=None))]
fn load_wiod<'py>(
    py: Python<'py>,
    path: &str,
    year: i32,
    labor: Option<&str>,
    sea: Option<&str>,
    exchange_rates: Option<&str>,
) -> PyResult<Bound<'py, PyDict>> {
    let labor = labor_of(labor, sea, exchange_rates)?;
    let table = py
        .detach(|| demplan_core::load_wiod(path, year, &labor))
        .map_err(wiod_error_to_py)?;
    wiod_table_to_dict(py, table)
}

/// Turns the labour arguments into a [`Labor`], refusing a measure without the
/// workbooks it reads.
fn labor_of(
    labor: Option<&str>,
    sea: Option<&str>,
    exchange_rates: Option<&str>,
) -> PyResult<Labor> {
    match (labor, sea, exchange_rates) {
        (None, _, _) => Ok(Labor::None),
        (Some(LABOR_COMPENSATION), Some(sea), Some(exchange_rates)) => Ok(Labor::Compensation {
            sea: sea.into(),
            exchange_rates: exchange_rates.into(),
        }),
        (Some(LABOR_COMPENSATION), _, _) => Err(PyValueError::new_err(
            "labor='compensation' needs both sea and exchange_rates",
        )),
        (Some(LABOR_HOURS), Some(sea), _) => Ok(Labor::Hours { sea: sea.into() }),
        (Some(LABOR_HOURS), None, _) => Err(PyValueError::new_err("labor='hours' needs sea")),
        (Some(other), _, _) => Err(PyValueError::new_err(format!(
            "labor is {other:?}, expected None, {LABOR_COMPENSATION:?} or {LABOR_HOURS:?}"
        ))),
    }
}

/// Maps a WIOD load failure onto the matching Python exception.
fn wiod_error_to_py(error: WiodError) -> PyErr {
    match error {
        WiodError::Schema(schema) => SchemaError::new_err(schema.to_string()),
        other => LoadError::new_err(other.to_string()),
    }
}

fn wiod_table_to_dict(py: Python<'_>, table: WiodTable) -> PyResult<Bound<'_, PyDict>> {
    let n_consumers = table.economy.n_consumers();
    let dict = PyDict::new(py);
    dict.set_item("economy", economy_to_dict(py, table.economy)?)?;
    dict.set_item(
        "observed",
        observed_to_dict(py, table.observed, n_consumers)?,
    )?;
    let unproduced = PyDict::new(py);
    unproduced.set_item(
        "commodity",
        table.unproduced_inputs.commodity.into_pyarray(py),
    )?;
    unproduced.set_item("used", table.unproduced_inputs.used.into_pyarray(py))?;
    dict.set_item("unproduced_inputs", unproduced)?;
    Ok(dict)
}

fn observed_to_dict(
    py: Python<'_>,
    observed: ObservedFlows,
    n_consumers: usize,
) -> PyResult<Bound<'_, PyDict>> {
    let n_columns = observed.consumption_commodity.len();
    let dict = PyDict::new(py);
    dict.set_item("output", observed.output.into_pyarray(py))?;
    dict.set_item("input_use", observed.input_use.into_pyarray(py))?;
    dict.set_item(
        "consumption",
        reshape(
            py,
            "consumption",
            vec![n_consumers, n_columns],
            observed.consumption,
        )?,
    )?;
    dict.set_item(
        "consumption_commodity",
        observed.consumption_commodity.into_pyarray(py),
    )?;
    dict.set_item("shared_use", observed.shared_use.into_pyarray(py))?;
    Ok(dict)
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
    dict.set_item("endowment", economy.endowment.into_pyarray(py))?;
    dict.set_item(
        "commodity_extra",
        extra_to_dict(py, economy.commodity_extra)?,
    )?;

    dict.set_item("unit_id", economy.unit_id.into_pyarray(py))?;
    dict.set_item("technology_kind", PyList::new(py, economy.technology_kind)?)?;
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
    dict.set_item("output_offsets", economy.output_offsets.into_pyarray(py))?;
    dict.set_item(
        "output_commodity",
        economy.output_commodity.into_pyarray(py),
    )?;
    dict.set_item(
        "output_coefficient",
        economy.output_coefficient.into_pyarray(py),
    )?;
    dict.set_item("unit_extra", extra_to_dict(py, economy.unit_extra)?)?;

    dict.set_item("consumer_id", economy.consumer_id.into_pyarray(py))?;
    dict.set_item("consumer_extra", extra_to_dict(py, economy.consumer_extra)?)?;

    Ok(dict)
}

/// Turns one extra bag into a dictionary, restoring the stored shape of numeric
/// arrays so a two-dimensional array arrives two-dimensional. Text arrays arrive
/// as a `list` of `str`.
fn extra_to_dict(py: Python<'_>, bag: BTreeMap<String, ExtraArray>) -> PyResult<Bound<'_, PyDict>> {
    let dict = PyDict::new(py);
    for (key, array) in bag {
        let value = match array {
            ExtraArray::F64 { shape, data } => reshape(py, &key, shape, data)?.into_any(),
            ExtraArray::I64 { shape, data } => reshape(py, &key, shape, data)?.into_any(),
            ExtraArray::Text { data } => PyList::new(py, data)?.into_any(),
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
    m.add_function(wrap_pyfunction!(load_wiod, m)?)?;
    m.add("LoadError", m.py().get_type::<LoadError>())?;
    m.add("SchemaError", m.py().get_type::<SchemaError>())?;
    Ok(())
}
