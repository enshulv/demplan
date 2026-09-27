//! Core data model and loaders for demplan.
//!
//! [`Economy`] is the state of an economy in one period, stored as three
//! columnar tables. [`load_dep1ex`] builds one from a dep1ex scenario file.

#![deny(missing_docs)]

pub mod dep1ex;
pub mod economy;

pub use dep1ex::{load_dep1ex, LoadError};
pub use economy::{Economy, ExtraArray, SchemaError};
