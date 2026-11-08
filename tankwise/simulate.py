"""Daily tank balance simulation."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from .config import DEFICIT_TOLERANCE_L, INITIAL_FILL_FRACTION, SPINUP_DAYS
from .demand import DailyDemand
from .rainfall import RainfallSeries


@dataclass
class SimulationResult:
    dates: list[date]
    inflow_l: list[float]
    demand_l: list[float]
    met_l: list[float]
    deficit_l: list[float]
    spill_l: list[float]
    level_l: list[float]
    capacity_l: float
    metrics: dict = field(default_factory=dict)

    def monthly_series(self, months: int = 36) -> list[dict]:
        """Aggregate the tail of the record into calendar months."""
        buckets: dict[str, dict] = {}
        order: list[str] = []
        for day, level, spill, met, demand in zip(
            self.dates, self.level_l, self.spill_l, self.met_l, self.demand_l
        ):
            key = f"{day.year:04d}-{day.month:02d}"
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "month": key,
                    "rainfall_mm": 0.0,
                    "inflow_kl": 0.0,
                    "demand_kl": 0.0,
                    "harvested_kl": 0.0,
                    "spill_kl": 0.0,
                    "level_pct_sum": 0.0,
                    "days": 0,
                }
                buckets[key] = bucket
                order.append(key)
            bucket["inflow_kl"] += 0.0
            bucket["demand_kl"] += demand / 1000.0
            bucket["harvested_kl"] += met / 1000.0
            bucket["spill_kl"] += spill / 1000.0
            bucket["level_pct_sum"] += (
                (level / self.capacity_l * 100.0) if self.capacity_l else 0.0
            )
            bucket["days"] += 1

        rows = [buckets[key] for key in order][-months:]
        for row in rows:
            days = row["days"] or 1
            row["level_pct_avg"] = round(row["level_pct_sum"] / days, 1)
            for key in ("inflow_kl", "demand_kl", "harvested_kl", "spill_kl"):
                row[key] = round(row[key], 2)
            row["days"] = days
            del row["level_pct_sum"]
        return rows


def simulate(
    rainfall: RainfallSeries,
    demand: DailyDemand,
    capacity_l: float,
    catchment_m2: float,
    runoff_coefficient: float,
    first_flush_mm: float,
    initial_fraction: float = INITIAL_FILL_FRACTION,
    spinup_days: int = SPINUP_DAYS,
) -> SimulationResult:
    """Run the daily balance for one tank size."""
    if capacity_l <= 0:
        raise ValueError("capacity_l must be positive")
    if catchment_m2 < 0:
        raise ValueError("catchment_m2 must not be negative")

    inflow: list[float] = []
    for value in rainfall.mm:
        harvestable = max(0.0, value - first_flush_mm)
        inflow.append(harvestable * catchment_m2 * runoff_coefficient)

    daily_demand = demand.total_l
    if len(daily_demand) != len(inflow):
        raise ValueError("demand series must align with rainfall series")

    level = capacity_l * initial_fraction
    levels: list[float] = []
    met_values: list[float] = []
    deficits: list[float] = []
    spills: list[float] = []

    for day_index in range(len(inflow)):
        level += inflow[day_index]
        spill = 0.0
        if level > capacity_l:
            spill = level - capacity_l
            level = capacity_l

        wanted = daily_demand[day_index]
        met = min(level, wanted)
        level -= met
        deficit = wanted - met

        spills.append(spill)
        met_values.append(met)
        deficits.append(deficit)
        levels.append(level)

    metrics = _metrics(
        dates=rainfall.dates,
        demand_l=daily_demand,
        met_l=met_values,
        deficit_l=deficits,
        spill_l=spills,
        spinup_days=spinup_days,
    )

    return SimulationResult(
        dates=list(rainfall.dates),
        inflow_l=inflow,
        demand_l=daily_demand,
        met_l=met_values,
        deficit_l=deficits,
        spill_l=spills,
        level_l=levels,
        capacity_l=capacity_l,
        metrics=metrics,
    )


def _metrics(
    dates: list[date],
    demand_l: list[float],
    met_l: list[float],
    deficit_l: list[float],
    spill_l: list[float],
    spinup_days: int,
) -> dict:
    start = min(spinup_days, max(0, len(dates) - 1))
    idx = range(start, len(dates))
    window_days = len(idx)
    if window_days <= 0:
        raise ValueError("record too short for the spin-up period")

    total_demand = sum(demand_l[i] for i in idx)
    total_met = sum(met_l[i] for i in idx)
    total_spill = sum(spill_l[i] for i in idx)
    dry_days = sum(1 for i in idx if deficit_l[i] > DEFICIT_TOLERANCE_L)
    years = window_days / 365.25

    coverage = total_met / total_demand if total_demand else 0.0

    per_year: dict[int, list[float]] = {}
    for i in idx:
        year = dates[i].year
        bucket = per_year.setdefault(year, [0.0, 0.0])
        bucket[0] += met_l[i]
        bucket[1] += demand_l[i]

    year_coverages = [
        met / dem for met, dem in per_year.values() if dem > 0
    ]
    median_cov = statistics.median(year_coverages) if year_coverages else coverage
    p10_cov = (
        sorted(year_coverages)[max(0, int(round(0.10 * (len(year_coverages) - 1))))]
        if year_coverages
        else coverage
    )

    return {
        "coverage": round(coverage, 4),
        "dry_days_per_year": round(dry_days / years, 1),
        "spill_kl_per_year": round(total_spill / 1000.0 / years, 2),
        "harvested_kl_per_year": round(total_met / 1000.0 / years, 2),
        "mains_topup_kl_per_year": round((total_demand - total_met) / 1000.0 / years, 2),
        "median_annual_coverage": round(median_cov, 4),
        "p10_annual_coverage": round(p10_cov, 4),
        "years_simulated": round(years, 2),
        "dry_days_total": dry_days,
        "demand_kl_per_year": round(total_demand / 1000.0 / years, 2),
    }