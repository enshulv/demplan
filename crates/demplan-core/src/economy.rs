//! The `Economy` data model and its structural checks.

use std::collections::BTreeMap;

/// Extra keys whose first dimension counts exponent columns rather than table
/// rows, each with the one bag it is registered in.
///
/// `utility_exponent_commodity` maps the columns of `consumer_extra["utility_exponent"]`
/// to commodities, so it is as long as there are columns. The consumption unit
/// table has a different row count, and the row-count rule cannot hold for this
/// key there. In any other bag the key is an ordinary extra array.
const COLUMN_MAPPING_EXTRA_KEYS: &[(&str, &str)] =
    &[("consumer_extra", "utility_exponent_commodity")];

/// `count` followed by the noun that agrees with it: the singular for exactly
/// one, the plural otherwise. Error messages use it for every count they state.
pub(crate) fn counted(count: &usize, singular: &str, plural: &str) -> String {
    let noun = if *count == 1 { singular } else { plural };
    format!("{count} {noun}")
}

/// A named array stored in one of the three `extra` bags.
///
/// Numeric arrays are row-major, and `shape` gives their dimensions. A
/// one-dimensional array carries one value per table row; a two-dimensional
/// array carries one row of values per table row. Text arrays are always
/// one-dimensional: one label per table row.
#[derive(Debug, Clone, PartialEq)]
pub enum ExtraArray {
    /// Floating-point payload.
    F64 {
        /// Dimensions of the array, outermost first.
        shape: Vec<usize>,
        /// Row-major values.
        data: Vec<f64>,
    },
    /// Integer payload.
    I64 {
        /// Dimensions of the array, outermost first.
        shape: Vec<usize>,
        /// Row-major values.
        data: Vec<i64>,
    },
    /// Text labels, one per table row.
    Text {
        /// One label per table row. The empty string is not a label, and a
        /// label does not end in a NUL character.
        data: Vec<String>,
    },
}

impl ExtraArray {
    /// Returns the dimensions of the array, outermost first.
    ///
    /// A text array has the single dimension `[len]`.
    pub fn shape(&self) -> Vec<usize> {
        match self {
            ExtraArray::F64 { shape, .. } | ExtraArray::I64 { shape, .. } => shape.clone(),
            ExtraArray::Text { data } => vec![data.len()],
        }
    }

    /// Returns the number of stored values.
    pub fn len(&self) -> usize {
        match self {
            ExtraArray::F64 { data, .. } => data.len(),
            ExtraArray::I64 { data, .. } => data.len(),
            ExtraArray::Text { data } => data.len(),
        }
    }

    /// Reports whether the array stores no values.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// The state of an economy in one period.
///
/// Three columnar tables — commodities, production units, consumption units —
/// each with a bag of named extra arrays. A production unit's inputs and outputs
/// are both variable in length, so each lives in flat arrays indexed through an
/// offsets column (`input_offsets`, `output_offsets`) rather than in a padded
/// rectangle.
///
/// Every column of a table has the same length, and each identifier column
/// equals its row index. `validate` checks that and the other structural rules.
/// Apart from requiring positive output coefficients, it checks nothing about
/// economic meaning, because sign and magnitude conventions differ between
/// schools. The data model records no ratio between a unit's outputs and
/// assumes none.
#[derive(Debug, Clone, PartialEq)]
pub struct Economy {
    /// Which period this state describes.
    pub period: i64,

    /// Stable commodity identifier, equal to the row index.
    pub commodity_id: Vec<i64>,
    /// Quantity available in this period without being produced.
    pub endowment: Vec<f64>,
    /// Named arrays over the commodity table.
    pub commodity_extra: BTreeMap<String, ExtraArray>,

    /// Stable production unit identifier, equal to the row index.
    pub unit_id: Vec<i64>,
    /// Label naming each production unit's technology; any non-empty text that
    /// does not end in a NUL character.
    pub technology_kind: Vec<String>,
    /// Scale coefficient of the technology.
    pub technology_scale: Vec<f64>,
    /// Unit `i` owns the input range `[input_offsets[i], input_offsets[i + 1])`.
    pub input_offsets: Vec<i64>,
    /// Commodity consumed by each input entry.
    pub input_commodity: Vec<i64>,
    /// A number per input entry whose meaning the unit's technology sets.
    pub input_coefficient: Vec<f64>,
    /// Unit `i` owns the output range `[output_offsets[i], output_offsets[i + 1])`.
    pub output_offsets: Vec<i64>,
    /// Commodity produced by each output entry.
    pub output_commodity: Vec<i64>,
    /// A positive number per output entry whose meaning the unit's technology sets.
    pub output_coefficient: Vec<f64>,
    /// Named arrays over the production unit table.
    pub unit_extra: BTreeMap<String, ExtraArray>,

    /// Stable consumption unit identifier, equal to the row index.
    pub consumer_id: Vec<i64>,
    /// Named arrays over the consumption unit table.
    pub consumer_extra: BTreeMap<String, ExtraArray>,
}

/// A structural rule of the data model that an `Economy` does not satisfy.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum SchemaError {
    /// A column is shorter or longer than the rest of its table.
    #[error("column `{column}` of the {table} table has length {len}, expected {expected}")]
    ColumnLength {
        /// Table the column belongs to.
        table: &'static str,
        /// Name of the offending column.
        column: &'static str,
        /// Length found.
        len: usize,
        /// Length required.
        expected: usize,
    },

    /// An identifier column carries a value other than its row index.
    #[error("`{column}[{row}]` is {value}, expected {row}: identifiers equal the row index")]
    IdentifierNotRowIndex {
        /// Name of the identifier column.
        column: &'static str,
        /// Row that carries the wrong identifier.
        row: usize,
        /// Value found.
        value: i64,
    },

    /// A label column carries the empty string.
    #[error("`{column}[{row}]` is empty, expected a non-empty label")]
    EmptyLabel {
        /// Name of the label column.
        column: &'static str,
        /// Row that carries the empty label.
        row: usize,
    },

    /// A label column carries a label that ends in a NUL character.
    ///
    /// A numpy text array drops trailing NUL characters, so the Python package
    /// could not hold the label as given.
    #[error("`{column}[{row}]` ends in a NUL character, which a numpy text array cannot hold")]
    LabelEndsInNul {
        /// Name of the label column.
        column: &'static str,
        /// Row that carries the label.
        row: usize,
    },

    /// A commodity reference falls outside the commodity table.
    #[error("`{column}[{row}]` is {value}, expected a commodity index in [0, {n_commodities})")]
    CommodityIndexOutOfRange {
        /// Name of the referencing column.
        column: &'static str,
        /// Row that carries the out-of-range reference.
        row: usize,
        /// Value found.
        value: i64,
        /// Number of rows in the commodity table.
        n_commodities: usize,
    },

    /// `input_offsets` does not have one entry per production unit plus a terminator.
    #[error("`input_offsets` has length {len}, expected {expected} (n_units + 1)")]
    InputOffsetsLength {
        /// Length found.
        len: usize,
        /// Length required.
        expected: usize,
    },

    /// `input_offsets` does not begin at zero.
    #[error("`input_offsets[0]` is {value}, expected 0")]
    InputOffsetsStart {
        /// Value found.
        value: i64,
    },

    /// `input_offsets` decreases, so a production unit would own a negative range.
    #[error(
        "`input_offsets[{row}]` is {value}, expected at least {previous}: offsets never decrease"
    )]
    InputOffsetsNotMonotonic {
        /// Row that decreases.
        row: usize,
        /// Value found.
        value: i64,
        /// Value of the preceding entry.
        previous: i64,
    },

    /// The last entry of `input_offsets` does not cover the whole input array.
    #[error("the last entry of `input_offsets` is {value}, expected {expected} (length of `input_commodity`)")]
    InputOffsetsEnd {
        /// Value found.
        value: i64,
        /// Length of the flat input arrays.
        expected: usize,
    },

    /// `output_offsets` does not have one entry per production unit plus a terminator.
    #[error("`output_offsets` has length {len}, expected {expected} (n_units + 1)")]
    OutputOffsetsLength {
        /// Length found.
        len: usize,
        /// Length required.
        expected: usize,
    },

    /// `output_offsets` does not begin at zero.
    #[error("`output_offsets[0]` is {value}, expected 0")]
    OutputOffsetsStart {
        /// Value found.
        value: i64,
    },

    /// `output_offsets` decreases, so a production unit would own a negative range.
    #[error(
        "`output_offsets[{row}]` is {value}, expected at least {previous}: offsets never decrease"
    )]
    OutputOffsetsNotMonotonic {
        /// Row that decreases.
        row: usize,
        /// Value found.
        value: i64,
        /// Value of the preceding entry.
        previous: i64,
    },

    /// The last entry of `output_offsets` does not cover the whole output array.
    #[error("the last entry of `output_offsets` is {value}, expected {expected} (length of `output_commodity`)")]
    OutputOffsetsEnd {
        /// Value found.
        value: i64,
        /// Length of the flat output arrays.
        expected: usize,
    },

    /// A production unit owns an empty output range.
    #[error("production unit {unit} has no output entry, expected at least one")]
    UnitWithoutOutput {
        /// Row of the production unit.
        unit: usize,
    },

    /// A production unit lists the same commodity in two of its output entries.
    #[error("production unit {unit} lists commodity {commodity} more than once among its outputs")]
    DuplicateOutputCommodity {
        /// Row of the production unit.
        unit: usize,
        /// Commodity listed more than once.
        commodity: i64,
    },

    /// A floating-point column carries a value that is not finite.
    #[error("`{column}[{row}]` is {value}, expected a finite number")]
    NonFinite {
        /// Name of the offending column.
        column: &'static str,
        /// Row that carries the value.
        row: usize,
        /// Value found.
        value: f64,
    },

    /// An output entry carries a coefficient that is zero or negative.
    #[error(
        "`output_coefficient[{entry}]` of production unit {unit} is {value}, expected a positive number"
    )]
    NonPositiveOutputCoefficient {
        /// Row of the production unit that owns the entry.
        unit: usize,
        /// Index of the entry in the flat output arrays.
        entry: usize,
        /// Value found.
        value: f64,
    },

    /// The dimensions of an extra array do not multiply out to its data length.
    #[error(
        "`{bag}[\"{key}\"]` has shape {shape:?} covering {}, expected {len}",
        counted(.product, "value", "values")
    )]
    ExtraShape {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
        /// Dimensions found.
        shape: Vec<usize>,
        /// Product of the dimensions.
        product: usize,
        /// Number of values stored.
        len: usize,
    },

    /// The first dimension of an extra array does not match its table row count.
    #[error("`{bag}[\"{key}\"]` has first dimension {first}, expected {expected} (row count of its table)")]
    ExtraFirstDimension {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
        /// First dimension found.
        first: usize,
        /// Row count of the table the bag belongs to.
        expected: usize,
    },

    /// A floating-point extra array holds a value that is not finite.
    #[error("`{bag}[\"{key}\"]` holds {value} at index {index}, expected a finite value")]
    ExtraNonFinite {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
        /// Position of the offending value in the row-major payload.
        index: usize,
        /// Value found.
        value: f64,
    },

    /// A text extra array holds the empty string.
    #[error(
        "`{bag}[\"{key}\"]` holds an empty label at index {index}, expected a non-empty label"
    )]
    ExtraEmptyText {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
        /// Position of the empty label.
        index: usize,
    },

    /// A text extra array holds a label that ends in a NUL character.
    ///
    /// A numpy text array drops trailing NUL characters, so the Python package
    /// could not hold the label as given.
    #[error(
        "`{bag}[\"{key}\"]` holds a label ending in a NUL character at index {index}, which a numpy text array cannot hold"
    )]
    ExtraTextEndsInNul {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
        /// Position of the label.
        index: usize,
    },

    /// An extra array has no dimensions at all.
    #[error("`{bag}[\"{key}\"]` has an empty shape, expected at least one dimension")]
    ExtraEmptyShape {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
    },
}

/// Which flat entry array an offsets column indexes; selects the error variants
/// a breach of the shared offsets rules is reported under.
#[derive(Clone, Copy)]
enum EntryTable {
    Input,
    Output,
}

/// A breach of the rules every offsets column follows, before it is named.
enum OffsetsBreach {
    Length {
        len: usize,
        expected: usize,
    },
    Start {
        value: i64,
    },
    NotMonotonic {
        row: usize,
        value: i64,
        previous: i64,
    },
    End {
        value: i64,
        expected: usize,
    },
}

impl EntryTable {
    /// Names an offsets breach after the column it was found in.
    fn error(self, breach: OffsetsBreach) -> SchemaError {
        match (self, breach) {
            (EntryTable::Input, OffsetsBreach::Length { len, expected }) => {
                SchemaError::InputOffsetsLength { len, expected }
            }
            (EntryTable::Input, OffsetsBreach::Start { value }) => {
                SchemaError::InputOffsetsStart { value }
            }
            (
                EntryTable::Input,
                OffsetsBreach::NotMonotonic {
                    row,
                    value,
                    previous,
                },
            ) => SchemaError::InputOffsetsNotMonotonic {
                row,
                value,
                previous,
            },
            (EntryTable::Input, OffsetsBreach::End { value, expected }) => {
                SchemaError::InputOffsetsEnd { value, expected }
            }
            (EntryTable::Output, OffsetsBreach::Length { len, expected }) => {
                SchemaError::OutputOffsetsLength { len, expected }
            }
            (EntryTable::Output, OffsetsBreach::Start { value }) => {
                SchemaError::OutputOffsetsStart { value }
            }
            (
                EntryTable::Output,
                OffsetsBreach::NotMonotonic {
                    row,
                    value,
                    previous,
                },
            ) => SchemaError::OutputOffsetsNotMonotonic {
                row,
                value,
                previous,
            },
            (EntryTable::Output, OffsetsBreach::End { value, expected }) => {
                SchemaError::OutputOffsetsEnd { value, expected }
            }
        }
    }
}

impl Economy {
    /// Returns the number of rows in the commodity table.
    pub fn n_commodities(&self) -> usize {
        self.commodity_id.len()
    }

    /// Returns the number of rows in the production unit table.
    pub fn n_units(&self) -> usize {
        self.unit_id.len()
    }

    /// Returns the number of input entries across all production units.
    pub fn n_inputs(&self) -> usize {
        self.input_commodity.len()
    }

    /// Returns the number of output entries across all production units.
    pub fn n_outputs(&self) -> usize {
        self.output_commodity.len()
    }

    /// Returns the number of rows in the consumption unit table.
    pub fn n_consumers(&self) -> usize {
        self.consumer_id.len()
    }

    /// Checks the structural rules of the data model and reports the first breach.
    ///
    /// The checks run in this order: column lengths, identifier columns,
    /// technology labels, commodity references, the shape of `input_offsets`,
    /// the shape of `output_offsets` and the output entries of each unit,
    /// finiteness of the floating-point columns, positivity of
    /// `output_coefficient`, and the shape and values of every extra array.
    ///
    /// Economic meaning is out of scope apart from one rule: an output
    /// coefficient is output per unit of activity, and zero or a negative number
    /// cannot be one. Non-negativity of the other columns is a theoretical
    /// commitment rather than a property of the data model, so it belongs to the
    /// optional invariant toolbox instead. Technology labels are not checked
    /// against any list: which technologies exist is the researcher's statement.
    pub fn validate(&self) -> Result<(), SchemaError> {
        self.check_column_lengths()?;
        self.check_identifiers()?;
        self.check_technology_labels()?;
        self.check_commodity_references()?;
        check_offsets(
            &self.input_offsets,
            self.n_units(),
            self.n_inputs(),
            EntryTable::Input,
        )?;
        check_offsets(
            &self.output_offsets,
            self.n_units(),
            self.n_outputs(),
            EntryTable::Output,
        )?;
        self.check_output_entries()?;
        self.check_finite_columns()?;
        self.check_output_coefficients()?;
        self.check_extra_bags()
    }

    fn check_column_lengths(&self) -> Result<(), SchemaError> {
        check_length(
            "commodity",
            "endowment",
            self.endowment.len(),
            self.n_commodities(),
        )?;

        let n_units = self.n_units();
        check_length(
            "production unit",
            "technology_kind",
            self.technology_kind.len(),
            n_units,
        )?;
        check_length(
            "production unit",
            "technology_scale",
            self.technology_scale.len(),
            n_units,
        )?;
        check_length(
            "production input",
            "input_coefficient",
            self.input_coefficient.len(),
            self.n_inputs(),
        )?;
        check_length(
            "production output",
            "output_coefficient",
            self.output_coefficient.len(),
            self.n_outputs(),
        )
    }

    fn check_identifiers(&self) -> Result<(), SchemaError> {
        check_identifier("commodity_id", &self.commodity_id)?;
        check_identifier("unit_id", &self.unit_id)?;
        check_identifier("consumer_id", &self.consumer_id)
    }

    fn check_technology_labels(&self) -> Result<(), SchemaError> {
        const COLUMN: &str = "technology_kind";
        for (row, label) in self.technology_kind.iter().enumerate() {
            if label.is_empty() {
                return Err(SchemaError::EmptyLabel {
                    column: COLUMN,
                    row,
                });
            }
            if ends_in_nul(label) {
                return Err(SchemaError::LabelEndsInNul {
                    column: COLUMN,
                    row,
                });
            }
        }
        Ok(())
    }

    fn check_commodity_references(&self) -> Result<(), SchemaError> {
        let n_commodities = self.n_commodities();
        check_commodity_index("output_commodity", &self.output_commodity, n_commodities)?;
        check_commodity_index("input_commodity", &self.input_commodity, n_commodities)
    }

    /// Checks that every unit owns at least one output entry and lists each
    /// output commodity once.
    ///
    /// Runs after `check_offsets` has accepted `output_offsets`, so every range
    /// is non-decreasing and inside the output arrays.
    fn check_output_entries(&self) -> Result<(), SchemaError> {
        for unit in 0..self.n_units() {
            let start = self.output_offsets[unit] as usize;
            let end = self.output_offsets[unit + 1] as usize;
            if start == end {
                return Err(SchemaError::UnitWithoutOutput { unit });
            }

            let outputs = &self.output_commodity[start..end];
            for (position, &commodity) in outputs.iter().enumerate() {
                if outputs[..position].contains(&commodity) {
                    return Err(SchemaError::DuplicateOutputCommodity { unit, commodity });
                }
            }
        }
        Ok(())
    }

    fn check_finite_columns(&self) -> Result<(), SchemaError> {
        check_finite("endowment", &self.endowment)?;
        check_finite("technology_scale", &self.technology_scale)?;
        check_finite("input_coefficient", &self.input_coefficient)?;
        check_finite("output_coefficient", &self.output_coefficient)
    }

    /// Checks that every output coefficient is greater than zero and names the
    /// first entry that is not, with the unit that owns it.
    ///
    /// Runs after `check_offsets` has accepted `output_offsets` and after the
    /// finiteness check, so NaN and the infinities are already reported as
    /// non-finite. Negative zero is not greater than zero and is refused.
    fn check_output_coefficients(&self) -> Result<(), SchemaError> {
        for unit in 0..self.n_units() {
            let start = self.output_offsets[unit] as usize;
            let end = self.output_offsets[unit + 1] as usize;
            for entry in start..end {
                let value = self.output_coefficient[entry];
                if value <= 0.0 {
                    return Err(SchemaError::NonPositiveOutputCoefficient { unit, entry, value });
                }
            }
        }
        Ok(())
    }

    fn check_extra_bags(&self) -> Result<(), SchemaError> {
        check_extra_bag(
            "commodity_extra",
            &self.commodity_extra,
            self.n_commodities(),
        )?;
        check_extra_bag("unit_extra", &self.unit_extra, self.n_units())?;
        check_extra_bag("consumer_extra", &self.consumer_extra, self.n_consumers())
    }
}

fn check_length(
    table: &'static str,
    column: &'static str,
    len: usize,
    expected: usize,
) -> Result<(), SchemaError> {
    if len == expected {
        return Ok(());
    }
    Err(SchemaError::ColumnLength {
        table,
        column,
        len,
        expected,
    })
}

fn check_identifier(column: &'static str, values: &[i64]) -> Result<(), SchemaError> {
    for (row, &value) in values.iter().enumerate() {
        if value != row as i64 {
            return Err(SchemaError::IdentifierNotRowIndex { column, row, value });
        }
    }
    Ok(())
}

fn check_commodity_index(
    column: &'static str,
    values: &[i64],
    n_commodities: usize,
) -> Result<(), SchemaError> {
    for (row, &value) in values.iter().enumerate() {
        if value < 0 || value >= n_commodities as i64 {
            return Err(SchemaError::CommodityIndexOutOfRange {
                column,
                row,
                value,
                n_commodities,
            });
        }
    }
    Ok(())
}

/// Checks one offsets column against the rules shared by inputs and outputs.
///
/// The column has `n_units + 1` entries, starts at 0, never decreases, and ends
/// at `n_entries`, the length of the flat arrays it indexes. A breach is reported
/// under the variants of `table`.
fn check_offsets(
    offsets: &[i64],
    n_units: usize,
    n_entries: usize,
    table: EntryTable,
) -> Result<(), SchemaError> {
    let expected_len = n_units + 1;
    if offsets.len() != expected_len {
        return Err(table.error(OffsetsBreach::Length {
            len: offsets.len(),
            expected: expected_len,
        }));
    }

    let first = offsets[0];
    if first != 0 {
        return Err(table.error(OffsetsBreach::Start { value: first }));
    }

    for row in 1..offsets.len() {
        let previous = offsets[row - 1];
        let value = offsets[row];
        if value < previous {
            return Err(table.error(OffsetsBreach::NotMonotonic {
                row,
                value,
                previous,
            }));
        }
    }

    let last = offsets[expected_len - 1];
    if last != n_entries as i64 {
        return Err(table.error(OffsetsBreach::End {
            value: last,
            expected: n_entries,
        }));
    }
    Ok(())
}

fn check_finite(column: &'static str, values: &[f64]) -> Result<(), SchemaError> {
    for (row, &value) in values.iter().enumerate() {
        if !value.is_finite() {
            return Err(SchemaError::NonFinite { column, row, value });
        }
    }
    Ok(())
}

fn check_extra_bag(
    bag: &'static str,
    arrays: &BTreeMap<String, ExtraArray>,
    n_rows: usize,
) -> Result<(), SchemaError> {
    for (key, array) in arrays {
        let shape = array.shape();
        if shape.is_empty() {
            return Err(SchemaError::ExtraEmptyShape {
                bag,
                key: key.clone(),
            });
        }

        let product: usize = shape.iter().product();
        if product != array.len() {
            return Err(SchemaError::ExtraShape {
                bag,
                key: key.clone(),
                shape,
                product,
                len: array.len(),
            });
        }

        check_extra_values(bag, key, array)?;

        if COLUMN_MAPPING_EXTRA_KEYS.contains(&(bag, key.as_str())) {
            continue;
        }
        if shape[0] != n_rows {
            return Err(SchemaError::ExtraFirstDimension {
                bag,
                key: key.clone(),
                first: shape[0],
                expected: n_rows,
            });
        }
    }
    Ok(())
}

/// Checks the values of one extra array: floating-point values are finite, and
/// text labels are non-empty and do not end in a NUL character. Integer arrays
/// have no value rule.
fn check_extra_values(bag: &'static str, key: &str, array: &ExtraArray) -> Result<(), SchemaError> {
    match array {
        ExtraArray::F64 { data, .. } => {
            match data.iter().enumerate().find(|(_, v)| !v.is_finite()) {
                Some((index, &value)) => Err(SchemaError::ExtraNonFinite {
                    bag,
                    key: key.to_string(),
                    index,
                    value,
                }),
                None => Ok(()),
            }
        }
        ExtraArray::Text { data } => {
            for (index, label) in data.iter().enumerate() {
                if label.is_empty() {
                    return Err(SchemaError::ExtraEmptyText {
                        bag,
                        key: key.to_string(),
                        index,
                    });
                }
                if ends_in_nul(label) {
                    return Err(SchemaError::ExtraTextEndsInNul {
                        bag,
                        key: key.to_string(),
                        index,
                    });
                }
            }
            Ok(())
        }
        ExtraArray::I64 { .. } => Ok(()),
    }
}

/// Reports whether `label` ends in a NUL character.
///
/// A numpy text array drops trailing NUL characters, so such a label would reach
/// Python shorter than it was given. A NUL anywhere else survives numpy.
fn ends_in_nul(label: &str) -> bool {
    label.ends_with('\0')
}
