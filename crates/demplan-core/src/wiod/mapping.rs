//! Turning a WIOT sheet held in memory into an economy and its recorded flows.
//!
//! The rules are in the documentation of the `wiod` module. This file reads no
//! file: it works on a [`Grid`], so it is tested on small hand-built sheets.

use std::collections::BTreeMap;

use crate::economy::{Economy, ExtraArray};

use super::grid::Grid;
use super::labor::LaborFigures;
use super::layout::{parse_layout, Layout, Product, TOTALS_ROWS};
use super::{ObservedFlows, WiodError, WiodTable};

/// Technology label of every producing unit; the Python package names it `LEONTIEF`.
const TECHNOLOGY_LABEL: &str = "leontief";
/// Scale of every unit's technology.
const TECHNOLOGY_SCALE: f64 = 1.0;
/// Output coefficient of every unit's single output entry.
const OUTPUT_COEFFICIENT: f64 = 1.0;
/// `industry` label of a labour commodity.
const LABOR_INDUSTRY: &str = "labor";

/// Key of the economy code in all three `extra` bags.
const REGION_KEY: &str = "region";
/// Key of the industry code in `commodity_extra` and `unit_extra`.
const INDUSTRY_KEY: &str = "industry";
/// Key of the final-demand code in `consumer_extra`.
const FINAL_DEMAND_KEY: &str = "final_demand";
/// Key of the per-unit flag saying whether the unit has a labour figure.
const LABOR_OBSERVED_KEY: &str = "labor_observed";

/// Values of the labour flag.
const OBSERVED: f64 = 1.0;
const NOT_OBSERVED: f64 = 0.0;

/// Builds the economy and the observed flows of `year` from a WIOT sheet.
///
/// `labor` is `None` when no labour measure was chosen; then the economy has no
/// labour commodity and `unit_extra` has no `labor_observed` key. The economy is
/// returned unvalidated; [`super::load_wiod`] validates it.
pub(crate) fn table_from_grid(
    grid: &Grid,
    year: i32,
    labor: Option<&LaborFigures>,
) -> Result<WiodTable, WiodError> {
    let layout = parse_layout(grid)?;
    require_non_negative_intermediate_use(grid, &layout, year)?;
    let gross_output = gross_output(grid, &layout);
    let units = producing_units(grid, &layout, &gross_output)?;
    let unit_labor = labor.map(|figures| unit_labor_figures(&layout, &units, figures));
    let labor_commodities = unit_labor
        .as_ref()
        .map(|figures| labor_commodities(&layout, &units, figures))
        .unwrap_or_default();

    let n_products = layout.n_products();
    let n_commodities = n_products + labor_commodities.len();
    let inputs = unit_inputs(
        grid,
        &layout,
        &units,
        &gross_output,
        unit_labor.as_deref(),
        &labor_commodities,
    );

    let economy = Economy {
        period: i64::from(year),
        commodity_id: (0..n_commodities as i64).collect(),
        endowment: endowment(&layout, &units, unit_labor.as_deref(), &labor_commodities),
        commodity_extra: commodity_extra(&layout, &labor_commodities),
        unit_id: (0..units.len() as i64).collect(),
        technology_kind: vec![TECHNOLOGY_LABEL.to_string(); units.len()],
        technology_scale: vec![TECHNOLOGY_SCALE; units.len()],
        input_offsets: inputs.offsets,
        input_commodity: inputs.commodity,
        input_coefficient: inputs.coefficient,
        output_offsets: (0..=units.len() as i64).collect(),
        output_commodity: units.iter().map(|&product| product as i64).collect(),
        output_coefficient: vec![OUTPUT_COEFFICIENT; units.len()],
        unit_extra: unit_extra(grid, &layout, &units, unit_labor.as_deref()),
        consumer_id: (0..layout.final_demand.len() as i64).collect(),
        consumer_extra: consumer_extra(&layout),
    };
    let observed = ObservedFlows {
        output: units.iter().map(|&product| gross_output[product]).collect(),
        input_use: inputs.used,
        consumption: final_demand(grid, &layout),
        consumption_commodity: (0..n_products as i64).collect(),
        shared_use: vec![0.0; n_commodities],
    };
    Ok(WiodTable { economy, observed })
}

/// Refuses a negative entry anywhere in the intermediate-use block, naming the
/// first one in column order.
///
/// Inputs are the positive entries of a unit's column, so a negative one would
/// otherwise be left out without a word and its product row would no longer add
/// up to its gross output.
fn require_non_negative_intermediate_use(
    grid: &Grid,
    layout: &Layout,
    year: i32,
) -> Result<(), WiodError> {
    let (start, end) = layout.product_rows();
    for column in 0..layout.n_products() {
        let values = grid.column_numbers(layout.product_column(column), start, end);
        let Some(row) = values.iter().position(|&value| value < 0.0) else {
            continue;
        };
        let used = &layout.products[row];
        let user = &layout.products[column];
        return Err(WiodError::NegativeIntermediateUse {
            year,
            row_region: used.region.clone(),
            row_industry: used.industry.clone(),
            column_region: user.region.clone(),
            column_industry: user.industry.clone(),
            value: values[row],
        });
    }
    Ok(())
}

/// Gross output of every product, from the gross-output column.
fn gross_output(grid: &Grid, layout: &Layout) -> Vec<f64> {
    let (start, end) = layout.product_rows();
    grid.column_numbers(layout.gross_output_column, start, end)
        .to_vec()
}

/// Returns the products that get a producing unit: those with positive gross
/// output, in row order.
///
/// A product left out must record no intermediate input, since a unit is where
/// inputs are recorded and it gets none.
fn producing_units(
    grid: &Grid,
    layout: &Layout,
    gross_output: &[f64],
) -> Result<Vec<usize>, WiodError> {
    let (start, end) = layout.product_rows();
    let mut units = Vec::new();
    for (product, &output) in gross_output.iter().enumerate() {
        if output > 0.0 {
            units.push(product);
            continue;
        }
        let inputs = grid.column_numbers(layout.product_column(product), start, end);
        if inputs.iter().any(|&value| value != 0.0) {
            let Product { region, industry } = layout.products[product].clone();
            return Err(WiodError::InputsWithoutOutput {
                region,
                industry,
                output,
            });
        }
    }
    Ok(units)
}

/// The labour figure of each unit's product, `None` where it has none.
fn unit_labor_figures(
    layout: &Layout,
    units: &[usize],
    figures: &LaborFigures,
) -> Vec<Option<f64>> {
    units
        .iter()
        .map(|&product| {
            let Product { region, industry } = &layout.products[product];
            figures.figure(region, industry)
        })
        .collect()
}

/// One labour commodity per economy for which at least one unit has a labour
/// figure, in the table's economy order. Each entry is the economy's index in
/// `layout.economies`.
fn labor_commodities(layout: &Layout, units: &[usize], unit_labor: &[Option<f64>]) -> Vec<usize> {
    let mut has_figure = vec![false; layout.economies.len()];
    for (&product, figure) in units.iter().zip(unit_labor) {
        if figure.is_some() {
            has_figure[economy_index(layout, product)] = true;
        }
    }
    (0..layout.economies.len())
        .filter(|&economy| has_figure[economy])
        .collect()
}

fn economy_index(layout: &Layout, product: usize) -> usize {
    let region = &layout.products[product].region;
    layout
        .economies
        .iter()
        .position(|economy| economy == region)
        .expect("every product's economy is listed in the layout")
}

/// The flat input arrays of all units and the quantity each entry records.
struct UnitInputs {
    offsets: Vec<i64>,
    commodity: Vec<i64>,
    coefficient: Vec<f64>,
    used: Vec<f64>,
}

/// Lays out each unit's inputs: the positive entries of its intermediate-use
/// column in row order at `Z / GO`, then its economy's labour commodity at
/// `labour / GO` when the unit has a non-zero labour figure.
fn unit_inputs(
    grid: &Grid,
    layout: &Layout,
    units: &[usize],
    gross_output: &[f64],
    unit_labor: Option<&[Option<f64>]>,
    labor_commodities: &[usize],
) -> UnitInputs {
    let (start, end) = layout.product_rows();
    let n_products = layout.n_products();
    let mut inputs = UnitInputs {
        offsets: Vec::with_capacity(units.len() + 1),
        commodity: Vec::new(),
        coefficient: Vec::new(),
        used: Vec::new(),
    };
    inputs.offsets.push(0);

    for (unit, &product) in units.iter().enumerate() {
        let output = gross_output[product];
        let column = grid.column_numbers(layout.product_column(product), start, end);
        for (input, &used) in column.iter().enumerate() {
            if used > 0.0 {
                inputs.commodity.push(input as i64);
                inputs.coefficient.push(used / output);
                inputs.used.push(used);
            }
        }

        let labor = unit_labor.and_then(|figures| figures[unit]);
        if let Some(used) = labor.filter(|&used| used != 0.0) {
            let economy = economy_index(layout, product);
            let position = labor_commodities
                .iter()
                .position(|&listed| listed == economy)
                .expect("an economy with a labour figure has a labour commodity");
            inputs.commodity.push((n_products + position) as i64);
            inputs.coefficient.push(used / output);
            inputs.used.push(used);
        }
        inputs.offsets.push(inputs.commodity.len() as i64);
    }
    inputs
}

/// Zero for every product; for each labour commodity, the sum of the labour
/// figures of its economy's units, zeros included.
fn endowment(
    layout: &Layout,
    units: &[usize],
    unit_labor: Option<&[Option<f64>]>,
    labor_commodities: &[usize],
) -> Vec<f64> {
    let n_products = layout.n_products();
    let mut endowment = vec![0.0; n_products + labor_commodities.len()];
    let Some(figures) = unit_labor else {
        return endowment;
    };
    for (&product, figure) in units.iter().zip(figures) {
        let Some(figure) = figure else {
            continue;
        };
        let economy = economy_index(layout, product);
        let position = labor_commodities
            .iter()
            .position(|&listed| listed == economy)
            .expect("an economy with a labour figure has a labour commodity");
        endowment[n_products + position] += figure;
    }
    endowment
}

fn commodity_extra(layout: &Layout, labor_commodities: &[usize]) -> BTreeMap<String, ExtraArray> {
    let mut region: Vec<String> = layout.products.iter().map(|p| p.region.clone()).collect();
    let mut industry: Vec<String> = layout.products.iter().map(|p| p.industry.clone()).collect();
    for &economy in labor_commodities {
        region.push(layout.economies[economy].clone());
        industry.push(LABOR_INDUSTRY.to_string());
    }
    BTreeMap::from([
        (REGION_KEY.to_string(), ExtraArray::Text { data: region }),
        (
            INDUSTRY_KEY.to_string(),
            ExtraArray::Text { data: industry },
        ),
    ])
}

/// Labels, totals rows and, when labour was chosen, the labour flag of each unit.
fn unit_extra(
    grid: &Grid,
    layout: &Layout,
    units: &[usize],
    unit_labor: Option<&[Option<f64>]>,
) -> BTreeMap<String, ExtraArray> {
    let n_units = units.len();
    let float = |data: Vec<f64>| ExtraArray::F64 {
        shape: vec![n_units],
        data,
    };
    let mut extra = BTreeMap::new();
    extra.insert(
        REGION_KEY.to_string(),
        ExtraArray::Text {
            data: units
                .iter()
                .map(|&p| layout.products[p].region.clone())
                .collect(),
        },
    );
    extra.insert(
        INDUSTRY_KEY.to_string(),
        ExtraArray::Text {
            data: units
                .iter()
                .map(|&p| layout.products[p].industry.clone())
                .collect(),
        },
    );
    for (&row, (_, key)) in layout.totals_rows.iter().zip(TOTALS_ROWS.iter()) {
        let values = units
            .iter()
            .map(|&product| {
                grid.number(row, layout.product_column(product))
                    .expect("totals cells are checked to hold numbers")
            })
            .collect();
        extra.insert(key.to_string(), float(values));
    }
    if let Some(figures) = unit_labor {
        let flags = figures
            .iter()
            .map(|figure| {
                if figure.is_some() {
                    OBSERVED
                } else {
                    NOT_OBSERVED
                }
            })
            .collect();
        extra.insert(LABOR_OBSERVED_KEY.to_string(), float(flags));
    }
    extra
}

fn consumer_extra(layout: &Layout) -> BTreeMap<String, ExtraArray> {
    BTreeMap::from([
        (
            REGION_KEY.to_string(),
            ExtraArray::Text {
                data: layout
                    .final_demand
                    .iter()
                    .map(|c| c.region.clone())
                    .collect(),
            },
        ),
        (
            FINAL_DEMAND_KEY.to_string(),
            ExtraArray::Text {
                data: layout.final_demand.iter().map(|c| c.code.clone()).collect(),
            },
        ),
    ])
}

/// Final demand, row-major: one row per final-demand column, one entry per
/// product. Negative entries are kept.
fn final_demand(grid: &Grid, layout: &Layout) -> Vec<f64> {
    let (start, end) = layout.product_rows();
    let mut values = Vec::with_capacity(layout.final_demand.len() * layout.n_products());
    for column in &layout.final_demand {
        values.extend_from_slice(grid.column_numbers(column.column, start, end));
    }
    values
}
