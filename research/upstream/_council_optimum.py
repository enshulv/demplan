"""The problem a worker council solves in the Hahnel-Szczepanczyk simulations, and its optimum
computed without any upstream code.

A council chooses inputs x_1..x_N and effort e to

    maximise  lam * z  -  sum_i p_i * x_i  -  s * e**k,    z = a * x_1**b_1 * ... * x_N**b_N * e**c

lam is the price of the council's product, p_i the price of input i, a total factor
productivity, b_i the input exponents, c the effort elasticity, s and k the coefficient and
exponent of the disutility of effort; z is the council's output. With sum(b) + c < 1 and k > 1
the objective is strictly concave in (log x, log e) and has one maximum, where

    lam * b_i * z = p_i * x_i      and      lam * c * z = s * k * e**k.

pequod-cljs and pequod-plus solve it with one closed-form expression per number of inputs
(``solution-N``). This module finds the same optimum numerically, so that each closed form can
be checked against it.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
from scipy.optimize import minimize

POLISH_STEPS = 20
"""Newton steps after the trust-region search; each doubles the correct digits near the optimum."""
POLISH_STOP = 1e-15
"""A Newton step smaller than this in every log-coordinate ends the polish."""


@dataclasses.dataclass(frozen=True)
class CouncilProblem:
    """The parameters of one council's problem at one set of prices."""

    a: float
    s: float
    c: float
    k: float
    lam: float
    """Price of the council's product."""
    b: np.ndarray
    """Input exponents, one per input."""
    p: np.ndarray
    """Input prices, in the order of ``b``."""


def objective(problem: CouncilProblem, x: np.ndarray, e: float) -> float:
    """``lam * z - p @ x - s * e**k`` at inputs ``x`` and effort ``e``."""
    z = problem.a * np.prod(x ** problem.b) * e ** problem.c
    return problem.lam * z - float(problem.p @ x) - problem.s * e ** problem.k


def effort_condition_residual(problem: CouncilProblem, output: float, effort: float) -> float:
    """``log(lam * c * z) - log(s * k * e**k)``: zero where the effort is optimal for the output.

    Needs only the output and the effort, so it can be evaluated on a program's recorded values
    without its input quantities.
    """
    return (math.log(problem.lam * problem.c * output)
            - math.log(problem.s * problem.k * effort ** problem.k))


def foc_residuals(problem: CouncilProblem, output: float, effort: float, x: np.ndarray) -> np.ndarray:
    """Log residuals of the production function, the N input conditions and the effort condition."""
    production = math.log(output) - (math.log(problem.a) + float(problem.b @ np.log(x))
                                     + problem.c * math.log(effort))
    inputs = np.log(problem.lam * problem.b * output) - np.log(problem.p * x)
    return np.concatenate([[production], inputs, [effort_condition_residual(problem, output, effort)]])


def maximise(problem: CouncilProblem) -> tuple[float, float, np.ndarray]:
    """The numerical maximiser ``(output, effort, x)``, by trust-region Newton in w = (log x, log e).

    The objective is divided by ``lam * a`` to keep its scale near one. The gradient and Hessian
    are exact. The search starts at x = e = 1.
    """
    a, s, c, k, lam, b, p = problem.a, problem.s, problem.c, problem.k, problem.lam, problem.b, problem.p
    exps = np.append(b, c)
    scale = lam * a

    def parts(w):
        """Output, inputs and effort cost at w = (log x, log e)."""
        z = a * math.exp(float(exps @ w))
        x = np.exp(w[:-1])
        effort_cost = s * math.exp(k * w[-1])
        return z, x, effort_cost

    def f(w):
        """The objective at w, negated and scaled for minimisation."""
        z, x, effort_cost = parts(w)
        return -(lam * z - float(p @ x) - effort_cost) / scale

    def grad(w):
        """Gradient of f."""
        z, x, effort_cost = parts(w)
        g = lam * z * exps
        g[:-1] -= p * x
        g[-1] -= k * effort_cost
        return -g / scale

    def hess(w):
        """Hessian of f."""
        z, x, effort_cost = parts(w)
        h = lam * z * np.outer(exps, exps)
        h[np.arange(len(x)), np.arange(len(x))] -= p * x
        h[-1, -1] -= k * k * effort_cost
        return -h / scale

    result = minimize(f, np.zeros(len(exps)), jac=grad, hess=hess, method="trust-exact",
                      options={"gtol": 1e-13, "maxiter": 1000})
    w = result.x
    # trust-exact stops once its model predicts no further decrease of the scaled objective, which
    # can leave first-order residuals near 1e-7. Plain Newton steps from there converge quadratically.
    for _ in range(POLISH_STEPS):
        step = np.linalg.solve(hess(w), grad(w))
        w = w - step
        if float(np.max(np.abs(step))) < POLISH_STOP:
            break
    return a * math.exp(float(exps @ w)), math.exp(w[-1]), np.exp(w[:-1])


def predicted_effort_ratio(problem: CouncilProblem) -> float:
    """Effort from the closed form with +b_i*log(k) and +b_i*log(s) in place of -b_i*log(k) and
    -b_i*log(s), divided by the optimal effort.

    The optimal log effort is (... + log k - sum(b) log k + log s - sum(b) log s ...) / D with
    D = c - k + k * sum(b); flipping the sign of the sum(b) terms adds
    2 * sum(b) * (log k + log s) / D. This is algebra on the expression.
    """
    denominator = problem.c - problem.k + problem.k * float(problem.b.sum())
    return math.exp(2.0 * float(problem.b.sum()) * (math.log(problem.k) + math.log(problem.s)) / denominator)
