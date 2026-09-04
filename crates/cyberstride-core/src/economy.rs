//! The `Economy` data model and its structural checks.

use std::collections::BTreeMap;

/// Commodity kind: a good consumed privately by one consumption unit.
pub const COMMODITY_KIND_PRIVATE: i8 = 0;
/// Commodity kind: a good produced once and shared by every consumption unit.
pub const COMMODITY_KIND_PUBLIC: i8 = 1;
/// Commodity kind: a produced good used as an input.
pub const COMMODITY_KIND_INTERMEDIATE: i8 = 2;
/// Commodity kind: a natural resource, available from the endowment only.
pub const COMMODITY_KIND_NATURE: i8 = 3;
/// Commodity kind: labour, available from the endowment only.
pub const COMMODITY_KIND_LABOR: i8 = 4;

/// Commodity kinds the schema accepts.
const COMMODITY_KINDS: &[i8] = &[
    COMMODITY_KIND_PRIVATE,
    COMMODITY_KIND_PUBLIC,
    COMMODITY_KIND_INTERMEDIATE,
    COMMODITY_KIND_NATURE,
    COMMODITY_KIND_LABOR,
];

/// Technology kind: fixed input proportions.
pub const TECHNOLOGY_KIND_LEONTIEF: i8 = 0;
/// Technology kind: Cobb-Douglas, where `input_coefficient` holds exponents.
pub const TECHNOLOGY_KIND_COBB_DOUGLAS: i8 = 1;

/// Technology kinds the schema accepts.
const TECHNOLOGY_KINDS: &[i8] = &[TECHNOLOGY_KIND_LEONTIEF, TECHNOLOGY_KIND_COBB_DOUGLAS];

/// Extra keys whose first dimension counts exponent columns rather than table rows.
///
/// `utility_exponent_commodity` maps the columns of `utility_exponent` to
/// commodities, so it is as long as there are columns. The consumption unit table
/// has a different row count, and the row-count rule cannot hold for this key.
const COLUMN_MAPPING_EXTRA_KEYS: &[&str] = &["utility_exponent_commodity"];

/// A named array stored in one of the three `extra` bags.
///
/// `data` is row-major, and `shape` gives its dimensions. A one-dimensional array
/// carries one value per table row; a two-dimensional array carries one row of
/// values per table row.
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
}

impl ExtraArray {
    /// Returns the dimensions of the array, outermost first.
    pub fn shape(&self) -> &[usize] {
        match self {
            ExtraArray::F64 { shape, .. } | ExtraArray::I64 { shape, .. } => shape,
        }
    }

    /// Returns the number of stored values.
    pub fn len(&self) -> usize {
        match self {
            ExtraArray::F64 { data, .. } => data.len(),
            ExtraArray::I64 { data, .. } => data.len(),
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
/// each with a bag of named extra arrays. Production inputs are variable in
/// length, so they live in flat arrays indexed through `input_offsets` rather
/// than in a padded rectangle.
///
/// Every column of a table has the same length, and each identifier column
/// equals its row index. `validate` checks that and the other structural rules;
/// it deliberately checks nothing about economic meaning, because sign and
/// magnitude conventions differ between schools.
#[derive(Debug, Clone, PartialEq)]
pub struct Economy {
    /// Which period this state describes.
    pub period: i64,

    /// Stable commodity identifier, equal to the row index.
    pub commodity_id: Vec<i64>,
    /// Commodity kind, one of the `COMMODITY_KIND_*` values.
    pub commodity_kind: Vec<i8>,
    /// Quantity available in this period without being produced.
    pub endowment: Vec<f64>,
    /// Named arrays over the commodity table.
    pub commodity_extra: BTreeMap<String, ExtraArray>,

    /// Stable production unit identifier, equal to the row index.
    pub unit_id: Vec<i64>,
    /// Mapping from production unit to sector.
    pub unit_group: Vec<i64>,
    /// The single commodity each production unit produces.
    pub output_commodity: Vec<i64>,
    /// Technology kind, one of the `TECHNOLOGY_KIND_*` values.
    pub technology_kind: Vec<i8>,
    /// Scale coefficient of the technology.
    pub technology_scale: Vec<f64>,
    /// Unit `i` owns the input range `[input_offsets[i], input_offsets[i + 1])`.
    pub input_offsets: Vec<i64>,
    /// Commodity consumed by each input entry.
    pub input_commodity: Vec<i64>,
    /// Input coefficient, or exponent under a Cobb-Douglas technology.
    pub input_coefficient: Vec<f64>,
    /// Named arrays over the production unit table.
    pub unit_extra: BTreeMap<String, ExtraArray>,

    /// Stable consumption unit identifier, equal to the row index.
    pub consumer_id: Vec<i64>,
    /// Mapping from consumption unit to group.
    pub consumer_group: Vec<i64>,
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

    /// A kind column carries a value outside the defined enumeration.
    #[error("`{column}[{row}]` is {value}, expected one of {allowed:?}")]
    UnknownKind {
        /// Name of the kind column.
        column: &'static str,
        /// Row that carries the unknown kind.
        row: usize,
        /// Value found.
        value: i8,
        /// Values the enumeration defines.
        allowed: &'static [i8],
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

    /// The dimensions of an extra array do not multiply out to its data length.
    #[error("`{bag}[\"{key}\"]` has shape {shape:?} covering {product} values, expected {len}")]
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

    /// An extra array has no dimensions at all.
    #[error("`{bag}[\"{key}\"]` has an empty shape, expected at least one dimension")]
    ExtraEmptyShape {
        /// Bag the array belongs to.
        bag: &'static str,
        /// Key the array is stored under.
        key: String,
    },
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

    /// Returns the number of rows in the consumption unit table.
    pub fn n_consumers(&self) -> usize {
        self.consumer_id.len()
    }

    /// Checks the structural rules of the data model and reports the first breach.
    ///
    /// The checks cover column lengths, identifier columns, kind enumerations,
    /// commodity references, the shape of `input_offsets`, finiteness of the
    /// floating-point columns, and the shape of every extra array.
    ///
    /// Economic meaning is out of scope. Non-negativity, for one, is a theoretical
    /// commitment rather than a property of the data model, so it belongs to the
    /// optional invariant toolbox instead.
    pub fn validate(&self) -> Result<(), SchemaError> {
        self.check_column_lengths()?;
        self.check_identifiers()?;
        self.check_kinds()?;
        self.check_commodity_references()?;
        self.check_input_offsets()?;
        self.check_finite_columns()?;
        self.check_extra_bags()
    }

    fn check_column_lengths(&self) -> Result<(), SchemaError> {
        let n_commodities = self.n_commodities();
        check_length(
            "commodity",
            "commodity_kind",
            self.commodity_kind.len(),
            n_commodities,
        )?;
        check_length(
            "commodity",
            "endowment",
            self.endowment.len(),
            n_commodities,
        )?;

        let n_units = self.n_units();
        check_length(
            "production unit",
            "unit_group",
            self.unit_group.len(),
            n_units,
        )?;
        check_length(
            "production unit",
            "output_commodity",
            self.output_commodity.len(),
            n_units,
        )?;
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
            self.input_commodity.len(),
        )?;

        let n_consumers = self.n_consumers();
        check_length(
            "consumption unit",
            "consumer_group",
            self.consumer_group.len(),
            n_consumers,
        )
    }

    fn check_identifiers(&self) -> Result<(), SchemaError> {
        check_identifier("commodity_id", &self.commodity_id)?;
        check_identifier("unit_id", &self.unit_id)?;
        check_identifier("consumer_id", &self.consumer_id)
    }

    fn check_kinds(&self) -> Result<(), SchemaError> {
        check_kind("commodity_kind", &self.commodity_kind, COMMODITY_KINDS)?;
        check_kind("technology_kind", &self.technology_kind, TECHNOLOGY_KINDS)
    }

    fn check_commodity_references(&self) -> Result<(), SchemaError> {
        let n_commodities = self.n_commodities();
        check_commodity_index("output_commodity", &self.output_commodity, n_commodities)?;
        check_commodity_index("input_commodity", &self.input_commodity, n_commodities)
    }

    fn check_input_offsets(&self) -> Result<(), SchemaError> {
        let expected_len = self.n_units() + 1;
        if self.input_offsets.len() != expected_len {
            return Err(SchemaError::InputOffsetsLength {
                len: self.input_offsets.len(),
                expected: expected_len,
            });
        }

        let first = self.input_offsets[0];
        if first != 0 {
            return Err(SchemaError::InputOffsetsStart { value: first });
        }

        for row in 1..self.input_offsets.len() {
            let previous = self.input_offsets[row - 1];
            let value = self.input_offsets[row];
            if value < previous {
                return Err(SchemaError::InputOffsetsNotMonotonic {
                    row,
                    value,
                    previous,
                });
            }
        }

        let last = self.input_offsets[expected_len - 1];
        let expected_end = self.input_commodity.len();
        if last != expected_end as i64 {
            return Err(SchemaError::InputOffsetsEnd {
                value: last,
                expected: expected_end,
            });
        }
        Ok(())
    }

    fn check_finite_columns(&self) -> Result<(), SchemaError> {
        check_finite("endowment", &self.endowment)?;
        check_finite("technology_scale", &self.technology_scale)?;
        check_finite("input_coefficient", &self.input_coefficient)
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

fn check_kind(
    column: &'static str,
    values: &[i8],
    allowed: &'static [i8],
) -> Result<(), SchemaError> {
    for (row, &value) in values.iter().enumerate() {
        if !allowed.contains(&value) {
            return Err(SchemaError::UnknownKind {
                column,
                row,
                value,
                allowed,
            });
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
                shape: shape.to_vec(),
                product,
                len: array.len(),
            });
        }

        if COLUMN_MAPPING_EXTRA_KEYS.contains(&key.as_str()) {
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
