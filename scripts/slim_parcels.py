"""
slim_parcels.py

Reduces uk_industrial_parcels.geojson file size by:
1. Stripping properties not used by map.js
2. Reducing coordinate precision to 5 decimal places (~1m accuracy)
3. Simplifying polygon geometry (Visvalingam-Whyatt — removes imperceptible vertices)
4. Writing compact JSON (no extra whitespace)

Typical reduction: 136MB → ~55-65MB (plus Netlify gzip brings wire size to ~18-22MB).

Usage:
    python3 scripts/slim_parcels.py

    # To restore original:
    cp data/uk_industrial_parcels.bak.geojson data/uk_industrial_parcels.geojson
"""

import json, math, sys
from pathlib import Path

IN_FILE   = Path("data/uk_industrial_parcels.geojson")
OUT_FILE  = Path("data/uk_industrial_parcels.geojson")
BACKUP    = Path("data/uk_industrial_parcels.bak.geojson")
PRECISION = 5   # coordinate decimal places (~1m accuracy at UK latitudes)

# Visvalingam area threshold — in degrees² (not metres).
# 0.000000001 deg² ≈ removes vertices creating triangles < ~10m² visible area.
# Increase to 0.000000005 to remove more aggressively (still invisible at zoom < 16).
SIMPLIFY_EPSILON = 1e-7  # removes triangles < ~780m² area — invisible at zoom < 14

# Properties actually read by map.js — keep only these
KEEP_PROPS = {
    "osm_id", "name", "site_type", "osm_tag",
    "area_ha", "area_acres", "region", "operator", "addr_city",
    # power
    "nearest_sub_name", "nearest_sub_dist_km", "nearest_sub_voltage_kv",
    "nearest_sub_headroom_mva", "sub_queue_pressure_pct",
    "power_score_20", "power_score_50", "power_score_100",
    "nearest_renewable_km", "private_wire_km",
    # composite
    "composite_score_20", "composite_score_50", "composite_score_100",
    # fibre
    "fibre_route_km", "dist_to_ix_km", "best_fibre_km", "fibre_score",
    # permissioning
    "planning_score", "permissioning_score", "buildability_score",
    "green_belt", "grey_belt", "growth_zone",
    # flood / exclusions
    "flood_zone", "hard_excluded", "protected_designations",
}


# ── Visvalingam–Whyatt line simplification ────────────────────────
def _triangle_area(p1, p2, p3):
    """Signed triangle area (half cross-product). Fast scalar version."""
    return abs(
        (p2[0] - p1[0]) * (p3[1] - p1[1]) -
        (p3[0] - p1[0]) * (p2[1] - p1[1])
    ) / 2.0


def simplify_ring(ring, epsilon):
    """
    Simplify a coordinate ring (list of [lon, lat] pairs) using a
    simplified Visvalingam pass: remove any point whose triangle area
    with its neighbours is below epsilon.

    We do a single pass (not the full heap-based VW) — fast and good enough
    for our use case where polygons are already relatively simple.
    """
    if len(ring) <= 4:  # degenerate — don't touch
        return ring

    # Close the ring check
    closed = ring[0] == ring[-1]
    pts = ring[:-1] if closed else ring[:]

    for _ in range(8):  # multiple passes until stable
        if len(pts) <= 3:
            break
        keep = [True] * len(pts)
        n = len(pts)
        changed = False
        for i in range(1, n - 1):
            area = _triangle_area(pts[i - 1], pts[i], pts[i + 1])
            if area < epsilon:
                keep[i] = False
                changed = True
        if not changed:
            break
        pts = [p for p, k in zip(pts, keep) if k]

    if closed:
        pts = pts + [pts[0]]
    return pts


def simplify_coords(coords, geom_type, epsilon):
    """Recursively simplify coordinates depending on geometry type."""
    if geom_type in ("Polygon", "MultiLineString"):
        return [simplify_ring(ring, epsilon) for ring in coords]
    elif geom_type == "MultiPolygon":
        return [[simplify_ring(ring, epsilon) for ring in poly] for poly in coords]
    else:
        return coords  # LineString, Point — don't touch


# ── Coordinate rounding ───────────────────────────────────────────
def round_coords(coords, precision):
    if not coords:
        return coords
    if isinstance(coords[0], (int, float)):
        return [round(v, precision) for v in coords]
    return [round_coords(c, precision) for c in coords]


# ── Feature slimming ──────────────────────────────────────────────
def slim_feature(feat, epsilon, precision):
    props = {k: v for k, v in feat["properties"].items() if k in KEEP_PROPS}
    geom = feat["geometry"]
    if geom and geom.get("coordinates"):
        simplified = simplify_coords(geom["coordinates"], geom["type"], epsilon)
        rounded    = round_coords(simplified, precision)
        geom = {"type": geom["type"], "coordinates": rounded}
    return {"type": "Feature", "geometry": geom, "properties": props}


# ── Main ──────────────────────────────────────────────────────────
def main():
    if not IN_FILE.exists():
        print(f"ERROR: {IN_FILE} not found", file=sys.stderr)
        sys.exit(1)

    orig_mb = IN_FILE.stat().st_size / 1_048_576
    print(f"Reading {IN_FILE} ({orig_mb:.1f} MB)...")

    with open(IN_FILE) as f:
        data = json.load(f)

    features = data.get("features", [])
    orig_props = len(features[0]["properties"])
    print(f"  {len(features):,} features, {orig_props} properties each")

    # Backup if original backup doesn't exist
    if not BACKUP.exists():
        print(f"  Backing up original → {BACKUP}")
        import shutil
        shutil.copy(IN_FILE, BACKUP)

    print(f"Slimming ({PRECISION}dp precision, epsilon={SIMPLIFY_EPSILON:.2e})...")
    slim = [slim_feature(f, SIMPLIFY_EPSILON, PRECISION) for f in features]

    kept_props = len(slim[0]["properties"])

    # Count vertex reduction
    def count_v(coords):
        if not coords: return 0
        if isinstance(coords[0], (int, float)): return 1
        return sum(count_v(c) for c in coords)

    orig_verts = sum(count_v(f["geometry"]["coordinates"]) for f in features[:5000])
    new_verts  = sum(count_v(f["geometry"]["coordinates"]) for f in slim[:5000])
    vert_pct   = (1 - new_verts / orig_verts) * 100 if orig_verts else 0

    print(f"  Properties: {orig_props} → {kept_props}")
    print(f"  Vertices (sample 5k features): {orig_verts:,} → {new_verts:,} ({vert_pct:.0f}% fewer)")

    out = {"type": "FeatureCollection", "features": slim}

    print(f"Writing {OUT_FILE} (compact JSON)...")
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    new_mb = OUT_FILE.stat().st_size / 1_048_576
    pct = (1 - new_mb / orig_mb) * 100
    print(f"\nDone: {orig_mb:.1f} MB → {new_mb:.1f} MB ({pct:.0f}% smaller)")
    print(f"Estimated wire size with gzip: ~{new_mb/3.5:.0f}–{new_mb/2.5:.0f} MB")
    print(f"\nNext: git add data/uk_industrial_parcels.geojson && git push")


if __name__ == "__main__":
    main()
