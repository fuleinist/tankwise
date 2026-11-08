"""Default assumptions for the tankwise engine.

Every value here is an assumption the README states. Users can override each one
through the API.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

AUD_PER_KL_DEFAULT = 2.35
"""Sydney 2026 usage rate, AUD per kilolitre. Service charges are excluded."""

TOILET_L_PER_PERSON_DAY = 25.0
LAUNDRY_L_PER_PERSON_DAY = 20.0
GARDEN_MM_PER_WEEK_WINTER = 3.0
GARDEN_MM_PER_WEEK_SUMMER = 25.0

ROOF_AREA_DEFAULT_M2 = 200.0
RUNOFF_COEFFICIENT = 0.85
FIRST_FLUSH_MM = 1.0
INITIAL_FILL_FRACTION = 0.25
SPINUP_DAYS = 90
DEFICIT_TOLERANCE_L = 0.5

SWEEP_MIN_L = 1000.0
SWEEP_MAX_L = 10000.0
SWEEP_STEP_L = 500.0


@dataclass
class Assumptions:
    """Model inputs that a household can change."""

    occupants: int = 4
    garden_area_m2: float = 100.0
    include_garden: bool = True
    include_toilet: bool = True
    include_laundry: bool = True
    runoff_coefficient: float = RUNOFF_COEFFICIENT
    first_flush_mm: float = FIRST_FLUSH_MM
    water_price_per_kl: float = AUD_PER_KL_DEFAULT
    rebate_aud: float = 0.0
    target_coverage: float = 0.90

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TankOption:
    capacity_litres: float
    coverage: float
    dry_days_per_year: float
    spill_kl_per_year: float
    harvested_kl_per_year: float
    mains_topup_kl_per_year: float
    median_annual_coverage: float
    p10_annual_coverage: float
    payback_years: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def tank_install_cost(capacity_litres: float, rebate_aud: float = 0.0) -> float:
    """Installed cost model in AUD.

    The model uses a base cost plus a per-litre rate. A 5,000 L tank costs about
    AUD 3,200 before rebates. The README lists this as an estimate, not a quote.
    """
    base = 900.0
    per_litre = 0.46
    return max(0.0, base + per_litre * capacity_litres - rebate_aud)


def py_round(value: float, digits: int = 3) -> float:
    return float(round(value, digits))