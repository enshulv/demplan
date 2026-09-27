"""Loaders for published scenario files and data sets."""

from __future__ import annotations

import dataclasses
import operator
import os
import warnings

import numpy as np

from demplan._wording import counted
from demplan.economy import Economy, SchemaError
from demplan.plan import AllocatedPlan

_CORE_LOADER = "load_dep1ex"
_WIOD_LOADER = "load_wiod"

_COMPENSATION = "compensation"
_HOURS = "hours"
_LABOR_MEASURES = (None, _COMPENSATION, _HOURS)

_SEA_FILE = "Socio_Economic_Accounts.xlsx"
_EXCHANGE_RATE_FILE = "Exchange_Rates.xlsx"

_FIRST_YEAR = 2000
_LAST_YEAR = 2014

_LABOR_OBSERVED = "labor_observed"
_UNPRODUCED_INPUT_USE = "unproduced_input_use"
_REGION = "region"
_INDUSTRY = "industry"


class LoadError(ValueError):
    """A data file a loader cannot turn into an economy.

    The file cannot be opened, decompressed or parsed, or it does not have the layout the
    loader reads. The message is the Rust core's and names the file or the record at fault. An
    economy that the file describes but that breaches the data model raises
    :class:`demplan.SchemaError` instead.
    """


def load_dep1ex(path: str | os.PathLike[str], endowment: float = 1000.0) -> Economy:
    """Load one dep1ex archive from the Hahnel-Szczepanczyk-Weisdorf experiments.

    Commodities come out in five contiguous sections, in this order: private consumption
    goods, public goods, intermediate goods, natural resources, labour. Each commodity's
    section is written as a text label in ``commodity_extra["hahnel_kind"]``, and every
    producing unit is labelled ``"hahnel_cobb_douglas_effort"`` in ``technology_kind`` with one
    output entry of coefficient 1; :mod:`demplan.prefabs.hahnel` names both. Producing units
    and consumer units keep the order they appear in the archive.

    ``endowment`` is the per-commodity quantity available without production, applied to every
    natural resource and every kind of labour. The archives do not carry it; the figure comes
    from the papers' text, where it is 1000 per commodity.

    Parsing happens in the Rust core, which reads the file once and hands back a mapping of
    columns, text columns as lists of ``str``. Raises :class:`LoadError` when the file cannot be
    read, decompressed or parsed, :class:`demplan.SchemaError` when the economy it describes
    breaches the data model (a non-finite ``endowment``, for one), and ``NotImplementedError``
    while the core does not export the loader.
    """
    from demplan import _core

    loader = getattr(_core, _CORE_LOADER, None)
    if loader is None:
        raise NotImplementedError(
            f"the demplan core does not provide {_CORE_LOADER} yet; "
            "rebuild the extension module with a core that exports it"
        )
    return Economy.from_arrays(_call_core_loader(loader, str(path), float(endowment)))


def _call_core_loader(loader, *args):
    """Call one of the core's loaders, raising its two error types as this package's own.

    The core reports a file it cannot read as ``_core.LoadError`` and a breach of the data
    model as ``_core.SchemaError``. A researcher catches :class:`LoadError` and
    :class:`demplan.SchemaError`, the second being the class every schema check of the package
    raises, so each is raised in place of its core counterpart with the same message and the
    core's exception as its cause. Every other exception passes through unchanged.
    """
    from demplan import _core

    try:
        return loader(*args)
    except _core.SchemaError as error:
        raise SchemaError(str(error)) from error
    except _core.LoadError as error:
        raise LoadError(str(error)) from error


class WiodLaborGap(UserWarning):
    """Some producing units of a loaded WIOD table have no labour figure.

    Such a unit has no labour input entry and ``unit_extra["labor_observed"]`` 0.0. The warning
    names each economy with such units and how many it has.
    """


class WiodUnproducedInputs(UserWarning):
    """Producing units of a loaded WIOD table use products that no unit produces.

    Such a use is not an input entry of the unit; the unit's total is in
    ``unit_extra["unproduced_input_use"]``. The warning names the products, how many units use
    them and the total value.
    """


@dataclasses.dataclass(frozen=True, eq=False)
class WiodTable:
    """One year of the WIOD 2016 release, as :func:`load_wiod` returns it.

    ``economy`` is the economy the world input-output table describes, and ``observed`` is
    the year's recorded flows laid out as a plan of that economy. Equality is identity, as on
    :class:`Economy`.
    """

    economy: Economy
    observed: AllocatedPlan


def load_wiod(
    path: str | os.PathLike[str],
    year: int,
    labor: str | None = None,
    sea: str | os.PathLike[str] | None = None,
    exchange_rates: str | os.PathLike[str] | None = None,
) -> WiodTable:
    """Load one year of the World Input-Output Database (WIOD), 2016 release.

    ``path`` is the release zip ``WIOTS_in_EXCEL.zip``, from which the table
    ``WIOT{year}_Nov16_ROW.xlsb`` is read in memory without extracting it, or one such
    ``.xlsb`` workbook. ``year`` must be an integer from 2000 to 2014; anything else, including
    ``2014.0`` and ``"2014"``, raises ``ValueError``. A workbook without a sheet named after
    ``year`` raises :class:`LoadError`.

    The economy has one commodity per product (44 economies, including the rest of the world
    ``ROW``, times 56 industries, in the table's row order), labelled in
    ``commodity_extra["region"]`` and ``commodity_extra["industry"]``. Every product with
    positive gross output gets one producing unit, labelled ``LEONTIEF``, whose inputs are the
    products it uses that have a producing unit, at intermediate use over its gross output. A
    negative intermediate-use entry raises :class:`LoadError` naming the year, the two products
    and the value; no year of the release has one.

    There is one consumer unit per final-demand column (five per economy), labelled in
    ``consumer_extra["region"]`` and ``consumer_extra["final_demand"]``. ``unit_extra`` carries
    each unit's region and industry, the rows below the table body (taxes less subsidies, the
    cif/fob adjustment, purchases by residents abroad and by non-residents, value added and
    international transport margins), and ``unproduced_input_use``, described below.
    ``observed`` records gross output, intermediate use and final demand (negative entries,
    such as inventory draw-downs, kept) as an :class:`AllocatedPlan` of the economy. Values are
    millions of US$ at current prices.

    A unit that uses no product of the table has no input entry unless ``labor`` gives it its
    labour, and a Leontief technology reads a unit without inputs as able to produce any
    quantity. Every year of the release has 29 to 31 such units: industry ``T`` (activities of
    households as employers) in 28 or 29 economies, India's public administration ``IND O84``,
    and, in five of the fifteen years, one unit of Malta. Pass ``labor`` to give them their
    labour input. The rest of the world's ``ROW T`` stays without one, because ``ROW`` has no
    labour data.

    A product without output keeps its commodity and gets no unit. Units may still use it: such
    a use is not an input entry, because nothing produces the product and nothing holds it, and
    a Leontief unit that needed it could produce nothing. Each unit's total use of products
    without a unit is in ``unit_extra["unproduced_input_use"]`` (0.0 for a unit that uses none),
    ``observed.input_use`` leaves it out as the input entries do, and ``observed.consumption``
    keeps final demand as recorded. The loader emits one :class:`WiodUnproducedInputs` naming
    the products, how many units use them and the total. Every year of the release has such
    use. The rest of the world's product ``ROW M73`` has zero gross output in each year from
    2000 to 2014, yet about 2,240 units use it, for 5,500 to 15,300 million US$ a year (5,500.6
    in 2001, 15,322.8 in 2008, 6,992.5 in 2014); its row balances through negative final demand
    of the same size. Malta's ``MLT A02`` has no output either and is used for less than 1e-5
    million US$ a year.

    The world input-output table has no labour data. ``labor`` chooses whether and how labour
    enters, from the release's socio-economic accounts (``sea``, the path of
    ``Socio_Economic_Accounts.xlsx``):

    ``None``
        No labour commodity. This is the default.
    ``"compensation"``
        The money paid to employees: compensation of employees (``COMP``), in millions of
        national currency, converted to millions of US$ at the year's rate in
        ``exchange_rates`` (the path of ``Exchange_Rates.xlsx``, US$ per unit of local
        currency).
    ``"hours"``
        The time worked by employees: hours worked by employees (``H_EMPE``), in millions of
        hours.

    Neither measure includes the self-employed. Which one stands for labour input -- or
    neither -- is a theoretical choice the library does not make. With a measure chosen, each
    economy with data gets one labour commodity after the products, whose endowment is the
    economy's total labour input that year; each unit uses its economy's labour at its labour
    figure over its gross output. The figure of a product without a producing unit is no unit's
    input and not part of the endowment, so each endowment equals the labour input of its
    economy's units; no year of the release has a non-zero figure on such a product. The rest
    of the world ``ROW`` has no data under either measure, China ``CHN`` has no hours, and a
    figure that is not a number is missing too. ``sea`` and ``exchange_rates`` are read only
    when the measure needs them.

    A unit without a figure gets no labour input and ``unit_extra["labor_observed"]`` 0.0
    (1.0 otherwise; the key exists only when a measure is chosen), and the loader emits one
    :class:`WiodLaborGap` naming the economies affected and how many units each has. A figure
    of 0 is data, not a gap.

    The exchange-rate workbook lists Romania as ``ROM``, which the loader reads as the table's
    ``ROU``; every other economy is matched by its code as written. A workbook that lists one
    economy twice, under the same code or as both ``ROM`` and ``ROU``, raises
    :class:`LoadError`.

    Reading happens in the Rust core, which hands back a mapping of columns. Raises
    ``ValueError`` when an argument is wrong, including a year that is not an integer from 2000
    to 2014; :class:`LoadError`, itself a ``ValueError``, when a file cannot be read or does not
    have the release's layout; and :class:`demplan.SchemaError` when the economy the files
    describe breaches the data model.
    """
    year = _release_year(year)
    _require_labor_sources(labor, sea, exchange_rates)
    from demplan import _core

    loader = getattr(_core, _WIOD_LOADER, None)
    if loader is None:
        raise NotImplementedError(
            f"the demplan core does not provide {_WIOD_LOADER} yet; "
            "rebuild the extension module with a core that exports it"
        )
    mapping = _call_core_loader(
        loader, str(path), year, labor, _path_text(sea), _path_text(exchange_rates)
    )
    economy = Economy.from_arrays(mapping["economy"])
    observed = AllocatedPlan(**mapping["observed"])
    observed.validate(economy)
    _warn_about_unproduced_inputs(economy, mapping["unproduced_inputs"])
    if labor is not None:
        _warn_about_labor_gaps(economy)
    return WiodTable(economy=economy, observed=observed)


def _release_year(year) -> int:
    """Return ``year`` as an ``int`` when it is an integer the release covers.

    Raises ``ValueError`` naming the covered range for anything else: a year outside it, a
    number that is not an integer (``2014.0`` included), text or ``None``.
    """
    try:
        value = operator.index(year)
    except TypeError:
        value = None
    if value is None or not _FIRST_YEAR <= value <= _LAST_YEAR:
        raise ValueError(
            f"year is {year!r}; the WIOD 2016 release covers the years {_FIRST_YEAR} to "
            f"{_LAST_YEAR}, given as an integer"
        )
    return value


def _path_text(path: str | os.PathLike[str] | None) -> str | None:
    return None if path is None else str(path)


def _require_labor_sources(labor, sea, exchange_rates) -> None:
    """Refuse an unknown labour measure, or a measure without the workbooks it reads.

    Raises ``ValueError`` naming the missing argument and what it is for.
    """
    if labor not in _LABOR_MEASURES:
        raise ValueError(
            f"labor is {labor!r}; expected None, {_COMPENSATION!r} or {_HOURS!r}"
        )
    if labor is not None and sea is None:
        variable = (
            "the compensation of employees" if labor == _COMPENSATION
            else "the hours worked by employees"
        )
        raise ValueError(
            f"labor={labor!r} needs sea, the path of {_SEA_FILE}, which holds {variable} "
            "per economy and industry"
        )
    if labor == _COMPENSATION and exchange_rates is None:
        raise ValueError(
            f"labor={_COMPENSATION!r} needs exchange_rates, the path of {_EXCHANGE_RATE_FILE}, "
            "which holds the rate that converts compensation from national currency to US$"
        )


def _warn_about_unproduced_inputs(economy: Economy, unproduced: dict) -> None:
    """Emit one :class:`WiodUnproducedInputs` when producing units use products that no unit
    produces, naming those products in the table's order, how many units use them and the
    total value. Emits nothing when there are none.

    ``unproduced`` is the core's ``unproduced_inputs`` entry: the commodity index of each such
    product (``commodity``) and what units use of it (``used``).
    """
    products = unproduced["commodity"]
    if products.size == 0:
        return
    region = economy.commodity_extra[_REGION]
    industry = economy.commodity_extra[_INDUSTRY]
    names = ", ".join(f"{region[i]} {industry[i]}" for i in products)
    n_units = int(np.count_nonzero(economy.unit_extra[_UNPRODUCED_INPUT_USE]))
    total = float(unproduced["used"].sum())
    warnings.warn(
        f"{n_units} producing {'unit uses' if n_units == 1 else 'units use'} products that no "
        f"unit produces, {total:,.2f} million US$ in all: {names}. These uses are not input "
        f"entries; each unit's total is in unit_extra[{_UNPRODUCED_INPUT_USE!r}].",
        WiodUnproducedInputs,
        stacklevel=3,
    )


def _warn_about_labor_gaps(economy: Economy) -> None:
    """Emit one :class:`WiodLaborGap` naming each economy with units that have no labour
    figure, in the table's order, with how many units each has. Emits nothing when every unit
    has one."""
    missing = economy.unit_extra[_LABOR_OBSERVED] == 0.0
    if not missing.any():
        return
    regions = economy.unit_extra[_REGION][missing]
    names, first_seen, counts = np.unique(regions, return_index=True, return_counts=True)
    listed = ", ".join(
        f"{names[i]} ({counted(int(counts[i]), 'unit')})"
        for i in np.argsort(first_seen)
    )
    n_units = int(missing.sum())
    subject = "unit has" if n_units == 1 else "units have"
    pronoun = "it has" if n_units == 1 else "they have"
    warnings.warn(
        f"{n_units} producing {subject} no labour figure, so {pronoun} no labour input and "
        f"unit_extra[{_LABOR_OBSERVED!r}] is 0.0: {listed}",
        WiodLaborGap,
        stacklevel=3,
    )
