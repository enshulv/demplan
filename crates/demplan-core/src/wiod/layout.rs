//! Where the parts of a WIOT sit on its sheet.

use super::grid::Grid;
use super::WiodError;

/// Header row holding each column's code.
const CODE_ROW: usize = 2;
/// Header row holding each column's economy.
const REGION_ROW: usize = 4;
/// First row of the product block.
const FIRST_PRODUCT_ROW: usize = 6;
/// First column of the value blocks; columns before it hold row labels.
const FIRST_VALUE_COLUMN: usize = 4;
/// Column of a row's industry or totals code.
const ROW_CODE_COLUMN: usize = 0;
/// Column of a product row's economy.
const ROW_REGION_COLUMN: usize = 2;

/// The final-demand codes, in the order each economy's five columns follow.
pub(crate) const FINAL_DEMAND_CODES: [&str; 5] = ["CONS_h", "CONS_np", "CONS_g", "GFCF", "INVEN"];

/// Code of the gross-output column.
const GROSS_OUTPUT_CODE: &str = "GO";

/// Codes of the totals rows read per producing unit, with the `unit_extra` key
/// each is stored under.
pub(crate) const TOTALS_ROWS: [(&str, &str); 6] = [
    ("TXSP", "taxes_less_subsidies"),
    ("EXP_adj", "cif_fob_adjustment"),
    ("PURR", "purchases_by_residents_abroad"),
    ("PURNR", "purchases_by_nonresidents"),
    ("VA", "value_added"),
    ("IntTTM", "international_transport_margins"),
];

/// One product: an industry of an economy.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct Product {
    pub(crate) region: String,
    pub(crate) industry: String,
}

/// One final-demand column.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct FinalDemandColumn {
    pub(crate) region: String,
    pub(crate) code: String,
    pub(crate) column: usize,
}

/// The positions of a WIOT's parts on its sheet, checked against each other.
///
/// Product `i` sits in row `FIRST_PRODUCT_ROW + i` and in column
/// `FIRST_VALUE_COLUMN + i`: the intermediate-use block is square.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct Layout {
    /// Every product, in row order.
    pub(crate) products: Vec<Product>,
    /// Every economy, in the order its first product appears.
    pub(crate) economies: Vec<String>,
    /// Every final-demand column, in column order.
    pub(crate) final_demand: Vec<FinalDemandColumn>,
    pub(crate) gross_output_column: usize,
    /// Row of each entry of `TOTALS_ROWS`.
    pub(crate) totals_rows: Vec<usize>,
}

impl Layout {
    pub(crate) fn n_products(&self) -> usize {
        self.products.len()
    }

    pub(crate) fn product_column(&self, product: usize) -> usize {
        FIRST_VALUE_COLUMN + product
    }

    /// Rows `[start, end)` of the product block.
    pub(crate) fn product_rows(&self) -> (usize, usize) {
        (FIRST_PRODUCT_ROW, FIRST_PRODUCT_ROW + self.n_products())
    }
}

/// Locates the products, final-demand columns and totals rows of a WIOT sheet,
/// and checks that every cell the mapping reads holds a number.
///
/// The header is read left to right from the first value column: product
/// columns until the first final-demand code, then the final-demand columns,
/// then the gross-output column. Each product row must carry the industry and
/// economy of the column with the same index, and the final-demand columns must
/// come as five per economy, in the economies' order and in the order of
/// `FINAL_DEMAND_CODES`. Columns after the gross-output column are not read.
pub(crate) fn parse_layout(grid: &Grid) -> Result<Layout, WiodError> {
    let products = read_product_columns(grid)?;
    let n_products = products.len();
    check_product_rows(grid, &products)?;
    let economies = economies_of(&products);
    let final_demand =
        read_final_demand_columns(grid, FIRST_VALUE_COLUMN + n_products, &economies)?;
    let gross_output_column = FIRST_VALUE_COLUMN + n_products + final_demand.len();
    let totals_rows = find_totals_rows(grid, FIRST_PRODUCT_ROW + n_products)?;

    let layout = Layout {
        products,
        economies,
        final_demand,
        gross_output_column,
        totals_rows,
    };
    check_numbers(grid, &layout)?;
    Ok(layout)
}

fn header_error(grid: &Grid, row: usize, column: usize, expected: String) -> WiodError {
    WiodError::Header {
        row,
        column,
        expected,
        found: grid.describe(row, column),
    }
}

/// Reads the product columns: every column from the first value column whose
/// code is neither a final-demand code nor the gross-output code.
fn read_product_columns(grid: &Grid) -> Result<Vec<Product>, WiodError> {
    let mut products = Vec::new();
    let mut column = FIRST_VALUE_COLUMN;
    loop {
        let Some(code) = grid.text(CODE_ROW, column) else {
            return Err(header_error(
                grid,
                CODE_ROW,
                column,
                "an industry, final-demand or gross-output code".to_string(),
            ));
        };
        if code == GROSS_OUTPUT_CODE || FINAL_DEMAND_CODES.contains(&code) {
            break;
        }
        let Some(region) = grid.text(REGION_ROW, column) else {
            return Err(header_error(
                grid,
                REGION_ROW,
                column,
                format!("the economy of industry column {code}"),
            ));
        };
        products.push(Product {
            region: region.to_string(),
            industry: code.to_string(),
        });
        column += 1;
    }
    if products.is_empty() {
        return Err(header_error(
            grid,
            CODE_ROW,
            FIRST_VALUE_COLUMN,
            "an industry code".to_string(),
        ));
    }
    Ok(products)
}

/// Checks that product row `i` carries the industry and economy of product column `i`.
fn check_product_rows(grid: &Grid, products: &[Product]) -> Result<(), WiodError> {
    for (index, product) in products.iter().enumerate() {
        let row = FIRST_PRODUCT_ROW + index;
        if grid.text(row, ROW_CODE_COLUMN) != Some(product.industry.as_str()) {
            return Err(header_error(
                grid,
                row,
                ROW_CODE_COLUMN,
                format!(
                    "the industry code {} of column {}",
                    product.industry,
                    FIRST_VALUE_COLUMN + index
                ),
            ));
        }
        if grid.text(row, ROW_REGION_COLUMN) != Some(product.region.as_str()) {
            return Err(header_error(
                grid,
                row,
                ROW_REGION_COLUMN,
                format!(
                    "the economy {} of column {}",
                    product.region,
                    FIRST_VALUE_COLUMN + index
                ),
            ));
        }
    }
    Ok(())
}

/// Lists the economies in the order their first product appears.
fn economies_of(products: &[Product]) -> Vec<String> {
    let mut economies: Vec<String> = Vec::new();
    for product in products {
        if !economies.contains(&product.region) {
            economies.push(product.region.clone());
        }
    }
    economies
}

/// Reads the final-demand columns from `first`, five per economy, and checks
/// that the gross-output column follows them.
fn read_final_demand_columns(
    grid: &Grid,
    first: usize,
    economies: &[String],
) -> Result<Vec<FinalDemandColumn>, WiodError> {
    let mut columns = Vec::with_capacity(economies.len() * FINAL_DEMAND_CODES.len());
    for (group, region) in economies.iter().enumerate() {
        for (offset, code) in FINAL_DEMAND_CODES.iter().enumerate() {
            let column = first + group * FINAL_DEMAND_CODES.len() + offset;
            if grid.text(CODE_ROW, column) != Some(*code) {
                return Err(header_error(
                    grid,
                    CODE_ROW,
                    column,
                    format!("the final-demand code {code} of {region}"),
                ));
            }
            if grid.text(REGION_ROW, column) != Some(region.as_str()) {
                return Err(header_error(
                    grid,
                    REGION_ROW,
                    column,
                    format!("the economy {region} of final-demand column {code}"),
                ));
            }
            columns.push(FinalDemandColumn {
                region: region.clone(),
                code: (*code).to_string(),
                column,
            });
        }
    }
    let gross_output = first + columns.len();
    if grid.text(CODE_ROW, gross_output) != Some(GROSS_OUTPUT_CODE) {
        return Err(header_error(
            grid,
            CODE_ROW,
            gross_output,
            format!("the gross-output code {GROSS_OUTPUT_CODE} after the final-demand columns"),
        ));
    }
    Ok(columns)
}

/// Finds each totals row below the product block; each code must appear once.
fn find_totals_rows(grid: &Grid, first: usize) -> Result<Vec<usize>, WiodError> {
    TOTALS_ROWS
        .iter()
        .map(|(code, _)| {
            let rows: Vec<usize> = (first..grid.n_rows())
                .filter(|&row| grid.text(row, ROW_CODE_COLUMN) == Some(*code))
                .collect();
            match rows.as_slice() {
                [row] => Ok(*row),
                _ => Err(WiodError::TotalsRow {
                    code,
                    count: rows.len(),
                }),
            }
        })
        .collect()
}

/// Checks that every cell the mapping reads holds a number: the product rows
/// across the product, final-demand and gross-output columns, and the totals
/// rows across the product columns.
fn check_numbers(grid: &Grid, layout: &Layout) -> Result<(), WiodError> {
    let (start, end) = layout.product_rows();
    let n_products = layout.n_products();
    let blocks = [
        (
            "intermediate use",
            FIRST_VALUE_COLUMN,
            FIRST_VALUE_COLUMN + n_products,
        ),
        (
            "final demand",
            FIRST_VALUE_COLUMN + n_products,
            layout.gross_output_column,
        ),
        (
            "gross output",
            layout.gross_output_column,
            layout.gross_output_column + 1,
        ),
    ];
    for (what, first_column, end_column) in blocks {
        for column in first_column..end_column {
            if let Some(row) = grid.first_non_number(column, start, end) {
                return Err(not_a_number(grid, row, column, what));
            }
        }
    }
    for (&row, (code, _)) in layout.totals_rows.iter().zip(TOTALS_ROWS.iter()) {
        for product in 0..n_products {
            let column = layout.product_column(product);
            if grid.number(row, column).is_none() {
                return Err(not_a_number(grid, row, column, &format!("the {code} row")));
            }
        }
    }
    Ok(())
}

fn not_a_number(grid: &Grid, row: usize, column: usize, what: &str) -> WiodError {
    WiodError::NotANumber {
        row,
        column,
        what: what.to_string(),
        found: grid.describe(row, column),
    }
}
