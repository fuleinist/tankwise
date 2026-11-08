"""Tests for the daily tank balance."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tankwise.config import Assumptions
from tankwise.demand import build_demand
from tankwise.rainfall import RainfallSeries, demo_series
from tankwise.simulate import simulate


def make_series(values: list[float], start: date = date(2020, 1, 1)) -> RainfallSeries:
    dates = [start + timedelta(days=index) for index in range(len(values))]
    return RainfallSeries(
        dates=dates,
        mm=values,
        latitude=-33.77,
        longitude=151.18,
        source="test",
    )


def test_mass_balance_holds_every_day():
    series = demo_series(days=800, seed=3)
    demand = build_demand(series.dates, Assumptions(occupants=4, garden_area_m2=120))
    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=5000,
        catchment_m2=200,
        runoff_coefficient=0.85,
        first_flush_mm=1.0,
    )

    previous = 5000 * 0.25
    for index in range(len(series.dates)):
        expected = previous + result.inflow_l[index] - result.spill_l[index] - result.met_l[index]
        assert result.level_l[index] == pytest.approx(expected, abs=1e-6)
        previous = result.level_l[index]


def test_level_stays_within_bounds():
    series = demo_series(days=1200, seed=11)
    demand = build_demand(series.dates, Assumptions(occupants=2, garden_area_m2=50))
    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=2500,
        catchment_m2=150,
        runoff_coefficient=0.85,
        first_flush_mm=1.0,
    )
    assert min(result.level_l) >= 0.0
    assert max(result.level_l) <= 2500 + 1e-6


def test_dry_record_gives_zero_coverage():
    series = make_series([0.0] * 400)
    demand = build_demand(series.dates, Assumptions(occupants=4, garden_area_m2=100))
    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=5000,
        catchment_m2=200,
        runoff_coefficient=0.85,
        first_flush_mm=1.0,
    )
    assert result.metrics["coverage"] == pytest.approx(0.0, abs=0.02)
    assert result.metrics["dry_days_per_year"] > 300


def test_larger_tank_never_lowers_coverage():
    series = demo_series(days=1500, seed=5)
    demand = build_demand(series.dates, Assumptions(occupants=4, garden_area_m2=150))
    coverages = []
    for size in (1000, 3000, 5000, 8000):
        result = simulate(
            rainfall=series,
            demand=demand,
            capacity_l=size,
            catchment_m2=200,
            runoff_coefficient=0.85,
            first_flush_mm=1.0,
        )
        coverages.append(result.metrics["coverage"])
    assert coverages == sorted(coverages)


def test_spinup_days_are_excluded():
    series = make_series([10.0] * 400)
    demand = build_demand(series.dates, Assumptions(occupants=1, garden_area_m2=0))
    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=3000,
        catchment_m2=100,
        runoff_coefficient=0.85,
        first_flush_mm=1.0,
        spinup_days=100,
    )
    assert result.metrics["years_simulated"] == pytest.approx(300 / 365.25, abs=0.01)


def test_mismatched_demand_length_raises():
    series = make_series([1.0] * 400)
    demand = build_demand(series.dates[:300], Assumptions())
    with pytest.raises(ValueError):
        simulate(
            rainfall=series,
            demand=demand,
            capacity_l=5000,
            catchment_m2=200,
            runoff_coefficient=0.85,
            first_flush_mm=1.0,
        )


def test_monthly_series_shape():
    series = demo_series(days=1100, seed=9)
    demand = build_demand(series.dates, Assumptions())
    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=5000,
        catchment_m2=200,
        runoff_coefficient=0.85,
        first_flush_mm=1.0,
    )
    rows = result.monthly_series(months=12)
    assert len(rows) == 12
    assert {"month", "rainfall_mm", "demand_kl", "harvested_kl", "level_pct_avg"} <= set(rows[0])
    assert all(0 <= row["level_pct_avg"] <= 100 for row in rows)