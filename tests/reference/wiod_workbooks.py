"""Small WIOD workbooks written from scratch, and a plain reader for ``.xlsx`` sheets.

The loader reads the WIOD 2016 release: world input-output tables as ``.xlsb`` workbooks (one
sheet named after the year), bundled in ``WIOTS_in_EXCEL.zip``, and the socio-economic accounts
and exchange rates as ``.xlsx`` workbooks. The writers here produce files of the same shape with
a handful of cells, so the whole path from file to ``Economy`` runs in a fast test.

Only the parts of each format that a reader needs are written: for ``.xlsb`` the workbook's
sheet list and relationships and the sheet's cell records (MS-XLSB), for ``.xlsx`` the same in
SpreadsheetML with inline strings.

:func:`read_xlsx_rows` reads an ``.xlsx`` sheet with the standard library alone. The real-data
tests use it as a second reader of the socio-economic accounts, independent of the loader's.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

FINAL_DEMAND = ("CONS_h", "CONS_np", "CONS_g", "GFCF", "INVEN")

TOTALS = (
    ("TXSP", "taxes_less_subsidies"),
    ("EXP_adj", "cif_fob_adjustment"),
    ("PURR", "purchases_by_residents_abroad"),
    ("PURNR", "purchases_by_nonresidents"),
    ("VA", "value_added"),
    ("IntTTM", "international_transport_margins"),
)
"""Codes of the totals rows below the products, with the ``unit_extra`` key of each."""

FIRST_PRODUCT_ROW = 6
FIRST_VALUE_COLUMN = 4


class Integer(int):
    """A cell value written as an integer cell (an RK record) instead of a floating-point one.

    The release stores a few cells that way, and a reader that only handles floating-point
    cells would read them as empty.
    """


@dataclass
class WiotTable:
    """A world input-output table described by its blocks, laid out like the release."""

    economies: list[str]
    industries: list[str]
    z: list[list[float]]
    """``z[i][j]``: intermediate use of product ``i`` by the industry making product ``j``."""
    final_demand: list[list[float]]
    """``final_demand[i][c]``: final use of product ``i`` in final-demand column ``c``."""
    gross_output: list[float]
    totals: list[list[float]] = field(default_factory=list)
    """``totals[k][j]``: the value of ``TOTALS[k]`` in product column ``j``."""

    def __post_init__(self):
        if not self.totals:
            self.totals = [
                [(k + 1) * 1000.0 + j + 0.5 for j in range(self.n_products)]
                for k in range(len(TOTALS))
            ]

    @property
    def n_products(self) -> int:
        return len(self.economies) * len(self.industries)

    @property
    def n_final_demand(self) -> int:
        return len(self.economies) * len(FINAL_DEMAND)

    def product(self, i: int) -> tuple[str, str]:
        per = len(self.industries)
        return self.economies[i // per], self.industries[i % per]

    def cells(self) -> dict[tuple[int, int], object]:
        """Every non-empty cell of the sheet, keyed by ``(row, column)``."""
        n = self.n_products
        final_demand_start = FIRST_VALUE_COLUMN + n
        gross_output_column = final_demand_start + self.n_final_demand
        cells: dict[tuple[int, int], object] = {
            (0, 0): "Intercountry Input-Output Table",
            (1, 0): "synthetic, in current prices",
            (2, 0): "(industry-by-industry)",
            (3, 0): "(millions of US$)",
        }
        for j in range(n):
            region, industry = self.product(j)
            column = FIRST_VALUE_COLUMN + j
            cells[(2, column)] = industry
            cells[(3, column)] = f"name of {industry}"
            cells[(4, column)] = region
            cells[(5, column)] = f"c{j % len(self.industries) + 1}"
        for c in range(self.n_final_demand):
            column = final_demand_start + c
            cells[(2, column)] = FINAL_DEMAND[c % len(FINAL_DEMAND)]
            cells[(4, column)] = self.economies[c // len(FINAL_DEMAND)]
        cells[(2, gross_output_column)] = "GO"
        cells[(4, gross_output_column)] = "TOT"

        for i in range(n):
            region, industry = self.product(i)
            row = FIRST_PRODUCT_ROW + i
            cells[(row, 0)] = industry
            cells[(row, 1)] = f"name of {industry}"
            cells[(row, 2)] = region
            cells[(row, 3)] = f"r{i % len(self.industries) + 1}"
            for j in range(n):
                cells[(row, FIRST_VALUE_COLUMN + j)] = self.z[i][j]
            for c in range(self.n_final_demand):
                cells[(row, final_demand_start + c)] = self.final_demand[i][c]
            cells[(row, gross_output_column)] = self.gross_output[i]

        row = FIRST_PRODUCT_ROW + n
        cells[(row, 0)] = "II_fob"
        for j in range(n):
            cells[(row, FIRST_VALUE_COLUMN + j)] = float(sum(self.z[i][j] for i in range(n)))
        for k, (code, _) in enumerate(TOTALS):
            row = FIRST_PRODUCT_ROW + n + 1 + k
            cells[(row, 0)] = code
            cells[(row, 2)] = "TOT"
            for j in range(n):
                cells[(row, FIRST_VALUE_COLUMN + j)] = self.totals[k][j]
        row = FIRST_PRODUCT_ROW + n + 1 + len(TOTALS)
        cells[(row, 0)] = "GO"
        for j in range(n):
            cells[(row, FIRST_VALUE_COLUMN + j)] = self.gross_output[j]
        return cells


# ------------------------------------------------------------------------------ xlsb


def _record(record_type: int, payload: bytes = b"") -> bytes:
    """One BIFF12 record: variable-length type, variable-length size, payload."""
    if record_type < 0x80:
        header = bytearray([record_type])
    else:
        header = bytearray([(record_type & 0x7F) | 0x80, (record_type >> 7) & 0x7F])
    size = len(payload)
    for _ in range(4):
        byte = size & 0x7F
        size >>= 7
        header.append(byte | (0x80 if size else 0))
        if not size:
            break
    return bytes(header) + payload


def _wide(text: str) -> bytes:
    encoded = text.encode("utf-16-le")
    return struct.pack("<I", len(encoded) // 2) + encoded


def _cell_record(column: int, value) -> bytes:
    prefix = struct.pack("<II", column, 0)
    if isinstance(value, str):
        return _record(0x0006, prefix + _wide(value))  # BrtCellSt
    if isinstance(value, Integer):
        return _record(0x0002, prefix + struct.pack("<i", (int(value) << 2) | 0x2))  # BrtCellRk
    return _record(0x0005, prefix + struct.pack("<d", float(value)))  # BrtCellReal


def _sheet_bin(cells: dict[tuple[int, int], object]) -> bytes:
    rows = sorted({row for row, _ in cells})
    last_row = max(rows)
    last_column = max(column for _, column in cells)
    out = bytearray(_record(0x0081))  # BrtBeginSheet
    out += _record(0x0094, struct.pack("<IIII", 0, last_row, 0, last_column))  # BrtWsDim
    out += _record(0x0091)  # BrtBeginSheetData
    for row in rows:
        out += _record(0x0000, struct.pack("<I", row) + bytes(13))  # BrtRowHdr
        for column in sorted(column for r, column in cells if r == row):
            out += _cell_record(column, cells[(row, column)])
    out += _record(0x0092)  # BrtEndSheetData
    out += _record(0x0082)  # BrtEndSheet
    return bytes(out)


def xlsb_bytes(sheets: dict[str, dict[tuple[int, int], object]]) -> bytes:
    """An ``.xlsb`` workbook holding the given sheets, in order."""
    bundles = bytearray(_record(0x0083))  # BrtBeginBook
    bundles += _record(0x008F)  # BrtBeginBundleShs
    relationships = []
    for index, name in enumerate(sheets, start=1):
        relation = f"rId{index}"
        bundles += _record(0x009C, struct.pack("<II", 0, index) + _wide(relation) + _wide(name))
        relationships.append(
            f'<Relationship Id="{relation}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.bin"/>'
        )
    bundles += _record(0x0090)  # BrtEndBundleShs
    bundles += _record(0x009D)  # BrtCalcProp
    bundles += _record(0x0084)  # BrtEndBook

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.bin", bytes(bundles))
        archive.writestr(
            "xl/_rels/workbook.bin.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relationships)
            + "</Relationships>",
        )
        for index, cells in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.bin", _sheet_bin(cells))
    return buffer.getvalue()


def write_xlsb(path: Path, sheets: dict[str, dict[tuple[int, int], object]]) -> Path:
    path.write_bytes(xlsb_bytes(sheets))
    return path


def release_entry(year: int) -> str:
    return f"WIOT{year}_Nov16_ROW.xlsb"


def write_release_zip(path: Path, tables: dict[int, WiotTable]) -> Path:
    """A zip laid out like ``WIOTS_in_EXCEL.zip``: one workbook per year, sheet named by year."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for year, table in tables.items():
            archive.writestr(release_entry(year), xlsb_bytes({str(year): table.cells()}))
    return path


# ------------------------------------------------------------------------------ xlsx


def _column_name(column: int) -> str:
    name = ""
    column += 1
    while column:
        column, remainder = divmod(column - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _sheet_xml(rows: list[list[object]]) -> str:
    out = ['<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r, values in enumerate(rows, start=1):
        out.append(f'<row r="{r}">')
        for c, value in enumerate(values):
            if value is None:
                continue
            reference = f"{_column_name(c)}{r}"
            if isinstance(value, str):
                out.append(f'<c r="{reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
            else:
                out.append(f'<c r="{reference}"><v>{float(value)!r}</v></c>')
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def write_xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    """An ``.xlsx`` workbook whose sheets hold the given rows; ``None`` leaves a cell empty."""
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relations = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    entries = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets, start=1)
    )
    targets = "".join(
        f'<Relationship Id="rId{index}" Type="{relations}/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{relations}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{main}" xmlns:r="{relations}"><sheets>{entries}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{targets}</Relationships>",
        )
        for index, rows in enumerate(sheets.values(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))
    return path


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REFERENCE = re.compile(r"([A-Z]+)(\d+)")


def read_xlsx_rows(path: Path, sheet: str) -> list[list[object]]:
    """Every row of one ``.xlsx`` sheet: ``str`` for text, ``float`` for numbers, ``None`` empty."""
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relation = None
        for entry in workbook.iter(f"{{{_NS['m']}}}sheet"):
            if entry.get("name") == sheet:
                relation = next(value for key, value in entry.attrib.items() if key.endswith("}id"))
        if relation is None:
            raise KeyError(f"{path} has no sheet {sheet!r}")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(
            item.get("Target") for item in relationships if item.get("Id") == relation
        )
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target

        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in strings.iter(f"{{{_NS['m']}}}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{{{_NS['m']}}}t")))

        rows: dict[int, dict[int, object]] = {}
        with archive.open(target) as handle:
            for _, element in ET.iterparse(handle):
                if element.tag != f"{{{_NS['m']}}}c":
                    continue
                letters, digits = _REFERENCE.fullmatch(element.get("r")).groups()
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - ord("A") + 1
                kind = element.get("t")
                value_node = element.find("m:v", _NS)
                if kind == "s":
                    value = shared[int(value_node.text)]
                elif kind == "inlineStr":
                    value = "".join(node.text or "" for node in element.iter(f"{{{_NS['m']}}}t"))
                elif kind in ("str", "e"):
                    value = value_node.text if value_node is not None else ""
                elif value_node is None:
                    value = None
                else:
                    value = float(value_node.text)
                rows.setdefault(int(digits) - 1, {})[column - 1] = value
                element.clear()
    width = max((max(cells) + 1 for cells in rows.values() if cells), default=0)
    return [
        [rows.get(r, {}).get(c) for c in range(width)] for r in range(max(rows, default=-1) + 1)
    ]
