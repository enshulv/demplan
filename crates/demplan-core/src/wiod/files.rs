//! Reading the release's workbooks into [`Grid`]s.
//!
//! The release zip, an `.xlsb` workbook and an `.xlsx` workbook are all zip
//! archives. The WIOT path is told apart by content: an archive holding
//! `WIOT{year}_Nov16_ROW.xlsb` is the release zip, one holding `xl/workbook.bin`
//! is a workbook.

use std::fs::File;
use std::io::{BufReader, Cursor, Read, Seek};
use std::path::Path;

use calamine::{Data, DataRef, Reader, Xlsb, Xlsx};
use zip::ZipArchive;

use super::grid::Grid;
use super::{WiodError, FIRST_YEAR, LAST_YEAR};

/// Entry that every `.xlsb` workbook holds.
const XLSB_WORKBOOK_PART: &str = "xl/workbook.bin";

/// Refuses a year the release does not cover.
pub(crate) fn require_release_year(year: i32) -> Result<(), WiodError> {
    if (FIRST_YEAR..=LAST_YEAR).contains(&year) {
        return Ok(());
    }
    Err(WiodError::YearOutOfRange { year })
}

/// Name of the entry of the release zip that holds the table for `year`.
pub(crate) fn release_entry_name(year: i32) -> String {
    format!("WIOT{year}_Nov16_ROW.xlsb")
}

/// Returns the sheet named after `year`, or an error listing the sheets there are.
pub(crate) fn year_sheet(sheets: &[String], year: i32) -> Result<&str, WiodError> {
    let name = year.to_string();
    sheets
        .iter()
        .find(|sheet| **sheet == name)
        .map(String::as_str)
        .ok_or_else(|| WiodError::SheetNotFound {
            year,
            sheets: sheets.to_vec(),
        })
}

/// Reads the WIOT sheet of `year` from the release zip or from one workbook.
///
/// The release zip's entry is read into memory whole: the workbook reader needs
/// to seek, and a compressed zip entry cannot be sought in.
pub(crate) fn read_wiot_grid(path: &Path, year: i32) -> Result<Grid, WiodError> {
    let display = path.display().to_string();
    let file = File::open(path).map_err(|source| WiodError::Open {
        path: display.clone(),
        source,
    })?;
    let mut archive =
        ZipArchive::new(BufReader::new(file)).map_err(|error| WiodError::Archive {
            path: display.clone(),
            message: error.to_string(),
        })?;

    let entry = release_entry_name(year);
    let workbook_bytes = if archive.index_for_name(&entry).is_some() {
        read_entry(&mut archive, &entry, &display)?
    } else if archive.index_for_name(XLSB_WORKBOOK_PART).is_some() {
        drop(archive);
        std::fs::read(path).map_err(|source| WiodError::Open {
            path: display.clone(),
            source,
        })?
    } else {
        return Err(WiodError::NotAWiotFile {
            path: display,
            year,
            entry,
        });
    };

    let workbook_path = format!("{display} ({entry})");
    let mut workbook =
        Xlsb::new(Cursor::new(workbook_bytes)).map_err(|error| WiodError::Workbook {
            path: workbook_path.clone(),
            message: error.to_string(),
        })?;
    let sheet = year_sheet(&workbook.sheet_names(), year)?.to_string();
    read_xlsb_sheet(&mut workbook, &sheet, &workbook_path)
}

/// Reads one entry of a zip archive into memory.
fn read_entry<R: Read + Seek>(
    archive: &mut ZipArchive<R>,
    entry: &str,
    display: &str,
) -> Result<Vec<u8>, WiodError> {
    let mut file = archive.by_name(entry).map_err(|error| WiodError::Archive {
        path: display.to_string(),
        message: error.to_string(),
    })?;
    let mut bytes = Vec::with_capacity(file.size() as usize);
    file.read_to_end(&mut bytes)
        .map_err(|source| WiodError::Open {
            path: format!("{display} ({entry})"),
            source,
        })?;
    Ok(bytes)
}

/// Streams the cells of one `.xlsb` sheet into a grid sized by the dimensions
/// the sheet declares.
fn read_xlsb_sheet<R: Read + Seek>(
    workbook: &mut Xlsb<R>,
    sheet: &str,
    display: &str,
) -> Result<Grid, WiodError> {
    let workbook_error = |error: calamine::XlsbError| WiodError::Workbook {
        path: display.to_string(),
        message: error.to_string(),
    };
    let mut cells = workbook
        .worksheet_cells_reader(sheet)
        .map_err(workbook_error)?;
    let dimensions = cells.dimensions();
    let n_rows = dimensions.end.0 as usize + 1;
    let n_columns = dimensions.end.1 as usize + 1;
    let mut grid = Grid::new(n_rows, n_columns);

    while let Some(cell) = cells.next_cell().map_err(workbook_error)? {
        let (row, column) = cell.get_position();
        let (row, column) = (row as usize, column as usize);
        let value = match cell.get_value() {
            DataRef::Float(value) => CellValue::Number(*value),
            DataRef::Int(value) => CellValue::Number(*value as f64),
            DataRef::String(text) => CellValue::Text(text.clone()),
            DataRef::SharedString(text) => CellValue::Text(text.to_string()),
            DataRef::Empty => continue,
            other => CellValue::Text(format!("{other:?}")),
        };
        store(&mut grid, row, column, value)?;
    }
    Ok(grid)
}

/// Reads one sheet of an `.xlsx` workbook.
pub(crate) fn read_workbook_sheet(path: &Path, sheet: &'static str) -> Result<Grid, WiodError> {
    let display = path.display().to_string();
    let file = File::open(path).map_err(|source| WiodError::Open {
        path: display.clone(),
        source,
    })?;
    let mut workbook = Xlsx::new(BufReader::new(file)).map_err(|error| WiodError::Workbook {
        path: display.clone(),
        message: error.to_string(),
    })?;
    if !workbook.sheet_names().iter().any(|name| name == sheet) {
        return Err(WiodError::MissingSheet {
            path: display,
            sheet,
        });
    }
    let range = workbook
        .worksheet_range(sheet)
        .map_err(|error| WiodError::Workbook {
            path: display.clone(),
            message: error.to_string(),
        })?;

    let Some((end_row, end_column)) = range.end() else {
        return Ok(Grid::new(0, 0));
    };
    let mut grid = Grid::new(end_row as usize + 1, end_column as usize + 1);
    let (start_row, start_column) = range.start().unwrap_or((0, 0));
    for (row, column, data) in range.cells() {
        let row = start_row as usize + row;
        let column = start_column as usize + column;
        let value = match data {
            Data::Float(value) => CellValue::Number(*value),
            Data::Int(value) => CellValue::Number(*value as f64),
            Data::String(text) => CellValue::Text(text.clone()),
            Data::Empty => continue,
            other => CellValue::Text(other.to_string()),
        };
        store(&mut grid, row, column, value)?;
    }
    Ok(grid)
}

/// What a cell holds once read: a number, or anything else as text.
///
/// Booleans, errors and dates are kept as text: no cell the loader reads holds
/// one, and as text they are refused wherever a number is required.
enum CellValue {
    Number(f64),
    Text(String),
}

fn store(grid: &mut Grid, row: usize, column: usize, value: CellValue) -> Result<(), WiodError> {
    if !grid.contains(row, column) {
        return Err(WiodError::CellOutsideSheet {
            row,
            column,
            n_rows: grid.n_rows(),
            n_columns: grid.n_columns(),
        });
    }
    match value {
        CellValue::Number(value) => grid.set_number(row, column, value),
        CellValue::Text(text) => grid.set_text(row, column, text),
    }
    Ok(())
}
