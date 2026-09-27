//! Structural checks performed by `Economy::validate`.
//!
//! Every test breaks exactly one rule of a valid economy, so a failure names the
//! rule that regressed.

use std::collections::BTreeMap;

use demplan_core::{Economy, ExtraArray, SchemaError};

/// Builds an economy that satisfies every structural rule.
///
/// Layout: 3 commodities, 2 units, 2 consumers. Unit 0 has one output entry
/// (commodity 0); unit 1 is a joint producer with two output entries
/// (commodities 0 and 1), so commodity 0 is produced by both units. The two
/// technology labels are ones the library has no implementation for.
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
        endowment: vec![0.0, 0.0, 1000.0],
        commodity_extra: BTreeMap::new(),
        unit_id: vec![0, 1],
        technology_kind: vec!["my_own_technology".to_string(), "joint_output".to_string()],
        technology_scale: vec![2.0, 3.0],
        input_offsets: vec![0, 2, 3],
        input_commodity: vec![1, 2, 2],
        input_coefficient: vec![0.1, 0.2, 0.3],
        output_offsets: vec![0, 1, 3],
        output_commodity: vec![0, 0, 1],
        output_coefficient: vec![1.0, 2.0, 0.5],
        unit_extra,
        consumer_id: vec![0, 1],
        consumer_extra,
    }
}

/// Runs `validate` on an economy expected to be invalid and returns the error.
fn error_of(economy: Economy) -> SchemaError {
    economy
        .validate()
        .expect_err("expected validate to reject this economy")
}

/// A text extra array holding the given labels.
fn text(labels: &[&str]) -> ExtraArray {
    ExtraArray::Text {
        data: labels.iter().map(|label| label.to_string()).collect(),
    }
}

#[test]
fn valid_economy_passes_validate() {
    assert_eq!(valid_economy().validate(), Ok(()));
}

// ---- table sizes ----

#[test]
fn n_inputs_and_n_outputs_count_the_flat_entries() {
    let economy = valid_economy();
    assert_eq!(economy.n_inputs(), 3);
    assert_eq!(economy.n_outputs(), 3);
    assert_eq!(economy.n_units(), 2);
}

#[test]
fn n_outputs_follows_the_output_commodity_column_not_the_unit_count() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 2, 4];
    economy.output_commodity = vec![0, 2, 1, 2];
    economy.output_coefficient = vec![1.0, 1.0, 1.0, 1.0];

    assert_eq!(economy.n_outputs(), 4);
    assert_eq!(economy.validate(), Ok(()));
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
fn validate_rejects_a_technology_kind_column_of_the_wrong_length() {
    let mut economy = valid_economy();
    economy.technology_kind.push("leontief".to_string());

    assert!(matches!(
        error_of(economy),
        SchemaError::ColumnLength { column, len, expected, .. }
            if column == "technology_kind" && len == 3 && expected == 2
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

#[test]
fn validate_rejects_output_coefficient_length_differing_from_output_commodity() {
    let mut economy = valid_economy();
    economy.output_coefficient.pop();

    assert!(matches!(
        error_of(economy),
        SchemaError::ColumnLength { column, len, expected, .. }
            if column == "output_coefficient" && len == 2 && expected == 3
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

// ---- rule: technology_kind is a non-empty text label, any text accepted ----

#[test]
fn validate_accepts_technology_labels_the_library_does_not_know() {
    let mut economy = valid_economy();
    economy.technology_kind = vec![
        "hahnel_cobb_douglas_effort".to_string(),
        "技术 x".to_string(),
    ];

    assert_eq!(economy.validate(), Ok(()));
}

#[test]
fn validate_accepts_the_two_library_recognised_labels() {
    let mut economy = valid_economy();
    economy.technology_kind = vec!["leontief".to_string(), "cobb_douglas".to_string()];

    assert_eq!(economy.validate(), Ok(()));
}

#[test]
fn validate_rejects_an_empty_technology_label() {
    let mut economy = valid_economy();
    economy.technology_kind[1] = String::new();

    assert!(matches!(
        error_of(economy),
        SchemaError::EmptyLabel { column, row } if column == "technology_kind" && row == 1
    ));
}

#[test]
fn validate_accepts_a_whitespace_technology_label() {
    // The data model does not interpret labels; whitespace is text like any other.
    let mut economy = valid_economy();
    economy.technology_kind[0] = " ".to_string();

    assert_eq!(economy.validate(), Ok(()));
}

// A numpy text array drops trailing NUL characters, so the Python side cannot
// hold a label that ends in one. Both sides refuse it; a NUL elsewhere in the
// label survives numpy and is accepted.

#[test]
fn validate_rejects_a_technology_label_ending_in_nul() {
    let mut economy = valid_economy();
    economy.technology_kind[1] = "leontief\0".to_string();

    let error = error_of(economy);
    assert!(
        matches!(
            error,
            SchemaError::LabelEndsInNul { column, row } if column == "technology_kind" && row == 1
        ),
        "{error:?}"
    );
    let message = error.to_string();
    assert!(message.contains("technology_kind[1]"), "{message}");
    assert!(message.contains("NUL"), "{message}");
}

#[test]
fn validate_rejects_a_technology_label_that_is_only_nul() {
    // "\0" is not empty, but numpy would store it as the empty string.
    let mut economy = valid_economy();
    economy.technology_kind[0] = "\0".to_string();

    assert!(matches!(
        error_of(economy),
        SchemaError::LabelEndsInNul { column, row } if column == "technology_kind" && row == 0
    ));
}

#[test]
fn validate_accepts_a_technology_label_with_a_nul_before_its_last_character() {
    let mut economy = valid_economy();
    economy.technology_kind = vec!["a\0b".to_string(), "\0a".to_string()];

    assert_eq!(economy.validate(), Ok(()));
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
fn validate_rejects_an_out_of_range_commodity_in_the_last_output_entry() {
    // The last entry sits past n_units, so a check that walked one entry per
    // unit would never reach it.
    let mut economy = valid_economy();
    economy.output_commodity[2] = 3;

    assert!(matches!(
        error_of(economy),
        SchemaError::CommodityIndexOutOfRange { column, row, value, .. }
            if column == "output_commodity" && row == 2 && value == 3
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
fn validate_rejects_input_offsets_starting_below_zero() {
    // Still non-decreasing and still ending at the input count: only the start
    // is wrong.
    let mut economy = valid_economy();
    economy.input_offsets = vec![-1, 2, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::InputOffsetsStart { value } if value == -1
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

#[test]
fn validate_accepts_a_unit_without_inputs() {
    // Inputs may be empty; only outputs require at least one entry per unit.
    let mut economy = valid_economy();
    economy.input_offsets = vec![0, 0, 3];
    economy.input_commodity = vec![1, 2, 2];

    assert_eq!(economy.validate(), Ok(()));
}

// ---- rule: output_offsets shape ----

#[test]
fn validate_rejects_output_offsets_of_the_wrong_length() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsLength { len, expected } if len == 2 && expected == 3
    ));
}

#[test]
fn validate_rejects_output_offsets_not_starting_at_zero() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![1, 2, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsStart { value } if value == 1
    ));
}

#[test]
fn validate_rejects_output_offsets_starting_below_zero() {
    // The output windows are sliced after the offsets are accepted, so a
    // negative start let through would panic there instead of being reported.
    let mut economy = valid_economy();
    economy.output_offsets = vec![-1, 1, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsStart { value } if value == -1
    ));
}

#[test]
fn validate_rejects_output_offsets_starting_at_the_smallest_integer() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![i64::MIN, 1, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsStart { value } if value == i64::MIN
    ));
}

#[test]
fn validate_rejects_decreasing_output_offsets() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 3, 2];
    economy.output_commodity = vec![0, 1];
    economy.output_coefficient = vec![1.0, 1.0];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsNotMonotonic { row, value, previous }
            if row == 2 && value == 2 && previous == 3
    ));
}

#[test]
fn validate_rejects_output_offsets_not_ending_at_the_output_count() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 1, 2];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsEnd { value, expected } if value == 2 && expected == 3
    ));
}

#[test]
fn validate_rejects_output_offsets_ending_past_the_output_count() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 1, 4];

    assert!(matches!(
        error_of(economy),
        SchemaError::OutputOffsetsEnd { value, expected } if value == 4 && expected == 3
    ));
}

#[test]
fn validate_reports_output_offset_breaches_under_the_output_names() {
    // Input and output offsets share one rule; the message has to say which
    // column broke it.
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 1, 2];

    let message = error_of(economy).to_string();
    assert!(message.contains("output_offsets"), "{message}");
    assert!(message.contains("output_commodity"), "{message}");
    assert!(!message.contains("input"), "{message}");
}

// ---- rule: every unit has at least one output entry ----

#[test]
fn validate_rejects_a_last_unit_without_outputs() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 2, 2];
    economy.output_commodity = vec![0, 1];
    economy.output_coefficient = vec![1.0, 1.0];

    assert!(matches!(
        error_of(economy),
        SchemaError::UnitWithoutOutput { unit } if unit == 1
    ));
}

#[test]
fn validate_rejects_a_first_unit_without_outputs() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 0, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::UnitWithoutOutput { unit } if unit == 0
    ));
}

#[test]
fn validate_rejects_a_middle_unit_without_outputs() {
    let mut economy = valid_economy();
    economy.unit_id = vec![0, 1, 2];
    economy.technology_kind.push("leontief".to_string());
    economy.technology_scale.push(1.0);
    economy.input_offsets = vec![0, 2, 3, 3];
    economy.unit_extra.clear();
    economy.output_offsets = vec![0, 1, 1, 3];

    assert!(matches!(
        error_of(economy),
        SchemaError::UnitWithoutOutput { unit } if unit == 1
    ));
}

#[test]
fn validate_accepts_an_economy_without_units() {
    let mut economy = valid_economy();
    economy.unit_id.clear();
    economy.technology_kind.clear();
    economy.technology_scale.clear();
    economy.input_offsets = vec![0];
    economy.input_commodity.clear();
    economy.input_coefficient.clear();
    economy.output_offsets = vec![0];
    economy.output_commodity.clear();
    economy.output_coefficient.clear();
    economy.unit_extra.clear();

    assert_eq!(economy.validate(), Ok(()));
}

// ---- rule: a unit lists each output commodity at most once ----

#[test]
fn validate_rejects_a_unit_listing_the_same_output_commodity_twice() {
    let mut economy = valid_economy();
    economy.output_commodity = vec![0, 1, 1];

    assert!(matches!(
        error_of(economy),
        SchemaError::DuplicateOutputCommodity { unit, commodity } if unit == 1 && commodity == 1
    ));
}

#[test]
fn validate_rejects_a_repeated_output_commodity_that_is_not_adjacent() {
    let mut economy = valid_economy();
    economy.output_offsets = vec![0, 1, 4];
    economy.output_commodity = vec![0, 2, 1, 2];
    economy.output_coefficient = vec![1.0, 1.0, 1.0, 1.0];

    assert!(matches!(
        error_of(economy),
        SchemaError::DuplicateOutputCommodity { unit, commodity } if unit == 1 && commodity == 2
    ));
}

#[test]
fn validate_accepts_the_same_output_commodity_in_different_units() {
    // Commodity 0 is produced by both units in the valid economy; the check is
    // per unit, not across the table.
    let economy = valid_economy();
    assert_eq!(economy.output_commodity[0], economy.output_commodity[1]);
    assert_eq!(economy.validate(), Ok(()));
}

#[test]
fn validate_accepts_a_unit_that_lists_its_input_commodity_as_an_output() {
    let mut economy = valid_economy();
    economy.output_commodity = vec![1, 0, 2];

    assert_eq!(economy.validate(), Ok(()));
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

#[test]
fn validate_rejects_nan_output_coefficient() {
    let mut economy = valid_economy();
    economy.output_coefficient[2] = f64::NAN;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonFinite { column, row, .. } if column == "output_coefficient" && row == 2
    ));
}

#[test]
fn validate_rejects_infinite_output_coefficient() {
    let mut economy = valid_economy();
    economy.output_coefficient[0] = f64::NEG_INFINITY;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonFinite { column, row, .. } if column == "output_coefficient" && row == 0
    ));
}

// ---- rule: every output coefficient is positive ----

#[test]
fn validate_rejects_a_zero_output_coefficient() {
    let mut economy = valid_economy();
    economy.output_coefficient[0] = 0.0;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonPositiveOutputCoefficient { unit, entry, value }
            if unit == 0 && entry == 0 && value == 0.0
    ));
}

#[test]
fn validate_rejects_a_negative_output_coefficient_in_the_second_entry_of_a_joint_unit() {
    // Entry 2 is the second output of unit 1: the unit and the flat entry
    // index differ, and so do the entry index and the position inside the unit.
    let mut economy = valid_economy();
    economy.output_coefficient[2] = -1.5;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonPositiveOutputCoefficient { unit, entry, value }
            if unit == 1 && entry == 2 && value == -1.5
    ));
}

#[test]
fn validate_rejects_a_negative_zero_output_coefficient() {
    let mut economy = valid_economy();
    economy.output_coefficient[1] = -0.0;

    assert!(matches!(
        error_of(economy),
        SchemaError::NonPositiveOutputCoefficient { unit, entry, .. } if unit == 1 && entry == 1
    ));
}

#[test]
fn validate_reports_the_first_non_positive_output_coefficient() {
    let mut economy = valid_economy();
    economy.output_coefficient = vec![1.0, -2.0, 0.0];

    assert!(matches!(
        error_of(economy),
        SchemaError::NonPositiveOutputCoefficient { entry, .. } if entry == 1
    ));
}

#[test]
fn validate_names_the_unit_and_entry_of_a_non_positive_output_coefficient() {
    let mut economy = valid_economy();
    economy.output_coefficient[2] = -1.5;

    let message = error_of(economy).to_string();
    assert!(message.contains("output_coefficient[2]"), "{message}");
    assert!(message.contains("production unit 1"), "{message}");
    assert!(message.contains("-1.5"), "{message}");
}

#[test]
fn validate_accepts_the_smallest_and_largest_positive_output_coefficients() {
    let mut economy = valid_economy();
    economy.output_coefficient = vec![f64::from_bits(1), f64::MIN_POSITIVE, f64::MAX];

    assert_eq!(economy.validate(), Ok(()));
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
fn an_extra_shape_covering_one_value_counts_it_in_the_singular() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "utility_exponent".to_string(),
        ExtraArray::F64 {
            shape: vec![1],
            data: vec![0.5, 0.1],
        },
    );

    assert_eq!(
        error_of(economy).to_string(),
        "`consumer_extra[\"utility_exponent\"]` has shape [1] covering 1 value, expected 2"
    );
}

#[test]
fn an_extra_shape_covering_several_values_counts_them_in_the_plural() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "utility_exponent".to_string(),
        ExtraArray::F64 {
            shape: vec![2, 3],
            data: vec![0.5, 0.1],
        },
    );

    assert_eq!(
        error_of(economy).to_string(),
        "`consumer_extra[\"utility_exponent\"]` has shape [2, 3] covering 6 values, expected 2"
    );
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
fn validate_rejects_float_extra_data_longer_than_its_shape() {
    // The first dimension still matches the table, so only the shape rule can
    // catch the extra value.
    let mut economy = valid_economy();
    economy.unit_extra.insert(
        "effort_c".to_string(),
        ExtraArray::F64 {
            shape: vec![2],
            data: vec![0.61, 0.62, 0.63],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraShape { bag, ref key, ref shape, product, len }
            if bag == "unit_extra" && key == "effort_c" && *shape == vec![2]
                && product == 2 && len == 3
    ));
}

#[test]
fn validate_rejects_integer_extra_data_longer_than_its_shape() {
    let mut economy = valid_economy();
    economy.consumer_extra.insert(
        "group_label".to_string(),
        ExtraArray::I64 {
            shape: vec![2, 1],
            data: vec![0, 1, 2],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraShape { bag, ref key, product, len, .. }
            if bag == "consumer_extra" && key == "group_label" && product == 2 && len == 3
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

/// The mapping key is registered for the consumer table only. Under the same
/// name in the commodity table it is an ordinary extra array, one row per
/// commodity.
#[test]
fn validate_holds_the_mapping_key_to_the_row_count_in_the_commodity_table() {
    let mut economy = valid_economy();
    economy.commodity_extra.insert(
        "utility_exponent_commodity".to_string(),
        ExtraArray::I64 {
            shape: vec![1],
            data: vec![0],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraFirstDimension { bag, ref key, first, expected }
            if bag == "commodity_extra" && key == "utility_exponent_commodity"
                && first == 1 && expected == 3
    ));
}

/// Under the mapping key's name in the producing unit table, an array is one
/// row per unit like any other.
#[test]
fn validate_holds_the_mapping_key_to_the_row_count_in_the_unit_table() {
    let mut economy = valid_economy();
    economy.unit_extra.insert(
        "utility_exponent_commodity".to_string(),
        ExtraArray::I64 {
            shape: vec![3],
            data: vec![0, 1, 2],
        },
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraFirstDimension { bag, ref key, first, expected }
            if bag == "unit_extra" && key == "utility_exponent_commodity"
                && first == 3 && expected == 2
    ));
}

// ---- text extra arrays ----

#[test]
fn a_text_extra_array_is_one_dimensional_with_one_value_per_label() {
    let array = text(&["private_good", "labor", "labor"]);
    assert_eq!(array.shape(), vec![3]);
    assert_eq!(array.len(), 3);
    assert!(!array.is_empty());
}

#[test]
fn validate_accepts_a_text_extra_array_in_every_bag() {
    let mut economy = valid_economy();
    economy.commodity_extra.insert(
        "hahnel_kind".to_string(),
        text(&["private_good", "intermediate", "labor"]),
    );
    economy
        .unit_extra
        .insert("sector".to_string(), text(&["steel", "coal"]));
    economy
        .consumer_extra
        .insert("region".to_string(), text(&["north", "南"]));

    assert_eq!(economy.validate(), Ok(()));
}

#[test]
fn validate_rejects_a_text_extra_array_longer_than_its_table() {
    let mut economy = valid_economy();
    economy.commodity_extra.insert(
        "hahnel_kind".to_string(),
        text(&["private_good", "intermediate", "labor", "labor"]),
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraFirstDimension { bag, ref key, first, expected }
            if bag == "commodity_extra" && key == "hahnel_kind" && first == 4 && expected == 3
    ));
}

#[test]
fn validate_rejects_a_text_extra_array_shorter_than_its_table() {
    let mut economy = valid_economy();
    economy
        .unit_extra
        .insert("sector".to_string(), text(&["steel"]));

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraFirstDimension { bag, ref key, first, expected }
            if bag == "unit_extra" && key == "sector" && first == 1 && expected == 2
    ));
}

#[test]
fn validate_rejects_an_empty_label_in_a_text_extra_array() {
    let mut economy = valid_economy();
    economy
        .consumer_extra
        .insert("region".to_string(), text(&["north", ""]));

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraEmptyText { bag, ref key, index }
            if bag == "consumer_extra" && key == "region" && index == 1
    ));
}

#[test]
fn validate_rejects_a_text_extra_label_ending_in_nul() {
    let mut economy = valid_economy();
    economy
        .consumer_extra
        .insert("region".to_string(), text(&["north", "south\0\0"]));

    let error = error_of(economy);
    assert!(
        matches!(
            error,
            SchemaError::ExtraTextEndsInNul { bag, ref key, index }
                if bag == "consumer_extra" && key == "region" && index == 1
        ),
        "{error:?}"
    );
    let message = error.to_string();
    assert!(message.contains("region"), "{message}");
    assert!(message.contains("NUL"), "{message}");
}

#[test]
fn validate_rejects_a_text_extra_label_that_is_only_nul() {
    let mut economy = valid_economy();
    economy.commodity_extra.insert(
        "hahnel_kind".to_string(),
        text(&["\0", "intermediate", "labor"]),
    );

    assert!(matches!(
        error_of(economy),
        SchemaError::ExtraTextEndsInNul { bag, ref key, index }
            if bag == "commodity_extra" && key == "hahnel_kind" && index == 0
    ));
}

#[test]
fn validate_accepts_a_text_extra_label_with_a_nul_before_its_last_character() {
    let mut economy = valid_economy();
    economy
        .unit_extra
        .insert("sector".to_string(), text(&["st\0eel", "\0coal"]));

    assert_eq!(economy.validate(), Ok(()));
}

#[test]
fn validate_accepts_an_empty_text_extra_array_on_an_empty_table() {
    let mut economy = valid_economy();
    economy.consumer_id.clear();
    economy.consumer_extra.clear();
    economy
        .consumer_extra
        .insert("region".to_string(), text(&[]));

    assert_eq!(economy.validate(), Ok(()));
}
