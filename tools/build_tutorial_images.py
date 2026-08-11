#!/usr/bin/env python3
"""Render the figures the tutorial page walks through.

A dev tool, not part of the package. Every snippet in ``docs/tutorial.md`` is a
step of the same worked example, and each step's figure is written here so the
page shows exactly what its code produces. Run it from the repo root::

    .venv/bin/python tools/build_tutorial_images.py

It writes ``docs/images/tutorial_*.png``. Keep the code below and the snippets
on the page in sync - the page quotes them, it does not include them.
"""
from __future__ import annotations

import math
import os

import pyplotrs as plt

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "images")

# -- the worked example's data ----------------------------------------------
# Reaction rate against temperature for two catalysts, three replicates each.
temp = [280, 300, 320, 340, 360, 380, 400]
rate_a = [0.112, 0.165, 0.276, 0.402, 0.655, 0.978, 1.551]
rate_b = [0.068, 0.115, 0.174, 0.291, 0.451, 0.741, 1.163]
err_a = [0.010, 0.014, 0.022, 0.032, 0.052, 0.078, 0.124]
err_b = [0.008, 0.011, 0.016, 0.026, 0.040, 0.066, 0.105]


def _fit(ts, ys) -> tuple[float, float]:
    """Least squares of ``log y = log A + k*u``, ``u = (t - 280)/100``."""
    us = [(t - 280) / 100.0 for t in ts]
    ls = [math.log(y) for y in ys]
    ubar = sum(us) / len(us)
    lbar = sum(ls) / len(ls)
    k = (sum((u - ubar) * (l - lbar) for u, l in zip(us, ls))
         / sum((u - ubar) ** 2 for u in us))
    return math.exp(lbar - k * ubar), k


A, K = _fit(temp, rate_a)


def model(t: float) -> float:
    """The fitted Arrhenius-ish trend drawn through the points."""
    return A * math.exp(K * (t - 280) / 100.0)


fine = [280 + i for i in range(121)]


def step1() -> plt.Figure:
    fig, ax = plt.subplots()
    ax.line(temp, rate_a)
    return fig


def step2() -> plt.Figure:
    fig, ax = plt.subplots()
    ax.errorbar(temp, rate_a, yerr=err_a, marker="o", label="catalyst A")
    ax.errorbar(temp, rate_b, yerr=err_b, marker="s", label="catalyst B")
    ax.legend()
    return fig


def step3() -> plt.Figure:
    fig, ax = plt.subplots()
    fit = [model(t) for t in fine]
    band = [0.08 * y for y in fit]
    ax.fill_between(fine, [y - e for y, e in zip(fit, band)],
                    [y + e for y, e in zip(fit, band)],
                    color="C0", alpha=0.2, label="95% CI")
    ax.line(fine, fit, color="C0", label="fit")
    ax.errorbar(temp, rate_a, yerr=err_a, marker="o", linestyle="none",
                color="C0", label="catalyst A")
    ax.errorbar(temp, rate_b, yerr=err_b, marker="s", linestyle="none",
                color="C1", label="catalyst B")
    ax.set(title="Catalyst activity",
           xlabel=r"temperature $T$ (K)",
           ylabel=r"rate $k$ (s$^{-1}$)")
    ax.legend(loc="upper left")
    return fig


def step4() -> plt.Figure:
    fig, axs = plt.subplots(2, 1, figsize=(250, 260), sharex=True,
                            height_ratios=[3, 1])
    top, bottom = axs

    fit = [model(t) for t in fine]
    band = [0.08 * y for y in fit]
    top.fill_between(fine, [y - e for y, e in zip(fit, band)],
                     [y + e for y, e in zip(fit, band)],
                     color="C0", alpha=0.2, label="95% CI")
    top.line(fine, fit, color="C0", label="fit")
    top.errorbar(temp, rate_a, yerr=err_a, marker="o", linestyle="none",
                 color="C0", label="catalyst A")
    top.errorbar(temp, rate_b, yerr=err_b, marker="s", linestyle="none",
                 color="C1", label="catalyst B")
    top.set(ylabel=r"rate $k$ (s$^{-1}$)", xticklabels=[])
    top.legend(loc="upper left")

    resid = [r - model(t) for t, r in zip(temp, rate_a)]
    bottom.axhline(0.0, linestyle="dashed")
    bottom.scatter(temp, resid, color="C0")
    bottom.set(xlabel=r"temperature $T$ (K)", ylabel="resid.",
               yticks=[-0.01, 0.0, 0.01])

    fig.set(suptitle="Catalyst activity")
    return fig


def step5() -> plt.Figure:
    fig = step4()
    ax = fig.axes[0]
    ax.annotate("B lags by ~25%", (380, 0.741), xytext=(332, 0.06))
    return fig


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for name, build in [("tutorial_1", step1), ("tutorial_2", step2),
                        ("tutorial_3", step3), ("tutorial_4", step4),
                        ("tutorial_5", step5)]:
        build().save(os.path.join(OUT, f"{name}.png"), dpi=200)
        print(f"wrote {name}.png")


if __name__ == "__main__":
    main()
