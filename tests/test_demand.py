"""Tests for the demand model."""

from __future__ import annotations

from datetime import date

import pytest

from tankwise.config import Assumptions
from tankwise.demand import build_demand, seasonal_factor


def test_summer_peak_is_january_in_the_south():
    assert seasonal_factor(date(2024, 1, 15), southern_hemisphere=True) == pytest.approx(1.0, abs=0.02)
    assert seasonal_factor(date(2024, 7, 15), southern_hemisphere=True) == pytest.approx(0.0, abs=0.02)


def test_seasons_flip_in_the_north():
    assert seasonal_factor(date(2024, 7, 15), southern_hemisphere=False) == pytest.approx(1.0, abs=0.02)


def test_garden_demand_peaks_in_summer():
    dates = [date(2024, 1, 15), date(2024, 7, 15)]
    demand = build_demand(dates, Assumptions(occupants=0, garden_area_m2=100), True)
    assert demand.garden_l[0] > demand.garden_l[1] * 3


def test_end_use_switches_remove_demand():
    dates = [date(2024, 4, 1)]
    full = build_demand(dates, Assumptions(occupants=4, garden_area_m2=0), True)
    half = build_demand(
        dates,
        Assumptions(occupants=4, garden_area_m2=0, include_toilet=False, include_laundry=False),
        True,
    )
    assert full.total_l[0] == pytest.approx(180.0)
    assert half.total_l[0] == pytest.approx(0.0)


def test_summary_reports_annual_volume():
    dates = [date(2024, 1, 1)] * 365
    demand = build_demand(dates, Assumptions(occupants=4, garden_area_m2=0), True)
    summary = demand.summary()
    assert summary["mean_daily_litres"] == pytest.approx(180.0, abs=0.5)
    assert summary["annual_kl"] == pytest.approx(65.7, abs=0.5)


def test_no_garden_selected_gives_zero_garden_series():
    dates = [date(2024, 1, 1)]
    demand = build_demand(dates, Assumptions(garden_area_m2=300, include_garden=False), True)
    assert demand.garden_l[0] == 0.0