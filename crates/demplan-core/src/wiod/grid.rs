//! A worksheet held in memory as a rectangle of cells.

use std::collections::HashMap;

/// A worksheet's cells: numbers in a dense column-major rectangle, text in a
/// sparse map.
///
/// Column-major because the WIOT is read a column at a time: a producing unit's
/// inputs are one column of `Z`, and a consumer unit's final demand is one
/// column of the final-demand block. A cell holds a number, text, or nothing.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct Grid {
    n_rows: usize,
    n_columns: usize,
    /// Numeric value of each cell, column-major; 0.0 where `has_number` is false.
    numbers: Vec<f64>,
    /// Whether each cell holds a number, column-major.
    has_number: Vec<bool>,
    text: HashMap<(usize, usize), String>,
}

impl Grid {
    /// Returns a grid of `n_rows × n_columns` empty cells.
    pub(crate) fn new(n_rows: usize, n_columns: usize) -> Self {
        let n_cells = n_rows * n_columns;
        Self {
            n_rows,
            n_columns,
            numbers: vec![0.0; n_cells],
            has_number: vec![false; n_cells],
            text: HashMap::new(),
        }
    }

    pub(crate) fn n_rows(&self) -> usize {
        self.n_rows
    }

    pub(crate) fn n_columns(&self) -> usize {
        self.n_columns
    }

    /// Reports whether `(row, column)` lies inside the grid.
    pub(crate) fn contains(&self, row: usize, column: usize) -> bool {
        row < self.n_rows && column < self.n_columns
    }

    fn index(&self, row: usize, column: usize) -> usize {
        column * self.n_rows + row
    }

    /// Stores a number, replacing whatever the cell held.
    ///
    /// Panics when the cell lies outside the grid; callers check with
    /// [`Grid::contains`] first.
    pub(crate) fn set_number(&mut self, row: usize, column: usize, value: f64) {
        assert!(self.contains(row, column), "cell outside the grid");
        let index = self.index(row, column);
        self.numbers[index] = value;
        self.has_number[index] = true;
        self.text.remove(&(row, column));
    }

    /// Stores text, replacing whatever the cell held.
    ///
    /// Panics when the cell lies outside the grid; callers check with
    /// [`Grid::contains`] first.
    pub(crate) fn set_text(&mut self, row: usize, column: usize, value: String) {
        assert!(self.contains(row, column), "cell outside the grid");
        let index = self.index(row, column);
        self.numbers[index] = 0.0;
        self.has_number[index] = false;
        self.text.insert((row, column), value);
    }

    /// Returns the number in the cell, or `None` when it holds text or nothing
    /// or lies outside the grid.
    pub(crate) fn number(&self, row: usize, column: usize) -> Option<f64> {
        if !self.contains(row, column) {
            return None;
        }
        let index = self.index(row, column);
        self.has_number[index].then(|| self.numbers[index])
    }

    /// Returns the text in the cell, or `None` when it holds a number or nothing
    /// or lies outside the grid.
    pub(crate) fn text(&self, row: usize, column: usize) -> Option<&str> {
        self.text.get(&(row, column)).map(String::as_str)
    }

    /// Describes the content of a cell for an error message.
    pub(crate) fn describe(&self, row: usize, column: usize) -> String {
        if let Some(text) = self.text(row, column) {
            return format!("the text {text:?}");
        }
        match self.number(row, column) {
            Some(value) => format!("the number {value}"),
            None => "nothing".to_string(),
        }
    }

    /// Returns rows `[start, end)` of a column's numbers; cells without a number
    /// read as 0.0.
    ///
    /// Panics when the range lies outside the grid.
    pub(crate) fn column_numbers(&self, column: usize, start: usize, end: usize) -> &[f64] {
        let base = column * self.n_rows;
        &self.numbers[base + start..base + end]
    }

    /// Returns the first cell in rows `[start, end)` of `column` that holds no
    /// number, or `None` when every cell does.
    pub(crate) fn first_non_number(
        &self,
        column: usize,
        start: usize,
        end: usize,
    ) -> Option<usize> {
        let base = column * self.n_rows;
        self.has_number[base + start..base + end]
            .iter()
            .position(|&present| !present)
            .map(|offset| start + offset)
    }
}
