//! Structural checks performed by `Economy::validate`.
//!
//! Every test breaks exactly one rule of a valid economy, so a failure names the
//! rule that regressed.

use std::collections::BTreeMap;

use cyberstride_core::{Economy, ExtraArray, SchemaError};

/// Builds an economy that satisfies every structural rule.
///
/// Layout: 3 commodities (private, intermediate, labour), 2 units sharing one
/// output commodity, 2 consumers.
fn valid_economy() -> Economy {
    let mut unit_extra = BTreeMap::new();
    unit_extra.insert(
        "effort_c".to_string(),
        ExtraArray::F64 {
            shape: vec![2],
            data: vec![0.61, 0.62],
        },
    );

    let mut consumer_extra = BTreeMap::new();
    consumer_extra.insert(
        "entitlement".to_string(),
        ExtraArray::F64 {
            shape: vec![2],
            data: vec![5000.0, 250.5],
        },
    );
    consumer_extra.insert(
        "utility_exponent".to_string(),
        ExtraArray::F64 {
            shape: vec![2, 1],
            data: vec![0.5, 0.1],
        },
    );

    Economy {
        period: 0,
        commodity_id: vec![0, 1, 2],
        commodity_kind: vec![0, 2, 4],
        endowment: vec![0.0, 0.0, 1000.0],
        commodity_extra: BTreeMap::new(),
        unit_id: vec![0, 1],
        unit_group: vec![0, 0],
        output_commodity: vec![0, 0],
        technology_kind: vec![1, 1],
        technology_scale: vec![2.0, 3.0],
        input_offsets: vec![0, 2, 3],
        input_commodity: vec![1, 2, 2],
        input_coefficient: vec![0.1, 0.2, 0.3],
        unit_extra,
        consumer_id: vec![0, 1],
        consumer_group: vec![0, 0],
        consumer_extra,
    }
}

/// Runs `validate` on an economy expected to be invalid and returns the error.
fn error_of(economy: Economy) -> SchemaError {
    economy
        .validate()
        .expect_err("expected validate to reject this economy")
}

#[test]
fn valid_economy_passes_validate() {
    assert_eq!(valid_economy().validate(), Ok(()));
}

// ---- rule: every column of a table has the same length ----

#[test]
fn validate_rejects_short_commodity_column() {
    let mut economy = valid_economy();
    economy.endowment.pop();

    assert!(matches!(
        error_of(economy),
        SchemaError::ColumnLength { column, len, expected, .. }
            if column == "endowment" && len == 2 && expected == 3
    ));
}

#[test]
fn validate_rejects_short_unit_column() {
    let mut economy = valid_economy();
    economy.technology_scale.pop();

    assert!(matches!(
        error_of(economy),
        SchemaError::ColumnLength { column, len, expected, .. }
            if column == "technology_scale" && len == 1 && expected == 2
    ));
}

#[test]
fn validate_rejects_short_consumer_column() {
    let mut economy = valid_economy();
    economy.consumer_group.pop();

    assert!(matches!(
        error_of(economy),
        SchemaError::ColumnLength { column, len, expected, .. }
            if column == "consumer_group" && len == 1 && expected == 2
    ));
}

#[test]
fn validate_rejects_input_coefficient_length_differing_from_input_commodity() {
    let mut economy = valid_economy();
    economy.input_coefficient.pop();

    assert!(matches!(
        error_of(economy),
        SchemaError::ColumnLength { column, len, expected, .. }
            if column == "input_coefficient" && len == 2 && expected == 3
    ));
}

// ---- rule: identifier columns equal the row index ----

#[test]
fn validate_rejects_commodity_id_differing_from_row_index() {
    let mut economy = valid_economy();
    economy.commodity_id[1] = 7;

    assert!(matches!(
        error_of(economy),
        SchemaError::IdentifierNotRowIndex { column, row, value }
            if column == "commodity_id" && row == 1 && value == 7
    ));
}

#[test]
fn validate_rejects_unit_id_differing_from_row_index() {
    let mut economy = valid_economy();
    economy.unit_id[0] = 1;

    assert!(matches!(
        error_of(economy),
        SchemaError::IdentifierNotRowIndex { column, row, value }
            if column == "unit_id" && row == 0 && value == 1
    ));
}

#[test]
fn validate_rejects_consumer_id_differing_from_row_index() {
    let mut economy = valid_economy();
    economy.consumer_id[1] = -1;

    assert!(matches!(
        error_of(economy),
        SchemaError::IdentifierNotRowIndex { column, row, value }
            if column == "consumer_id" && row == 1 && value == -1
    ));
}

// ---- rule: kind columns stay inside the defined enumeration ----

#[test]
fn validate_rejects_commodity_kind_outside_the_enumeration() {
    let mut economy = valid_economy();
    economy.commodity_kind[2] = 5;

    assert!(matches!(
        error_of(economy),
        SchemaError::UnknownKind { column, row, value, .. }
            if column == "commodity_kind" && row == 2 && value == 5
    ));
}

#[test]
fn validate_rejects_technology_kind_outside_the_enumeration() {
    let mut economy = valid_economy();
    economy.technology_kind[1] = 2;

    assert!(matches!(
        error_of(economy),
        SchemaError::UnknownKind { column, row, value, .. }
            if column == "technology_kind" && row == 1 && value == 2
    ));
}

// ---- rule: commodity references stay inside [0, n_commodities) ----

#[test]
fn validate_rejects_output_commodity_above_the_commodity_count() {
    let mut economy = valid_economy();
    economy.output_commodity[1] = 3;

    assert!(matches!(
        error_of(economy),
        SchemaError::CommodityIndexOutOfRange { column, row, value, n_commodities }
            if column == "output_commodity" && row == 1 && value == 3 && n_commodities == 3
    ));
}

#[test]
fn validate_rejects_negative_output_commodity() {
    let mut economy = valid_economy();
    economy.output_commodity[0] = -1;

    assert!(matches!(
        error_of(economy),
        SchemaError::CommodityIndexOutOfRange { column, row, value, .. }
            if column == "output_commodity" && row == 0 && value == -1
    ));
}

#[test]
fn validate_rejects_input_commodity_above_the_commodity_count() {
    let mut economy = valid_economy();
    economy.input_commodity[2] = 3;

    assert!(matches!(
        error_of(economy),
        SchemaError::CommodityIndexOutOfRange { column, row, value, .. }
            if column == "input_commodity" && row == 2 && value == 3
    ));
}

// ---- rule: input_offsets shape ----

#[test]
fn validate_rejects_input_offsets_of_the_wrong_length() {
    let mut economy = valid_economy();
    economy.input_offsets = vec![0, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::InputOffsetsLength { len, expected } if len == 2 && expected == 3
    ));
}

#[test]
fn validate_rejects_input_offsets_not_starting_at_zero() {
    let mut economy = valid_economy();
    economy.input_offsets = vec![1, 2, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::InputOffsetsStart { value } if value == 1
    ));
}

#[test]
fn validate_rejects_decreasing_input_offsets() {
    let mut economy = valid_economy();
    economy.input_offsets = vec![0, 3, 2];
    economy.input_commodity = vec![1, 2];
    economy.input_coefficient = vec![0.1, 0.2];

    assert!(matches!(
        error_of(economy),
        SchemaError::InputOffsetsNotMonotonic { row, value, previous }
            if row == 2 && value == 2 && previous == 3
    ));
}

#[test]
fn validate_rejects_input_offsets_not_ending_at_the_input_count() {
    let mut economy = valid_economy();
    economy.input_offsets = vec![0, 2, 2];

    assert!(matches!(
        error_of(economy),
        SchemaError::InputOffsetsEnd { value, expected } if value == 2 && expected == 3
    ));
}

// ---- rule: every f64 column is finite ----

#[test]
fn validate_rejects_nan_endowment() {
    let mut economy = valid_economy();
    economy.endowment[2] = f64::NAN;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonFinite { column, row, .. } if column == "endowment" && row == 2
    ));
}

#[test]
fn validate_rejects_infinite_technology_scale() {
    let mut economy = valid_economy();
    economy.technology_scale[0] = f64::INFINITY;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonFinite { column, row, .. } if column == "technology_scale" && row == 0
    ));
}

#[test]
fn validate_rejects_nan_input_coefficient() {
    let mut economy = valid_economy();
    economy.input_coefficient[1] = f64::NAN;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonFinite { column, row, .. } if column == "input_coefficient" && row == 1
    ));
}

// ---- rule: extra arrays agree with their shape and their table ----

#[test]
fn validate_rejects_extra_shape_whose_product_differs_from_the_data_length() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "utility_exponent".to_string(),
        ExtraArray::F64 {
            shape: vec![2, 3],
            data: vec![0.5, 0.1],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraShape { ref key, product, len, .. }
            if key == "utility_exponent" && product == 6 && len == 2
    ));
}

#[test]
fn validate_rejects_extra_first_dimension_differing_from_the_row_count() {
    let mut economy = valid_economy();
    economy.unit_extra.insert(
        "effort_s".to_string(),
        ExtraArray::F64 {
            shape: vec![3],
            data: vec![1.0, 1.5, 2.0],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraFirstDimension { bag, ref key, first, expected }
            if bag == "unit_extra" && key == "effort_s" && first == 3 && expected == 2
    ));
}

#[test]
fn validate_rejects_extra_array_without_dimensions() {
    let mut economy = valid_economy();
    economy.commodity_extra.insert(
        "scalar".to_string(),
        ExtraArray::I64 {
            shape: vec![],
            data: vec![],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraEmptyShape { bag, ref key }
            if bag == "commodity_extra" && key == "scalar"
    ));
}

#[test]
fn validate_rejects_integer_extra_shape_whose_product_differs_from_the_data_length() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "group_label".to_string(),
        ExtraArray::I64 {
            shape: vec![2, 2],
            data: vec![0, 1],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraShape { ref key, product, len, .. }
            if key == "group_label" && product == 4 && len == 2
    ));
}

#[test]
fn validate_rejects_a_non_finite_value_in_a_float_extra_array() {
    let mut economy = valid_economy();
    economy.unit_extra.insert(
        "effort_c".to_string(),
        ExtraArray::F64 {
            shape: vec![2],
            data: vec![0.61, f64::NAN],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraNonFinite { bag, ref key, index, value }
            if bag == "unit_extra" && key == "effort_c" && index == 1 && value.is_nan()
    ));
}

#[test]
fn validate_rejects_an_infinite_value_in_a_two_dimensional_extra_array() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "utility_exponent".to_string(),
        ExtraArray::F64 {
            shape: vec![2, 1],
            data: vec![0.5, f64::INFINITY],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraNonFinite { bag, ref key, index, .. }
            if bag == "consumer_extra" && key == "utility_exponent" && index == 1
    ));
}

/// `utility_exponent_commodity` maps exponent columns to commodities, so its
/// first dimension is the column count rather than the consumer count. It is the
/// sole key exempt from the row-count rule.
#[test]
fn validate_accepts_the_column_to_commodity_mapping_key() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "utility_exponent_commodity".to_string(),
        ExtraArray::I64 {
            shape: vec![1],
            data: vec![0],
        },
    );

    assert_eq!(economy.validate(), Ok(()));
}
