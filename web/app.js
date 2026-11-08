/* tankwise front-end. Vanilla JS, hand-built SVG charts, no build step. */

const state = {
  lat: -33.7667,
  lon: 151.1833,
  label: "Sydney, New South Wales, Australia",
  roofSource: "default assumption",
  roofConfidence: "low",
  map: null,
  marker: null,
  busy: false,
};

const $ = (id) => document.getElementById(id);
const fmtInt = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 });
const fmt1 = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 1 });

function litres(value) {
  return `${fmtInt.format(Math.round(value))} L`;
}

function setBusy(busy) {
  state.busy = busy;
  $("plan-btn").disabled = busy;
  $("demo-btn").disabled = busy;
  $("plan-btn").textContent = busy ? "Running…" : "Plan this tank";
}

function errorText(payload, fallback) {
  const detail = payload && payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => `${(item.loc || []).join(".")}: ${item.msg || "invalid"}`)
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.hidden = false;
}

function clearError() {
  $("error").hidden = true;
}

/* ---------- map ---------- */

function initMap() {
  if (typeof L === "undefined") {
    $("map").innerHTML =
      '<p class="hint" style="padding:12px">Map library did not load. Enter coordinates through the address search.</p>';
    return;
  }

  state.map = L.map("map", { zoomControl: true, attributionControl: true }).setView(
    [state.lat, state.lon],
    11
  );

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(state.map);

  state.marker = L.marker([state.lat, state.lon]).addTo(state.map);

  state.map.on("click", (event) => {
    setLocation(event.latlng.lat, event.latlng.lng, "Pinned location");
    lookupRoof();
  });
}

function setLocation(lat, lon, label) {
  state.lat = lat;
  state.lon = lon;
  state.label = label;
  $("location-label").textContent = `${label} · ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  if (state.map && state.marker) {
    state.marker.setLatLng([lat, lon]);
    state.map.setView([lat, lon], Math.max(state.map.getZoom(), 12));
  }
}

/* ---------- geocode ---------- */

async function search() {
  const query = $("address").value.trim();
  if (query.length < 2) return;
  clearError();
  try {
    const response = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Search failed");
    renderResults(payload.results || []);
  } catch (error) {
    showError(`Address search failed. ${error.message}`);
  }
}

function renderResults(results) {
  const list = $("search-results");
  list.innerHTML = "";
  if (!results.length) {
    list.hidden = true;
    showError("No place found for that search.");
    return;
  }
  for (const item of results) {
    const li = document.createElement("li");
    li.textContent = item.label;
    li.tabIndex = 0;
    li.addEventListener("click", () => {
      setLocation(item.latitude, item.longitude, item.label);
      list.hidden = true;
      lookupRoof();
    });
    list.appendChild(li);
  }
  list.hidden = false;
}

/* ---------- roof ---------- */

async function lookupRoof() {
  $("roof-hint").textContent = "Looking up building footprint…";
  try {
    const response = await fetch("/api/roof", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude: state.lat, longitude: state.lon }),
    });
    const payload = await response.json();
    $("roof").value = Math.round(payload.roof_area_m2);
    state.roofSource = payload.source;
    state.roofConfidence = payload.confidence;
    $("roof-hint").textContent =
      payload.confidence === "fallback"
        ? "No footprint found. Default area used. Adjust it if you know the roof."
        : `Estimate from ${payload.source} (${payload.confidence} confidence). Adjust if needed.`;
  } catch (error) {
    $("roof-hint").textContent = "Roof lookup failed. Keep or edit the area above.";
  }
}

/* ---------- plan ---------- */

async function plan(offline = false) {
  if (state.busy) return;
  clearError();
  setBusy(true);

  const body = {
    latitude: state.lat,
    longitude: state.lon,
    roof_area_m2: Number($("roof").value),
    occupants: Number($("occupants").value),
    garden_area_m2: Number($("garden").value),
    tank_litres: Number($("tank").value),
    target_coverage: Number($("target").value),
    water_price_per_kl: Number($("price").value),
    rebate_aud: Number($("rebate").value),
    include_garden: $("use-garden").checked,
    include_toilet: $("use-toilet").checked,
    include_laundry: $("use-laundry").checked,
    offline_demo: offline,
  };

  try {
    const response = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(errorText(payload, "The plan failed."));
    }
    render(payload);
    $("placeholder").hidden = true;
    $("output").hidden = false;
    $("data-pill").textContent = offline ? "Offline demo series" : payload.location.rainfall_source;
  } catch (error) {
    showError(`Plan failed. ${error.message}`);
  } finally {
    setBusy(false);
  }
}

/* ---------- render ---------- */

function render(payload) {
  const { result, recommendation, economics, rainfall_summary, demand_summary } = payload;
  const chosen = Number(payload.tank.capacity_litres);

  $("rec-size").textContent = litres(recommendation.capacity_litres);
  $("rec-sub").textContent = recommendation.meets_target
    ? `meets ${Math.round(recommendation.coverage * 100)}% of demand in the median year`
    : `best available: ${Math.round(recommendation.coverage * 100)}% of demand`;

  const badge = $("rec-badge");
  badge.textContent = recommendation.meets_target ? "target met" : "target not reachable";
  badge.className = "badge" + (recommendation.meets_target ? "" : " warn");

  $("rec-your-tank").textContent = `${litres(chosen)} · ${Math.round(result.coverage * 100)}%`;
  $("rec-note").textContent = recommendation.note;

  $("t-coverage").textContent = `${Math.round(result.coverage * 100)}%`;
  $("t-coverage-sub").textContent = `median year ${Math.round(result.median_annual_coverage * 100)}%, dry year ${Math.round(result.p10_annual_coverage * 100)}%`;
  $("t-dry").textContent = fmt1.format(result.dry_days_per_year);
  $("t-harvest").textContent = fmt1.format(result.harvested_kl_per_year);
  $("t-harvest-sub").textContent = "kL per year, replaces mains";
  $("t-payback").textContent =
    economics.payback_years === null ? "n/a" : `${fmt1.format(economics.payback_years)} yr`;
  $("t-payback-sub").textContent =
    economics.payback_years === null
      ? "no saving at this price"
      : `saves A$${fmtInt.format(economics.annual_saving_aud)}/yr`;

  renderSweep(payload.sweep, payload.assumptions.target_coverage, recommendation.capacity_litres, chosen);
  renderMonthly(payload.monthly);

  $("sweep-note").textContent = `${Math.round(payload.assumptions.target_coverage * 100)}% target shown as a dashed line.`;

  fillFacts("site-list", [
    ["Rainfall", `${fmtInt.format(rainfall_summary.mean_annual_mm)} mm/yr`],
    ["Record", `${fmt1.format(rainfall_summary.years)} years`],
    ["Roof", `${fmtInt.format(payload.roof.area_m2)} m² (${payload.roof.confidence})`],
    ["Catchment", `${fmtInt.format(payload.tank.catchment_m2)} m²`],
    ["Runoff", `${Math.round(payload.tank.runoff_coefficient * 100)}%`],
    ["Location", `${payload.location.latitude.toFixed(3)}, ${payload.location.longitude.toFixed(3)}`],
  ]);

  const breakdown = demand_summary.breakdown_litres_per_day;
  fillFacts("demand-list", [
    ["Total", `${fmt1.format(demand_summary.mean_daily_litres)} L/day`],
    ["Annual", `${fmt1.format(demand_summary.annual_kl)} kL`],
    ["Garden", `${fmt1.format(breakdown.garden)} L/day`],
    ["Toilets", `${fmt1.format(breakdown.toilet)} L/day`],
    ["Laundry", `${fmt1.format(breakdown.laundry)} L/day`],
    ["People", `${payload.assumptions.occupants}`],
  ]);

  fillFacts("money-list", [
    ["Installed", `A$${fmtInt.format(economics.installed_cost_aud)}`],
    ["Rebate", `A$${fmtInt.format(economics.rebate_aud)}`],
    ["Saving", `A$${fmtInt.format(economics.annual_saving_aud)}/yr`],
    ["Payback", economics.payback_years === null ? "n/a" : `${fmt1.format(economics.payback_years)} yr`],
    ["20-year net", `A$${fmtInt.format(economics.lifetime_saving_aud)}`],
    ["Water price", `A$${fmt1.format(economics.water_price_per_kl)}/kL`],
  ]);

  const assumptions = payload.assumptions;
  $("assumption-list").innerHTML = [
    `First flush loss: ${fmt1.format(assumptions.first_flush_mm)} mm per rain day.`,
    `Runoff coefficient: ${Math.round(assumptions.runoff_coefficient * 100)}%.`,
    `Toilet use: 25 L per person per day. Laundry: 20 L per person per day.`,
    `Garden demand: 3 mm per week in winter to 25 mm per week in summer.`,
    "Initial tank level: 25%. First 90 days are spin-up and excluded from metrics.",
    `Installed cost model: A$900 + A$0.46 per litre, minus rebate. Lifetime assumed 20 years.`,
    `Water price: A$${fmt1.format(assumptions.water_price_per_kl)} per kL. Service charges are excluded.`,
    "Rainfall: Open-Meteo Archive (ERA5). Roof area: OpenStreetMap Overpass.",
    "Results are estimates for planning. Confirm with a plumber before purchase.",
  ]
    .map((line) => `<li>${line}</li>`)
    .join("");
}

function fillFacts(id, rows) {
  $(id).innerHTML = rows
    .map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`)
    .join("");
}

/* ---------- charts ---------- */

function svgEl(width, height) {
  return `<svg viewBox="0 0 ${width} ${height}" role="img" preserveAspectRatio="xMidYMid meet">`;
}

function renderSweep(sweep, target, recommended, chosen) {
  const width = 660;
  const height = 230;
  const pad = { l: 44, r: 14, t: 14, b: 42 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const maxY = 1.0;

  const barW = innerW / sweep.length;
  const y = (value) => pad.t + innerH - (value / maxY) * innerH;

  let marks = "";
  for (let pct = 0; pct <= 100; pct += 25) {
    const yy = y(pct / 100);
    marks += `<line x1="${pad.l}" y1="${yy}" x2="${width - pad.r}" y2="${yy}" stroke="#e4edf1" stroke-width="1"/>`;
    marks += `<text x="${pad.l - 8}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#5c7480">${pct}%</text>`;
  }

  let bars = "";
  sweep.forEach((item, index) => {
    const x = pad.l + index * barW + barW * 0.18;
    const w = barW * 0.64;
    const top = y(item.coverage);
    const h = Math.max(1, pad.t + innerH - top);
    let fill = "#cfe3ea";
    if (item.capacity_litres === recommended) fill = "#0f766e";
    else if (item.capacity_litres === chosen) fill = "#0369a1";
    bars += `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${fill}"/>`;
    if (index % 2 === 0) {
      bars += `<text x="${(x + w / 2).toFixed(1)}" y="${height - pad.b + 15}" text-anchor="middle" font-size="9.5" fill="#5c7480">${Math.round(item.capacity_litres / 1000)}k</text>`;
    }
  });

  const ty = y(target);
  const targetLine = `<line x1="${pad.l}" y1="${ty}" x2="${width - pad.r}" y2="${ty}" stroke="#b45309" stroke-width="1.5" stroke-dasharray="5 4"/>`;
  const targetText = `<text x="${width - pad.r}" y="${ty - 5}" text-anchor="end" font-size="10" fill="#b45309">target ${Math.round(target * 100)}%</text>`;
  const axisLabel = `<text x="${pad.l + innerW / 2}" y="${height - 6}" text-anchor="middle" font-size="10" fill="#5c7480">tank size (thousands of litres)</text>`;

  $("sweep-chart").innerHTML =
    svgEl(width, height) + marks + bars + targetLine + targetText + axisLabel + "</svg>";
}

function renderMonthly(monthly) {
  const width = 660;
  const height = 220;
  const pad = { l: 40, r: 42, t: 14, b: 34 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;

  if (!monthly || !monthly.length) {
    $("monthly-chart").innerHTML = "<p class='hint'>No monthly series.</p>";
    return;
  }

  const maxRain = Math.max(1, ...monthly.map((row) => row.rainfall_mm));
  const slot = innerW / monthly.length;
  const barW = slot * 0.55;

  let marks = "";
  for (let pct = 0; pct <= 100; pct += 50) {
    const yy = pad.t + innerH - (pct / 100) * innerH;
    marks += `<line x1="${pad.l}" y1="${yy}" x2="${width - pad.r}" y2="${yy}" stroke="#e4edf1" stroke-width="1"/>`;
    marks += `<text x="${width - pad.r + 6}" y="${yy + 4}" font-size="10" fill="#5c7480">${pct}%</text>`;
  }

  let bars = "";
  let points = [];
  monthly.forEach((row, index) => {
    const cx = pad.l + index * slot + slot / 2;
    const bh = (row.rainfall_mm / maxRain) * innerH * 0.85;
    bars += `<rect x="${(cx - barW / 2).toFixed(1)}" y="${(pad.t + innerH - bh).toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="#7fb8d8"/>`;
    const ly = pad.t + innerH - (row.level_pct_avg / 100) * innerH;
    points.push([cx, ly]);
  });

  const line = points.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" ");

  let labels = "";
  monthly.forEach((row, index) => {
    if (index % 6 !== 0) return;
    const cx = pad.l + index * slot + slot / 2;
    const [year, month] = row.month.split("-");
    labels += `<text x="${cx.toFixed(1)}" y="${height - 12}" text-anchor="middle" font-size="9.5" fill="#5c7480">${month}/${year.slice(2)}</text>`;
  });

  $("monthly-chart").innerHTML =
    svgEl(width, height) +
    marks +
    bars +
    `<polyline points="${line}" fill="none" stroke="#0f766e" stroke-width="2" stroke-linejoin="round"/>` +
    labels +
    `<text x="${pad.l - 6}" y="${pad.t + 4}" text-anchor="end" font-size="9.5" fill="#5c7480">${Math.round(maxRain)}mm</text>` +
    "</svg>";
}

/* ---------- events ---------- */

$("search-btn").addEventListener("click", search);
$("address").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    search();
  }
});
$("roof-btn").addEventListener("click", lookupRoof);
$("plan-btn").addEventListener("click", () => plan(false));
$("demo-btn").addEventListener("click", () => plan(true));
$("tank").addEventListener("input", (event) => {
  $("tank-out").textContent = litres(Number(event.target.value));
});

/* ---------- shareable plan links ---------- */

function applyQuery() {
  const params = new URLSearchParams(window.location.search);
  const number = (key, fallback) => {
    const value = params.get(key);
    return value === null || value === "" || Number.isNaN(Number(value))
      ? fallback
      : Number(value);
  };

  const lat = number("lat", state.lat);
  const lon = number("lon", state.lon);
  const label = params.get("place") || "Pinned location";
  setLocation(lat, lon, label);

  if (params.has("roof")) $("roof").value = number("roof", 200);
  if (params.has("occupants")) $("occupants").value = number("occupants", 4);
  if (params.has("garden")) $("garden").value = number("garden", 100);
  if (params.has("tank")) {
    $("tank").value = number("tank", 5000);
    $("tank-out").textContent = litres(number("tank", 5000));
  }
  if (params.has("target")) $("target").value = number("target", 0.9).toFixed(2);

  if (params.get("autoplay") === "1") {
    window.setTimeout(() => plan(params.get("offline") === "1"), 400);
  }
}

initMap();
$("tank-out").textContent = litres(Number($("tank").value));
applyQuery();