"""
test_feature2.py — Comprehensive Feature 2 test suite

Tests:
  T1  Data completeness  — all parcels have required power-score fields
  T2  Field ranges       — scores 0–100, distances positive, voltages valid
  T3  Score monotonicity — score_100 <= score_50 <= score_20 (bigger DC = harder)
  T4  Private wire bonus — bonus matches nearest_renewable_km bands
  T5  Distance penalty   — score drops as distance to sub grows (in aggregate)
  T6  Substation cross-check — every nearest_sub_name exists in uk_substations.json
  T7  Renewable centroids — renewable site self-proximity = 0 km
  T8  Spot-check: Drax   — should find a high-voltage nearby sub, high headroom
  T9  Spot-check: London E industrial — should have high queue pressure
  T10 Score interpolation — JS getPowerScore() logic reproduced in Python
  T11 Timeline bands      — queue % → timeline label correctness
  T12 Substation scores_real — all 134 subs have valid 20/50/100 score objects
  T13 Distribution sanity — at least 500 parcels with score_50 >= 70
  T14 No duplicate OSM IDs
  T15 Geometry validity  — all polygons have ≥3 coordinate pairs
"""

import json, math, sys

PARCELS  = "data/uk_industrial_parcels.geojson"
SUBS     = "data/uk_substations.json"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
INFO = "\033[94m·\033[0m"

results = []

def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    print(f"  {status} {name}" + (f"  — {detail}" if detail else ""))
    results.append((name, passed, detail))
    return passed

def warn(name, detail=""):
    print(f"  {WARN} {name}" + (f"  — {detail}" if detail else ""))
    results.append((name, None, detail))

def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")

# ── Helpers matching JS logic ──────────────────────────────────────
def lerp(a, b, t): return a + (b - a) * t

def get_power_score(props, mw):
    s20  = props.get("power_score_20",  0) or 0
    s50  = props.get("power_score_50",  0) or 0
    s100 = props.get("power_score_100", 0) or 0
    if mw <= 20:  return s20
    if mw >= 100: return s100
    if mw <= 50:  return lerp(s20, s50, (mw - 20) / 30)
    return lerp(s50, s100, (mw - 50) / 50)

def get_timeline(pct):
    if pct is None:  return ("Unknown",     "—")
    if pct <= 50:    return ("Short wait",   "~2–3 years")
    if pct <= 150:   return ("Moderate wait","~3–5 years")
    if pct <= 300:   return ("Long wait",    "~5–8 years")
    return              ("Very long wait","~8–12+ years")

def private_wire_bonus_expected(km):
    if km is None or km >= 9999: return 0
    if km <= 5:  return 10
    if km <= 15: return 6
    if km <= 30: return 3
    return 0

# ── Load data ──────────────────────────────────────────────────────
print("\nDC Site Finder — Feature 2 Test Suite")
print("=" * 50)
print(f"\nLoading data…")
with open(PARCELS) as f:
    geojson = json.load(f)
features = geojson["features"]
print(f"  {len(features):,} parcels loaded")

with open(SUBS) as f:
    raw = json.load(f)
subs = raw if isinstance(raw, list) else raw.get("substations", raw.get("features", raw))
sub_names = {s["name"] for s in subs}
print(f"  {len(subs)} substations loaded")

REQUIRED_FIELDS = [
    "nearest_sub_name", "nearest_sub_dist_km", "nearest_sub_voltage_kv",
    "nearest_sub_headroom_mva", "sub_queue_pressure_pct",
    "power_score_20", "power_score_50", "power_score_100",
    "private_wire_bonus",
]

# ── T1: Data completeness ──────────────────────────────────────────
section("T1  Data completeness")
missing_by_field = {f: 0 for f in REQUIRED_FIELDS}
for feat in features:
    p = feat["properties"]
    for field in REQUIRED_FIELDS:
        if p.get(field) is None:
            missing_by_field[field] += 1

all_complete = True
for field, n_missing in missing_by_field.items():
    ok = n_missing == 0
    if not ok: all_complete = False
    check(f"{field} present in all parcels",
          ok, f"{n_missing:,} missing" if not ok else f"all {len(features):,} present")

# ── T2: Field ranges ───────────────────────────────────────────────
section("T2  Field ranges")
out_of_range = {
    "score_20_oob":  0, "score_50_oob":  0, "score_100_oob": 0,
    "dist_negative": 0, "queue_negative": 0, "bonus_oob":     0,
    "voltage_odd":   0,
}
voltage_values = set()
for feat in features:
    p = feat["properties"]
    for key, field in [("score_20_oob","power_score_20"),
                       ("score_50_oob","power_score_50"),
                       ("score_100_oob","power_score_100")]:
        v = p.get(field)
        if v is not None and not (0 <= v <= 100):
            out_of_range[key] += 1
    d = p.get("nearest_sub_dist_km")
    if d is not None and d < 0: out_of_range["dist_negative"] += 1
    q = p.get("sub_queue_pressure_pct")
    if q is not None and q < 0: out_of_range["queue_negative"] += 1
    b = p.get("private_wire_bonus")
    if b is not None and b not in (0, 3, 6, 10): out_of_range["bonus_oob"] += 1
    v = p.get("nearest_sub_voltage_kv")
    if v is not None: voltage_values.add(v)

check("power_score_20 in [0,100]",   out_of_range["score_20_oob"]  == 0, f"{out_of_range['score_20_oob']} out-of-range")
check("power_score_50 in [0,100]",   out_of_range["score_50_oob"]  == 0, f"{out_of_range['score_50_oob']} out-of-range")
check("power_score_100 in [0,100]",  out_of_range["score_100_oob"] == 0, f"{out_of_range['score_100_oob']} out-of-range")
check("nearest_sub_dist_km >= 0",    out_of_range["dist_negative"]  == 0, f"{out_of_range['dist_negative']} negative")
check("sub_queue_pressure_pct >= 0", out_of_range["queue_negative"] == 0, f"{out_of_range['queue_negative']} negative")
check("private_wire_bonus in {0,3,6,10}", out_of_range["bonus_oob"] == 0, f"{out_of_range['bonus_oob']} invalid values")
check("voltage_kv only expected values (132/275/400)",
      voltage_values.issubset({132, 275, 400}),
      f"found: {sorted(voltage_values)}")

# ── T3: Score monotonicity ─────────────────────────────────────────
section("T3  Score monotonicity (larger DC = equal or lower score)")
violations = 0
for feat in features:
    p = feat["properties"]
    s20  = p.get("power_score_20",  0) or 0
    s50  = p.get("power_score_50",  0) or 0
    s100 = p.get("power_score_100", 0) or 0
    # Allow tiny floating-point tolerances
    if s50 > s20 + 0.1 or s100 > s50 + 0.1:
        violations += 1

check("score_20 >= score_50 >= score_100 for all parcels",
      violations == 0, f"{violations} monotonicity violations")

# ── T4: Private wire bonus correctness ────────────────────────────
section("T4  Private wire bonus vs nearest_renewable_km")
# Note: nearest_renewable_km is rounded to 1 dp at save time.
# Boundary precision: a parcel whose actual km was 5.0003 stores km=5.0 but
# received bonus=6 (correct for actual distance). We accept ±0.1km tolerance
# on the band boundaries (5/15/30) rather than flagging these as errors.
BOUNDARY_TOLERANCE = 0.11  # km
BOUNDARIES = {5.0, 15.0, 30.0}

bonus_wrong = 0
for feat in features:
    p = feat["properties"]
    km     = p.get("nearest_renewable_km")
    bonus  = p.get("private_wire_bonus", 0) or 0
    expected = private_wire_bonus_expected(km)
    if bonus != expected:
        # Accept if km is within tolerance of a band boundary
        at_boundary = km is not None and any(abs(km - b) <= BOUNDARY_TOLERANCE for b in BOUNDARIES)
        if not at_boundary:
            bonus_wrong += 1

check("private_wire_bonus consistent with nearest_renewable_km (ignoring ±0.1km boundaries)",
      bonus_wrong == 0, f"{bonus_wrong} mismatches")

# ── T5: Distance penalty ───────────────────────────────────────────
section("T5  Distance penalty (parcels <2km get avg score > parcels >20km)")
close_scores = [f["properties"]["power_score_50"] for f in features
                if (f["properties"].get("nearest_sub_dist_km") or 999) < 2]
far_scores   = [f["properties"]["power_score_50"] for f in features
                if (f["properties"].get("nearest_sub_dist_km") or 0) > 20]

if close_scores and far_scores:
    avg_close = sum(close_scores) / len(close_scores)
    avg_far   = sum(far_scores)   / len(far_scores)
    check(f"avg score <2km ({avg_close:.1f}) > avg score >20km ({avg_far:.1f})",
          avg_close > avg_far,
          f"n_close={len(close_scores):,}  n_far={len(far_scores):,}")
else:
    warn("Not enough data for distance penalty test")

# ── T6: Substation name cross-check ───────────────────────────────
section("T6  Substation name cross-check")
unknown_sub_names = set()
for feat in features:
    name = feat["properties"].get("nearest_sub_name")
    if name and name not in sub_names:
        unknown_sub_names.add(name)

check("all nearest_sub_name values exist in uk_substations.json",
      len(unknown_sub_names) == 0,
      f"{len(unknown_sub_names)} unknown: {list(unknown_sub_names)[:3]}" if unknown_sub_names else "")

# ── T7: Renewable self-proximity ──────────────────────────────────
section("T7  Renewable sites: self-proximity nearly zero")
renewable_keywords = {"wind", "solar", "tidal", "wave", "offshore"}
ren_features = [f for f in features
                if f["properties"].get("site_type") == "power"
                and any(kw in (f["properties"].get("name") or "").lower()
                        for kw in renewable_keywords)]
non_zero_self = sum(1 for f in ren_features
                    if (f["properties"].get("nearest_renewable_km") is None
                        or f["properties"]["nearest_renewable_km"] > 0.1))
print(f"  {INFO} {len(ren_features)} renewable power sites found")
check("renewable sites have nearest_renewable_km ≈ 0",
      non_zero_self < len(ren_features) * 0.05,   # allow <5% edge cases
      f"{non_zero_self} of {len(ren_features)} have km > 0.1")

# ── T8: Spot-check Drax ───────────────────────────────────────────
section("T8  Spot-check: Drax Power Station")
drax_features = [f for f in features
                 if "drax" in (f["properties"].get("name") or "").lower()]
print(f"  {INFO} {len(drax_features)} Drax feature(s) found")
if drax_features:
    best = max(drax_features, key=lambda f: f["properties"].get("power_score_50") or 0)
    p = best["properties"]
    print(f"  {INFO} Best match: {p['name']!r} ({p['region']})")
    print(f"  {INFO} Nearest sub: {p.get('nearest_sub_name')} ({p.get('nearest_sub_voltage_kv')}kV, "
          f"{p.get('nearest_sub_dist_km')} km)")
    print(f"  {INFO} Headroom: {p.get('nearest_sub_headroom_mva')} MVA  "
          f"Queue: {p.get('sub_queue_pressure_pct')}%")
    print(f"  {INFO} Scores — 20MW: {p.get('power_score_20')}  "
          f"50MW: {p.get('power_score_50')}  100MW: {p.get('power_score_100')}")
    check("Drax: nearest sub voltage >= 132kV",    (p.get("nearest_sub_voltage_kv") or 0) >= 132)
    check("Drax: distance to sub < 30km",          (p.get("nearest_sub_dist_km") or 999) < 30)
    check("Drax: power_score_50 > 40",             (p.get("power_score_50") or 0) > 40,
          f"score={p.get('power_score_50')}")
else:
    warn("Drax not found in dataset — may be missing OSM data")

# ── T9: Spot-check: London industrial (high queue pressure) ───────
section("T9  Spot-check: London industrial parcels")
london_industrial = [f for f in features
                     if f["properties"].get("site_type") == "industrial"
                     and f["properties"].get("region") in ("London & SE", "South East")]
print(f"  {INFO} {len(london_industrial):,} London/SE industrial parcels")
if london_industrial:
    queue_pressures = [f["properties"].get("sub_queue_pressure_pct") or 0
                       for f in london_industrial]
    avg_queue = sum(queue_pressures) / len(queue_pressures)
    high_queue = sum(1 for q in queue_pressures if q > 200)
    print(f"  {INFO} Avg queue pressure: {avg_queue:.0f}%")
    print(f"  {INFO} Parcels with >200% queue: {high_queue:,} of {len(london_industrial):,}")
    check("London industrial: avg queue pressure > 100%",
          avg_queue > 100, f"avg={avg_queue:.0f}%")
    check("London industrial: >10% of parcels have >200% queue",
          high_queue > len(london_industrial) * 0.1,
          f"{high_queue}/{len(london_industrial)}")

    # Show the 3 best London industrial parcels
    best3 = sorted(london_industrial, key=lambda f: f["properties"].get("power_score_50") or 0, reverse=True)[:3]
    print(f"\n  Top 3 London/SE industrial by power score:")
    for f in best3:
        p = f["properties"]
        name = p.get("name") or f"{p.get('addr_city','')} · {p.get('region')}"
        print(f"    {name[:40]:<40}  score={p.get('power_score_50'):5.1f}  "
              f"dist={p.get('nearest_sub_dist_km'):5.1f}km  queue={p.get('sub_queue_pressure_pct'):6.1f}%")

# ── T10: Score interpolation correctness ──────────────────────────
section("T10  Score interpolation (getPowerScore logic)")
# Use a parcel with divergent 20/50/100 scores to test
divergent = [f for f in features
             if abs((f["properties"].get("power_score_20") or 0) -
                    (f["properties"].get("power_score_100") or 0)) > 10]
if divergent:
    p = divergent[0]["properties"]
    s20, s50, s100 = p["power_score_20"], p["power_score_50"], p["power_score_100"]
    print(f"  {INFO} Test parcel: 20MW={s20}, 50MW={s50}, 100MW={s100}")

    # Test boundary values
    check("mw=20 returns score_20",  abs(get_power_score(p, 20)  - s20)  < 0.01)
    check("mw=50 returns score_50",  abs(get_power_score(p, 50)  - s50)  < 0.01)
    check("mw=100 returns score_100",abs(get_power_score(p, 100) - s100) < 0.01)

    # Test midpoint interpolation
    expected_35 = lerp(s20, s50, (35 - 20) / 30)
    actual_35   = get_power_score(p, 35)
    check(f"mw=35 interpolates correctly ({expected_35:.2f})",
          abs(actual_35 - expected_35) < 0.01)

    expected_75 = lerp(s50, s100, (75 - 50) / 50)
    actual_75   = get_power_score(p, 75)
    check(f"mw=75 interpolates correctly ({expected_75:.2f})",
          abs(actual_75 - expected_75) < 0.01)

    # Monotonicity of interpolation
    prev = get_power_score(p, 1)
    mono = True
    for mw in range(2, 501):
        cur = get_power_score(p, mw)
        if cur > prev + 0.01:
            mono = False; break
        prev = cur
    check("interpolated score monotonically non-increasing across 1–500MW", mono)
else:
    warn("No parcels with divergent 20/100 scores found for interpolation test")

# ── T11: Timeline band correctness ────────────────────────────────
section("T11  Timeline band correctness")
cases = [
    (0,   "Short wait",    "~2–3 years"),
    (50,  "Short wait",    "~2–3 years"),
    (51,  "Moderate wait", "~3–5 years"),
    (150, "Moderate wait", "~3–5 years"),
    (151, "Long wait",     "~5–8 years"),
    (300, "Long wait",     "~5–8 years"),
    (301, "Very long wait","~8–12+ years"),
    (999, "Very long wait","~8–12+ years"),
]
all_ok = True
for pct, exp_label, exp_years in cases:
    label, years = get_timeline(pct)
    ok = (label == exp_label and years == exp_years)
    if not ok: all_ok = False
    check(f"queue={pct:>4}% → '{exp_label}' / '{exp_years}'", ok)

# ── T12: Substation scores_real completeness ──────────────────────
section("T12  Substation scores_real validity")
missing_scores = 0
invalid_scores = 0
for s in subs:
    sr = s.get("scores_real", {})
    if not sr:
        missing_scores += 1
        continue
    for mw in ("20", "50", "100"):
        entry = sr.get(mw, {})
        ts = entry.get("total_score")
        if ts is None or not (0 <= ts <= 100):
            invalid_scores += 1

check("all substations have scores_real", missing_scores == 0,
      f"{missing_scores} missing")
check("all scores_real total_score in [0,100]", invalid_scores == 0,
      f"{invalid_scores} invalid")

# Check score monotonicity per sub
sub_violations = 0
for s in subs:
    sr = s.get("scores_real", {})
    s20_  = sr.get("20",  {}).get("total_score", 0) or 0
    s50_  = sr.get("50",  {}).get("total_score", 0) or 0
    s100_ = sr.get("100", {}).get("total_score", 0) or 0
    if s50_ > s20_ + 0.5 or s100_ > s50_ + 0.5:
        sub_violations += 1
check("substation scores monotonic (20>=50>=100)",
      sub_violations == 0, f"{sub_violations} violations")

# ── T13: Distribution sanity ───────────────────────────────────────
section("T13  Score distribution sanity")
scores_50 = [f["properties"].get("power_score_50") or 0 for f in features]
buckets = {
    "≥90": sum(1 for s in scores_50 if s >= 90),
    "70–89": sum(1 for s in scores_50 if 70 <= s < 90),
    "50–69": sum(1 for s in scores_50 if 50 <= s < 70),
    "30–49": sum(1 for s in scores_50 if 30 <= s < 50),
    "<30":  sum(1 for s in scores_50 if s < 30),
}
print(f"\n  Score distribution (50MW basis, n={len(scores_50):,}):")
for label, n in buckets.items():
    bar = "█" * (n * 30 // len(features))
    pct = n * 100 / len(features)
    print(f"    {label:>6}  {bar:<30}  {n:>6,}  ({pct:.1f}%)")

check("at least 500 parcels with score_50 >= 70",
      buckets["70–89"] + buckets["≥90"] >= 500,
      f"found {buckets['70-89'] + buckets['≥90']:,}" if False else
      f"found {buckets['70–89'] + buckets['≥90']:,}")
check("at least 1,000 parcels with score_50 >= 50",
      sum(buckets[k] for k in ("≥90","70–89","50–69")) >= 1000)
check("no more than 80% of parcels scoring <30",
      buckets["<30"] / len(features) < 0.8,
      f"{buckets['<30']/len(features)*100:.1f}% scored <30")

# ── T14: No duplicate OSM IDs ─────────────────────────────────────
section("T14  No duplicate OSM IDs")
osm_ids = [f["properties"]["osm_id"] for f in features]
dupes = len(osm_ids) - len(set(osm_ids))
check("all OSM IDs unique", dupes == 0, f"{dupes} duplicates")

# ── T15: Geometry validity ────────────────────────────────────────
section("T15  Geometry validity")
bad_geom = 0
for feat in features:
    coords = feat.get("geometry", {}).get("coordinates", [[]])
    ring = coords[0] if coords else []
    if len(ring) < 3:
        bad_geom += 1

check("all polygons have ≥3 coordinate pairs",
      bad_geom == 0, f"{bad_geom} invalid")

# ── Summary ───────────────────────────────────────────────────────
section("Summary")
passed  = sum(1 for _, r, _ in results if r is True)
failed  = sum(1 for _, r, _ in results if r is False)
warned  = sum(1 for _, r, _ in results if r is None)
total   = passed + failed

print(f"\n  {PASS} {passed}/{total} tests passed"
      + (f"   {WARN} {warned} warnings" if warned else ""))

if failed:
    print(f"\n  {FAIL} FAILED tests:")
    for name, r, detail in results:
        if r is False:
            print(f"      • {name}" + (f": {detail}" if detail else ""))

print()
sys.exit(0 if failed == 0 else 1)
