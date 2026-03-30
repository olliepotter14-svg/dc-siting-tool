"""
enrich_power_scores.py

Enriches uk_industrial_parcels.geojson with power scoring data.

Key change (v2): Scores against the BEST substation within 25km, not just
the nearest. A site 9km from an uncongested 400kV GSP scores better than
one 3km from a saturated 132kV node. DC developers evaluate all connection
options within reach, not just the closest.

Properties written per parcel:
  nearest_sub_name        — name of geographically nearest substation
  nearest_sub_dist_km     — distance to nearest sub (km)
  nearest_sub_voltage_kv  — voltage at nearest sub
  nearest_sub_headroom_mva— headroom at nearest sub (display only)
  sub_queue_pressure_pct  — real TEC queue pressure at nearest sub
  best_sub_name           — name of best-scoring sub within 25km
  best_sub_dist_km        — distance to best sub (km)
  best_sub_voltage_kv     — voltage at best sub
  best_sub_queue_pct      — queue pressure at best sub
  power_score_20/50/100   — power score for each DC size (0–100)
  nearest_renewable_km    — km to nearest wind/solar plant (detail panel)
  private_wire_km         — same as nearest_renewable_km (renamed for clarity)

Usage:
    python3 scripts/enrich_power_scores.py
Takes ~3-4 minutes for 63k parcels.
"""

import json
import math
import time
import os

PARCELS_FILE = "data/uk_industrial_parcels.geojson"
SUBS_FILE    = "data/uk_substations.json"
OUTPUT_FILE  = "data/uk_industrial_parcels.geojson"

BEST_SUB_RADIUS_KM = 25.0   # search radius for best-sub-within-25km


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
    return y, x   # lat, lng


def distance_factor(km):
    """Score multiplier based on distance to substation."""
    if km <= 2:   return 1.00
    if km <= 5:   return 0.95
    if km <= 10:  return 0.85
    if km <= 20:  return 0.70
    if km <= 35:  return 0.50
    return 0.30


def main():
    print("DC Site Finder — Power Score Enrichment (v2: best sub within 25km)")
    print("=" * 65)
    t0 = time.time()

    # ── Load substations ──────────────────────────────────────────────
    with open(SUBS_FILE) as f:
        raw = json.load(f)
    subs = raw if isinstance(raw, list) else raw.get("substations", raw.get("features", raw))

    # Only score against 132kV+ substations (relevant for large DC)
    hv_subs = [s for s in subs if s.get("voltage_kv", 0) >= 132]
    print(f"Substations loaded: {len(subs)} total, {len(hv_subs)} at 132kV+")

    # Pre-extract sub coords for speed
    sub_coords = [(s["lat"], s["lng"]) for s in hv_subs]

    # ── Load parcels ──────────────────────────────────────────────────
    with open(PARCELS_FILE) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"Parcels loaded: {len(features):,}")

    # ── Extract renewable plant centroids for detail panel flag ───────
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
    print(f"Renewable plant centroids: {len(renewable_centroids)}")
    print()

    # ── Enrich each parcel ────────────────────────────────────────────
    t_report = time.time()
    for i, feat in enumerate(features):
        coords = feat["geometry"]["coordinates"][0]
        plat, plng = centroid(coords)

        # ── Find nearest sub (for display/backward compat) ───────────
        nearest_dist = float("inf")
        nearest_sub  = None
        for j, (slat, slng) in enumerate(sub_coords):
            d = haversine(plat, plng, slat, slng)
            if d < nearest_dist:
                nearest_dist = d
                nearest_sub  = hv_subs[j]

        # ── Find best sub within 25km (new scoring logic) ───────────
        # Best = highest (total_score_at_required_mw × distance_factor)
        # Use 50MW as the reference MW for choosing "best" sub (typical
        # first-phase DC size). The per-MW scores are then taken from
        # that same best sub.
        best_sub      = None
        best_score_50 = -1.0
        best_dist_km  = float("inf")

        for j, (slat, slng) in enumerate(sub_coords):
            d = haversine(plat, plng, slat, slng)
            if d > BEST_SUB_RADIUS_KM:
                continue
            s = hv_subs[j]
            base_50 = s.get("scores_real", {}).get("50", {}).get("total_score", 0)
            candidate_score = base_50 * distance_factor(d)
            if candidate_score > best_score_50:
                best_score_50 = candidate_score
                best_sub      = s
                best_dist_km  = d

        # Fall back to nearest if nothing within 25km
        if best_sub is None:
            best_sub     = nearest_sub
            best_dist_km = nearest_dist

        # ── Power scores using best sub ───────────────────────────────
        df = distance_factor(best_dist_km)
        scores = {}
        for mw_str in ("20", "50", "100"):
            base = best_sub.get("scores_real", {}).get(mw_str, {}).get("total_score", 0)
            scores[mw_str] = round(base * df, 1)

        # ── Private wire / renewable proximity (detail panel only) ───
        nearest_ren_km = 9999.0
        if renewable_centroids:
            nearest_ren_km = min(haversine(plat, plng, rlat, rlng)
                                 for rlat, rlng in renewable_centroids)

        # ── Write enriched properties ─────────────────────────────────
        p = feat["properties"]
        # Nearest sub (display / backward compat)
        p["nearest_sub_name"]         = nearest_sub["name"]
        p["nearest_sub_dist_km"]      = round(nearest_dist, 2)
        p["nearest_sub_voltage_kv"]   = nearest_sub.get("voltage_kv", 0)
        p["nearest_sub_headroom_mva"] = nearest_sub.get("estimated_headroom_mva", 0)
        p["sub_queue_pressure_pct"]   = round(nearest_sub.get("real_queue_pressure_pct", 0), 1)

        # Best sub (scoring basis)
        p["best_sub_name"]       = best_sub["name"]
        p["best_sub_dist_km"]    = round(best_dist_km, 2)
        p["best_sub_voltage_kv"] = best_sub.get("voltage_kv", 0)
        p["best_sub_queue_pct"]  = round(best_sub.get("real_queue_pressure_pct", 0), 1)
        p["best_sub_headroom_mva"] = best_sub.get("estimated_headroom_mva", 0)

        # Power scores (from best sub, no private wire bonus in score)
        p["power_score_20"]  = min(100, scores["20"])
        p["power_score_50"]  = min(100, scores["50"])
        p["power_score_100"] = min(100, scores["100"])

        # Private wire flag for detail panel (not used in scoring)
        p["nearest_renewable_km"] = (round(nearest_ren_km, 1)
                                     if nearest_ren_km < 9999 else None)
        p["private_wire_km"]      = p["nearest_renewable_km"]
        p.pop("private_wire_bonus", None)   # remove old field

        # Progress report every 5k
        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t_report
            rate    = 5000 / elapsed
            rem     = (len(features) - i - 1) / rate
            print(f"  {i+1:>6,} / {len(features):,}  ({rate:.0f}/s, ~{rem:.0f}s remaining)")
            t_report = time.time()

    # ── Save atomically ───────────────────────────────────────────────
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)

    elapsed_total = time.time() - t0
    size_mb = os.path.getsize(OUTPUT_FILE) / 1e6
    print()
    print(f"Done in {elapsed_total:.0f}s — {OUTPUT_FILE} ({size_mb:.1f} MB)")

    # ── Score distribution summary ────────────────────────────────────
    scores_50 = [f["properties"]["power_score_50"] for f in features]
    buckets = {"90-100": 0, "70-89": 0, "50-69": 0, "30-49": 0, "<30": 0}
    for s in scores_50:
        if   s >= 90: buckets["90-100"] += 1
        elif s >= 70: buckets["70-89"]  += 1
        elif s >= 50: buckets["50-69"]  += 1
        elif s >= 30: buckets["30-49"]  += 1
        else:         buckets["<30"]    += 1
    print()
    print("Power score distribution (50MW basis):")
    for label, n in buckets.items():
        bar = "█" * (n * 40 // len(features))
        print(f"  {label:>8}  {bar:<40} {n:>6,}")

    print("\nNext step: python3 scripts/enrich_composite_scores.py")


if __name__ == "__main__":
    main()
