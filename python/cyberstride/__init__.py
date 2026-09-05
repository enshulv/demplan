"""cyberstride: shared research infrastructure for democratic economic planning.

Two data types and two functions carry the whole interface. ``Economy`` is one period of an
economy, ``Plan`` is one period's plan, ``solve(economy, seed) -> Plan`` is what a coordination
procedure implements, and ``run`` calls it while recording how the run went.

Everything else in this package is optional. Use the pieces whose assumptions you accept.
"""

from cyberstride._core import core_version
from cyberstride.checks import DeterminismReport, check_determinism
from cyberstride.configuration import (
    ConfigurationError,
    EconomyDigestReport,
    RunConfiguration,
    compare_economy_digests,
    economy_digest,
    run_configuration,
)
from cyberstride.economy import CommodityKind, Economy, SchemaError, TechnologyKind
from cyberstride.io import load_dep1ex
from cyberstride.iterate import IterateResult, iterate
from cyberstride.objectives import MaximizeWeightedConsumption, MinimizeLabor, Objective
from cyberstride.plan import (
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
from cyberstride.procedure import Procedure, RunResult, RunSummary, run
from cyberstride.reference import (
    ReferenceInfeasible,
    ReferenceProcedure,
    ReferenceResult,
    reference_solution,
)
from cyberstride.seeds import rng, split_seed
from cyberstride import prefabs, tools

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
