"""Tank size sweep, recommendation, and payback."""

from __future__ import annotations

from .config import (
    SWEEP_MAX_L,
    SWEEP_MIN_L,
    SWEEP_STEP_L,
    Assumptions,
    TankOption,
    tank_install_cost,
)
from .demand import DailyDemand
from .rainfall import RainfallSeries
from .simulate import simulate


def sweep_sizes(
    rainfall: RainfallSeries,
    demand: DailyDemand,
    catchment_m2: float,
    assumptions: Assumptions,
    sizes: list[float] | None = None,
) -> list[TankOption]:
    """Simulate every candidate tank size. Results are ordered by capacity."""
    candidates = sizes or default_sizes()
    options: list[TankOption] = []

    for capacity in candidates:
        result = simulate(
            rainfall=rainfall,
            demand=demand,
            capacity_l=capacity,
            catchment_m2=catchment_m2,
            runoff_coefficient=assumptions.runoff_coefficient,
            first_flush_mm=assumptions.first_flush_mm,
        )
        metrics = result.metrics
        cost = tank_install_cost(capacity, assumptions.rebate_aud)
        annual_saving = metrics["harvested_kl_per_year"] * assumptions.water_price_per_kl
        payback = round(cost / annual_saving, 1) if annual_saving > 0 else None

        options.append(
            TankOption(
                capacity_litres=capacity,
                coverage=metrics["coverage"],
                dry_days_per_year=metrics["dry_days_per_year"],
                spill_kl_per_year=metrics["spill_kl_per_year"],
                harvested_kl_per_year=metrics["harvested_kl_per_year"],
                mains_topup_kl_per_year=metrics["mains_topup_kl_per_year"],
                median_annual_coverage=metrics["median_annual_coverage"],
                p10_annual_coverage=metrics["p10_annual_coverage"],
                payback_years=payback,
            )
        )

    return options


def default_sizes() -> list[float]:
    sizes: list[float] = []
    size = SWEEP_MIN_L
    while size <= SWEEP_MAX_L + 0.001:
        sizes.append(size)
        size += SWEEP_STEP_L
    return sizes


def recommend(
    options: list[TankOption], target_coverage: float
) -> dict:
    """Pick the smallest tank that meets the coverage target."""
    if not options:
        raise ValueError("no tank options to choose from")

    ordered = sorted(options, key=lambda item: item.capacity_litres)
    best = next((item for item in ordered if item.coverage >= target_coverage), None)

    if best is not None:
        return {
            "capacity_litres": best.capacity_litres,
            "coverage": best.coverage,
            "dry_days_per_year": best.dry_days_per_year,
            "payback_years": best.payback_years,
            "meets_target": True,
            "target_coverage": target_coverage,
            "note": (
                f"A {int(best.capacity_litres):,} L tank meets "
                f"{best.coverage * 100:.0f}% of demand in the median year."
            ),
        }

    largest = ordered[-1]
    return {
        "capacity_litres": largest.capacity_litres,
        "coverage": largest.coverage,
        "dry_days_per_year": largest.dry_days_per_year,
        "payback_years": largest.payback_years,
        "meets_target": False,
        "target_coverage": target_coverage,
        "note": (
            f"No size up to {int(largest.capacity_litres):,} L meets "
            f"{target_coverage * 100:.0f}% of demand. Rain or roof area limits yield."
        ),
    }


def economics(metrics: dict, capacity_l: float, assumptions: Assumptions) -> dict:
    cost = tank_install_cost(capacity_l, assumptions.rebate_aud)
    annual_saving = metrics["harvested_kl_per_year"] * assumptions.water_price_per_kl
    payback = round(cost / annual_saving, 1) if annual_saving > 0 else None
    return {
        "installed_cost_aud": round(cost, 0),
        "rebate_aud": assumptions.rebate_aud,
        "water_price_per_kl": assumptions.water_price_per_kl,
        "annual_saving_aud": round(annual_saving, 0),
        "payback_years": payback,
        "lifetime_saving_aud": round(
            annual_saving * 20 - cost, 0
        ),
        "lifetime_years": 20,
    }