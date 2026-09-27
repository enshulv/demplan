//! Loading a dep1ex scenario file into an `Economy`.
//!
//! The fixture is a hand-written dep1ex file small enough to state every expected
//! column literally. Its numbers are pairwise distinct so that a column read from
//! the wrong key cannot go unnoticed.
//!
//! Fixture layout: 2 consumers with 4 private and 2 public exponents each, and 3
//! production units, one per `:industry` value. The largest `:product` number is
//! 4 and the largest input number is 3, so a loader that folded `:product` into
//! the goods count would lay out 18 commodities instead of 15.

use std::collections::hash_map::DefaultHasher;
use std::fs;
use std::hash::{Hash, Hasher};
use std::io::Write;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};

use demplan_core::{load_dep1ex, Economy, ExtraArray, LoadError};
use flate2::write::GzEncoder;
use flate2::Compression;

const N_PRIV: i64 = 4;
const N_PUB: i64 = 2;
const N_GOODS: i64 = 3;

const BASE_PRIV: i64 = 0;
const BASE_PUB: i64 = N_PRIV;
const BASE_INTER: i64 = N_PRIV + N_PUB;
const BASE_NATURE: i64 = BASE_INTER + N_GOODS;
const BASE_LABOR: i64 = BASE_NATURE + N_GOODS;
const N_COMMODITIES: usize = (N_PRIV + N_PUB + 3 * N_GOODS) as usize;

/// Endowment deliberately unlike the paper value of 1000, so a hard-coded
/// constant in the loader would show up.
const TEST_ENDOWMENT: f64 = 7.5;

const CONSUMER_RECORDS: &str = "\
[{:effort 1,
  :num-workers 10,
  :utility-exponents [0.5 0.25 0.45 0.35],
  :final-demands [0 0],
  :cy 1,
  :public-good-exponents [0.125 0.0625],
  :public-good-demands [0],
  :income 5000}
 {:income 250.5,
  :public-good-exponents [0.3 0.4],
  :utility-exponents [0.1 0.2 0.15 0.05],
  :effort 1,
  :num-workers 10,
  :final-demands [0 0],
  :cy 1,
  :public-good-demands [0]}]";

const UNIT_RECORDS: &str = "\
[{:effort 0.5,
  :labor-exponents [0.14],
  :industry 0,
  :output 0,
  :s 1,
  :du 3.0,
  :c 0.61,
  :product 4,
  :labor-quantities [0],
  :production-inputs [[1 3] [2] [3]],
  :input-exponents [0.11 0.12],
  :toothache false,
  :nature-exponents [0.13],
  :a 2.0}
 {:effort 0.5,
  :labor-exponents [0.24],
  :industry 1,
  :output 0,
  :s 1.5,
  :du 3.5,
  :c 0.62,
  :product 2,
  :labor-quantities [0],
  :production-inputs [[2] [1 3] [1]],
  :input-exponents [0.21],
  :toothache false,
  :nature-exponents [0.22 0.23],
  :a 4.0}
 {:effort 0.5,
  :labor-exponents [0.34 0.35],
  :industry 2,
  :output 0,
  :s 2,
  :du 4.5,
  :c 0.63,
  :product 1,
  :labor-quantities [0],
  :production-inputs [[3] [3] [2 3]],
  :input-exponents [0.31],
  :toothache false,
  :nature-exponents [0.32],
  :a 5.0}]";

/// Assembles a dep1ex source file from the two record vectors.
fn scenario_text(consumers: &str, units: &str) -> String {
    format!("(ns pequod-cljs.fixture)\n\n(def ccs \n{consumers}\n)\n\n(def wcs \n{units}\n)\n")
}

/// Writes `bytes` to a uniquely named file under the temporary directory and
/// returns its path. Files are left behind on failure so the input can be
/// inspected.
fn temp_file(label: &str, bytes: &[u8]) -> PathBuf {
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    let mut hasher = DefaultHasher::new();
    std::process::id().hash(&mut hasher);
    let serial = COUNTER.fetch_add(1, Ordering::Relaxed);

    let dir = std::env::temp_dir().join("demplan-tests");
    fs::create_dir_all(&dir).expect("create temp directory");
    let path = dir.join(format!("{label}-{:x}-{serial}.clj.gz", hasher.finish()));
    fs::write(&path, bytes).expect("write temp file");
    path
}

/// Gzips `text` and writes it to a temporary file.
fn gzip_file(label: &str, text: &str) -> PathBuf {
    let mut encoder = GzEncoder::new(Vec::new(), Compression::fast());
    encoder.write_all(text.as_bytes()).expect("gzip fixture");
    temp_file(label, &encoder.finish().expect("finish gzip stream"))
}

/// Loads the fixture scenario with `TEST_ENDOWMENT`.
fn fixture_economy() -> Economy {
    let path = gzip_file("fixture", &scenario_text(CONSUMER_RECORDS, UNIT_RECORDS));
    load_dep1ex(&path, TEST_ENDOWMENT).expect("fixture loads")
}

/// Returns the `f64` payload of an extra array, failing if the key is absent or
/// holds integers.
fn extra_f64<'a>(bag: &'a std::collections::BTreeMap<String, ExtraArray>, key: &str) -> &'a [f64] {
    match bag.get(key) {
        Some(ExtraArray::F64 { data, .. }) => data,
        other => panic!("expected f64 extra array at {key}, found {other:?}"),
    }
}

/// Returns the shape of an extra array, failing if the key is absent.
fn extra_shape(bag: &std::collections::BTreeMap<String, ExtraArray>, key: &str) -> Vec<usize> {
    match bag.get(key) {
        Some(array) => array.shape(),
        None => panic!("expected an extra array at {key}"),
    }
}

/// Returns the `hahnel_kind` label column, failing if it is absent or not text.
fn hahnel_kind(economy: &Economy) -> Vec<&str> {
    match economy.commodity_extra.get("hahnel_kind") {
        Some(ExtraArray::Text { data }) => data.iter().map(String::as_str).collect(),
        other => panic!("expected a text extra array at hahnel_kind, found {other:?}"),
    }
}

// ---- commodity table ----

#[test]
fn load_derives_the_commodity_count_from_the_largest_number_in_the_file() {
    assert_eq!(fixture_economy().commodity_id.len(), N_COMMODITIES);
}

#[test]
fn load_sizes_the_goods_sections_from_the_input_numbers_alone() {
    // `:product` numbers the private and public sections, which have their own
    // lengths, so folding it into the goods count invents commodities that
    // nothing produces and nothing consumes.
    let economy = fixture_economy();
    let largest_product = 4;
    assert!(largest_product > N_GOODS);
    assert_eq!(
        hahnel_kind(&economy)
            .iter()
            .filter(|&&label| label == "intermediate")
            .count(),
        N_GOODS as usize
    );
    assert_eq!(
        economy.commodity_id.len(),
        (N_PRIV + N_PUB + 3 * N_GOODS) as usize
    );
}

#[test]
fn load_labels_commodities_private_public_intermediate_nature_labour() {
    assert_eq!(
        hahnel_kind(&fixture_economy()),
        vec![
            "private_good",
            "private_good",
            "private_good",
            "private_good",
            "public_good",
            "public_good",
            "intermediate",
            "intermediate",
            "intermediate",
            "natural_resource",
            "natural_resource",
            "natural_resource",
            "labor",
            "labor",
            "labor",
        ]
    );
}

#[test]
fn load_stores_the_labels_as_one_text_value_per_commodity() {
    let economy = fixture_economy();
    assert_eq!(
        extra_shape(&economy.commodity_extra, "hahnel_kind"),
        [N_COMMODITIES]
    );
}

#[test]
fn load_sets_endowment_exactly_where_the_label_is_natural_resource_or_labour() {
    let economy = fixture_economy();
    for (row, label) in hahnel_kind(&economy).into_iter().enumerate() {
        let expected = match label {
            "natural_resource" | "labor" => TEST_ENDOWMENT,
            _ => 0.0,
        };
        assert_eq!(economy.endowment[row], expected, "row {row} ({label})");
    }
}

#[test]
fn load_sets_endowment_on_nature_and_labour_only() {
    let e = TEST_ENDOWMENT;
    assert_eq!(
        fixture_economy().endowment,
        vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, e, e, e, e, e, e]
    );
}

#[test]
fn load_puts_only_the_label_column_in_the_commodity_extra_bag() {
    let economy = fixture_economy();
    let keys: Vec<&str> = economy.commodity_extra.keys().map(String::as_str).collect();
    assert_eq!(keys, ["hahnel_kind"]);
}

// ---- production units ----

#[test]
fn load_maps_each_industry_to_its_commodity_section() {
    // industry 0 -> private, 1 -> intermediate, 2 -> public; product numbers 4, 2, 1.
    assert_eq!(
        fixture_economy().output_commodity,
        vec![BASE_PRIV + 3, BASE_INTER + 1, BASE_PUB]
    );
}

#[test]
fn load_gives_every_unit_exactly_one_output_entry() {
    let economy = fixture_economy();
    assert_eq!(economy.output_offsets, vec![0, 1, 2, 3]);
    assert_eq!(economy.n_outputs(), 3);
}

#[test]
fn load_sets_every_output_coefficient_to_one() {
    assert_eq!(fixture_economy().output_coefficient, vec![1.0, 1.0, 1.0]);
}

#[test]
fn load_puts_each_output_in_the_section_its_industry_names() {
    // industry 0 -> private good, 1 -> intermediate, 2 -> public good.
    let economy = fixture_economy();
    let labels = hahnel_kind(&economy);
    let output_labels: Vec<&str> = economy
        .output_commodity
        .iter()
        .map(|&commodity| labels[commodity as usize])
        .collect();
    assert_eq!(
        output_labels,
        ["private_good", "intermediate", "public_good"]
    );
}

#[test]
fn load_puts_each_input_segment_in_its_own_section() {
    // Segment order in the file: intermediate, nature, labour; see
    // `load_expands_input_segments_in_intermediate_nature_labour_order`.
    let economy = fixture_economy();
    let labels = hahnel_kind(&economy);
    let input_labels: Vec<&str> = economy
        .input_commodity
        .iter()
        .map(|&commodity| labels[commodity as usize])
        .collect();
    assert_eq!(
        input_labels,
        [
            "intermediate",
            "intermediate",
            "natural_resource",
            "labor",
            "intermediate",
            "natural_resource",
            "natural_resource",
            "labor",
            "intermediate",
            "natural_resource",
            "labor",
            "labor",
        ]
    );
}

#[test]
fn load_labels_every_unit_with_the_hahnel_effort_technology() {
    assert_eq!(
        fixture_economy().technology_kind,
        vec![
            "hahnel_cobb_douglas_effort",
            "hahnel_cobb_douglas_effort",
            "hahnel_cobb_douglas_effort"
        ]
    );
}

#[test]
fn load_reads_technology_scale_from_the_a_key() {
    assert_eq!(fixture_economy().technology_scale, vec![2.0, 4.0, 5.0]);
}

#[test]
fn load_expands_input_segments_in_intermediate_nature_labour_order() {
    assert_eq!(
        fixture_economy().input_commodity,
        vec![
            // unit 0: intermediate 1, 3; nature 2; labour 3
            BASE_INTER,
            BASE_INTER + 2,
            BASE_NATURE + 1,
            BASE_LABOR + 2,
            // unit 1: intermediate 2; nature 1, 3; labour 1
            BASE_INTER + 1,
            BASE_NATURE,
            BASE_NATURE + 2,
            BASE_LABOR,
            // unit 2: intermediate 3; nature 3; labour 2, 3
            BASE_INTER + 2,
            BASE_NATURE + 2,
            BASE_LABOR + 1,
            BASE_LABOR + 2,
        ]
    );
}

#[test]
fn load_pairs_each_input_commodity_with_the_exponent_of_its_segment() {
    assert_eq!(
        fixture_economy().input_coefficient,
        vec![0.11, 0.12, 0.13, 0.14, 0.21, 0.22, 0.23, 0.24, 0.31, 0.32, 0.34, 0.35]
    );
}

#[test]
fn load_builds_input_offsets_from_the_per_unit_input_counts() {
    assert_eq!(fixture_economy().input_offsets, vec![0, 4, 8, 12]);
}

#[test]
fn load_reads_the_effort_parameters_into_the_unit_extra_bag() {
    let economy = fixture_economy();
    assert_eq!(
        extra_f64(&economy.unit_extra, "effort_c"),
        [0.61, 0.62, 0.63]
    );
    assert_eq!(extra_f64(&economy.unit_extra, "effort_s"), [1.0, 1.5, 2.0]);
    assert_eq!(extra_f64(&economy.unit_extra, "effort_k"), [3.0, 3.5, 4.5]);
}

#[test]
fn load_shapes_the_effort_parameters_as_one_value_per_unit() {
    let economy = fixture_economy();
    assert_eq!(extra_shape(&economy.unit_extra, "effort_c"), [3]);
}

// ---- consumption units ----

#[test]
fn load_reads_income_into_the_entitlement_key() {
    let economy = fixture_economy();
    assert_eq!(
        extra_f64(&economy.consumer_extra, "entitlement"),
        [5000.0, 250.5]
    );
}

#[test]
fn load_concatenates_private_exponents_then_public_exponents() {
    let economy = fixture_economy();
    assert_eq!(
        extra_f64(&economy.consumer_extra, "utility_exponent"),
        [0.5, 0.25, 0.45, 0.35, 0.125, 0.0625, 0.1, 0.2, 0.15, 0.05, 0.3, 0.4]
    );
}

#[test]
fn load_shapes_utility_exponents_as_consumers_by_columns() {
    let economy = fixture_economy();
    assert_eq!(
        extra_shape(&economy.consumer_extra, "utility_exponent"),
        [2, 6]
    );
}

#[test]
fn load_maps_utility_exponent_columns_to_private_then_public_commodities() {
    let economy = fixture_economy();
    let mapping = match economy.consumer_extra.get("utility_exponent_commodity") {
        Some(ExtraArray::I64 { data, .. }) => data.clone(),
        other => panic!("expected an integer mapping, found {other:?}"),
    };
    assert_eq!(
        mapping,
        vec![
            BASE_PRIV,
            BASE_PRIV + 1,
            BASE_PRIV + 2,
            BASE_PRIV + 3,
            BASE_PUB,
            BASE_PUB + 1
        ]
    );
}

// ---- identifiers and period ----

#[test]
fn load_sets_identifier_columns_to_the_row_index() {
    let economy = fixture_economy();
    assert_eq!(
        economy.commodity_id,
        (0..N_COMMODITIES as i64).collect::<Vec<_>>()
    );
    assert_eq!(economy.unit_id, vec![0, 1, 2]);
    assert_eq!(economy.consumer_id, vec![0, 1]);
}

#[test]
fn load_sets_the_period_to_zero() {
    assert_eq!(fixture_economy().period, 0);
}

#[test]
fn load_returns_an_economy_that_passes_validate() {
    assert_eq!(fixture_economy().validate(), Ok(()));
}

// ---- rejected inputs ----

#[test]
fn load_rejects_an_input_segment_whose_exponent_count_differs() {
    let units = UNIT_RECORDS.replace(":nature-exponents [0.13]", ":nature-exponents [0.13 0.19]");
    let path = gzip_file("segment-mismatch", &scenario_text(CONSUMER_RECORDS, &units));

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::InputSegmentLength { unit, segment, commodities, exponents }
            if unit == 0 && segment == "nature" && commodities == 1 && exponents == 2
    ));
}

#[test]
fn an_input_segment_mismatch_counts_one_commodity_in_the_singular() {
    let units = UNIT_RECORDS.replace(":nature-exponents [0.13]", ":nature-exponents [0.13 0.19]");
    let path = gzip_file(
        "segment-one-commodity",
        &scenario_text(CONSUMER_RECORDS, &units),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert_eq!(
        err.to_string(),
        "production unit 0: the nature segment lists 1 commodity but 2 exponents"
    );
}

#[test]
fn an_input_segment_mismatch_counts_one_exponent_in_the_singular() {
    let units = UNIT_RECORDS.replace(":input-exponents [0.11 0.12]", ":input-exponents [0.11]");
    let path = gzip_file(
        "segment-one-exponent",
        &scenario_text(CONSUMER_RECORDS, &units),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert_eq!(
        err.to_string(),
        "production unit 0: the intermediate segment lists 2 commodities but 1 exponent"
    );
}

#[test]
fn load_rejects_a_private_product_number_past_the_private_section() {
    let units = UNIT_RECORDS.replace(":product 4,", ":product 5,");
    let path = gzip_file(
        "product-past-private",
        &scenario_text(CONSUMER_RECORDS, &units),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::SectionNumber { unit, section, value, bound }
            if unit == 0 && section == "private" && value == 5 && bound == N_PRIV as usize
    ));
}

#[test]
fn load_rejects_a_public_product_number_past_the_public_section() {
    let units = UNIT_RECORDS.replace(":product 1,", ":product 3,");
    let path = gzip_file(
        "product-past-public",
        &scenario_text(CONSUMER_RECORDS, &units),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::SectionNumber { unit, section, value, bound }
            if unit == 2 && section == "public" && value == 3 && bound == N_PUB as usize
    ));
}

#[test]
fn load_rejects_an_intermediate_product_number_past_the_goods_count() {
    let units = UNIT_RECORDS.replace(":product 2,", ":product 9,");
    let path = gzip_file(
        "product-past-goods",
        &scenario_text(CONSUMER_RECORDS, &units),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::SectionNumber { unit, section, value, bound }
            if unit == 1 && section == "intermediate" && value == 9 && bound == N_GOODS as usize
    ));
}

#[test]
fn load_rejects_an_input_number_below_one() {
    // Input numbers set the goods count themselves, so the only way past the
    // upper bound is under the lower one; unchecked, a 0 lands in the section
    // before the segment it belongs to.
    let units = UNIT_RECORDS.replace(
        ":production-inputs [[1 3] [2] [3]],",
        ":production-inputs [[1 3] [0] [3]],",
    );
    let path = gzip_file("input-below-one", &scenario_text(CONSUMER_RECORDS, &units));

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::SectionNumber { unit, section, value, bound }
            if unit == 0 && section == "nature" && value == 0 && bound == N_GOODS as usize
    ));
}

#[test]
fn load_attributes_an_input_number_to_the_unit_whose_record_carries_it() {
    // The bad number sits in the third unit's labour segment, so a message that
    // reported unit 0 for every input would still name a unit that exists.
    let units = UNIT_RECORDS.replace(
        ":production-inputs [[3] [3] [2 3]],",
        ":production-inputs [[3] [3] [2 0]],",
    );
    let path = gzip_file(
        "input-below-one-third-unit",
        &scenario_text(CONSUMER_RECORDS, &units),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::SectionNumber { unit, section, value, bound }
            if unit == 2 && section == "labor" && value == 0 && bound == N_GOODS as usize
    ));
}

#[test]
fn the_section_number_message_names_the_unit_the_section_and_the_bound() {
    let units = UNIT_RECORDS.replace(":product 4,", ":product 5,");
    let path = gzip_file("product-message", &scenario_text(CONSUMER_RECORDS, &units));

    let message = load_dep1ex(&path, TEST_ENDOWMENT)
        .expect_err("expected a load error")
        .to_string();
    assert!(message.contains("production unit 0"), "{message}");
    assert!(message.contains("private"), "{message}");
    assert!(message.contains('5'), "{message}");
    assert!(message.contains('4'), "{message}");
}

#[test]
fn load_rejects_an_unknown_industry() {
    let units = UNIT_RECORDS.replace(":industry 1,", ":industry 7,");
    let path = gzip_file("unknown-industry", &scenario_text(CONSUMER_RECORDS, &units));

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::UnknownIndustry { unit, value } if unit == 1 && value == 7
    ));
}

#[test]
fn load_rejects_a_unit_record_missing_a_required_key() {
    let units = UNIT_RECORDS.replace(":a 4.0}", ":aa 4.0}");
    let path = gzip_file("missing-key", &scenario_text(CONSUMER_RECORDS, &units));

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::MissingKey { key, record, .. } if key == "a" && record == 1
    ));
}

#[test]
fn load_rejects_consumers_whose_exponent_counts_disagree() {
    let consumers = CONSUMER_RECORDS.replace(
        ":utility-exponents [0.1 0.2 0.15 0.05]",
        ":utility-exponents [0.1]",
    );
    let path = gzip_file("ragged-consumer", &scenario_text(&consumers, UNIT_RECORDS));

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::ConsumerExponentCount { consumer, count, expected, .. }
            if consumer == 1 && count == 1 && expected == 4
    ));
}

#[test]
fn a_consumer_exponent_count_of_one_is_counted_in_the_singular() {
    let consumers = CONSUMER_RECORDS.replace(
        ":utility-exponents [0.1 0.2 0.15 0.05]",
        ":utility-exponents [0.1]",
    );
    let path = gzip_file(
        "one-consumer-exponent",
        &scenario_text(&consumers, UNIT_RECORDS),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert_eq!(
        err.to_string(),
        "consumption unit 1: `:utility-exponents` lists 1 exponent, expected 4 to match the \
         first record"
    );
}

#[test]
fn a_consumer_exponent_count_of_several_is_counted_in_the_plural() {
    let consumers = CONSUMER_RECORDS.replace(
        ":utility-exponents [0.1 0.2 0.15 0.05]",
        ":utility-exponents [0.1 0.2]",
    );
    let path = gzip_file(
        "two-consumer-exponents",
        &scenario_text(&consumers, UNIT_RECORDS),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert_eq!(
        err.to_string(),
        "consumption unit 1: `:utility-exponents` lists 2 exponents, expected 4 to match the \
         first record"
    );
}

#[test]
fn load_rejects_a_file_missing_the_unit_section() {
    let text = format!("(ns pequod-cljs.fixture)\n\n(def ccs \n{CONSUMER_RECORDS}\n)\n");
    let path = gzip_file("no-wcs", &text);

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(err, LoadError::MissingSection { section } if section == "(def wcs"));
}

#[test]
fn load_rejects_input_that_is_not_gzip() {
    let path = temp_file(
        "plain-text",
        scenario_text(CONSUMER_RECORDS, UNIT_RECORDS).as_bytes(),
    );

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(err, LoadError::Decompress { .. }));
}

#[test]
fn load_rejects_a_path_that_does_not_exist() {
    let path = std::env::temp_dir().join("demplan-tests/absent-scenario.clj.gz");

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(err, LoadError::Open { .. }));
}

#[test]
fn load_rejects_a_malformed_number() {
    let units = UNIT_RECORDS.replace(":a 5.0}", ":a 5..0}");
    let path = gzip_file("bad-number", &scenario_text(CONSUMER_RECORDS, &units));

    let err = load_dep1ex(&path, TEST_ENDOWMENT).expect_err("expected a load error");
    assert!(matches!(
        err,
        LoadError::Number { key, ref text, .. } if key == "a" && text == "5..0"
    ));
}
