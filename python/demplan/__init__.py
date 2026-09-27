"""demplan: shared research infrastructure for democratic economic planning.

Two data types and two functions carry the whole interface. ``Economy`` is one period of an
economy, ``Plan`` is one period's plan, ``solve(economy, seed) -> Plan`` is what a coordination
procedure implements, and ``run`` calls it while recording how the run went.

Everything else in this package is optional. Use the pieces whose assumptions you accept.
"""

from demplan._core import core_version
from demplan.checks import (
    DeterminismReport,
    HomogeneityReport,
    check_determinism,
    check_homogeneity,
)
from demplan.configuration import (
    ConfigurationError,
    EconomyDigestReport,
    RunConfiguration,
    compare_economy_digests,
    economy_digest,
    run_configuration,
)
from demplan.differences import (
    BudgetDifference,
    Coverage,
    MaterialBalance,
    NonNegativity,
    PeriodDifferences,
    PlanDifferences,
    period_differences,
    plan_differences,
)
from demplan.economy import COBB_DOUGLAS, LEONTIEF, Economy, SchemaError
from demplan.indicators import PlanComparison, compare_plans, input_use_on
from demplan.io import WiodTable, load_dep1ex, load_wiod
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
    EXPENDITURE,
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
    "BudgetDifference",
    "COBB_DOUGLAS",
    "CONSUMER_DEMAND",
    "CobbDouglas",
    "ConfigurationError",
    "Coverage",
    "DeterminismReport",
    "EFFORT",
    "EXPENDITURE",
    "Economy",
    "EconomyDigestReport",
    "FixedRatios",
    "HomogeneityReport",
    "INCOME",
    "INDICATIVE_PRICE",
    "InputSide",
    "IterateResult",
    "LABOR_VALUE",
    "LEONTIEF",
    "Leontief",
    "MaterialBalance",
    "MaximizeWeightedConsumption",
    "MinimizeLabor",
    "NextProcedure",
    "NonNegativity",
    "Objective",
    "OutputSide",
    "PeriodDifferences",
    "PeriodResult",
    "PeriodWarning",
    "PeriodsResult",
    "Plan",
    "PlanComparison",
    "PlanDifferences",
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
    "WiodTable",
    "check_determinism",
    "check_homogeneity",
    "compare_economy_digests",
    "compare_plans",
    "core_version",
    "economy_digest",
    "input_use_on",
    "iterate",
    "load_dep1ex",
    "load_wiod",
    "period_differences",
    "plan_differences",
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
