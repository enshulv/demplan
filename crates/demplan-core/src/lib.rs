//! Core data model and loaders for demplan.
//!
//! [`Economy`] is the state of an economy in one period, stored as three
//! columnar tables. [`load_dep1ex`] builds one from a dep1ex scenario file, and
//! [`load_wiod`] from one year of the WIOD 2016 release.

#![deny(missing_docs)]

pub mod dep1ex;
pub mod economy;
pub mod wiod;

pub use dep1ex::{load_dep1ex, LoadError};
pub use economy::{Economy, ExtraArray, SchemaError};
pub use wiod::{load_wiod, Labor, ObservedFlows, WiodError, WiodTable};
