//! Mapping a WIOT sheet to an economy, on small hand-built sheets.
//!
//! The standard sheet has two economies, `AAA` and `ROW`, and three industries,
//! `A01`, `C10-C12` and `U`, laid out like the release: header rows 0–5, one row
//! per product from row 6, the totals rows below, labels in columns 0–3, then the
//! intermediate-use block, the final-demand block and the gross-output column.
//!
//! Products, in row order: 0 AAA A01, 1 AAA C10-C12, 2 AAA U, 3 ROW A01,
//! 4 ROW C10-C12, 5 ROW U. Products 2 and 5 have no output and an all-zero
//! intermediate-use column, so the producing units make products 0, 1, 3 and 4.

use std::collections::BTreeMap;

use super::files::{release_entry_name, require_release_year, year_sheet};
use super::grid::Grid;
use super::labor::{labor_figures, LaborFigures, LaborMeasure};
use super::mapping::table_from_grid;
use super::{load_wiod, Labor, WiodError, WiodTable};
use crate::economy::ExtraArray;

const YEAR: i32 = 2014;

const HEADER_CODE_ROW: usize = 2;
const HEADER_REGION_ROW: usize = 4;
const FIRST_PRODUCT_ROW: usize = 6;
const FIRST_VALUE_COLUMN: usize = 4;

const FINAL_DEMAND: [&str; 5] = ["CONS_h", "CONS_np", "CONS_g", "GFCF", "INVEN"];

/// Codes of the totals rows the loader reads, with the `unit_extra` key each
/// lands under, in the order they appear on the sheet.
const TOTALS: [(&str, &str); 6] = [
    ("TXSP", "taxes_less_subsidies"),
    ("EXP_adj", "cif_fob_adjustment"),
    ("PURR", "purchases_by_residents_abroad"),
    ("PURNR", "purchases_by_nonresidents"),
    ("VA", "value_added"),
    ("IntTTM", "international_transport_margins"),
];

/// The products that get a producing unit on the standard sheet.
const UNIT_PRODUCTS: [usize; 4] = [0, 1, 3, 4];

/// A WIOT sheet described by its blocks.
struct Synthetic {
    economies: Vec<&'static str>,
    industries: Vec<&'static str>,
    /// `z[i][j]`: intermediate use of product `i` by the industry making product `j`.
    z: Vec<Vec<f64>>,
    /// `final_demand[i][c]`: final use of product `i` in final-demand column `c`.
    final_demand: Vec<Vec<f64>>,
    gross_output: Vec<f64>,
    /// `totals[k][j]`: the value of `TOTALS[k]` in product column `j`.
    totals: Vec<Vec<f64>>,
}

impl Synthetic {
    /// The standard sheet. Every row satisfies `Σ z + Σ final demand = gross output`.
    fn standard() -> Self {
        let z = vec![
            vec![10.0, 20.0, 0.0, 0.0, 5.0, 0.0],
            vec![0.0, 30.0, 0.0, 40.0, 0.0, 0.0],
            vec![0.0; 6],
            vec![3.0, 0.0, 0.0, 25.0, 1.0, 0.0],
            vec![0.0, 7.0, 0.0, 0.0, 2.0, 0.0],
            vec![0.0; 6],
        ];
        let final_demand = vec![
            vec![40.0, 5.0, 10.0, 15.0, -5.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            vec![100.0, 0.0, 20.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0],
            vec![0.0; 10],
            vec![0.0, 0.0, 0.0, 0.0, 0.0, 300.0, 1.0, 50.0, 30.0, -10.0],
            vec![20.0, 0.0, 0.0, 0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 1.0],
            vec![0.0; 10],
        ];
        let gross_output = vec![100.0, 200.0, 0.0, 400.0, 50.0, 0.0];
        // Distinct per row and column; one negative tax to show signs are kept.
        let mut totals: Vec<Vec<f64>> = (0..TOTALS.len())
            .map(|k| {
                (0..6)
                    .map(|j| (k as f64 + 1.0) * 1000.0 + j as f64 + 0.5)
                    .collect()
            })
            .collect();
        totals[0][1] = -2.5;
        Self {
            economies: vec!["AAA", "ROW"],
            industries: vec!["A01", "C10-C12", "U"],
            z,
            final_demand,
            gross_output,
            totals,
        }
    }

    /// Three economies, `AAA`, `BBB` and `CCC`, with one industry `A01` each. Every
    /// product has output and uses only itself; every row balances.
    fn three_economies() -> Self {
        let mut final_demand = vec![vec![0.0; 15]; 3];
        final_demand[0][0] = 90.0;
        final_demand[1][5] = 180.0;
        final_demand[2][10] = 270.0;
        Self {
            economies: vec!["AAA", "BBB", "CCC"],
            industries: vec!["A01"],
            z: vec![
                vec![10.0, 0.0, 0.0],
                vec![0.0, 20.0, 0.0],
                vec![0.0, 0.0, 30.0],
            ],
            final_demand,
            gross_output: vec![100.0, 200.0, 300.0],
            totals: vec![vec![1.0; 3]; TOTALS.len()],
        }
    }

    fn n_products(&self) -> usize {
        self.economies.len() * self.industries.len()
    }

    fn n_final_demand(&self) -> usize {
        self.economies.len() * FINAL_DEMAND.len()
    }

    fn product(&self, i: usize) -> (&'static str, &'static str) {
        let n_industries = self.industries.len();
        (
            self.economies[i / n_industries],
            self.industries[i % n_industries],
        )
    }

    fn product_row(i: usize) -> usize {
        FIRST_PRODUCT_ROW + i
    }

    fn product_column(j: usize) -> usize {
        FIRST_VALUE_COLUMN + j
    }

    fn final_demand_column(&self, c: usize) -> usize {
        FIRST_VALUE_COLUMN + self.n_products() + c
    }

    fn gross_output_column(&self) -> usize {
        FIRST_VALUE_COLUMN + self.n_products() + self.n_final_demand()
    }

    /// Row of `TOTALS[k]`; an `II_fob` row sits between the products and the totals.
    fn totals_row(&self, k: usize) -> usize {
        FIRST_PRODUCT_ROW + self.n_products() + 1 + k
    }

    fn grid(&self) -> Grid {
        let n = self.n_products();
        let n_rows = FIRST_PRODUCT_ROW + n + 1 + TOTALS.len() + 1;
        let n_columns = self.gross_output_column() + 1;
        let mut grid = Grid::new(n_rows, n_columns);
        grid.set_text(0, 0, "Intercountry Input-Output Table".into());
        grid.set_text(HEADER_CODE_ROW, 0, "(industry-by-industry)".into());

        for j in 0..n {
            let (region, industry) = self.product(j);
            let column = Self::product_column(j);
            grid.set_text(HEADER_CODE_ROW, column, industry.into());
            grid.set_text(3, column, format!("name of {industry}"));
            grid.set_text(HEADER_REGION_ROW, column, region.into());
            grid.set_text(5, column, format!("c{}", j % self.industries.len() + 1));
        }
        for c in 0..self.n_final_demand() {
            let column = self.final_demand_column(c);
            grid.set_text(HEADER_CODE_ROW, column, FINAL_DEMAND[c % 5].into());
            grid.set_text(HEADER_REGION_ROW, column, self.economies[c / 5].into());
        }
        let go = self.gross_output_column();
        grid.set_text(HEADER_CODE_ROW, go, "GO".into());
        grid.set_text(HEADER_REGION_ROW, go, "TOT".into());

        for i in 0..n {
            let (region, industry) = self.product(i);
            let row = Self::product_row(i);
            grid.set_text(row, 0, industry.into());
            grid.set_text(row, 1, format!("name of {industry}"));
            grid.set_text(row, 2, region.into());
            grid.set_text(row, 3, format!("r{}", i % self.industries.len() + 1));
            for j in 0..n {
                grid.set_number(row, Self::product_column(j), self.z[i][j]);
            }
            for c in 0..self.n_final_demand() {
                grid.set_number(row, self.final_demand_column(c), self.final_demand[i][c]);
            }
            grid.set_number(row, go, self.gross_output[i]);
        }

        let ii_fob = FIRST_PRODUCT_ROW + n;
        grid.set_text(ii_fob, 0, "II_fob".into());
        for j in 0..n {
            let column_total: f64 = (0..n).map(|i| self.z[i][j]).sum();
            grid.set_number(ii_fob, Self::product_column(j), column_total);
        }
        for (k, (code, _)) in TOTALS.iter().enumerate() {
            let row = self.totals_row(k);
            grid.set_text(row, 0, (*code).into());
            grid.set_text(row, 2, "TOT".into());
            for j in 0..n {
                grid.set_number(row, Self::product_column(j), self.totals[k][j]);
            }
        }
        let go_row = n_rows - 1;
        grid.set_text(go_row, 0, "GO".into());
        for j in 0..n {
            grid.set_number(go_row, Self::product_column(j), self.gross_output[j]);
        }
        grid
    }
}

fn load(grid: &Grid, labor: Option<&LaborFigures>) -> WiodTable {
    table_from_grid(grid, YEAR, labor).expect("the sheet should load")
}

fn error_of(grid: &Grid) -> WiodError {
    match table_from_grid(grid, YEAR, None) {
        Ok(_) => panic!("expected the sheet to be refused"),
        Err(error) => error,
    }
}

fn floats(bag: &BTreeMap<String, ExtraArray>, key: &str) -> Vec<f64> {
    match bag.get(key) {
        Some(ExtraArray::F64 { shape, data }) => {
            assert_eq!(
                shape,
                &vec![data.len()],
                "`{key}` should be one-dimensional"
            );
            data.clone()
        }
        other => panic!("`{key}` should be a float array, found {other:?}"),
    }
}

fn labels(bag: &BTreeMap<String, ExtraArray>, key: &str) -> Vec<String> {
    match bag.get(key) {
        Some(ExtraArray::Text { data }) => data.clone(),
        other => panic!("`{key}` should be a text array, found {other:?}"),
    }
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| value.to_string()).collect()
}

/// The labour figures of economy `AAA`: A01 8, C10-C12 12, and U 5 on the
/// product that gets no unit. `ROW` has none.
fn aaa_figures() -> LaborFigures {
    let mut figures = LaborFigures::default();
    figures.insert("AAA", "A01", 8.0);
    figures.insert("AAA", "C10-C12", 12.0);
    figures.insert("AAA", "U", 5.0);
    figures
}

// ---------------------------------------------------------------- products

#[test]
fn every_product_becomes_a_commodity_in_row_order() {
    let table = load(&Synthetic::standard().grid(), None);
    let economy = &table.economy;
    assert_eq!(economy.commodity_id, vec![0, 1, 2, 3, 4, 5]);
    assert_eq!(economy.endowment, vec![0.0; 6]);
    assert_eq!(
        labels(&economy.commodity_extra, "region"),
        strings(&["AAA", "AAA", "AAA", "ROW", "ROW", "ROW"])
    );
    assert_eq!(
        labels(&economy.commodity_extra, "industry"),
        strings(&["A01", "C10-C12", "U", "A01", "C10-C12", "U"])
    );
}

#[test]
fn the_economy_is_in_the_period_of_the_year() {
    let table = table_from_grid(&Synthetic::standard().grid(), 2003, None).unwrap();
    assert_eq!(table.economy.period, 2003);
}

// ---------------------------------------------------------------- producing units

#[test]
fn only_products_with_positive_output_get_a_unit() {
    let table = load(&Synthetic::standard().grid(), None);
    let economy = &table.economy;
    assert_eq!(economy.unit_id, vec![0, 1, 2, 3]);
    assert_eq!(economy.output_commodity, vec![0, 1, 3, 4]);
    assert_eq!(economy.output_offsets, vec![0, 1, 2, 3, 4]);
}

#[test]
fn a_product_with_negative_output_gets_no_unit() {
    let mut sheet = Synthetic::standard();
    sheet.gross_output[5] = -1.0;
    let table = load(&sheet.grid(), None);
    assert_eq!(table.economy.output_commodity, vec![0, 1, 3, 4]);
    assert_eq!(table.economy.n_commodities(), 6);
}

#[test]
fn every_unit_is_a_leontief_unit_making_its_own_product() {
    let table = load(&Synthetic::standard().grid(), None);
    let economy = &table.economy;
    assert_eq!(economy.technology_kind, strings(&["leontief"; 4]));
    assert_eq!(economy.technology_scale, vec![1.0; 4]);
    assert_eq!(economy.output_coefficient, vec![1.0; 4]);
}

#[test]
fn unit_labels_name_the_product() {
    let table = load(&Synthetic::standard().grid(), None);
    let extra = &table.economy.unit_extra;
    assert_eq!(
        labels(extra, "region"),
        strings(&["AAA", "AAA", "ROW", "ROW"])
    );
    assert_eq!(
        labels(extra, "industry"),
        strings(&["A01", "C10-C12", "A01", "C10-C12"])
    );
}

#[test]
fn unit_totals_come_from_the_rows_below_the_products_in_the_unit_column() {
    let sheet = Synthetic::standard();
    let table = load(&sheet.grid(), None);
    for (k, (_, key)) in TOTALS.iter().enumerate() {
        let expected: Vec<f64> = UNIT_PRODUCTS.iter().map(|&j| sheet.totals[k][j]).collect();
        assert_eq!(
            floats(&table.economy.unit_extra, key),
            expected,
            "unit_extra[{key}]"
        );
    }
    assert_eq!(
        floats(&table.economy.unit_extra, "taxes_less_subsidies")[1],
        -2.5
    );
}

#[test]
fn without_labour_the_unit_extra_bag_has_no_labour_flag() {
    let table = load(&Synthetic::standard().grid(), None);
    let mut keys: Vec<&str> = table
        .economy
        .unit_extra
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    let mut expected: Vec<&str> = TOTALS.iter().map(|(_, key)| *key).collect();
    expected.extend(["region", "industry", "unproduced_input_use"]);
    expected.sort_unstable();
    assert_eq!(keys, expected);
}

// ---------------------------------------------------------------- inputs

#[test]
fn inputs_are_the_positive_entries_of_the_unit_column_in_row_order() {
    let table = load(&Synthetic::standard().grid(), None);
    let economy = &table.economy;
    assert_eq!(economy.input_offsets, vec![0, 2, 5, 7, 10]);
    assert_eq!(economy.input_commodity, vec![0, 3, 0, 1, 4, 1, 3, 0, 3, 4]);
}

#[test]
fn input_coefficients_divide_intermediate_use_by_the_unit_output() {
    let table = load(&Synthetic::standard().grid(), None);
    let expected = vec![
        10.0 / 100.0,
        3.0 / 100.0,
        20.0 / 200.0,
        30.0 / 200.0,
        7.0 / 200.0,
        40.0 / 400.0,
        25.0 / 400.0,
        5.0 / 50.0,
        1.0 / 50.0,
        2.0 / 50.0,
    ];
    assert_eq!(table.economy.input_coefficient, expected);
}

#[test]
fn a_product_without_output_that_records_inputs_is_refused() {
    let mut sheet = Synthetic::standard();
    sheet.z[0][2] = 1.5;
    match error_of(&sheet.grid()) {
        WiodError::InputsWithoutOutput {
            region, industry, ..
        } => {
            assert_eq!((region.as_str(), industry.as_str()), ("AAA", "U"));
        }
        other => panic!("unexpected error {other:?}"),
    }
}

#[test]
fn a_product_without_output_that_records_an_input_below_the_first_row_is_refused() {
    let mut sheet = Synthetic::standard();
    // Product 3 (ROW A01) used by the industry making product 5 (ROW U), which has no output.
    sheet.z[3][5] = 1.5;
    match error_of(&sheet.grid()) {
        WiodError::InputsWithoutOutput {
            region, industry, ..
        } => {
            assert_eq!((region.as_str(), industry.as_str()), ("ROW", "U"));
        }
        other => panic!("unexpected error {other:?}"),
    }
}

// ---------------------------------------------------------------- products used but not produced

/// The standard sheet with products 2 (AAA U) and 5 (ROW U), which have no output,
/// used by units: product 2 by the units making products 0 and 3, product 5 by the
/// unit making product 3. Negative final demand keeps both rows at zero.
fn sheet_with_unproduced_inputs() -> Synthetic {
    let mut sheet = Synthetic::standard();
    sheet.z[2][0] = 4.0;
    sheet.z[2][3] = 6.0;
    sheet.z[5][3] = 1.0;
    sheet.final_demand[2][4] = -10.0;
    sheet.final_demand[5][9] = -1.0;
    sheet
}

#[test]
fn a_product_without_a_unit_is_not_an_input_of_the_units_that_use_it() {
    let table = load(&sheet_with_unproduced_inputs().grid(), None);
    let economy = &table.economy;
    assert_eq!(economy.input_offsets, vec![0, 2, 5, 7, 10]);
    assert_eq!(economy.input_commodity, vec![0, 3, 0, 1, 4, 1, 3, 0, 3, 4]);
    assert_eq!(
        table.observed.input_use,
        vec![10.0, 3.0, 20.0, 30.0, 7.0, 40.0, 25.0, 5.0, 1.0, 2.0]
    );
}

#[test]
fn each_unit_records_what_it_draws_from_products_without_a_unit() {
    let table = load(&sheet_with_unproduced_inputs().grid(), None);
    // Unit 0 makes product 0 and uses 4 of product 2; unit 2 makes product 3 and
    // uses 6 of product 2 and 1 of product 5.
    assert_eq!(
        floats(&table.economy.unit_extra, "unproduced_input_use"),
        vec![4.0, 0.0, 7.0, 0.0]
    );
}

#[test]
fn the_table_lists_each_product_without_a_unit_that_units_use_with_its_total() {
    let table = load(&sheet_with_unproduced_inputs().grid(), None);
    assert_eq!(table.unproduced_inputs.commodity, vec![2, 5]);
    assert_eq!(table.unproduced_inputs.used, vec![10.0, 1.0]);
}

#[test]
fn final_demand_on_a_product_without_a_unit_is_kept_as_recorded() {
    let sheet = sheet_with_unproduced_inputs();
    let table = load(&sheet.grid(), None);
    let n = sheet.n_products();
    assert_eq!(table.observed.consumption[4 * n + 2], -10.0);
    assert_eq!(table.observed.consumption[9 * n + 5], -1.0);
}

#[test]
fn without_products_used_but_not_produced_every_unit_records_zero() {
    let table = load(&Synthetic::standard().grid(), None);
    assert_eq!(
        floats(&table.economy.unit_extra, "unproduced_input_use"),
        vec![0.0; 4]
    );
    assert!(table.unproduced_inputs.commodity.is_empty());
    assert!(table.unproduced_inputs.used.is_empty());
}

#[test]
fn a_sheet_with_products_used_but_not_produced_passes_validation() {
    let table = load(&sheet_with_unproduced_inputs().grid(), None);
    table.economy.validate().unwrap();
}

// ---------------------------------------------------------------- observed flows

#[test]
fn observed_output_is_the_gross_output_of_each_unit() {
    let table = load(&Synthetic::standard().grid(), None);
    assert_eq!(table.observed.output, vec![100.0, 200.0, 400.0, 50.0]);
}

#[test]
fn observed_input_use_is_the_intermediate_use_of_each_entry() {
    let table = load(&Synthetic::standard().grid(), None);
    assert_eq!(
        table.observed.input_use,
        vec![10.0, 3.0, 20.0, 30.0, 7.0, 40.0, 25.0, 5.0, 1.0, 2.0]
    );
}

#[test]
fn observed_consumption_is_final_demand_per_column_and_product_with_signs_kept() {
    let sheet = Synthetic::standard();
    let table = load(&sheet.grid(), None);
    let n = sheet.n_products();
    let expected: Vec<f64> = (0..sheet.n_final_demand())
        .flat_map(|c| (0..n).map(move |i| (c, i)))
        .map(|(c, i)| sheet.final_demand[i][c])
        .collect();
    assert_eq!(table.observed.consumption, expected);
    // Inventory draw-downs: AAA's INVEN column holds -5 of product 0, ROW's -10 of product 3.
    assert_eq!(table.observed.consumption[4 * n], -5.0);
    assert_eq!(table.observed.consumption[9 * n + 3], -10.0);
    assert_eq!(table.observed.consumption_commodity, vec![0, 1, 2, 3, 4, 5]);
}

#[test]
fn observed_shared_use_is_zero_for_every_commodity() {
    let table = load(&Synthetic::standard().grid(), Some(&aaa_figures()));
    assert_eq!(table.observed.shared_use, vec![0.0; 7]);
}

// ---------------------------------------------------------------- consumer units

#[test]
fn one_consumer_unit_per_final_demand_column_in_column_order() {
    let table = load(&Synthetic::standard().grid(), None);
    let economy = &table.economy;
    assert_eq!(economy.consumer_id, (0..10).collect::<Vec<i64>>());
    assert_eq!(
        labels(&economy.consumer_extra, "region"),
        strings(&["AAA", "AAA", "AAA", "AAA", "AAA", "ROW", "ROW", "ROW", "ROW", "ROW"])
    );
    let mut codes = strings(&FINAL_DEMAND);
    codes.extend(strings(&FINAL_DEMAND));
    assert_eq!(labels(&economy.consumer_extra, "final_demand"), codes);
}

// ---------------------------------------------------------------- labour

#[test]
fn labour_commodities_follow_the_products_one_per_economy_with_labour_data() {
    let table = load(&Synthetic::standard().grid(), Some(&aaa_figures()));
    let economy = &table.economy;
    assert_eq!(economy.n_commodities(), 7);
    assert_eq!(labels(&economy.commodity_extra, "region")[6], "AAA");
    assert_eq!(labels(&economy.commodity_extra, "industry")[6], "labor");
}

#[test]
fn labour_endowment_is_the_economy_total_over_its_units() {
    let table = load(&Synthetic::standard().grid(), Some(&aaa_figures()));
    // A01 and C10-C12; U has a figure but no unit.
    assert_eq!(
        table.economy.endowment,
        vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 20.0]
    );
}

#[test]
fn a_labour_entry_follows_the_product_inputs_at_labour_over_output() {
    let table = load(&Synthetic::standard().grid(), Some(&aaa_figures()));
    let economy = &table.economy;
    assert_eq!(economy.input_offsets, vec![0, 3, 7, 9, 12]);
    assert_eq!(
        economy.input_commodity,
        vec![0, 3, 6, 0, 1, 4, 6, 1, 3, 0, 3, 4]
    );
    assert_eq!(economy.input_coefficient[2], 8.0 / 100.0);
    assert_eq!(economy.input_coefficient[6], 12.0 / 200.0);
    assert_eq!(table.observed.input_use[2], 8.0);
    assert_eq!(table.observed.input_use[6], 12.0);
}

#[test]
fn a_unit_without_a_labour_figure_is_flagged_and_gets_no_labour_entry() {
    let table = load(&Synthetic::standard().grid(), Some(&aaa_figures()));
    assert_eq!(
        floats(&table.economy.unit_extra, "labor_observed"),
        vec![1.0, 1.0, 0.0, 0.0]
    );
    // ROW's units keep their product inputs and nothing else.
    assert_eq!(&table.economy.input_commodity[7..], &[1, 3, 0, 3, 4]);
}

#[test]
fn a_labour_figure_of_zero_is_data_and_keeps_the_labour_commodity() {
    let mut figures = LaborFigures::default();
    figures.insert("AAA", "A01", 0.0);
    let table = load(&Synthetic::standard().grid(), Some(&figures));
    let economy = &table.economy;
    assert_eq!(
        floats(&economy.unit_extra, "labor_observed"),
        vec![1.0, 0.0, 0.0, 0.0]
    );
    assert_eq!(economy.n_commodities(), 7);
    assert_eq!(economy.endowment[6], 0.0);
    // The zero is not an input entry.
    assert_eq!(economy.input_offsets, vec![0, 2, 5, 7, 10]);
    assert!(!economy.input_commodity.contains(&6));
}

#[test]
fn an_economy_whose_only_figure_is_on_a_product_without_a_unit_gets_no_labour_commodity() {
    let mut figures = LaborFigures::default();
    figures.insert("AAA", "U", 5.0);
    let table = load(&Synthetic::standard().grid(), Some(&figures));
    assert_eq!(table.economy.n_commodities(), 6);
    assert_eq!(
        floats(&table.economy.unit_extra, "labor_observed"),
        vec![0.0; 4]
    );
}

#[test]
fn labour_commodities_are_in_the_economy_order_of_the_table() {
    let mut figures = LaborFigures::default();
    figures.insert("ROW", "A01", 3.0);
    figures.insert("AAA", "C10-C12", 4.0);
    let table = load(&Synthetic::standard().grid(), Some(&figures));
    let economy = &table.economy;
    assert_eq!(
        labels(&economy.commodity_extra, "region")[6..],
        strings(&["AAA", "ROW"])
    );
    assert_eq!(economy.endowment[6..], [4.0, 3.0]);
    // Unit 2 makes ROW A01 and uses ROW's labour, commodity 7.
    let window = economy.input_offsets[2] as usize..economy.input_offsets[3] as usize;
    assert_eq!(economy.input_commodity[window], [1, 3, 7]);
}

#[test]
fn labour_goes_to_the_unit_own_economy_when_an_earlier_economy_has_none() {
    // AAA has no figure, so BBB's labour is the first labour commodity (3) and
    // CCC's the second (4): an economy's position among the labour commodities
    // differs from its position in the table.
    let mut figures = LaborFigures::default();
    figures.insert("BBB", "A01", 7.0);
    figures.insert("CCC", "A01", 11.0);
    let table = load(&Synthetic::three_economies().grid(), Some(&figures));
    let economy = &table.economy;
    assert_eq!(
        labels(&economy.commodity_extra, "region")[3..],
        strings(&["BBB", "CCC"])
    );
    assert_eq!(economy.input_offsets, vec![0, 1, 3, 5]);
    assert_eq!(economy.input_commodity, vec![0, 1, 3, 2, 4]);
    assert_eq!(table.observed.input_use, vec![10.0, 20.0, 7.0, 30.0, 11.0]);
    assert_eq!(economy.endowment, vec![0.0, 0.0, 0.0, 7.0, 11.0]);
}

#[test]
fn labour_chosen_without_any_figure_flags_every_unit() {
    let table = load(
        &Synthetic::standard().grid(),
        Some(&LaborFigures::default()),
    );
    assert_eq!(table.economy.n_commodities(), 6);
    assert_eq!(
        floats(&table.economy.unit_extra, "labor_observed"),
        vec![0.0; 4]
    );
}

// ---------------------------------------------------------------- header parsing

#[test]
fn a_product_row_labelled_with_another_industry_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(Synthetic::product_row(1), 0, "C13-C15".into());
    assert!(matches!(
        error_of(&grid),
        WiodError::Header {
            row: 7,
            column: 0,
            ..
        }
    ));
}

#[test]
fn a_product_row_labelled_with_another_economy_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(Synthetic::product_row(4), 2, "AAA".into());
    assert!(matches!(
        error_of(&grid),
        WiodError::Header {
            row: 10,
            column: 2,
            ..
        }
    ));
}

#[test]
fn a_product_column_without_an_economy_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_number(HEADER_REGION_ROW, Synthetic::product_column(2), 7.0);
    assert!(matches!(
        error_of(&grid),
        WiodError::Header {
            row: HEADER_REGION_ROW,
            column: 6,
            ..
        }
    ));
}

#[test]
fn final_demand_codes_out_of_order_are_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(
        HEADER_CODE_ROW,
        sheet.final_demand_column(6),
        "CONS_g".into(),
    );
    grid.set_text(
        HEADER_CODE_ROW,
        sheet.final_demand_column(7),
        "CONS_np".into(),
    );
    assert!(matches!(
        error_of(&grid),
        WiodError::Header {
            row: HEADER_CODE_ROW,
            ..
        }
    ));
}

#[test]
fn a_final_demand_column_of_another_economy_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(
        HEADER_REGION_ROW,
        sheet.final_demand_column(5),
        "AAA".into(),
    );
    assert!(matches!(
        error_of(&grid),
        WiodError::Header {
            row: HEADER_REGION_ROW,
            ..
        }
    ));
}

#[test]
fn a_sheet_without_a_gross_output_column_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(HEADER_CODE_ROW, sheet.gross_output_column(), "TOTAL".into());
    assert!(matches!(
        error_of(&grid),
        WiodError::Header {
            row: HEADER_CODE_ROW,
            ..
        }
    ));
}

#[test]
fn a_missing_totals_row_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(sheet.totals_row(5), 0, "IntTTM_old".into());
    assert!(matches!(
        error_of(&grid),
        WiodError::TotalsRow {
            code: "IntTTM",
            count: 0
        }
    ));
}

#[test]
fn a_repeated_totals_row_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(FIRST_PRODUCT_ROW + sheet.n_products(), 0, "VA".into());
    assert!(matches!(
        error_of(&grid),
        WiodError::TotalsRow {
            code: "VA",
            count: 2
        }
    ));
}

#[test]
fn text_in_the_intermediate_use_block_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(
        Synthetic::product_row(2),
        Synthetic::product_column(1),
        "n/a".into(),
    );
    assert!(matches!(
        error_of(&grid),
        WiodError::NotANumber {
            row: 8,
            column: 5,
            ..
        }
    ));
}

#[test]
fn an_empty_final_demand_cell_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    let column = sheet.final_demand_column(3);
    grid.set_text(Synthetic::product_row(0), column, String::new());
    assert!(matches!(
        error_of(&grid),
        WiodError::NotANumber { row: 6, .. }
    ));
}

#[test]
fn text_in_the_gross_output_column_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(
        Synthetic::product_row(3),
        sheet.gross_output_column(),
        "-".into(),
    );
    assert!(matches!(
        error_of(&grid),
        WiodError::NotANumber { row: 9, .. }
    ));
}

#[test]
fn text_in_a_totals_row_is_refused() {
    let sheet = Synthetic::standard();
    let mut grid = sheet.grid();
    grid.set_text(
        sheet.totals_row(4),
        Synthetic::product_column(0),
        "n/a".into(),
    );
    assert!(matches!(
        error_of(&grid),
        WiodError::NotANumber { column: 4, .. }
    ));
}

#[test]
fn a_sheet_with_extra_columns_after_gross_output_still_loads() {
    let sheet = Synthetic::standard();
    let small = sheet.grid();
    let mut grid = Grid::new(small.n_rows(), small.n_columns() + 2);
    for row in 0..small.n_rows() {
        for column in 0..small.n_columns() {
            if let Some(text) = small.text(row, column) {
                grid.set_text(row, column, text.to_string());
            } else if let Some(value) = small.number(row, column) {
                grid.set_number(row, column, value);
            }
        }
    }
    assert_eq!(load(&grid, None), load(&small, None));
}

// ---------------------------------------------------------------- year and sheet

#[test]
fn years_outside_the_release_are_refused() {
    assert!(matches!(
        require_release_year(1999),
        Err(WiodError::YearOutOfRange { year: 1999 })
    ));
    assert!(matches!(
        require_release_year(2015),
        Err(WiodError::YearOutOfRange { year: 2015 })
    ));
    assert!(require_release_year(2000).is_ok());
    assert!(require_release_year(2014).is_ok());
}

#[test]
fn the_year_is_checked_before_any_file_is_opened() {
    let error = load_wiod("no/such/file.xlsb", 2015, &Labor::None).unwrap_err();
    assert!(matches!(error, WiodError::YearOutOfRange { year: 2015 }));
}

#[test]
fn a_missing_file_is_reported_with_its_path() {
    let error = load_wiod("no/such/file.xlsb", 2014, &Labor::None).unwrap_err();
    assert!(matches!(error, WiodError::Open { .. }));
    assert!(error.to_string().contains("no/such/file.xlsb"));
}

#[test]
fn the_release_zip_entry_is_named_after_the_year() {
    assert_eq!(release_entry_name(2003), "WIOT2003_Nov16_ROW.xlsb");
}

#[test]
fn the_sheet_must_be_named_after_the_year() {
    let sheets = strings(&["2013"]);
    match year_sheet(&sheets, 2014) {
        Err(WiodError::SheetNotFound { year, sheets }) => {
            assert_eq!(year, 2014);
            assert_eq!(sheets, strings(&["2013"]));
        }
        other => panic!("unexpected result {other:?}"),
    }
    let sheets = strings(&["Notes", "2014"]);
    assert_eq!(year_sheet(&sheets, 2014).unwrap(), "2014");
}

// ---------------------------------------------------------------- socio-economic accounts

enum Cell {
    Text(&'static str),
    Number(f64),
}

fn grid_of(rows: &[Vec<Cell>]) -> Grid {
    let n_columns = rows.iter().map(Vec::len).max().unwrap_or(0);
    let mut grid = Grid::new(rows.len(), n_columns);
    for (row, cells) in rows.iter().enumerate() {
        for (column, cell) in cells.iter().enumerate() {
            match cell {
                Cell::Text(text) => grid.set_text(row, column, text.to_string()),
                Cell::Number(value) => grid.set_number(row, column, *value),
            }
        }
    }
    grid
}

fn sea_row(
    region: &'static str,
    variable: &'static str,
    industry: &'static str,
    values: [Cell; 2],
) -> Vec<Cell> {
    let [first, second] = values;
    vec![
        Cell::Text(region),
        Cell::Text(variable),
        Cell::Text("description"),
        Cell::Text(industry),
        first,
        second,
    ]
}

/// Accounts for 2013 and 2014: `AAA` has compensation and hours, `BBB` has
/// compensation and hours that are not numbers.
fn sea_rows() -> Vec<Vec<Cell>> {
    use Cell::{Number as N, Text as T};
    vec![
        vec![
            T("country"),
            T("variable"),
            T("description"),
            T("code"),
            N(2013.0),
            N(2014.0),
        ],
        sea_row("AAA", "COMP", "A01", [N(1.0), N(10.0)]),
        sea_row("AAA", "COMP", "C10-C12", [N(2.0), T("NA")]),
        sea_row("AAA", "COMP", "U", [N(3.0), N(0.0)]),
        sea_row("AAA", "H_EMPE", "A01", [N(4.0), N(40.0)]),
        sea_row("AAA", "H_EMPE", "C10-C12", [N(5.0), N(50.0)]),
        sea_row("AAA", "EMP", "U", [N(9.0), N(90.0)]),
        sea_row("BBB", "COMP", "A01", [N(6.0), N(60.0)]),
        sea_row("BBB", "H_EMPE", "A01", [T("NA"), T("NA")]),
    ]
}

/// Rates for 2013 and 2014, with the header on row 3 as in the release; `BBB`
/// has no usable rate for 2014.
fn exchange_rate_rows() -> Vec<Vec<Cell>> {
    use Cell::{Number as N, Text as T};
    vec![
        vec![T("Exchange rates")],
        vec![T(" US$ per Unit of Local currency")],
        vec![],
        vec![T("Country"), T("Acronym"), T("_2013"), T("_2014")],
        vec![T("Aland"), T("AAA"), N(0.5), N(0.25)],
        vec![T("Bland"), T("BBB"), N(2.0), T("n/a")],
    ]
}

#[test]
fn hours_are_the_hours_worked_by_employees() {
    let figures = labor_figures(&grid_of(&sea_rows()), None, 2014, LaborMeasure::Hours).unwrap();
    assert_eq!(figures.figure("AAA", "A01"), Some(40.0));
    assert_eq!(figures.figure("AAA", "C10-C12"), Some(50.0));
    assert_eq!(figures.figure("AAA", "U"), None);
    assert_eq!(figures.figure("BBB", "A01"), None);
}

#[test]
fn compensation_is_converted_to_us_dollars_at_the_year_rate() {
    let rates = grid_of(&exchange_rate_rows());
    let sea = grid_of(&sea_rows());
    let figures = labor_figures(&sea, Some(&rates), 2014, LaborMeasure::Compensation).unwrap();
    assert_eq!(figures.figure("AAA", "A01"), Some(10.0 * 0.25));
    assert_eq!(figures.figure("AAA", "U"), Some(0.0));
    let figures = labor_figures(&sea, Some(&rates), 2013, LaborMeasure::Compensation).unwrap();
    assert_eq!(figures.figure("AAA", "A01"), Some(1.0 * 0.5));
    assert_eq!(figures.figure("BBB", "A01"), Some(6.0 * 2.0));
}

#[test]
fn a_cell_that_is_not_a_number_is_a_gap() {
    let rates = grid_of(&exchange_rate_rows());
    let figures = labor_figures(
        &grid_of(&sea_rows()),
        Some(&rates),
        2014,
        LaborMeasure::Compensation,
    )
    .unwrap();
    assert_eq!(figures.figure("AAA", "C10-C12"), None);
}

#[test]
fn compensation_without_a_usable_rate_is_a_gap() {
    let mut rates = exchange_rate_rows();
    rates.push(vec![
        Cell::Text("Cland"),
        Cell::Text("CCC"),
        Cell::Number(1.0),
    ]);
    let mut sea = sea_rows();
    sea.push(sea_row(
        "DDD",
        "COMP",
        "A01",
        [Cell::Number(1.0), Cell::Number(1.0)],
    ));
    let figures = labor_figures(
        &grid_of(&sea),
        Some(&grid_of(&rates)),
        2014,
        LaborMeasure::Compensation,
    )
    .unwrap();
    // BBB's rate for 2014 is not a number; DDD has no rate at all.
    assert_eq!(figures.figure("BBB", "A01"), None);
    assert_eq!(figures.figure("DDD", "A01"), None);
}

#[test]
fn an_economy_absent_from_the_accounts_has_no_figures() {
    let figures = labor_figures(&grid_of(&sea_rows()), None, 2014, LaborMeasure::Hours).unwrap();
    assert_eq!(figures.figure("ROW", "A01"), None);
}

#[test]
fn a_year_header_written_as_text_is_found() {
    let mut sea = sea_rows();
    sea[0][5] = Cell::Text("2014");
    let figures = labor_figures(&grid_of(&sea), None, 2014, LaborMeasure::Hours).unwrap();
    assert_eq!(figures.figure("AAA", "A01"), Some(40.0));
}

#[test]
fn accounts_without_the_year_are_refused() {
    let error = labor_figures(&grid_of(&sea_rows()), None, 2012, LaborMeasure::Hours).unwrap_err();
    assert!(matches!(error, WiodError::LaborHeader { .. }));
    assert!(error.to_string().contains("2012"));
}

#[test]
fn accounts_without_a_code_column_are_refused() {
    let mut sea = sea_rows();
    sea[0][3] = Cell::Text("industry");
    let error = labor_figures(&grid_of(&sea), None, 2014, LaborMeasure::Hours).unwrap_err();
    assert!(matches!(error, WiodError::LaborHeader { .. }));
}

#[test]
fn exchange_rates_without_the_year_are_refused() {
    let error = labor_figures(
        &grid_of(&sea_rows()),
        Some(&grid_of(&exchange_rate_rows())),
        2012,
        LaborMeasure::Compensation,
    )
    .unwrap_err();
    assert!(matches!(error, WiodError::LaborHeader { .. }));
}

#[test]
fn a_figure_listed_twice_is_refused() {
    let mut sea = sea_rows();
    sea.push(sea_row(
        "AAA",
        "H_EMPE",
        "A01",
        [Cell::Number(1.0), Cell::Number(1.0)],
    ));
    let error = labor_figures(&grid_of(&sea), None, 2014, LaborMeasure::Hours).unwrap_err();
    assert!(matches!(error, WiodError::DuplicateLaborFigure { .. }));
}

#[test]
fn a_repeated_row_of_another_variable_is_not_read() {
    let mut sea = sea_rows();
    sea.push(sea_row(
        "AAA",
        "EMP",
        "U",
        [Cell::Number(1.0), Cell::Number(1.0)],
    ));
    assert!(labor_figures(&grid_of(&sea), None, 2014, LaborMeasure::Hours).is_ok());
}

#[test]
fn the_rate_listed_under_rom_is_romania_under_the_table_code_rou() {
    let mut rates = exchange_rate_rows();
    rates.push(vec![
        Cell::Text("Romania"),
        Cell::Text("ROM"),
        Cell::Number(0.5),
        Cell::Number(0.2),
    ]);
    let mut sea = sea_rows();
    sea.push(sea_row(
        "ROU",
        "COMP",
        "A01",
        [Cell::Number(1.0), Cell::Number(5.0)],
    ));
    let figures = labor_figures(
        &grid_of(&sea),
        Some(&grid_of(&rates)),
        2014,
        LaborMeasure::Compensation,
    )
    .unwrap();
    assert_eq!(figures.figure("ROU", "A01"), Some(5.0 * 0.2));
}

#[test]
fn the_rom_alias_is_the_only_code_translated() {
    let mut rates = exchange_rate_rows();
    rates.push(vec![
        Cell::Text("Romania"),
        Cell::Text("ROM"),
        Cell::Number(0.5),
        Cell::Number(0.2),
    ]);
    let mut sea = sea_rows();
    // An accounts row coded ROM gets no rate: ROM names ROU, nothing else.
    sea.push(sea_row(
        "ROM",
        "COMP",
        "A01",
        [Cell::Number(1.0), Cell::Number(5.0)],
    ));
    let figures = labor_figures(
        &grid_of(&sea),
        Some(&grid_of(&rates)),
        2014,
        LaborMeasure::Compensation,
    )
    .unwrap();
    assert_eq!(figures.figure("ROM", "A01"), None);
    assert_eq!(figures.figure("AAA", "A01"), Some(10.0 * 0.25));
}

fn exchange_rate_error(rates: Vec<Vec<Cell>>) -> WiodError {
    labor_figures(
        &grid_of(&sea_rows()),
        Some(&grid_of(&rates)),
        2014,
        LaborMeasure::Compensation,
    )
    .unwrap_err()
}

#[test]
fn an_economy_listed_twice_in_the_exchange_rates_is_refused() {
    let mut rates = exchange_rate_rows();
    rates.push(vec![
        Cell::Text("Aland again"),
        Cell::Text("AAA"),
        Cell::Number(0.5),
        Cell::Number(0.3),
    ]);
    let error = exchange_rate_error(rates);
    match &error {
        WiodError::DuplicateExchangeRate {
            code,
            first,
            second,
        } => {
            assert_eq!(
                (code.as_str(), first.as_str(), second.as_str()),
                ("AAA", "AAA", "AAA")
            );
        }
        other => panic!("unexpected error {other:?}"),
    }
    assert!(error.to_string().contains("AAA"));
}

#[test]
fn romania_listed_as_both_rom_and_rou_is_refused() {
    let mut rates = exchange_rate_rows();
    rates.push(vec![
        Cell::Text("Romania"),
        Cell::Text("ROM"),
        Cell::Number(0.5),
        Cell::Number(0.2),
    ]);
    rates.push(vec![
        Cell::Text("Romania"),
        Cell::Text("ROU"),
        Cell::Number(0.5),
        Cell::Number(0.3),
    ]);
    let error = exchange_rate_error(rates);
    match &error {
        WiodError::DuplicateExchangeRate {
            code,
            first,
            second,
        } => {
            assert_eq!(
                (code.as_str(), first.as_str(), second.as_str()),
                ("ROU", "ROM", "ROU")
            );
        }
        other => panic!("unexpected error {other:?}"),
    }
    let message = error.to_string();
    assert!(
        message.contains("ROM") && message.contains("ROU"),
        "{message}"
    );
}

#[test]
fn hours_do_not_read_the_exchange_rates() {
    let mut rates = exchange_rate_rows();
    rates.push(vec![Cell::Text("Aland again"), Cell::Text("AAA")]);
    let figures = labor_figures(
        &grid_of(&sea_rows()),
        Some(&grid_of(&rates)),
        2014,
        LaborMeasure::Hours,
    )
    .unwrap();
    assert_eq!(figures.figure("AAA", "A01"), Some(40.0));
}

// ---------------------------------------------------------------- negative intermediate use

#[test]
fn a_negative_intermediate_use_is_refused_naming_year_products_and_value() {
    let mut sheet = Synthetic::standard();
    // Product 3 (ROW A01) used by the industry making product 1 (AAA C10-C12).
    sheet.z[3][1] = -2.5;
    let error = match table_from_grid(&sheet.grid(), 2007, None) {
        Ok(_) => panic!("expected the negative entry to be refused"),
        Err(error) => error,
    };
    match &error {
        WiodError::NegativeIntermediateUse {
            year,
            row_region,
            row_industry,
            column_region,
            column_industry,
            value,
        } => {
            assert_eq!(*year, 2007);
            assert_eq!((row_region.as_str(), row_industry.as_str()), ("ROW", "A01"));
            assert_eq!(
                (column_region.as_str(), column_industry.as_str()),
                ("AAA", "C10-C12")
            );
            assert_eq!(*value, -2.5);
        }
        other => panic!("unexpected error {other:?}"),
    }
    let message = error.to_string();
    for part in ["2007", "ROW", "A01", "AAA", "C10-C12", "-2.5"] {
        assert!(message.contains(part), "{part} missing from {message}");
    }
}

#[test]
fn a_negative_intermediate_use_in_a_column_without_output_is_refused_as_negative() {
    let mut sheet = Synthetic::standard();
    sheet.z[0][5] = -1.0;
    assert!(matches!(
        error_of(&sheet.grid()),
        WiodError::NegativeIntermediateUse { value, .. } if value == -1.0
    ));
}
