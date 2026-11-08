"""Household demand model.

Three end uses are modelled. Each one has a documented default rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .config import (
    GARDEN_MM_PER_WEEK_SUMMER,
    GARDEN_MM_PER_WEEK_WINTER,
    LAUNDRY_L_PER_PERSON_DAY,
    TOILET_L_PER_PERSON_DAY,
    Assumptions,
)


def seasonal_factor(day: date, southern_hemisphere: bool = True) -> float:
    """Return 1.0 at midsummer and 0.0 at midwinter."""
    # Day 15 of January is the southern summer peak.
    day_of_year = day.timetuple().tm_yday
    phase = 2.0 * math.pi * (day_of_year - 15) / 365.25
    if not southern_hemisphere:
        phase += math.pi
    return 0.5 + 0.5 * math.cos(phase)


@dataclass
class DailyDemand:
    dates: list[date]
    garden_l: list[float]
    toilet_l: list[float]
    laundry_l: list[float]

    @property
    def total_l(self) -> list[float]:
        return [
            g + t + l
            for g, t, l in zip(self.garden_l, self.toilet_l, self.laundry_l)
        ]

    def summary(self) -> dict:
        total = self.total_l
        annual = sum(total) / (len(total) / 365.25) if total else 0.0
        return {
            "mean_daily_litres": round(sum(total) / len(total), 1) if total else 0.0,
            "annual_kl": round(annual / 1000.0, 2),
            "breakdown_litres_per_day": {
                "garden": round(sum(self.garden_l) / len(self.garden_l), 1)
                if self.garden_l
                else 0.0,
                "toilet": round(sum(self.toilet_l) / len(self.toilet_l), 1)
                if self.toilet_l
                else 0.0,
                "laundry": round(sum(self.laundry_l) / len(self.laundry_l), 1)
                if self.laundry_l
                else 0.0,
            },
        }


def build_demand(
    dates: list[date],
    assumptions: Assumptions,
    southern_hemisphere: bool = True,
) -> DailyDemand:
    """Build a daily demand series aligned to the rainfall dates."""
    garden: list[float] = []
    toilet: list[float] = []
    laundry: list[float] = []

    toilet_rate = TOILET_L_PER_PERSON_DAY if assumptions.include_toilet else 0.0
    laundry_rate = LAUNDRY_L_PER_PERSON_DAY if assumptions.include_laundry else 0.0
    indoor = assumptions.occupants * (toilet_rate + laundry_rate)

    for day in dates:
        if assumptions.include_garden and assumptions.garden_area_m2 > 0:
            factor = seasonal_factor(day, southern_hemisphere)
            mm_per_week = (
                GARDEN_MM_PER_WEEK_WINTER
                + (GARDEN_MM_PER_WEEK_SUMMER - GARDEN_MM_PER_WEEK_WINTER) * factor
            )
            garden_l = assumptions.garden_area_m2 * mm_per_week / 7.0
        else:
            garden_l = 0.0

        toilet_l = assumptions.occupants * toilet_rate
        laundry_l = assumptions.occupants * laundry_rate
        garden.append(garden_l)
        toilet.append(toilet_l)
        laundry.append(laundry_l)

    return DailyDemand(dates=dates, garden_l=garden, toilet_l=toilet, laundry_l=laundry)