"""
enrich_power_scores.py

Enriches uk_industrial_parcels.geojson with power scoring data:
  - nearest_sub_name        : name of nearest substation
  - nearest_sub_dist_km     : distance in km
  - nearest_sub_voltage_kv  : voltage (400/275/132)
  - nearest_sub_headroom_mva: available headroom
  - sub_queue_pressure_pct  : real TEC queue pressure
  - power_score_20          : power score for 20MW DC (0-100)
  - power_score_50          : power score for 50MW DC (0-100)
  - power_score_100         : power score for 100MW DC (0-100)
  - private_wire_bonus      : bonus if near renewable generation (0/5/10)
  - nearest_renewable_km    : km to nearest wind/solar power plant

Usage:
    python scripts/enrich_power_scores.py
Takes ~2-3 minutes for 40k parcels.
"""

import json
import math
import time
import os

PARCELS_FILE  = "data/uk_industrial_parcels.geojson"
SUBS_FILE     = "data/uk_substations.json"
OUTPUT_FILE   = "data/uk_industrial_parcels.geojson"

def haversine(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))

def centroid(coords):
    x = sum(c[0] for c in coords) / len(coords)
    y = sum(c[1] for c in coords) / len(coords)
    return y, x  # lat, lng

def distance_factor(km):
    """Multiplier applied to base sub score based on distance to substation."""
    if km <= 2:   return 1.00
    if km <= 5:   return 0.95
    if km <= 10:  return 0.85
    if km <= 20:  return 0.70
    if km <= 35:  return 0.50
    return 0.30

def private_wire_bonus(km):
    """Bonus points for proximity to renewable generation (private wire potential)."""
    if km <= 5:  return 10
    if km <= 15: return 6
    if km <= 30: return 3
    return 0

def main():
    print("DC Site Finder — Power Score Enrichment")
    print("=" * 45)
    t0 = time.time()

    # ── Load substations ───────────────────────────────────────────
    with open(SUBS_FILE) as f:
        raw = json.load(f)
    subs = raw if isinstance(raw, list) else raw.get("substations", raw.get("features", raw))

    # Only score against 132kV+ substations (relevant for large DC)
    hv_subs = [s for s in subs if s.get("voltage_kv", 0) >= 132]
    print(f"Substations loaded: {len(subs)} total, {len(hv_subs)} at 132kV+")

    # Pre-extract sub coords for speed
    sub_coords = [(s["lat"], s["lng"]) for s in hv_subs]

    # ── Load parcels ───────────────────────────────────────────────
    with open(PARCELS_FILE) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"Parcels loaded: {len(features):,}")

    # ── Extract renewable plant centroids for private wire calc ────
    renewable_keywords = {"wind", "solar", "tidal", "wave", "offshore"}
    renewable_centroids = []
    for feat in features:
        if feat["properties"].get("site_type") != "power":
            continue
        name = feat["properties"].get("name", "").lower()
        if any(kw in name for kw in renewable_keywords):
            coords = feat["geometry"]["coordinates"][0]
            lat, lng = centroid(coords)
            renewable_centroids.append((lat, lng))
    print(f"Renewable power plant centroids: {len(renewable_centroids)}")
    print()

    # ── Enrich each parcel ─────────────────────────────────────────
    t_report = time.time()
    for i, feat in enumerate(features):
        coords = feat["geometry"]["coordinates"][0]
        plat, plng = centroid(coords)

        # Find nearest 132kV+ substation
        best_dist = float("inf")
        best_sub  = None
        for j, (slat, slng) in enumerate(sub_coords):
            d = haversine(plat, plng, slat, slng)
            if d < best_dist:
                best_dist = d
                best_sub  = hv_subs[j]

        # Compute power scores for 20/50/100MW with distance penalty
        df = distance_factor(best_dist)
        scores = {}
        for mw in ("20", "50", "100"):
            real = best_sub.get("scores_real", {}).get(mw, {})
            base = real.get("total_score", 0)
            scores[mw] = round(base * df, 1)

        # Private wire bonus — nearest renewable plant
        pw_bonus = 0
        nearest_ren_km = 9999.0
        if renewable_centroids:
            nearest_ren_km = min(haversine(plat, plng, rlat, rlng)
                                 for rlat, rlng in renewable_centroids)
            pw_bonus = private_wire_bonus(nearest_ren_km)

        # Write enriched properties
        p = feat["properties"]
        p["nearest_sub_name"]        = best_sub["name"]
        p["nearest_sub_dist_km"]     = round(best_dist, 2)
        p["nearest_sub_voltage_kv"]  = best_sub.get("voltage_kv", 0)
        p["nearest_sub_headroom_mva"]= best_sub.get("estimated_headroom_mva", 0)
        p["sub_queue_pressure_pct"]  = round(best_sub.get("real_queue_pressure_pct", 0), 1)
        p["power_score_20"]          = min(100, scores["20"]  + pw_bonus)
        p["power_score_50"]          = min(100, scores["50"]  + pw_bonus)
        p["power_score_100"]         = min(100, scores["100"] + pw_bonus)
        p["private_wire_bonus"]      = pw_bonus
        p["nearest_renewable_km"]    = round(nearest_ren_km, 1) if nearest_ren_km < 9999 else None

        # Progress report every 5k
        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t_report
            rate = 5000 / elapsed
            remaining = (len(features) - i - 1) / rate
            print(f"  {i+1:>6,} / {len(features):,}  ({rate:.0f}/s, ~{remaining:.0f}s remaining)")
            t_report = time.time()

    # ── Save atomically ───────────────────────────────────────────
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)

    elapsed_total = time.time() - t0
    size_mb = os.path.getsize(OUTPUT_FILE) / 1e6
    print()
    print(f"Done in {elapsed_total:.0f}s — {OUTPUT_FILE} ({size_mb:.1f} MB)")

    # ── Score distribution summary ─────────────────────────────────
    scores_50 = [f["properties"]["power_score_50"] for f in features]
    buckets = {"90-100": 0, "70-89": 0, "50-69": 0, "30-49": 0, "<30": 0}
    for s in scores_50:
        if s >= 90: buckets["90-100"] += 1
        elif s >= 70: buckets["70-89"] += 1
        elif s >= 50: buckets["50-69"] += 1
        elif s >= 30: buckets["30-49"] += 1
        else: buckets["<30"] += 1
    print()
    print("Power score distribution (50MW basis):")
    for label, n in buckets.items():
        bar = "█" * (n * 40 // len(features))
        print(f"  {label:>8}  {bar:<40} {n:>6,}")

if __name__ == "__main__":
    main()
