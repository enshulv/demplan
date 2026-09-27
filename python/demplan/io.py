"""Loaders for published scenario files and data sets."""

from __future__ import annotations

import dataclasses
import os
import warnings

import numpy as np

from demplan.economy import Economy
from demplan.plan import AllocatedPlan

_CORE_LOADER = "load_dep1ex"
_WIOD_LOADER = "load_wiod"

_COMPENSATION = "compensation"
_HOURS = "hours"
_LABOR_MEASURES = (None, _COMPENSATION, _HOURS)

_SEA_FILE = "Socio_Economic_Accounts.xlsx"
_EXCHANGE_RATE_FILE = "Exchange_Rates.xlsx"

_LABOR_OBSERVED = "labor_observed"
_REGION = "region"


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
    columns, text columns as lists of ``str``. Raises ``NotImplementedError`` while the core
    does not export the loader.
    """
    from demplan import _core

    loader = getattr(_core, _CORE_LOADER, None)
    if loader is None:
        raise NotImplementedError(
            f"the demplan core does not provide {_CORE_LOADER} yet; "
            "rebuild the extension module with a core that exports it"
        )
    return Economy.from_arrays(loader(str(path), float(endowment)))


class WiodLaborGap(UserWarning):
    """Some producing units of a loaded WIOD table have no labour figure.

    Such a unit has no labour input entry and ``unit_extra["labor_observed"]`` 0.0. The warning
    names each economy with such units and how many it has.
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
    ``.xlsb`` workbook. The workbook must have a sheet named after ``year``, and ``year`` must
    be between 2000 and 2014; otherwise ``ValueError``.

    The economy has one commodity per product (44 economies, including the rest of the world
    ``ROW``, times 56 industries, in the table's row order), labelled in
    ``commodity_extra["region"]`` and ``commodity_extra["industry"]``. Every product with
    positive gross output gets one producing unit, labelled ``LEONTIEF``, whose inputs are the
    products it uses at intermediate use over its gross output. A product without output keeps
    its commodity and gets no unit. A negative intermediate-use entry raises ``ValueError``
    naming the year, the two products and the value; no year of the release has one. There is one consumer unit per final-demand column (five
    per economy), labelled in ``consumer_extra["region"]`` and
    ``consumer_extra["final_demand"]``. ``unit_extra`` carries each unit's region and industry
    and the rows below the table body: taxes less subsidies, the cif/fob adjustment, purchases
    by residents abroad and by non-residents, value added and international transport margins.
    ``observed`` records gross output, intermediate use and final demand (negative entries,
    such as inventory draw-downs, kept) as an :class:`AllocatedPlan` of the economy. Values
    are millions of US$ at current prices.

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
    figure over its gross output. The rest of the world ``ROW`` has no data under either
    measure, China ``CHN`` has no hours, and a figure that is not a number is missing too.
    The exchange-rate workbook lists Romania as ``ROM``, which the loader reads as the table's
    ``ROU``; every other economy is matched by its code as written.
    A unit without a figure gets no labour input and ``unit_extra["labor_observed"]`` 0.0
    (1.0 otherwise; the key exists only when a measure is chosen), and the loader emits one
    :class:`WiodLaborGap` naming the economies affected and how many units each has. A figure
    of 0 is data, not a gap. ``sea`` and ``exchange_rates`` are read only when the measure
    needs them.

    Reading happens in the Rust core, which hands back a mapping of columns. Raises
    ``ValueError`` when an argument is wrong or a file cannot be read or does not have the
    release's layout.
    """
    _require_labor_sources(labor, sea, exchange_rates)
    from demplan import _core

    loader = getattr(_core, _WIOD_LOADER, None)
    if loader is None:
        raise NotImplementedError(
            f"the demplan core does not provide {_WIOD_LOADER} yet; "
            "rebuild the extension module with a core that exports it"
        )
    mapping = loader(str(path), year, labor, _path_text(sea), _path_text(exchange_rates))
    economy = Economy.from_arrays(mapping["economy"])
    observed = AllocatedPlan(**mapping["observed"])
    observed.validate(economy)
    if labor is not None:
        _warn_about_labor_gaps(economy)
    return WiodTable(economy=economy, observed=observed)


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
        f"{names[i]} ({counts[i]} {'unit' if counts[i] == 1 else 'units'})"
        for i in np.argsort(first_seen)
    )
    warnings.warn(
        f"{int(missing.sum())} producing units have no labour figure, so they have no labour "
        f"input and unit_extra[{_LABOR_OBSERVED!r}] is 0.0: {listed}",
        WiodLaborGap,
        stacklevel=3,
    )
