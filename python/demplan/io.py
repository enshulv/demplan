"""Loaders for published scenario files."""

from __future__ import annotations

import os

from demplan.economy import Economy

_CORE_LOADER = "load_dep1ex"


def load_dep1ex(path: str | os.PathLike[str], endowment: float = 1000.0) -> Economy:
    """Load one dep1ex archive from the Hahnel-Szczepanczyk-Weisdorf experiments.

    Commodities come out in five contiguous sections, in this order: private consumption
    goods, public goods, intermediate goods, natural resources, labour. Producing units and
    consumer units keep the order they appear in the archive.

    ``endowment`` is the per-commodity quantity available without production, applied to every
    natural resource and every kind of labour. The archives do not carry it; the figure comes
    from the papers' text, where it is 1000 per commodity.

    Parsing happens in the Rust core, which reads the file once and hands back a mapping of
    columns. Raises ``NotImplementedError`` while the core does not export the loader.
    """
    from demplan import _core

    loader = getattr(_core, _CORE_LOADER, None)
    if loader is None:
        raise NotImplementedError(
            f"the demplan core does not provide {_CORE_LOADER} yet; "
            "rebuild the extension module with a core that exports it"
        )
    return Economy.from_arrays(loader(str(path), float(endowment)))
