//! Labour figures per product from the socio-economic accounts.

use std::collections::HashMap;

use super::grid::Grid;
use super::WiodError;

/// Sheet of the socio-economic accounts workbook that holds the figures.
pub(crate) const SEA_SHEET: &str = "DATA";
/// Sheet of the exchange-rate workbook that holds the rates.
pub(crate) const EXCHANGE_RATE_SHEET: &str = "EXR";

/// Which labour variable of the socio-economic accounts is read.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum LaborMeasure {
    /// `COMP`, compensation of employees, converted to millions of US$.
    Compensation,
    /// `H_EMPE`, millions of hours worked by employees.
    Hours,
}

/// The labour figure of each product that has one, keyed by economy and
/// industry code.
///
/// A product without an entry has no labour figure: its economy is absent from
/// the accounts, its cell is not a number, or, for compensation, its economy has
/// no exchange rate for the year.
#[derive(Debug, Clone, Default, PartialEq)]
pub(crate) struct LaborFigures {
    figures: HashMap<(String, String), f64>,
}

impl LaborFigures {
    /// Records the labour figure of one product.
    pub(crate) fn insert(&mut self, region: &str, industry: &str, value: f64) {
        self.figures
            .insert((region.to_string(), industry.to_string()), value);
    }

    /// Returns the labour figure of one product, or `None` when it has none.
    pub(crate) fn figure(&self, region: &str, industry: &str) -> Option<f64> {
        self.figures
            .get(&(region.to_string(), industry.to_string()))
            .copied()
    }
}

impl LaborMeasure {
    /// Code of the variable in the accounts' `variable` column.
    fn variable(self) -> &'static str {
        match self {
            LaborMeasure::Compensation => "COMP",
            LaborMeasure::Hours => "H_EMPE",
        }
    }
}

/// Row of the accounts sheet that names its columns.
const SEA_HEADER_ROW: usize = 0;
const SEA_REGION_COLUMN: &str = "country";
const SEA_VARIABLE_COLUMN: &str = "variable";
const SEA_INDUSTRY_COLUMN: &str = "code";

/// Header cell of the exchange-rate sheet's economy code column; the row holding
/// it names the year columns too.
const EXCHANGE_RATE_CODE_COLUMN: &str = "Acronym";

/// Exchange-rate codes that differ from the table's economy codes, with the
/// table code each stands for. The exchange-rate workbook lists Romania as `ROM`;
/// the table and the accounts code it `ROU`. Every other code is used as written.
const EXCHANGE_RATE_CODE_ALIASES: [(&str, &str); 1] = [("ROM", "ROU")];

/// Reads the labour figures of `year` from the socio-economic accounts sheet.
///
/// The accounts sheet has one row per economy, variable and industry, and one
/// column per year; its first row names the columns (`country`, `variable`,
/// `code`, and each year as a number or as text). Only rows of the measure's
/// variable are read. A cell that is not a number is a gap, not an error.
///
/// For compensation, each figure is multiplied by the economy's rate for `year`
/// from `exchange_rates` (US$ per unit of national currency). An economy with no
/// rate, or whose rate is not a number, has no figures; so has every economy
/// when `exchange_rates` is `None`.
pub(crate) fn labor_figures(
    sea: &Grid,
    exchange_rates: Option<&Grid>,
    year: i32,
    measure: LaborMeasure,
) -> Result<LaborFigures, WiodError> {
    let rates = match (measure, exchange_rates) {
        (LaborMeasure::Compensation, Some(sheet)) => Some(read_exchange_rates(sheet, year)?),
        (LaborMeasure::Compensation, None) => Some(HashMap::new()),
        (LaborMeasure::Hours, _) => None,
    };

    let region_column = sea_column(sea, SEA_REGION_COLUMN)?;
    let variable_column = sea_column(sea, SEA_VARIABLE_COLUMN)?;
    let industry_column = sea_column(sea, SEA_INDUSTRY_COLUMN)?;
    let year_column = (0..sea.n_columns())
        .find(|&column| names_year(sea, SEA_HEADER_ROW, column, year))
        .ok_or_else(|| WiodError::LaborHeader {
            sheet: SEA_SHEET,
            column: year.to_string(),
        })?;

    let variable = measure.variable();
    let mut seen = HashMap::new();
    let mut figures = LaborFigures::default();
    for row in SEA_HEADER_ROW + 1..sea.n_rows() {
        if sea.text(row, variable_column) != Some(variable) {
            continue;
        }
        let (Some(region), Some(industry)) =
            (sea.text(row, region_column), sea.text(row, industry_column))
        else {
            continue;
        };
        if seen.insert((region, industry), row).is_some() {
            return Err(WiodError::DuplicateLaborFigure {
                region: region.to_string(),
                variable,
                industry: industry.to_string(),
            });
        }

        let Some(value) = sea.number(row, year_column) else {
            continue;
        };
        let figure = match &rates {
            None => Some(value),
            Some(rates) => rates
                .get(region)
                .copied()
                .flatten()
                .map(|rate| value * rate),
        };
        if let Some(figure) = figure {
            figures.insert(region, industry, figure);
        }
    }
    Ok(figures)
}

/// Finds the accounts column whose header cell is `name`.
fn sea_column(sea: &Grid, name: &str) -> Result<usize, WiodError> {
    (0..sea.n_columns())
        .find(|&column| sea.text(SEA_HEADER_ROW, column) == Some(name))
        .ok_or_else(|| WiodError::LaborHeader {
            sheet: SEA_SHEET,
            column: name.to_string(),
        })
}

/// Reports whether a header cell names `year`, as a number or as text.
fn names_year(grid: &Grid, row: usize, column: usize, year: i32) -> bool {
    if let Some(value) = grid.number(row, column) {
        return value == f64::from(year);
    }
    grid.text(row, column).map(str::trim) == Some(year.to_string().as_str())
}

/// The table's economy code for an exchange-rate code.
fn table_code(code: &str) -> &str {
    EXCHANGE_RATE_CODE_ALIASES
        .iter()
        .find(|(listed, _)| *listed == code)
        .map_or(code, |(_, table)| table)
}

/// Reads each economy's rate for `year`: `Some(rate)` when the cell is a number,
/// `None` when it is not.
///
/// The header row is the row holding `Acronym`; the year column is headed
/// `_{year}` in that row. Rates are keyed by the table's economy code, through
/// `EXCHANGE_RATE_CODE_ALIASES`. Two rows that name the same economy, under the
/// same code or under a code and its alias, are refused: nothing says which of
/// the two rates applies.
fn read_exchange_rates(sheet: &Grid, year: i32) -> Result<HashMap<String, Option<f64>>, WiodError> {
    let missing = |column: String| WiodError::LaborHeader {
        sheet: EXCHANGE_RATE_SHEET,
        column,
    };
    let (header_row, code_column) = (0..sheet.n_rows())
        .flat_map(|row| (0..sheet.n_columns()).map(move |column| (row, column)))
        .find(|&(row, column)| sheet.text(row, column) == Some(EXCHANGE_RATE_CODE_COLUMN))
        .ok_or_else(|| missing(EXCHANGE_RATE_CODE_COLUMN.to_string()))?;
    let year_header = format!("_{year}");
    let year_column = (0..sheet.n_columns())
        .find(|&column| sheet.text(header_row, column) == Some(year_header.as_str()))
        .ok_or_else(|| missing(year_header.clone()))?;

    let mut rates = HashMap::new();
    let mut listed_as: HashMap<&str, &str> = HashMap::new();
    for row in header_row + 1..sheet.n_rows() {
        let Some(code) = sheet.text(row, code_column) else {
            continue;
        };
        let economy = table_code(code);
        if let Some(first) = listed_as.insert(economy, code) {
            return Err(WiodError::DuplicateExchangeRate {
                code: economy.to_string(),
                first: first.to_string(),
                second: code.to_string(),
            });
        }
        rates.insert(economy.to_string(), sheet.number(row, year_column));
    }
    Ok(rates)
}
