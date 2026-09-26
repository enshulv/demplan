# WIOD field mapping: what's missing from `Economy`

Per the requirement in [decisions/phasing-and-granularity.md](../decisions/phasing-and-granularity.md),
2026-09-05, before Stage 2 locks down the residual definition, this document lists what is
missing to load the WIOD 2016 release into `Economy`. **This document only lists gaps; it
writes no code and settles on no approach.**

⚠ This document was written from memory of the WIOD 2016 release's public documentation,
**without checking the original files**. Before starting Stage 3, download a copy and check
against it — rows marked ⚠ especially need checking.

## What the WIOD 2016 release provides

| Table | Contents | Dimensions |
|---|---|---|
| WIOT | World input-output table, industry × industry, year by year from 2000 to 2014 | 43 economies plus "rest of world," 56 ISIC Rev.4 industries each, intermediate-use matrix 2464×2464 |
| WIOT final demand | Five categories: household consumption, non-profit institution consumption, government consumption, fixed capital formation, inventory change | 5 categories × 44 economies |
| WIOT value-added rows | Taxes less subsidies, compensation of employees, other net taxes, consumption of fixed capital, operating surplus, etc. (⚠ exact row names need checking) | By industry |
| WIOT international transport margins row | ⚠ | By industry |
| SEA | Socio-economic accounts: employment, hours worked, compensation of employees, capital stock, hours worked by skill level (⚠ whether the 2016 release still splits into three skill tiers needs checking) | Economy × industry × year |
| Environmental accounts | Not included in the 2016 release itself. CO₂ emissions have a separate supplementary dataset released in 2019 (⚠ source needs checking) | Economy × industry × year |

All values are denominated in **millions of current-price US dollars**. This determines
most of the gaps below.

## Item-by-item mapping

| WIOD item | Where it lands in `Economy` | Gap |
|---|---|---|
| Industry × economy | One commodity row (kind: intermediate good) plus one producing-unit row, `unit_group` = industry | The economy dimension has no place. `unit_group` has only one level; "grouped by industry" and "grouped by economy" cannot both be expressed |
| Intermediate-use matrix `Z` | `input_commodity` and `input_coefficient`, Leontief coefficient `a_ij = Z_ij / x_j` | 2464×2464, dense, roughly 40% nonzero (⚠), about 2.4 million entries as a flat array. This scale is within v1's range |
| Household consumption | One consumer unit per economy, its `consumption` column mapping to all 2464 commodities | Consumer-unit grouping has only one level, `consumer_group`; "household / government / non-profit" and "which economy" cannot both be expressed |
| Government consumption, non-profit consumption | Public goods' `provision` | WIOD's government consumption is counted by industry, not by "public good" as a kind. The same industry's output goes into both household and government consumption, so **one commodity is simultaneously a private good and a public good**; a single-valued `commodity_kind` cannot hold this |
| Fixed capital formation | No place for it | Capital stock has been deferred past v1. Stage 3 can only treat this as one category of final consumption |
| Inventory change | No place for it | Can be negative. Under a within-period closed definition, the material-balance residual would absorb this into the residual — that is a property of the data, not a defect of the mechanism. A possible landing spot is a negative value in the `endowment` column, but `endowment` is defined as "the quantity available in this period without production," and a negative value needs a separate interpretation |
| Compensation of employees | Input use of the labor commodity | The unit is currency, not hours. SEA has hours worked, but WIOT's labor input is compensation; the ratio between the two is a wage rate, which is data, not theory. Need to decide whether the labor commodity is denominated in currency or in hours |
| Consumption of fixed capital, operating surplus | No place for it | Not a commodity. v1 can ignore it, but this is where the material-balance residual "inputs don't sum to output" comes from; the residual's definition needs to account for this part |
| Taxes less subsidies | No place for it | Can be negative. Same as above |
| Imports and exports | Intermediate use and final demand between economies, already in `Z` and final demand | No gap. WIOT is a closed world table |
| "Rest of world" | One economy | No gap |
| Natural resources | None | WIOD has no physical natural-resource account. Either leave it blank or source it elsewhere (EXIOBASE has one) |
| CO₂ emissions | Needs a new commodity kind | Emissions are a "bad": output with negative utility, subject to an upper-bound constraint. Adding one value to `commodity_kind` suffices, but **the definition of the non-negativity residual has to be reversed for it**; Stage 2 needs to leave room for this when defining residuals |
| Hours worked, employment | `unit_extra` | No gap |
| Year | `period` | No gap. The year-by-year tables can be used directly as multi-period data, but WIOD's adjacent years are not derived from the same evolution rule; using them as a trajectory needs to be documented |

## Summary: there are four real gaps

1. **Two-level grouping.** Both producing units and consumer units need two dimensions,
   "economy" plus "industry / type." `unit_group` and `consumer_group` each have only one
   level. Candidate: put the economy into `extra` (`unit_extra["region"]`), leaving the fixed
   columns unchanged. This is to be decided at Stage 3.
2. **One commodity is simultaneously a private good and a public good.** A single-valued
   `commodity_kind` cannot hold WIOD's government consumption. Candidate: let the kind only
   mark "who produces it" (intermediate good), and move the private/public distinction to
   the consumption side of `Plan` (`consumption` and `provision` are already two separate
   columns). This would change how dep1ex's kinds are tagged; **when Stage 2 defines the
   material-balance residual, it needs to be written to allow for this possibility, and must
   not weld "public-good demand divided by the number of consumer units" into the residual**.
3. **Negative entries.** Inventory change, subsidies, bads. Stage 2's non-negativity residual
   and material-balance residual need to give a definition for negative entries, rather than
   erroring out.
4. **Monetary valuation.** WIOD's "quantities" are currency amounts at current prices.
   `Economy`'s f64 columns are unit-agnostic, which is not a structural gap, but for a WIOD
   economy the prices in `Plan.valuation` are relative price indices, and the documentation
   needs to say so.

The natural-resource account and capital stock are missing data, not gaps in `Economy`.

## Direct requirements for Stage 2

- Material-balance residual: computed per commodity as
  `output + endowment − input_use − consumption − provision`, allowing any term to be
  negative; the residual is a signed number, not an absolute value
- Non-negativity residual: takes a sign convention per commodity kind; for bads,
  "non-negative" means "non-positive"
- Budget residual: WIOD consumer units have no `entitlement`, nor `income`, so the residual
  is N/A. This is the first real use case for N/A
