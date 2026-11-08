"""Command-line interface for tankwise."""

from __future__ import annotations

import argparse
import json
import sys

from .config import Assumptions, ROOF_AREA_DEFAULT_M2
from .demand import build_demand
from .geo import GeoError, roof_area
from .rainfall import RainfallError, demo_series, fetch_open_meteo, window
from .simulate import simulate
from .sizing import default_sizes, economics, recommend, sweep_sizes


def _fmt_litres(value: float) -> str:
    return f"{int(value):,} L"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tankwise",
        description="Simulate a rainwater tank against 30 years of local rainfall.",
    )
    parser.add_argument("--lat", type=float, required=False, help="latitude")
    parser.add_argument("--lon", type=float, required=False, help="longitude")
    parser.add_argument("--roof", type=float, default=None, help="roof area in m2")
    parser.add_argument("--tank", type=float, default=5000, help="tank size in litres")
    parser.add_argument("--occupants", type=int, default=4)
    parser.add_argument("--garden", type=float, default=100.0, help="garden area in m2")
    parser.add_argument("--years", type=int, default=30)
    parser.add_argument("--target", type=float, default=0.90, help="target coverage 0-1")
    parser.add_argument("--price", type=float, default=2.35, help="water price AUD per kL")
    parser.add_argument("--rebate", type=float, default=0.0, help="rebate in AUD")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use the offline synthetic series instead of the live API",
    )
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)

    if not args.demo and (args.lat is None or args.lon is None):
        parser.error("--lat and --lon are required unless --demo is set")

    latitude = args.lat if args.lat is not None else -33.77
    longitude = args.lon if args.lon is not None else 151.18

    assumptions = Assumptions(
        occupants=args.occupants,
        garden_area_m2=args.garden,
        target_coverage=args.target,
        water_price_per_kl=args.price,
        rebate_aud=args.rebate,
    )

    roof = args.roof
    if roof is None:
        try:
            roof = float(roof_area(latitude, longitude)["roof_area_m2"])
            roof_source = "OpenStreetMap"
        except GeoError:
            roof = ROOF_AREA_DEFAULT_M2
            roof_source = "default"
    else:
        roof_source = "input"

    try:
        if args.demo:
            series = demo_series(days=args.years * 365 + 8)
        else:
            start, end = window(args.years)
            series = fetch_open_meteo(latitude, longitude, start, end)
    except RainfallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    demand = build_demand(series.dates, assumptions, southern_hemisphere=latitude < 0)
    result = simulate(
        rainfall=series,
        demand=demand,
        capacity_l=args.tank,
        catchment_m2=roof,
        runoff_coefficient=assumptions.runoff_coefficient,
        first_flush_mm=assumptions.first_flush_mm,
    )
    options = sweep_sizes(
        rainfall=series,
        demand=demand,
        catchment_m2=roof,
        assumptions=assumptions,
        sizes=default_sizes(),
    )
    choice = recommend(options, assumptions.target_coverage)
    money = economics(result.metrics, args.tank, assumptions)

    if args.json:
        print(
            json.dumps(
                {
                    "location": {"latitude": latitude, "longitude": longitude},
                    "roof_area_m2": round(roof, 1),
                    "roof_source": roof_source,
                    "rainfall": {
                        "source": series.source,
                        "years": round(series.years, 1),
                        "mean_annual_mm": round(series.mean_annual_mm(), 1),
                    },
                    "result": result.metrics,
                    "economics": money,
                    "recommendation": choice,
                    "sweep": [option.to_dict() for option in options],
                },
                indent=2,
            )
        )
        return 0

    metrics = result.metrics
    print()
    print(f"tankwise  |  {latitude:.4f}, {longitude:.4f}")
    print("-" * 62)
    print(f"Rainfall        {series.mean_annual_mm():>7.0f} mm/year  ({series.source})")
    print(f"Roof area       {roof:>7.0f} m2      ({roof_source})")
    print(f"Demand          {demand.summary()['annual_kl']:>7.1f} kL/year")
    print(f"Tank            {_fmt_litres(args.tank):>10}")
    print("-" * 62)
    print(f"Coverage        {metrics['coverage'] * 100:>7.0f} %")
    print(f"Dry days/year   {metrics['dry_days_per_year']:>7.0f}")
    print(f"Harvested       {metrics['harvested_kl_per_year']:>7.1f} kL/year")
    print(f"Mains top-up    {metrics['mains_topup_kl_per_year']:>7.1f} kL/year")
    print(f"Median year     {metrics['median_annual_coverage'] * 100:>7.0f} % coverage")
    print(f"Dry year (p10)  {metrics['p10_annual_coverage'] * 100:>7.0f} % coverage")
    print("-" * 62)
    payback = money["payback_years"]
    payback_text = f"{payback:.1f} years" if payback else "n/a"
    print(f"Installed cost  {money['installed_cost_aud']:>7.0f} AUD")
    print(f"Saving          {money['annual_saving_aud']:>7.0f} AUD/year")
    print(f"Payback         {payback_text:>10}")
    print("-" * 62)
    print(choice["note"])
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())