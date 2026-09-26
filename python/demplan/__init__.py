"""demplan: shared research infrastructure for democratic economic planning.

Two data types and two functions carry the whole interface. ``Economy`` is one period of an
economy, ``Plan`` is one period's plan, ``solve(economy, seed) -> Plan`` is what a coordination
procedure implements, and ``run`` calls it while recording how the run went.

Everything else in this package is optional. Use the pieces whose assumptions you accept.
"""

from demplan._core import core_version
from demplan.checks import DeterminismReport, check_determinism
from demplan.configuration import (
    ConfigurationError,
    EconomyDigestReport,
    RunConfiguration,
    compare_economy_digests,
    economy_digest,
    run_configuration,
)
from demplan.economy import CommodityKind, Economy, SchemaError, TechnologyKind
from demplan.io import load_dep1ex
from demplan.iterate import IterateResult, iterate
from demplan.objectives import MaximizeWeightedConsumption, MinimizeLabor, Objective
from demplan.plan import (
    CONSUMER_DEMAND,
    EFFORT,
    INCOME,
    INDICATIVE_PRICE,
    LABOR_VALUE,
    SHADOW_PRICE,
    AllocatedPlan,
    Plan,
    PlanFieldAbsent,
    StatedPlan,
    require_comparable,
)
from demplan.procedure import Procedure, RunResult, RunSummary, run
from demplan.reference import (
    ReferenceInfeasible,
    ReferenceProcedure,
    ReferenceResult,
    reference_solution,
)
from demplan.seeds import rng, split_seed
from demplan import prefabs, tools

__all__ = [
    "AllocatedPlan",
    "CONSUMER_DEMAND",
    "CommodityKind",
    "ConfigurationError",
    "DeterminismReport",
    "EFFORT",
    "Economy",
    "EconomyDigestReport",
    "INCOME",
    "INDICATIVE_PRICE",
    "IterateResult",
    "LABOR_VALUE",
    "MaximizeWeightedConsumption",
    "MinimizeLabor",
    "Objective",
    "Plan",
    "PlanFieldAbsent",
    "Procedure",
    "ReferenceInfeasible",
    "ReferenceProcedure",
    "ReferenceResult",
    "RunConfiguration",
    "RunResult",
    "RunSummary",
    "SHADOW_PRICE",
    "SchemaError",
    "StatedPlan",
    "TechnologyKind",
    "check_determinism",
    "compare_economy_digests",
    "core_version",
    "economy_digest",
    "iterate",
    "load_dep1ex",
    "prefabs",
    "reference_solution",
    "require_comparable",
    "rng",
    "run",
    "run_configuration",
    "split_seed",
    "tools",
]
