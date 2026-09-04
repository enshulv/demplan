//! Loading dep1ex scenario files into an [`Economy`].
//!
//! A dep1ex file is a gzipped Clojure source file holding two vectors of maps:
//! `ccs`, the consumption units, and `wcs`, the production units. Values are
//! numbers, vectors of numbers, or booleans, and never contain a colon, so the
//! scanner below finds keys by looking for the next `:`.
//!
//! # Commodity layout
//!
//! The file numbers commodities from 1 within each of its own categories. The
//! loader lays them out in one table, in five contiguous sections:
//!
//! | Section              | `commodity_kind` | Length                                    |
//! |----------------------|------------------|-------------------------------------------|
//! | private consumption  | 0                | `n_priv`, the `:utility-exponents` count   |
//! | public               | 1                | `n_pub`, the `:public-good-exponents` count |
//! | intermediate         | 2                | `n_goods`                                 |
//! | natural resource     | 3                | `n_goods`                                 |
//! | labour               | 4                | `n_goods`                                 |
//!
//! `n_goods` is the largest number appearing in `:product` or in any of the three
//! `:production-inputs` segments. The natural resource and labour sections carry
//! the `endowment` argument; every other section carries zero, because those
//! commodities have to be produced.

use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::Path;

use flate2::read::GzDecoder;

use crate::economy::{
    Economy, ExtraArray, SchemaError, COMMODITY_KIND_INTERMEDIATE, COMMODITY_KIND_LABOR,
    COMMODITY_KIND_NATURE, COMMODITY_KIND_PRIVATE, COMMODITY_KIND_PUBLIC,
    TECHNOLOGY_KIND_COBB_DOUGLAS,
};

/// Marks the start of the production unit vector and the end of the consumption
/// unit vector.
const UNIT_SECTION: &str = "(def wcs";

/// Names used in errors raised while reading a consumption unit record.
const CONSUMPTION_UNIT: &str = "consumption unit";
/// Names used in errors raised while reading a production unit record.
const PRODUCTION_UNIT: &str = "production unit";

/// The three input segments of `:production-inputs`, in file order.
const SEGMENT_NAMES: [&str; 3] = ["intermediate", "nature", "labor"];

/// `:industry` value placing the output in the private consumption section.
const INDUSTRY_PRIVATE: i64 = 0;
/// `:industry` value placing the output in the intermediate section.
const INDUSTRY_INTERMEDIATE: i64 = 1;
/// `:industry` value placing the output in the public section.
const INDUSTRY_PUBLIC: i64 = 2;

/// A dep1ex scenario file that cannot be turned into an [`Economy`].
#[derive(Debug, thiserror::Error)]
pub enum LoadError {
    /// The scenario file cannot be read.
    #[error("cannot read scenario file `{path}`: {source}")]
    Open {
        /// Path that was tried.
        path: String,
        /// Underlying failure.
        source: std::io::Error,
    },

    /// The scenario file is not a readable gzip stream.
    #[error("cannot decompress scenario file `{path}`: {source}")]
    Decompress {
        /// Path that was tried.
        path: String,
        /// Underlying failure.
        source: std::io::Error,
    },

    /// The scenario file lacks one of the two record vectors.
    #[error("scenario file has no `{section}` section")]
    MissingSection {
        /// Marker that was searched for.
        section: &'static str,
    },

    /// A record opens with `{` that is never closed.
    #[error("{record_kind} record {record} is not closed")]
    UnterminatedRecord {
        /// Which vector the record belongs to.
        record_kind: &'static str,
        /// Position of the record within its vector.
        record: usize,
    },

    /// A record lacks a key the loader needs.
    #[error("{record_kind} record {record} has no `:{key}` key")]
    MissingKey {
        /// Which vector the record belongs to.
        record_kind: &'static str,
        /// Position of the record within its vector.
        record: usize,
        /// Key that is absent.
        key: &'static str,
    },

    /// A value that should be a number cannot be parsed as one.
    #[error("{record_kind} record {record}: `:{key}` holds `{text}`, expected a number")]
    Number {
        /// Which vector the record belongs to.
        record_kind: &'static str,
        /// Position of the record within its vector.
        record: usize,
        /// Key whose value is malformed.
        key: &'static str,
        /// Text that was read.
        text: String,
    },

    /// A value does not have the shape the key requires.
    #[error("{record_kind} record {record}: reading `:{key}`, expected {expected}")]
    Syntax {
        /// Which vector the record belongs to.
        record_kind: &'static str,
        /// Position of the record within its vector.
        record: usize,
        /// Key whose value is malformed.
        key: &'static str,
        /// What the scanner required at that point.
        expected: &'static str,
    },

    /// One input segment lists a different number of commodities and exponents.
    #[error(
        "production unit {unit}: the {segment} segment lists {commodities} commodities \
         but {exponents} exponents"
    )]
    InputSegmentLength {
        /// Position of the production unit within its vector.
        unit: usize,
        /// Segment that disagrees.
        segment: &'static str,
        /// Number of commodity numbers in the segment.
        commodities: usize,
        /// Number of exponents for the segment.
        exponents: usize,
    },

    /// A production unit names an industry with no commodity section.
    #[error("production unit {unit}: `:industry` is {value}, expected 0, 1 or 2")]
    UnknownIndustry {
        /// Position of the production unit within its vector.
        unit: usize,
        /// Value found.
        value: i64,
    },

    /// Consumption units disagree on how many exponents they carry.
    ///
    /// The exponents form one rectangle across all consumption units, so every
    /// record has to list as many as the first one.
    #[error(
        "consumption unit {consumer}: `:{key}` lists {count} exponents, \
         expected {expected} to match the first record"
    )]
    ConsumerExponentCount {
        /// Position of the consumption unit within its vector.
        consumer: usize,
        /// Key whose length disagrees.
        key: &'static str,
        /// Number of exponents found.
        count: usize,
        /// Number of exponents the first record set.
        expected: usize,
    },

    /// The assembled economy breaches the data model.
    #[error("the loaded economy breaches the data model: {0}")]
    Schema(#[from] SchemaError),
}

/// Reads a dep1ex scenario file and returns the economy it describes.
///
/// `endowment` is the quantity of every natural resource and every kind of
/// labour available in the period. The file does not carry it; the paper this
/// data comes from uses 1000.
///
/// The returned economy is in period 0 and has passed [`Economy::validate`].
/// Commodity numbering, section order and the endowment rule are described in
/// the module documentation.
pub fn load_dep1ex(path: impl AsRef<Path>, endowment: f64) -> Result<Economy, LoadError> {
    let path = path.as_ref();
    let text = read_scenario(path)?;

    let split = find_marker(&text, UNIT_SECTION.as_bytes()).ok_or(LoadError::MissingSection {
        section: UNIT_SECTION,
    })?;

    let consumers = parse_consumption_units(&text[..split])?;
    let units = parse_production_units(&text[split..])?;

    let economy = assemble(consumers, units, endowment)?;
    economy.validate()?;
    Ok(economy)
}

/// Reads and decompresses the scenario file into memory in one pass.
fn read_scenario(path: &Path) -> Result<Vec<u8>, LoadError> {
    let compressed = fs::read(path).map_err(|source| LoadError::Open {
        path: path.display().to_string(),
        source,
    })?;

    let mut text = Vec::with_capacity(decompressed_size_hint(&compressed));
    GzDecoder::new(compressed.as_slice())
        .read_to_end(&mut text)
        .map_err(|source| LoadError::Decompress {
            path: path.display().to_string(),
            source,
        })?;
    Ok(text)
}

/// Reads the ISIZE trailer of a gzip stream, which holds the decompressed size
/// modulo 2^32.
///
/// This is a capacity hint only. A multi-member or larger-than-4-GiB stream
/// still decompresses correctly; the output buffer just grows on its own.
fn decompressed_size_hint(compressed: &[u8]) -> usize {
    let Some(trailer) = compressed.len().checked_sub(4) else {
        return 0;
    };
    let mut bytes = [0u8; 4];
    bytes.copy_from_slice(&compressed[trailer..]);
    u32::from_le_bytes(bytes) as usize
}

/// Returns the offset of the first occurrence of `needle` in `haystack`.
fn find_marker(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    let first = *needle.first()?;
    let mut from = 0;
    while let Some(offset) = haystack[from..].iter().position(|&b| b == first) {
        let start = from + offset;
        if haystack[start..].starts_with(needle) {
            return Some(start);
        }
        from = start + 1;
    }
    None
}

/// Walks the `{...}` maps of one record vector.
struct RecordIter<'a> {
    bytes: &'a [u8],
    pos: usize,
    record_kind: &'static str,
    index: usize,
}

impl<'a> RecordIter<'a> {
    fn new(bytes: &'a [u8], record_kind: &'static str) -> Self {
        Self {
            bytes,
            pos: 0,
            record_kind,
            index: 0,
        }
    }

    /// Returns the position and body of the next record, braces excluded.
    fn next_body(&mut self) -> Result<Option<(usize, &'a [u8])>, LoadError> {
        let Some(offset) = self.bytes[self.pos..].iter().position(|&b| b == b'{') else {
            return Ok(None);
        };
        let start = self.pos + offset;
        let index = self.index;
        self.index += 1;

        let mut depth = 0usize;
        for (offset, &byte) in self.bytes[start..].iter().enumerate() {
            match byte {
                b'{' => depth += 1,
                b'}' => {
                    depth -= 1;
                    if depth == 0 {
                        self.pos = start + offset + 1;
                        return Ok(Some((index, &self.bytes[start + 1..start + offset])));
                    }
                }
                _ => {}
            }
        }
        Err(LoadError::UnterminatedRecord {
            record_kind: self.record_kind,
            record: index,
        })
    }
}

/// Scans the keys and values of one record body.
struct Cursor<'a> {
    bytes: &'a [u8],
    pos: usize,
    record_kind: &'static str,
    record: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8], record_kind: &'static str, record: usize) -> Self {
        Self {
            bytes,
            pos: 0,
            record_kind,
            record,
        }
    }

    /// Advances to the next `:keyword` and returns its name.
    ///
    /// Values in this format never contain a colon, so an unread value needs no
    /// explicit skip: scanning forward to the next colon steps over it.
    fn next_key(&mut self) -> Option<&'a [u8]> {
        let offset = self.bytes[self.pos..].iter().position(|&b| b == b':')?;
        let start = self.pos + offset + 1;
        let mut end = start;
        while let Some(&byte) = self.bytes.get(end) {
            if byte.is_ascii_alphanumeric() || byte == b'-' {
                end += 1;
            } else {
                break;
            }
        }
        self.pos = end;
        Some(&self.bytes[start..end])
    }

    /// Steps over whitespace and commas, which Clojure treats alike.
    fn skip_space(&mut self) {
        while let Some(&byte) = self.bytes.get(self.pos) {
            if byte.is_ascii_whitespace() || byte == b',' {
                self.pos += 1;
            } else {
                break;
            }
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.pos).copied()
    }

    fn expect(
        &mut self,
        byte: u8,
        key: &'static str,
        expected: &'static str,
    ) -> Result<(), LoadError> {
        self.skip_space();
        if self.peek() == Some(byte) {
            self.pos += 1;
            return Ok(());
        }
        Err(self.syntax_error(key, expected))
    }

    fn syntax_error(&self, key: &'static str, expected: &'static str) -> LoadError {
        LoadError::Syntax {
            record_kind: self.record_kind,
            record: self.record,
            key,
            expected,
        }
    }

    fn number_error(&self, token: &[u8], key: &'static str) -> LoadError {
        LoadError::Number {
            record_kind: self.record_kind,
            record: self.record,
            key,
            text: String::from_utf8_lossy(token).into_owned(),
        }
    }

    /// Consumes the longest run of characters that can appear inside a number.
    fn number_token(&mut self) -> &'a [u8] {
        self.skip_space();
        let start = self.pos;
        while let Some(&byte) = self.bytes.get(self.pos) {
            if byte.is_ascii_digit() || matches!(byte, b'+' | b'-' | b'.' | b'e' | b'E') {
                self.pos += 1;
            } else {
                break;
            }
        }
        &self.bytes[start..self.pos]
    }

    fn to_f64(&self, token: &[u8], key: &'static str) -> Result<f64, LoadError> {
        std::str::from_utf8(token)
            .ok()
            .and_then(|text| text.parse::<f64>().ok())
            .ok_or_else(|| self.number_error(token, key))
    }

    fn to_i64(&self, token: &[u8], key: &'static str) -> Result<i64, LoadError> {
        std::str::from_utf8(token)
            .ok()
            .and_then(|text| text.parse::<i64>().ok())
            .ok_or_else(|| self.number_error(token, key))
    }

    fn read_f64(&mut self, key: &'static str) -> Result<f64, LoadError> {
        let token = self.number_token();
        self.to_f64(token, key)
    }

    fn read_i64(&mut self, key: &'static str) -> Result<i64, LoadError> {
        let token = self.number_token();
        self.to_i64(token, key)
    }

    fn read_f64_vector(&mut self, key: &'static str, out: &mut Vec<f64>) -> Result<(), LoadError> {
        self.expect(b'[', key, "`[`")?;
        loop {
            self.skip_space();
            if self.peek() == Some(b']') {
                self.pos += 1;
                return Ok(());
            }
            let token = self.number_token();
            if token.is_empty() {
                return Err(self.syntax_error(key, "a number or `]`"));
            }
            let value = self.to_f64(token, key)?;
            out.push(value);
        }
    }

    fn read_i64_vector(&mut self, key: &'static str, out: &mut Vec<i64>) -> Result<(), LoadError> {
        self.expect(b'[', key, "`[`")?;
        loop {
            self.skip_space();
            if self.peek() == Some(b']') {
                self.pos += 1;
                return Ok(());
            }
            let token = self.number_token();
            if token.is_empty() {
                return Err(self.syntax_error(key, "a number or `]`"));
            }
            let value = self.to_i64(token, key)?;
            out.push(value);
        }
    }

    /// Reads `[[..] [..] [..]]`, the three input segments of one production unit.
    fn read_input_segments(
        &mut self,
        key: &'static str,
        out: &mut [Vec<i64>; 3],
    ) -> Result<(), LoadError> {
        self.expect(b'[', key, "`[`")?;
        for segment in out.iter_mut() {
            self.read_i64_vector(key, segment)?;
        }
        self.expect(b']', key, "`]` after three input segments")
    }
}

/// Everything read from the `ccs` vector.
struct ConsumptionUnits {
    n_priv: usize,
    n_pub: usize,
    income: Vec<f64>,
    /// Row-major, one row per unit: private exponents then public exponents.
    utility_exponent: Vec<f64>,
}

/// Everything read from the `wcs` vector, still in the numbering of the file.
struct ProductionUnits {
    technology_scale: Vec<f64>,
    effort_c: Vec<f64>,
    effort_s: Vec<f64>,
    effort_k: Vec<f64>,
    industry: Vec<i64>,
    product: Vec<i64>,
    /// Commodity numbers, flattened per unit in segment order.
    input_number: Vec<i64>,
    /// Segment each `input_number` entry came from, as an index into `SEGMENT_NAMES`.
    input_segment: Vec<u8>,
    input_coefficient: Vec<f64>,
    input_offsets: Vec<i64>,
}

fn parse_consumption_units(region: &[u8]) -> Result<ConsumptionUnits, LoadError> {
    let mut income = Vec::new();
    let mut utility_exponent = Vec::new();
    let mut private_exponents = Vec::new();
    let mut public_exponents = Vec::new();
    let mut n_priv = 0usize;
    let mut n_pub = 0usize;

    let mut records = RecordIter::new(region, CONSUMPTION_UNIT);
    while let Some((record, body)) = records.next_body()? {
        private_exponents.clear();
        public_exponents.clear();
        let mut saw_private = false;
        let mut saw_public = false;
        let mut record_income = None;

        let mut cursor = Cursor::new(body, CONSUMPTION_UNIT, record);
        while let Some(key) = cursor.next_key() {
            match key {
                b"utility-exponents" => {
                    cursor.read_f64_vector("utility-exponents", &mut private_exponents)?;
                    saw_private = true;
                }
                b"public-good-exponents" => {
                    cursor.read_f64_vector("public-good-exponents", &mut public_exponents)?;
                    saw_public = true;
                }
                b"income" => record_income = Some(cursor.read_f64("income")?),
                _ => {}
            }
        }

        let missing = |key| LoadError::MissingKey {
            record_kind: CONSUMPTION_UNIT,
            record,
            key,
        };
        if !saw_private {
            return Err(missing("utility-exponents"));
        }
        if !saw_public {
            return Err(missing("public-good-exponents"));
        }
        let Some(value) = record_income else {
            return Err(missing("income"));
        };

        if record == 0 {
            n_priv = private_exponents.len();
            n_pub = public_exponents.len();
        } else {
            check_exponent_count(record, "utility-exponents", private_exponents.len(), n_priv)?;
            check_exponent_count(
                record,
                "public-good-exponents",
                public_exponents.len(),
                n_pub,
            )?;
        }

        income.push(value);
        utility_exponent.extend_from_slice(&private_exponents);
        utility_exponent.extend_from_slice(&public_exponents);
    }

    Ok(ConsumptionUnits {
        n_priv,
        n_pub,
        income,
        utility_exponent,
    })
}

fn check_exponent_count(
    consumer: usize,
    key: &'static str,
    count: usize,
    expected: usize,
) -> Result<(), LoadError> {
    if count == expected {
        return Ok(());
    }
    Err(LoadError::ConsumerExponentCount {
        consumer,
        key,
        count,
        expected,
    })
}

fn parse_production_units(region: &[u8]) -> Result<ProductionUnits, LoadError> {
    let mut units = ProductionUnits {
        technology_scale: Vec::new(),
        effort_c: Vec::new(),
        effort_s: Vec::new(),
        effort_k: Vec::new(),
        industry: Vec::new(),
        product: Vec::new(),
        input_number: Vec::new(),
        input_segment: Vec::new(),
        input_coefficient: Vec::new(),
        input_offsets: vec![0],
    };

    let mut numbers: [Vec<i64>; 3] = Default::default();
    let mut exponents: [Vec<f64>; 3] = Default::default();

    let mut records = RecordIter::new(region, PRODUCTION_UNIT);
    while let Some((record, body)) = records.next_body()? {
        for segment in numbers.iter_mut() {
            segment.clear();
        }
        for segment in exponents.iter_mut() {
            segment.clear();
        }

        let mut scale = None;
        let mut effort_c = None;
        let mut effort_s = None;
        let mut effort_k = None;
        let mut industry = None;
        let mut product = None;
        let mut saw_segments = false;
        let mut saw_exponents = [false; 3];

        let mut cursor = Cursor::new(body, PRODUCTION_UNIT, record);
        while let Some(key) = cursor.next_key() {
            match key {
                b"a" => scale = Some(cursor.read_f64("a")?),
                b"c" => effort_c = Some(cursor.read_f64("c")?),
                b"s" => effort_s = Some(cursor.read_f64("s")?),
                b"du" => effort_k = Some(cursor.read_f64("du")?),
                b"industry" => industry = Some(cursor.read_i64("industry")?),
                b"product" => product = Some(cursor.read_i64("product")?),
                b"production-inputs" => {
                    cursor.read_input_segments("production-inputs", &mut numbers)?;
                    saw_segments = true;
                }
                b"input-exponents" => {
                    cursor.read_f64_vector("input-exponents", &mut exponents[0])?;
                    saw_exponents[0] = true;
                }
                b"nature-exponents" => {
                    cursor.read_f64_vector("nature-exponents", &mut exponents[1])?;
                    saw_exponents[1] = true;
                }
                b"labor-exponents" => {
                    cursor.read_f64_vector("labor-exponents", &mut exponents[2])?;
                    saw_exponents[2] = true;
                }
                _ => {}
            }
        }

        let missing = |key| LoadError::MissingKey {
            record_kind: PRODUCTION_UNIT,
            record,
            key,
        };
        let (Some(scale), Some(effort_c), Some(effort_s), Some(effort_k)) =
            (scale, effort_c, effort_s, effort_k)
        else {
            return Err(missing(first_missing(&[
                ("a", scale.is_some()),
                ("c", effort_c.is_some()),
                ("s", effort_s.is_some()),
                ("du", effort_k.is_some()),
            ])));
        };
        let (Some(industry), Some(product)) = (industry, product) else {
            return Err(missing(first_missing(&[
                ("industry", industry.is_some()),
                ("product", product.is_some()),
            ])));
        };
        if !saw_segments {
            return Err(missing("production-inputs"));
        }
        if !saw_exponents[0] {
            return Err(missing("input-exponents"));
        }
        if !saw_exponents[1] {
            return Err(missing("nature-exponents"));
        }
        if !saw_exponents[2] {
            return Err(missing("labor-exponents"));
        }

        units.technology_scale.push(scale);
        units.effort_c.push(effort_c);
        units.effort_s.push(effort_s);
        units.effort_k.push(effort_k);
        units.industry.push(industry);
        units.product.push(product);

        for segment in 0..SEGMENT_NAMES.len() {
            if numbers[segment].len() != exponents[segment].len() {
                return Err(LoadError::InputSegmentLength {
                    unit: record,
                    segment: SEGMENT_NAMES[segment],
                    commodities: numbers[segment].len(),
                    exponents: exponents[segment].len(),
                });
            }
            units.input_number.extend_from_slice(&numbers[segment]);
            units
                .input_coefficient
                .extend_from_slice(&exponents[segment]);
            units
                .input_segment
                .extend(std::iter::repeat_n(segment as u8, numbers[segment].len()));
        }
        units.input_offsets.push(units.input_number.len() as i64);
    }

    Ok(units)
}

/// Returns the first key of `keys` that was not seen.
///
/// Only called once a required key is known to be absent, so the fallback never
/// reaches an error message in practice.
fn first_missing(keys: &[(&'static str, bool)]) -> &'static str {
    keys.iter()
        .find(|(_, seen)| !seen)
        .map(|(key, _)| *key)
        .unwrap_or("")
}

/// Turns the parsed records into an economy, taking ownership so the parse
/// buffers become the economy's columns instead of being copied.
fn assemble(
    consumers: ConsumptionUnits,
    units: ProductionUnits,
    endowment: f64,
) -> Result<Economy, LoadError> {
    let n_goods = largest_commodity_number(&units);
    let n_priv = consumers.n_priv;
    let n_pub = consumers.n_pub;

    let base_private = 0i64;
    let base_public = n_priv as i64;
    let base_intermediate = (n_priv + n_pub) as i64;
    let base_nature = base_intermediate + n_goods as i64;
    let base_labor = base_nature + n_goods as i64;

    let n_commodities = n_priv + n_pub + 3 * n_goods;
    let mut commodity_kind = Vec::with_capacity(n_commodities);
    commodity_kind.extend(std::iter::repeat_n(COMMODITY_KIND_PRIVATE, n_priv));
    commodity_kind.extend(std::iter::repeat_n(COMMODITY_KIND_PUBLIC, n_pub));
    commodity_kind.extend(std::iter::repeat_n(COMMODITY_KIND_INTERMEDIATE, n_goods));
    commodity_kind.extend(std::iter::repeat_n(COMMODITY_KIND_NATURE, n_goods));
    commodity_kind.extend(std::iter::repeat_n(COMMODITY_KIND_LABOR, n_goods));

    let endowment_column = commodity_kind
        .iter()
        .map(|&kind| {
            if kind == COMMODITY_KIND_NATURE || kind == COMMODITY_KIND_LABOR {
                endowment
            } else {
                0.0
            }
        })
        .collect();

    let mut output_commodity = Vec::with_capacity(units.product.len());
    for (unit, (&industry, &product)) in units.industry.iter().zip(&units.product).enumerate() {
        let base = match industry {
            INDUSTRY_PRIVATE => base_private,
            INDUSTRY_INTERMEDIATE => base_intermediate,
            INDUSTRY_PUBLIC => base_public,
            value => return Err(LoadError::UnknownIndustry { unit, value }),
        };
        output_commodity.push(base + product - 1);
    }

    // The file numbers commodities from 1 inside each segment; rebase them onto
    // the section the segment maps to, in place.
    let segment_base = [base_intermediate, base_nature, base_labor];
    let mut input_commodity = units.input_number;
    for (value, &segment) in input_commodity.iter_mut().zip(&units.input_segment) {
        *value = segment_base[segment as usize] + *value - 1;
    }

    let n_units = units.product.len();
    let unit_extra = BTreeMap::from([
        (
            "effort_c".to_string(),
            ExtraArray::F64 {
                shape: vec![n_units],
                data: units.effort_c,
            },
        ),
        (
            "effort_s".to_string(),
            ExtraArray::F64 {
                shape: vec![n_units],
                data: units.effort_s,
            },
        ),
        (
            "effort_k".to_string(),
            ExtraArray::F64 {
                shape: vec![n_units],
                data: units.effort_k,
            },
        ),
    ]);

    let n_consumers = consumers.income.len();
    let utility_columns: Vec<i64> = (base_private..base_private + n_priv as i64)
        .chain(base_public..base_public + n_pub as i64)
        .collect();
    let consumer_extra = BTreeMap::from([
        (
            "entitlement".to_string(),
            ExtraArray::F64 {
                shape: vec![n_consumers],
                data: consumers.income,
            },
        ),
        (
            "utility_exponent".to_string(),
            ExtraArray::F64 {
                shape: vec![n_consumers, n_priv + n_pub],
                data: consumers.utility_exponent,
            },
        ),
        (
            "utility_exponent_commodity".to_string(),
            ExtraArray::I64 {
                shape: vec![utility_columns.len()],
                data: utility_columns,
            },
        ),
    ]);

    Ok(Economy {
        period: 0,
        commodity_id: (0..n_commodities as i64).collect(),
        commodity_kind,
        endowment: endowment_column,
        commodity_extra: BTreeMap::new(),
        unit_id: (0..n_units as i64).collect(),
        unit_group: output_commodity.clone(),
        output_commodity,
        technology_kind: vec![TECHNOLOGY_KIND_COBB_DOUGLAS; n_units],
        technology_scale: units.technology_scale,
        input_offsets: units.input_offsets,
        input_commodity,
        input_coefficient: units.input_coefficient,
        unit_extra,
        consumer_id: (0..n_consumers as i64).collect(),
        consumer_group: vec![0; n_consumers],
        consumer_extra,
    })
}

/// Returns the largest commodity number written in the production unit records.
///
/// The file numbers intermediate goods, natural resources and labour with the
/// same range, so one count sizes all three sections.
fn largest_commodity_number(units: &ProductionUnits) -> usize {
    let largest = units
        .product
        .iter()
        .chain(&units.input_number)
        .copied()
        .max()
        .unwrap_or(0);
    largest.max(0) as usize
}
