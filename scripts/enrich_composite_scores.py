"""
enrich_composite_scores.py

Second enrichment pass — adds fibre, flood risk, planning, buildability,
and permissioning scores to uk_industrial_parcels.geojson, then computes
a composite 0-100 score across four dimensions.

Run AFTER enrich_power_scores.py (which adds the power score properties).

Scoring model (4 factors):
  Power (40%)          : grid headroom × distance factor (from enrich_power_scores.py)
  Permissioning (30%)  : planning_score from site type + green/grey belt + growth zone bonus
  Fibre (20%)          : distance to backbone route / carrier-neutral colo
  Buildability (10%)   : site area + type penalties

  Note: flood zone is NOT in the composite — Zone 3 is a hard exclusion, Zone 1/2 are
  informational tags shown in the UI.

New properties added per parcel:
  dist_to_ix_km        : km to nearest PeeringDB IXP or carrier facility
  nearest_ix_name      : name of that IX/facility
  fibre_score          : 0-100 fibre connectivity score
  flood_zone           : 1 / 2 / 3 (EA zones; 1=low, 2=medium, 3=high)
  flood_score          : 0-100 (100=zone1, 50=zone2, 0=zone3)
  hard_excluded        : true if flood zone 3 or protected designation
  planning_score       : 0-100 from site_type (with green/grey belt adjustments)
  permissioning_score  : 0-100 average of planning_score + flood_score
  buildability_score   : 0-100 from area + type
  composite_score_20   : weighted composite score for 20MW DC
  composite_score_50   : weighted composite score for 50MW DC
  composite_score_100  : weighted composite score for 100MW DC

Usage:
    python3 scripts/enrich_composite_scores.py
Takes ~3-5 minutes for 40k parcels.
"""

import json, math, time, os

PARCELS_FILE   = "data/uk_industrial_parcels.geojson"
PEERINGDB_FILE = "data/uk_peeringdb.json"
OUTPUT_FILE    = "data/uk_industrial_parcels.geojson"

# ── Scoring weights ────────────────────────────────────────────────
WEIGHTS = {
    "power":          0.40,
    "permissioning":  0.30,
    "fibre":          0.20,
    "buildability":   0.10,
}

# ── Geometry helpers ───────────────────────────────────────────────
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

def point_in_ring(lng, lat, ring):
    """Ray casting point-in-polygon for a single ring."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside

def point_in_feature(lng, lat, feat):
    """Test if (lng, lat) falls inside a Polygon or MultiPolygon feature."""
    geom = feat.get("geometry") or {}
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = coords
    else:
        return False

    for rings in polys:
        if not rings:
            continue
        if point_in_ring(lng, lat, rings[0]):
            # Check holes (inner rings)
            in_hole = any(point_in_ring(lng, lat, hole) for hole in rings[1:])
            if not in_hole:
                return True
    return False

# ── Spatial index for flood zones ─────────────────────────────────
CELL_DEG = 0.1  # ~10 km cells

class GridIndex:
    """Simple grid-based spatial index for polygon features."""

    def __init__(self, features):
        self.features = features
        self.grid = {}
        self.bboxes = []

        for i, feat in enumerate(features):
            geom = feat.get("geometry") or {}
            coords = self._flat_coords(geom)
            if not coords:
                self.bboxes.append(None)
                continue
            lngs = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            bbox = (min(lngs), min(lats), max(lngs), max(lats))
            self.bboxes.append(bbox)

            cx0 = int(bbox[0] / CELL_DEG)
            cx1 = int(bbox[2] / CELL_DEG) + 1
            cy0 = int(bbox[1] / CELL_DEG)
            cy1 = int(bbox[3] / CELL_DEG) + 1
            for cx in range(cx0, cx1):
                for cy in range(cy0, cy1):
                    self.grid.setdefault((cx, cy), []).append(i)

    def _flat_coords(self, geom):
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        result = []
        if gtype == "Polygon":
            for ring in coords:
                result.extend(ring)
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    result.extend(ring)
        return result

    def query(self, lng, lat):
        """Return list of feature indices whose bbox contains (lng, lat)."""
        cx = int(lng / CELL_DEG)
        cy = int(lat / CELL_DEG)
        return self.grid.get((cx, cy), [])


# ── Dimension scorers ──────────────────────────────────────────────
def fibre_score(dist_km):
    if dist_km is None: return 20
    if dist_km <= 5:    return 100
    if dist_km <= 15:   return 80
    if dist_km <= 30:   return 60
    if dist_km <= 60:   return 35
    if dist_km <= 100:  return 15
    return 5

def flood_score(zone):
    if zone == 1:  return 100
    if zone == 2:  return 50
    if zone == 3:  return 0     # Zone 3a/3b both treated as hard exclude
    return 100                   # default Zone 1 (e.g. Scotland/Wales)

# ── Permissioning buckets ──────────────────────────────────────────
# Three buckets reflecting real planning consent risk for DC conversion.
#
# Bucket A (score 85) — Permitted / low consent risk
#   Industrial: DC is a lawful or near-lawful B2/B8 use; prior approval often sufficient
#   Brownfield: previously developed, same planning path as industrial
#   Power station: brownfield, existing HV grid on-site, strong DC precedents
#     (Microsoft Skelton Grange, Rugeley, Ratcliffe); NESO actively promoting
#     former power station sites for DC reuse; treated as previously developed land
#
# Bucket B (score 55) — Achievable / standard consent path
#   Transport, Commercial, Military: change of use required but DC precedents
#     exist; consent likely within 2–4 years through standard planning process
#
# Bucket C (score 20) — Complex / material change of use
#   Extraction, Aviation, Farmland: significant change of use; sequential test;
#     likely long timeline and high refusal risk without special circumstances
#
# Multipliers applied on top:
#   Grey Belt (brownfield within Green Belt): ×0.80
#     — surmountable with CNI status; precedent: Hertfordshire £3.75bn DC
#   Green Belt (undeveloped): ×0.55
#     — significant hurdle even with CNI; NPPF "very special circumstances" required
#   AI Growth Zone: +15 points (capped at 100)
#     — political alignment; government target of 2-year consent

BUCKET_A = 85   # Permitted / low consent risk
BUCKET_B = 55   # Achievable / standard consent
BUCKET_C = 20   # Complex / change of use

PLANNING_SCORES = {
    "industrial":  BUCKET_A,
    "brownfield":  BUCKET_A,
    "power":       BUCKET_A,
    "transport":   BUCKET_B,
    "commercial":  BUCKET_B,
    "military":    BUCKET_B,
    "extraction":  BUCKET_C,
    "aviation":    BUCKET_C,
    "farmland":    BUCKET_C,
}

def planning_score(site_type, green_belt=False, grey_belt=False):
    base = PLANNING_SCORES.get(site_type, BUCKET_B)
    if grey_belt:
        return max(5, round(base * 0.80))
    if green_belt:
        return max(5, round(base * 0.55))
    return base

def buildability_score(area_acres, site_type):
    if area_acres >= 200: size_s = 100
    elif area_acres >= 100: size_s = 90
    elif area_acres >= 50:  size_s = 78
    elif area_acres >= 25:  size_s = 63
    elif area_acres >= 10:  size_s = 48
    elif area_acres >= 5:   size_s = 35
    else:                   size_s = 20

    # Type adjustments
    penalty = {"brownfield": -8, "extraction": -15, "farmland": -5}.get(site_type, 0)
    return max(0, min(100, size_s + penalty))

def permissioning_score(planning_s, growth_zone=False):
    """
    Permissioning score = planning consent risk for the site type.
    Three natural buckets based on planning_score value:
      Bucket A (≥75): Industrial/brownfield on non-GB — pre-approved land use, low consent risk
      Bucket B (50-74): Power/transport/commercial/grey belt — standard DC consent path
      Bucket C (<50):  Farmland/extraction/Green Belt — complex/change-of-use required

    growth_zone: +15 bonus for AI Growth Zones (political alignment, 2yr consent target).
    Note: flood zone is NOT included — Zone 3 is a hard exclusion, Zone 1/2 are informational tags.
    """
    score = planning_s
    if growth_zone:
        score = min(100, score + 15)
    return round(score, 1)

def composite(power_s, perm_s, fibre_s, build_s):
    return round(
        power_s * WEIGHTS["power"]
        + perm_s  * WEIGHTS["permissioning"]
        + fibre_s * WEIGHTS["fibre"]
        + build_s * WEIGHTS["buildability"],
        1,
    )


# ── Main ───────────────────────────────────────────────────────────
def main():
    print("DC Site Finder — Composite Score Enrichment")
    print("=" * 50)
    t0 = time.time()

    # ── Load parcels ───────────────────────────────────────────────
    with open(PARCELS_FILE) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"Parcels loaded: {len(features):,}")

    # Check power scores are present
    sample = features[0]["properties"]
    if "power_score_50" not in sample:
        print("WARNING: power_score_50 not found — run enrich_power_scores.py first")

    # ── Load PeeringDB ─────────────────────────────────────────────
    if os.path.exists(PEERINGDB_FILE):
        with open(PEERINGDB_FILE) as f:
            pdb = json.load(f)
        # Combine exchanges + facilities into one list
        ix_points = []
        for x in pdb.get("exchanges", []):
            ix_points.append((x["lat"], x["lng"], x["name"]))
        for x in pdb.get("facilities", []):
            ix_points.append((x["lat"], x["lng"], x["name"]))
        print(f"PeeringDB points loaded: {len(ix_points)}")
    else:
        print("WARNING: uk_peeringdb.json not found — fibre scores will use fallback")
        ix_points = []

    # ── Check flood zones ──────────────────────────────────────────
    # flood_zone is added by enrich_flood_zones.py (run before this script)
    has_flood = features[0]["properties"].get("flood_zone") is not None if features else False
    if not has_flood:
        print("WARNING: flood_zone not found on parcels — run enrich_flood_zones.py first")
        print("         Flood scores will default to Zone 1 (score = 100)")
    else:
        z_counts = {}
        for f in features:
            z = f["properties"].get("flood_zone", 1)
            z_counts[z] = z_counts.get(z, 0) + 1
        print(f"Flood zones: Zone1={z_counts.get(1,0):,}  Zone2={z_counts.get(2,0):,}  Zone3={z_counts.get(3,0):,}")

    print()

    # ── Enrich each parcel ─────────────────────────────────────────
    t_report = time.time()
    flood_stats = {1: 0, 2: 0, 3: 0}

    for i, feat in enumerate(features):
        coords = feat["geometry"]["coordinates"][0]
        plat, plng = centroid(coords)
        p = feat["properties"]

        # ── Fibre score ────────────────────────────────────────────
        # PeeringDB colo/IX distance
        if ix_points:
            ix_dist = min(haversine(plat, plng, ilat, ilng)
                          for ilat, ilng, _ in ix_points)
            ix_name = min(ix_points, key=lambda x: haversine(plat, plng, x[0], x[1]))[2]
        else:
            ix_dist = None
            ix_name = ""

        # ITU backbone route distance (pre-computed by enrich_fibre_routes.py)
        route_dist = p.get("fibre_route_km")

        # Best of: nearest backbone route OR nearest carrier-neutral colo
        if route_dist is not None and ix_dist is not None:
            best_dist = min(ix_dist, route_dist)
        elif route_dist is not None:
            best_dist = route_dist
        elif ix_dist is not None:
            best_dist = ix_dist
        else:
            best_dist = None
        best_name = ix_name  # keep IX name for display

        f_score = fibre_score(best_dist)

        # ── Flood zone (pre-computed by enrich_flood_zones.py) ────
        zone      = p.get("flood_zone", 1)
        hard_excl = p.get("hard_excluded", zone == 3)
        flood_stats[zone] = flood_stats.get(zone, 0) + 1
        fld_score = flood_score(zone)

        # ── Other dimensions ───────────────────────────────────────
        pl_score  = planning_score(
            p.get("site_type", ""),
            green_belt=p.get("green_belt", False),
            grey_belt=p.get("grey_belt", False),
        )
        # growth_zone field will be added by a future enrichment pass;
        # defaults False until then
        growth_zone = p.get("growth_zone", False)
        perm_s  = permissioning_score(pl_score, growth_zone=growth_zone)
        build_s = buildability_score(p.get("area_acres", 0), p.get("site_type", ""))

        # ── Composite scores (three MW anchors) ────────────────────
        for mw in ("20", "50", "100"):
            power_s = p.get(f"power_score_{mw}", 0)
            p[f"composite_score_{mw}"] = composite(power_s, perm_s, f_score, build_s)

        # Hard exclusions override — SSSI, National Park, AONB, Flood Zone 3 etc.
        if hard_excl:
            for mw in ("20", "50", "100"):
                p[f"composite_score_{mw}"] = 0.0

        # ── Write new properties ───────────────────────────────────
        p["dist_to_ix_km"]        = round(ix_dist, 2) if ix_dist is not None else None
        p["nearest_ix_name"]      = best_name
        p["best_fibre_km"]        = round(best_dist, 2) if best_dist is not None else None
        p["fibre_score"]          = f_score
        p["flood_zone"]           = zone
        p["flood_score"]          = fld_score
        p["hard_excluded"]        = hard_excl
        p["planning_score"]       = pl_score
        p["permissioning_score"]  = perm_s
        p["green_belt"]           = p.get("green_belt", False)
        p["grey_belt"]            = p.get("grey_belt", False)
        p["buildability_score"]   = build_s

        # Progress every 5k
        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t_report
            rate    = 5000 / elapsed
            remain  = (len(features) - i - 1) / rate
            print(f"  {i+1:>6,} / {len(features):,}  ({rate:.0f}/s, ~{remain:.0f}s remaining)")
            t_report = time.time()

    # ── Save ───────────────────────────────────────────────────────
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)

    elapsed_total = time.time() - t0
    size_mb = os.path.getsize(OUTPUT_FILE) / 1e6
    print(f"\nDone in {elapsed_total:.0f}s — {OUTPUT_FILE} ({size_mb:.1f} MB)")

    # ── Summary ────────────────────────────────────────────────────
    print("\nFlood zone distribution:")
    for z in (1, 2, 3):
        n = flood_stats.get(z, 0)
        label = {1: "Zone 1 (low)", 2: "Zone 2 (medium)", 3: "Zone 3 (high/excl)"}[z]
        print(f"  {label:<25} {n:>6,}  ({100*n/len(features):.1f}%)")

    scores = [f["properties"]["composite_score_50"] for f in features]
    buckets = {"90-100": 0, "70-89": 0, "50-69": 0, "30-49": 0, "<30": 0}
    for s in scores:
        if s >= 90:   buckets["90-100"] += 1
        elif s >= 70: buckets["70-89"]  += 1
        elif s >= 50: buckets["50-69"]  += 1
        elif s >= 30: buckets["30-49"]  += 1
        else:         buckets["<30"]    += 1
    print("\nComposite score distribution (50MW basis):")
    for label, n in buckets.items():
        bar = "█" * (n * 40 // len(features))
        print(f"  {label:>8}  {bar:<40} {n:>6,}")


if __name__ == "__main__":
    main()
