"""Tests for the size sweep and the recommendation."""

from __future__ import annotations

import pytest

from tankwise.config import Assumptions, TankOption, tank_install_cost
from tankwise.demand import build_demand
from tankwise.rainfall import demo_series
from tankwise.sizing import default_sizes, economics, recommend, sweep_sizes


def make_option(capacity: float, coverage: float) -> TankOption:
    return TankOption(
        capacity_litres=capacity,
        coverage=coverage,
        dry_days_per_year=10.0,
        spill_kl_per_year=1.0,
        harvested_kl_per_year=40.0,
        mains_topup_kl_per_year=10.0,
        median_annual_coverage=coverage,
        p10_annual_coverage=coverage - 0.05,
        payback_years=5.0,
    )


def test_default_sweep_covers_the_range():
    sizes = default_sizes()
    assert sizes[0] == 1000
    assert sizes[-1] == 10000
    assert len(sizes) == 19


def test_recommend_picks_the_smallest_that_meets_target():
    options = [make_option(1000, 0.4), make_option(3000, 0.8), make_option(5000, 0.93)]
    choice = recommend(options, 0.90)
    assert choice["capacity_litres"] == 5000
    assert choice["meets_target"] is True


def test_recommend_reports_when_target_is_unreachable():
    options = [make_option(1000, 0.4), make_option(2000, 0.6)]
    choice = recommend(options, 0.95)
    assert choice["meets_target"] is False
    assert choice["capacity_litres"] == 2000
    assert "No size" in choice["note"]


def test_coverage_rises_with_tank_size_on_real_record():
    series = demo_series(days=1500, seed=21)
    assumptions = Assumptions(occupants=4, garden_area_m2=100)
    demand = build_demand(series.dates, assumptions, southern_hemisphere=True)
    options = sweep_sizes(
        rainfall=series,
        demand=demand,
        catchment_m2=200,
        assumptions=assumptions,
        sizes=[1000, 2500, 5000, 10000],
    )
    assert [item.capacity_litres for item in options] == [1000, 2500, 5000, 10000]
    coverages = [item.coverage for item in options]
    assert coverages == sorted(coverages)


def test_install_cost_scales_with_capacity():
    assert tank_install_cost(5000) == pytest.approx(3200.0)
    assert tank_install_cost(5000, rebate_aud=500) == pytest.approx(2700.0)
    assert tank_install_cost(5000, rebate_aud=99999) == 0.0


def test_payback_is_none_without_harvest():
    metrics = {
        "harvested_kl_per_year": 0.0,
        "mains_topup_kl_per_year": 60.0,
        "coverage": 0.0,
    }
    money = economics(metrics, 5000, Assumptions())
    assert money["payback_years"] is None
    assert money["annual_saving_aud"] == 0


def test_payback_uses_water_price():
    metrics = {"harvested_kl_per_year": 40.0}
    money = economics(metrics, 5000, Assumptions(water_price_per_kl=3.00))
    assert money["annual_saving_aud"] == pytest.approx(120.0)
    assert money["payback_years"] == pytest.approx(3200 / 120, abs=0.1)