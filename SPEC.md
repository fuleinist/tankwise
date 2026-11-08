# SPEC — tankwise

## 1. Problem

Households buy rainwater tanks by guess or by plumber advice. They do not know how
much mains water the tank will replace. They do not know how many days the tank will
run dry. A wrong size wastes money in both directions. A small tank misses demand.
A large tank costs more than the water it saves.

## 2. Goal

Give a household one number it can act on. The tool simulates a tank against 30 years
of local daily rainfall. It reports the share of demand the tank meets. It recommends
the smallest tank that reaches a target reliability. It estimates payback.

## 3. Users

- A homeowner who plans to buy a tank.
- A plumber or installer who wants a neutral sizing check.
- A council or rebate assessor who checks a claimed tank size.

## 4. Scope of the first release

### 4.1 In scope

1. Location input by address search, postcode, or map click.
2. Daily rainfall for 30 full years from Open-Meteo Archive (ERA5). No API key.
3. Roof area estimate from OpenStreetMap building footprints. The user can override it.
4. Demand model with three end uses: garden, toilet, laundry.
5. Daily tank balance with first-flush loss, runoff coefficient, spill, and draw.
6. Tank size sweep from 1,000 L to 10,000 L in 500 L steps.
7. Reliability metrics: demand coverage, dry days per year, spill, harvested volume.
8. Recommendation of the smallest tank that meets the target coverage.
9. Payback estimate from a mains water price and an installed cost model.
10. Web UI with map, inputs, result cards, and two charts.
11. CLI for the same calculation.

### 4.2 Out of scope

- Pump, pressure, and plumbing design.
- Rainwater quality and treatment.
- Rebate rules for each jurisdiction. The user enters a rebate amount.
- Real-time tank sensors.
- Stormwater detention credits.

## 5. Data sources

| Source | Use | Cost |
| --- | --- | --- |
| Open-Meteo Archive API (`archive-api.open-meteo.com`) | Daily precipitation, 1940 to present | Free, no key |
| Open-Meteo Geocoding API (`geocoding-api.open-meteo.com`) | Address and postcode search | Free, no key |
| OpenStreetMap Overpass API (`overpass-api.de`) | Building footprints for roof area | Free, fair use |
| OpenStreetMap tiles | Map background | Free, attribution required |

SILO (Queensland Long Paddock) stays a planned second provider. Its data drill needs
a registered API key. The provider interface allows a later addition.

## 6. Model

### 6.1 Catchment

```
catchment_m2 = roof_area_m2
inflow_L   = max(0, rain_mm - first_flush_mm) * catchment_m2 * runoff_coefficient
```

Defaults: `runoff_coefficient = 0.85` for a hard roof. `first_flush_mm = 1.0` per rain day.

### 6.2 Demand

```
indoor_L_per_day = occupants * (toilet_L + laundry_L)      # selected end uses only
garden_L_per_day = garden_area_m2 * seasonal_mm_per_week / 7
demand_L_per_day = indoor_L_per_day + garden_L_per_day
```

Default rates: toilet 25 L per person per day. Laundry 20 L per person per day.
Garden 3 mm per week in winter to 25 mm per week in summer. The seasonal curve flips
for the northern hemisphere.

### 6.3 Tank balance

For each day, in this order:

1. Add inflow.
2. Spill the volume above capacity.
3. Draw demand, limited by the available level.
4. Record the deficit.

Initial level is 25 percent of capacity. The first 90 days are spin-up and are
excluded from reliability metrics.

### 6.4 Metrics

- `coverage = sum(met_L) / sum(demand_L)`
- `dry_days_per_year = days with deficit > 0.5 L / (days / 365.25)`
- `spill_kl_per_year`, `harvested_kl_per_year`, `mains_topup_kl_per_year`
- `median_annual_coverage` and `p10_annual_coverage` over full calendar years

### 6.5 Economics

```
installed_cost_aud = 900 + 0.46 * capacity_L - rebate_aud
annual_saving_aud  = harvested_kl_per_year * water_price_per_kl
payback_years      = installed_cost_aud / annual_saving_aud
```

Default water price is 2.35 AUD per kL. This is the Sydney 2026 usage rate.
Service charges are excluded. The README states this assumption.

## 7. API

`GET /api/health` returns status and version.

`GET /api/geocode?q=<text>` returns up to five places with name, region, country,
latitude, and longitude.

`POST /api/roof` with `{latitude, longitude}` returns an estimated roof area, the
building count, and a confidence label. The call falls back to the default area when
Overpass fails.

`POST /api/plan` with the plan request returns:

- `location`, `rainfall_summary`, `demand_summary`
- `result` metrics for the chosen tank
- `sweep` list for the chart
- `recommendation`
- `economics`
- `monthly` series for the level chart
- `assumptions` list

## 8. Acceptance criteria

1. `pytest` passes with no network access.
2. Mass balance holds on every simulated day: inflow minus spill minus draw equals
   the change in stored volume, within 0.001 L.
3. Tank level never goes below zero and never exceeds capacity.
4. Coverage does not fall when tank size rises.
5. The recommended tank meets the target coverage, or the response reports that no
   size in the sweep meets it.
6. `python -m tankwise.cli --lat -33.77 --lon 151.18 --tank 5000` prints a result
   table with no server running.
7. The web page renders results from a real API call. No placeholder numbers.
8. The README states every default assumption and every data source.

## 9. Stack

- Python 3.10 or later. The engine uses the standard library only.
- FastAPI and uvicorn for the HTTP server. These are optional extras.
- Vanilla JavaScript, hand-built SVG charts, and Leaflet for the map. No build step.
- SQLite for the rainfall cache.

### 9.1 Deviation from the idea record

The idea record lists pandas. The engine uses plain Python lists and the `statistics`
module instead. Rationale: the dataset is small, the tests run without pandas, and
the tool installs on any Python 3.10 system. The API shape does not change.

## 10. Risks

- Roof area from OSM can be missing or wrong. The UI shows the estimate as editable.
- Demand varies by household. The UI exposes every rate through advanced inputs.
- CAMS-style gridded rainfall is coarse. The model reports a range across years.
- Payback depends on local water price. The user sets the price.