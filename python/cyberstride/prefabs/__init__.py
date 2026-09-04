"""Prefabs: coordination procedures set up to reproduce a published experiment.

A prefab is where theoretical commitments belong. It fixes the behavioural equations, the
parameter values and the convergence rule of one paper, so that a run of it can be compared
with what that paper reported. The base layer stays free of all of it.
"""

from __future__ import annotations

from cyberstride.prefabs.hahnel_2020_slides import HahnelSlides2020

__all__ = ["HahnelSlides2020"]
