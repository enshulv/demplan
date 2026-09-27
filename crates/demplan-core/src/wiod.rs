//! Loading one year of the World Input-Output Database (WIOD), 2016 release.
//!
//! The release ships one world input-output table (WIOT) per year from 2000 to
//! 2014, each an `.xlsb` workbook named `WIOT{year}_Nov16_ROW.xlsb` with one
//! sheet named after the year, bundled in `WIOTS_in_EXCEL.zip`. The loader reads
//! one table, either from the release zip (in memory, nothing is extracted to
//! disk) or from one extracted workbook, and returns the economy it describes
//! together with the flows the table records for that year.
//!
//! # Table layout
//!
//! Row 2 holds the column codes (industry codes, then the five final-demand
//! codes per economy, then `GO`), row 4 the economy of each column. From row 6
//! on, one row per product (economy × industry) carries its industry code in
//! column 0 and its economy in column 2; its intermediate use `Z` sits in the
//! product columns and its final use in the final-demand columns. Below the
//! product rows, rows whose column 0 holds `TXSP`, `EXP_adj`, `PURR`, `PURNR`,
//! `VA` and `IntTTM` carry per-column totals. Values are millions of US$ at
//! current prices.
//!
//! # Economy built from one table
//!
//! - Commodities: every product in row order, then, when a labour measure is
//!   chosen, one labour commodity per economy for which at least one producing
//!   unit has a labour figure, in the table's economy order.
//! - Producing units: one per product whose gross output `GO` is positive, in
//!   row order, each a Leontief unit making its own product. A product with no
//!   output keeps its commodity but gets no unit.
//! - Inputs of the unit making product `j`: every product `i` with `Z[i][j] > 0`
//!   at coefficient `Z[i][j] / GO[j]`, then its economy's labour commodity at
//!   coefficient `labour[j] / GO[j]` when the unit has a non-zero labour figure.
//!   A negative `Z` entry is refused.
//! - Consumer units: one per final-demand column.
//!
//! The observed flows record `GO` per unit, `Z` and the labour figures per input
//! entry, and final demand per consumer unit and product, negative values kept.

mod files;
mod grid;
mod labor;
mod layout;
mod mapping;

#[cfg(test)]
mod tests;

use std::path::{Path, PathBuf};

use crate::economy::{Economy, SchemaError};

use labor::LaborMeasure;

/// First year the 2016 release covers.
pub const FIRST_YEAR: i32 = 2000;
/// Last year the 2016 release covers.
pub const LAST_YEAR: i32 = 2014;

/// Which labour figure, if any, the loaded economy carries.
///
/// The WIOT has no labour data of its own; labour comes from the release's
/// socio-economic accounts (`Socio_Economic_Accounts.xlsx`).
#[derive(Debug, Clone, PartialEq)]
pub enum Labor {
    /// No labour commodity.
    None,
    /// Compensation of employees (`COMP`), converted from millions of national
    /// currency to millions of US$ with the year's rate from the exchange-rate
    /// workbook (`Exchange_Rates.xlsx`, sheet `EXR`).
    Compensation {
        /// The socio-economic accounts workbook.
        sea: PathBuf,
        /// The exchange-rate workbook.
        exchange_rates: PathBuf,
    },
    /// Hours worked by employees (`H_EMPE`), millions of hours.
    Hours {
        /// The socio-economic accounts workbook.
        sea: PathBuf,
    },
}

/// One year of the WIOT: the economy it describes and the flows it records.
#[derive(Debug, Clone, PartialEq)]
pub struct WiodTable {
    /// The economy built from the table.
    pub economy: Economy,
    /// The flows the table records for the year, shaped as a plan of `economy`.
    pub observed: ObservedFlows,
}

/// The year's recorded flows, laid out like the physical layer of a plan.
#[derive(Debug, Clone, PartialEq)]
pub struct ObservedFlows {
    /// Gross output of each producing unit, one per output entry.
    pub output: Vec<f64>,
    /// Quantity used by each input entry: `Z` for products, the labour figure for
    /// labour.
    pub input_use: Vec<f64>,
    /// Final demand, row-major, one row per consumer unit and one column per
    /// entry of `consumption_commodity`.
    pub consumption: Vec<f64>,
    /// Commodity of each consumption column: every product, in row order.
    pub consumption_commodity: Vec<i64>,
    /// Use in common per commodity; zero everywhere, because the table files all
    /// final use under a final-demand category.
    pub shared_use: Vec<f64>,
}

/// A WIOD file that cannot be turned into an economy.
#[derive(Debug, thiserror::Error)]
pub enum WiodError {
    /// The requested year is not in the release.
    #[error(
        "year {year} is not in the WIOD 2016 release, which covers {FIRST_YEAR} to {LAST_YEAR}"
    )]
    YearOutOfRange {
        /// Year requested.
        year: i32,
    },

    /// A file cannot be opened or read.
    #[error("cannot read `{path}`: {source}")]
    Open {
        /// Path that was tried.
        path: String,
        /// Underlying failure.
        source: std::io::Error,
    },

    /// A file is not a readable zip archive, which every `.zip`, `.xlsb` and
    /// `.xlsx` file is.
    #[error("`{path}` is not a readable zip archive: {message}")]
    Archive {
        /// Path that was tried.
        path: String,
        /// What the zip reader reported.
        message: String,
    },

    /// A zip archive is neither the release zip holding the year's table nor
    /// an `.xlsb` workbook.
    #[error(
        "`{path}` holds neither `{entry}` (the table for {year} in the release zip) \
         nor an .xlsb workbook"
    )]
    NotAWiotFile {
        /// Path that was tried.
        path: String,
        /// Year requested.
        year: i32,
        /// Name of the release zip entry that was looked for.
        entry: String,
    },

    /// A workbook cannot be parsed.
    #[error("cannot read the workbook `{path}`: {message}")]
    Workbook {
        /// Path of the workbook.
        path: String,
        /// What the workbook reader reported.
        message: String,
    },

    /// The WIOT workbook has no sheet named after the requested year.
    #[error("the table for {year} is on a sheet named `{year}`, but the workbook has the sheets {sheets:?}")]
    SheetNotFound {
        /// Year requested.
        year: i32,
        /// Sheet names the workbook has.
        sheets: Vec<String>,
    },

    /// A workbook lacks a sheet the loader reads.
    #[error("the workbook `{path}` has no sheet `{sheet}`")]
    MissingSheet {
        /// Path of the workbook.
        path: String,
        /// Sheet looked for.
        sheet: &'static str,
    },

    /// A cell lies outside the dimensions the sheet declares.
    #[error(
        "cell ({row}, {column}) lies outside the {n_rows} × {n_columns} cells the sheet declares"
    )]
    CellOutsideSheet {
        /// Row of the cell.
        row: usize,
        /// Column of the cell.
        column: usize,
        /// Rows the sheet declares.
        n_rows: usize,
        /// Columns the sheet declares.
        n_columns: usize,
    },

    /// A header cell does not hold what the table layout requires.
    #[error("WIOT cell ({row}, {column}): expected {expected}, found {found}")]
    Header {
        /// Row of the cell.
        row: usize,
        /// Column of the cell.
        column: usize,
        /// What the layout requires there.
        expected: String,
        /// What the cell holds, as text.
        found: String,
    },

    /// A row that carries per-column totals is absent or appears more than once.
    #[error(
        "the WIOT has {count} rows coded `{code}` below the product rows, expected exactly one"
    )]
    TotalsRow {
        /// Code in column 0 of the row.
        code: &'static str,
        /// Rows found with that code.
        count: usize,
    },

    /// A value cell does not hold a number.
    #[error("WIOT cell ({row}, {column}) in {what} holds {found}, expected a number")]
    NotANumber {
        /// Row of the cell.
        row: usize,
        /// Column of the cell.
        column: usize,
        /// Which block of the table the cell belongs to.
        what: String,
        /// What the cell holds, as text.
        found: String,
    },

    /// A product without positive output has intermediate inputs recorded.
    ///
    /// Such a product gets no producing unit, so its inputs would be lost.
    #[error(
        "product {region} {industry} has gross output {output} but records intermediate \
         inputs; a product without positive output gets no producing unit, so they \
         would be dropped"
    )]
    InputsWithoutOutput {
        /// Economy of the product.
        region: String,
        /// Industry of the product.
        industry: String,
        /// Its gross output.
        output: f64,
    },

    /// An intermediate-use entry is negative.
    ///
    /// The loader records intermediate use as input entries with positive
    /// coefficients; a negative entry has no such form, and leaving it out would
    /// break the balance of its product row.
    #[error(
        "the WIOT for {year} records intermediate use {value} of {row_region} {row_industry} \
         by {column_region} {column_industry}; negative intermediate use is not supported"
    )]
    NegativeIntermediateUse {
        /// Year of the table.
        year: i32,
        /// Economy of the product used (the row).
        row_region: String,
        /// Industry of the product used (the row).
        row_industry: String,
        /// Economy of the using industry (the column).
        column_region: String,
        /// Industry of the using industry (the column).
        column_industry: String,
        /// Value found.
        value: f64,
    },

    /// The socio-economic accounts or the exchange-rate workbook lacks a column
    /// the loader reads.
    #[error("the sheet `{sheet}` has no `{column}` column in its header")]
    LaborHeader {
        /// Sheet searched.
        sheet: &'static str,
        /// Column looked for.
        column: String,
    },

    /// The socio-economic accounts list one figure twice.
    #[error("the socio-economic accounts list {variable} for {region} {industry} more than once")]
    DuplicateLaborFigure {
        /// Economy of the row.
        region: String,
        /// Variable of the row.
        variable: &'static str,
        /// Industry of the row.
        industry: String,
    },

    /// The assembled economy breaches the data model.
    #[error("the loaded economy breaches the data model: {0}")]
    Schema(#[from] SchemaError),
}

/// Reads one year of the WIOT and returns the economy and the recorded flows.
///
/// `path` is either the release zip `WIOTS_in_EXCEL.zip`, from which the entry
/// `WIOT{year}_Nov16_ROW.xlsb` is read into memory, or one `.xlsb` workbook. The
/// workbook must have a sheet named after `year`. `labor` selects the labour
/// figure, if any, and names the workbooks it comes from.
///
/// The year is checked before any file is opened. The returned economy is in
/// period `year` and has passed [`Economy::validate`]; the layout rules are in
/// the module documentation.
pub fn load_wiod(path: impl AsRef<Path>, year: i32, labor: &Labor) -> Result<WiodTable, WiodError> {
    files::require_release_year(year)?;
    let figures = match labor {
        Labor::None => None,
        Labor::Compensation {
            sea,
            exchange_rates,
        } => {
            let sea = files::read_workbook_sheet(sea, labor::SEA_SHEET)?;
            let rates = files::read_workbook_sheet(exchange_rates, labor::EXCHANGE_RATE_SHEET)?;
            Some(labor::labor_figures(
                &sea,
                Some(&rates),
                year,
                LaborMeasure::Compensation,
            )?)
        }
        Labor::Hours { sea } => {
            let sea = files::read_workbook_sheet(sea, labor::SEA_SHEET)?;
            Some(labor::labor_figures(&sea, None, year, LaborMeasure::Hours)?)
        }
    };
    let grid = files::read_wiot_grid(path.as_ref(), year)?;
    let table = mapping::table_from_grid(&grid, year, figures.as_ref())?;
    table.economy.validate()?;
    Ok(table)
}
