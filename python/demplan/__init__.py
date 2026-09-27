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
from demplan.economy import COBB_DOUGLAS, LEONTIEF, Economy, SchemaError
from demplan.io import load_dep1ex
from demplan.iterate import IterateResult, iterate
from demplan.objectives import MaximizeWeightedConsumption, MinimizeLabor, Objective
from demplan.periods import (
    Advance,
    NextProcedure,
    PeriodResult,
    PeriodWarning,
    PeriodsResult,
    run_periods,
)
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
from demplan.technology import (
    CobbDouglas,
    FixedRatios,
    InputSide,
    Leontief,
    OutputSide,
    SeparableTechnology,
    SingleOutput,
    Technology,
    TechnologyReport,
    technology_margins,
)
from demplan import prefabs, tools

__all__ = [
    "Advance",
    "AllocatedPlan",
    "COBB_DOUGLAS",
    "CONSUMER_DEMAND",
    "CobbDouglas",
    "ConfigurationError",
    "DeterminismReport",
    "EFFORT",
    "Economy",
    "EconomyDigestReport",
    "FixedRatios",
    "INCOME",
    "INDICATIVE_PRICE",
    "InputSide",
    "IterateResult",
    "LABOR_VALUE",
    "LEONTIEF",
    "Leontief",
    "MaximizeWeightedConsumption",
    "MinimizeLabor",
    "NextProcedure",
    "Objective",
    "OutputSide",
    "PeriodResult",
    "PeriodWarning",
    "PeriodsResult",
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
    "SeparableTechnology",
    "SingleOutput",
    "StatedPlan",
    "Technology",
    "TechnologyReport",
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
    "run_periods",
    "split_seed",
    "technology_margins",
    "tools",
]
