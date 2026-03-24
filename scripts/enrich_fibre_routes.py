"""
enrich_fibre_routes.py

Adds fibre_route_km (distance to nearest ITU backbone fibre route) to every
parcel in uk_industrial_parcels.geojson.

Source: ITU BBmaps — 1,187 operational UK backbone fibre routes (LineStrings).

Run AFTER fetch_itu_fibre.py and BEFORE enrich_composite_scores.py.

New properties added:
  fibre_route_km   : km to nearest backbone fibre route segment
  nearest_route_id : uid of that route

Usage:
    python3 scripts/enrich_fibre_routes.py
Runs in ~30 seconds for 40k parcels.
"""

import json, math, time, os

PARCELS_FILE = "data/uk_industrial_parcels.geojson"
ROUTES_FILE  = "data/uk_fibre_routes.geojson"
OUTPUT_FILE  = "data/uk_industrial_parcels.geojson"


# ── Geometry helpers ───────────────────────────────────────────────

def centroid(coords):
    x = sum(c[0] for c in coords) / len(coords)
    y = sum(c[1] for c in coords) / len(coords)
    return y, x  # lat, lng

def point_to_segment_km(plat, plng, lat1, lng1, lat2, lng2):
    """
    Approximate great-circle distance from (plat, plng) to the nearest point
    on the segment (lat1,lng1)–(lat2,lng2), in km.

    Uses a locally-flat projection (equidistant at the query latitude) which
    is accurate to <1% for segments shorter than ~300 km.
    """
    # Convert to approximate km-space at plat latitude
    clat = math.cos(math.radians(plat))
    KM_PER_LAT = 111.32
    KM_PER_LNG = 111.32 * clat

    px = plng  * KM_PER_LNG
    py = plat  * KM_PER_LAT
    ax = lng1  * KM_PER_LNG
    ay = lat1  * KM_PER_LAT
    bx = lng2  * KM_PER_LNG
    by = lat2  * KM_PER_LAT

    dx, dy = bx - ax, by - ay
    lenSq = dx * dx + dy * dy
    if lenSq == 0.0:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)

    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / lenSq))
    nearX = ax + t * dx
    nearY = ay + t * dy
    return math.sqrt((px - nearX) ** 2 + (py - nearY) ** 2)


def nearest_route(plat, plng, routes):
    """Return (min_km, route_uid) for the closest backbone fibre route."""
    best_km  = float("inf")
    best_uid = None

    for feat in routes:
        uid   = feat["properties"]["uid"]
        coords = feat["geometry"]["coordinates"]
        # All routes are 2-vertex segments; iterate over segments
        for i in range(len(coords) - 1):
            lng1, lat1 = coords[i]
            lng2, lat2 = coords[i + 1]
            d = point_to_segment_km(plat, plng, lat1, lng1, lat2, lng2)
            if d < best_km:
                best_km  = d
                best_uid = uid

    return best_km, best_uid


# ── Main ───────────────────────────────────────────────────────────

def main():
    print("DC Site Finder — ITU Fibre Route Enrichment")
    print("=" * 50)
    t0 = time.time()

    with open(PARCELS_FILE) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"Parcels loaded: {len(features):,}")

    with open(ROUTES_FILE) as f:
        routes = json.load(f)["features"]
    print(f"Fibre routes loaded: {len(routes):,}")
    print()

    t_report = time.time()

    for i, feat in enumerate(features):
        coords = feat["geometry"]["coordinates"][0]
        plat, plng = centroid(coords)
        p = feat["properties"]

        km, uid = nearest_route(plat, plng, routes)

        p["fibre_route_km"]   = round(km, 2)
        p["nearest_route_id"] = uid

        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t_report
            rate    = 5000 / elapsed
            remain  = (len(features) - i - 1) / rate
            print(f"  {i+1:>6,} / {len(features):,}  ({rate:.0f}/s, ~{remain:.0f}s remaining)")
            t_report = time.time()

    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)

    elapsed_total = time.time() - t0
    size_mb = os.path.getsize(OUTPUT_FILE) / 1e6
    print(f"\nDone in {elapsed_total:.0f}s — {OUTPUT_FILE} ({size_mb:.1f} MB)")

    # Summary stats
    dists = [f["properties"]["fibre_route_km"] for f in features]
    dists.sort()
    n = len(dists)
    print(f"\nFibre route distance summary:")
    print(f"  Median:   {dists[n//2]:.1f} km")
    print(f"  75th pct: {dists[3*n//4]:.1f} km")
    print(f"  95th pct: {dists[19*n//20]:.1f} km")
    print(f"  Max:      {dists[-1]:.1f} km")

    buckets = {"≤5 km": 0, "5–20 km": 0, "20–50 km": 0, "50–100 km": 0, ">100 km": 0}
    for d in dists:
        if d <= 5:    buckets["≤5 km"]    += 1
        elif d <= 20: buckets["5–20 km"]  += 1
        elif d <= 50: buckets["20–50 km"] += 1
        elif d <= 100:buckets["50–100 km"]+= 1
        else:         buckets[">100 km"]  += 1
    print("\nDistance distribution:")
    for label, cnt in buckets.items():
        bar = "█" * (cnt * 30 // n)
        print(f"  {label:>10}  {bar:<30} {cnt:>6,}  ({100*cnt/n:.0f}%)")

    print("\nRun  python3 scripts/enrich_composite_scores.py  to recompute composite scores.")


if __name__ == "__main__":
    main()
