//! Core data model and loaders for cyberstride.
//!
//! [`Economy`] is the state of an economy in one period, stored as three
//! columnar tables. [`load_dep1ex`] builds one from a dep1ex scenario file.

#![deny(missing_docs)]

pub mod dep1ex;
pub mod economy;

pub use dep1ex::{load_dep1ex, LoadError};
pub use economy::{
    Economy, ExtraArray, SchemaError, COMMODITY_KIND_INTERMEDIATE, COMMODITY_KIND_LABOR,
    COMMODITY_KIND_NATURE, COMMODITY_KIND_PRIVATE, COMMODITY_KIND_PUBLIC,
    TECHNOLOGY_KIND_COBB_DOUGLAS, TECHNOLOGY_KIND_LEONTIEF,
};
