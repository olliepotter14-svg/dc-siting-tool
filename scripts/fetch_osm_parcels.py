"""
fetch_osm_parcels.py  (v4)

Fetches all DC-relevant land parcel types from OpenStreetMap via the Overpass API.
Saves as data/uk_industrial_parcels.geojson

Site types fetched:
  industrial  — landuse=industrial, landuse=depot, landuse=logistics, disused:landuse=industrial
  brownfield  — landuse=brownfield, landuse=landfill (>10 acres)
  power       — power=plant (excludes solar farms)
  aviation    — aeroway=aerodrome
  military    — landuse=military
  transport   — landuse=railway, landuse=port
  extraction  — landuse=quarry
  farmland    — landuse=farmland (>50 acres — lowered from 100 for mid-scale DCs)
  commercial  — landuse=commercial, landuse=retail (>25 acres — avoids retail noise)

v4 changes vs v3:
  - Regions: Northern Ireland added; Scotland North extended to Shetland (61.5°N)
  - Added landuse=depot and landuse=logistics (logistics parks, distribution centres)
  - Added landuse=landfill (large brownfield reclamation candidates)
  - Added disused:landuse=industrial (decommissioned industrial sites)
  - Farmland minimum lowered 100→50 acres (captures viable mid-scale DC sites)
  - Solar farms (power_source=solar) now excluded from power sites
  - Deduplication uses (type, id) tuples to avoid cross-type ID collision
  - Better name extraction: alt_name, addr:street, description fallbacks added

Usage:
    pip install requests
    python scripts/fetch_osm_parcels.py
"""

import json
import time
import math
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_FILE  = "data/uk_industrial_parcels.geojson"

# Minimum area per site type (m²)
# 1 acre = 4,047 m²
MIN_AREA = {
    "industrial":  8_094,    # 2 acres
    "brownfield":  8_094,    # 2 acres
    "power":       20_235,   # 5 acres
    "aviation":    20_235,   # 5 acres (includes disused airfields + military airfields)
    "military":    20_235,   # 5 acres
    "transport":   20_235,   # 5 acres
    "extraction":  20_235,   # 5 acres
    "farmland":   202_343,   # 50 acres — captures mid-scale DC sites (was 100)
    "commercial":  40_469,   # 10 acres — golf courses need lower threshold than retail
}

UK_REGIONS = [
    {"name": "London & SE",      "bbox": "51.0,-0.6,51.8,0.4"},
    {"name": "East of England",  "bbox": "51.5,-0.5,53.0,1.8"},
    {"name": "South West",       "bbox": "49.9,-5.8,51.5,-1.5"},
    {"name": "South East",       "bbox": "50.7,-1.5,51.5,1.5"},
    {"name": "East Midlands",    "bbox": "52.0,-2.0,53.3,0.0"},
    {"name": "West Midlands",    "bbox": "51.8,-3.2,53.0,-1.2"},
    {"name": "North West",       "bbox": "53.0,-3.4,54.8,-1.8"},
    {"name": "Yorkshire",        "bbox": "53.3,-2.5,54.6,0.2"},
    {"name": "North East",       "bbox": "54.5,-2.5,55.9,-0.8"},
    {"name": "Wales",            "bbox": "51.3,-5.3,53.5,-2.6"},
    {"name": "Scotland South",   "bbox": "54.8,-5.2,56.5,-1.8"},
    {"name": "Scotland North",   "bbox": "56.5,-7.6,61.5,-0.8"},   # extended to Shetland
    {"name": "Northern Ireland", "bbox": "54.0,-8.2,55.5,-5.4"},   # previously missing
]

def overpass_query(bbox):
    """Single combined query covering all site types — one round trip per region."""
    return f"""
[out:json][timeout:300];
(
  way["landuse"~"^(industrial|brownfield|military|quarry|port|railway|farmland|retail|commercial|depot|logistics|landfill)$"]({bbox});
  relation["landuse"~"^(industrial|brownfield|military|quarry|port|railway|farmland|retail|commercial|depot|logistics|landfill)$"]({bbox});
  way["disused:landuse"="industrial"]({bbox});
  relation["disused:landuse"="industrial"]({bbox});
  way["power"="plant"]({bbox});
  relation["power"="plant"]({bbox});
  way["aeroway"="aerodrome"]({bbox});
  relation["aeroway"="aerodrome"]({bbox});
  way["man_made"="works"][!"landuse"]({bbox});
  relation["man_made"="works"][!"landuse"]({bbox});
  way["disused:aeroway"="aerodrome"]({bbox});
  relation["disused:aeroway"="aerodrome"]({bbox});
  way["military"="airfield"]({bbox});
  relation["military"="airfield"]({bbox});
  way["leisure"="golf_course"]({bbox});
  relation["leisure"="golf_course"]({bbox});
);
out body;
>;
out skel qt;
"""

_SOLAR_SOURCES = {"solar", "photovoltaic", "pv"}

def get_site_type(tags):
    """Map OSM tags to display site type."""
    power   = tags.get("power",   "")
    aeroway = tags.get("aeroway", "")
    landuse  = tags.get("landuse",  "")
    disused  = tags.get("disused:landuse", "")

    disused_aeroway = tags.get("disused:aeroway", "")
    military_sub    = tags.get("military", "")
    leisure         = tags.get("leisure", "")
    man_made        = tags.get("man_made", "")

    if power == "plant":
        # Exclude solar farms — wrong shape/location for DCs; used as proximity signal only
        src = tags.get("plant:source", tags.get("power_source", "")).lower()
        if src in _SOLAR_SOURCES:
            return "other"
        return "power"
    if aeroway == "aerodrome":
        return "aviation"
    if disused_aeroway == "aerodrome":
        return "aviation"        # former/disused airfields — prime DC land
    if military_sub == "airfield":
        return "aviation"        # former military airfields
    if man_made == "works" and not landuse:
        return "industrial"      # standalone factories/processing plants missing landuse tag
    if leisure == "golf_course":
        return "commercial"      # declining golf clubs — large flat sites near urban fringe
    if disused == "industrial":
        return "industrial"      # decommissioned industrial — often best brownfield candidates
    return {
        "industrial":  "industrial",
        "depot":       "industrial",   # logistics parks, distribution centres
        "logistics":   "industrial",   # same
        "brownfield":  "brownfield",
        "landfill":    "brownfield",   # large closed landfills — reclamation candidates
        "military":    "military",
        "quarry":      "extraction",
        "port":        "transport",
        "railway":     "transport",
        "farmland":    "farmland",
        "retail":      "commercial",
        "commercial":  "commercial",
    }.get(landuse, "other")

def get_osm_tag(tags):
    """Return the primary OSM tag string for display."""
    for key in ("power", "aeroway", "man_made", "landuse"):
        if key in tags:
            return f"{key}={tags[key]}"
    return "unknown"

def calculate_area(coords):
    """Shoelace formula area in m² using equirectangular projection."""
    if len(coords) < 3:
        return 0
    lat_mid = sum(c[1] for c in coords) / len(coords)
    m_lon = 111_320 * math.cos(math.radians(lat_mid))
    m_lat = 111_320
    n, area = len(coords), 0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * m_lon * coords[j][1] * m_lat
        area -= coords[j][0] * m_lon * coords[i][1] * m_lat
    return abs(area) / 2

def make_feature(osm_id, tags, coords, region_name):
    """Build a GeoJSON feature from resolved coordinates."""
    site_type = get_site_type(tags)
    if site_type == "other" or len(coords) < 4:
        return None
    area_m2 = calculate_area(coords)
    if area_m2 < MIN_AREA.get(site_type, 8_094):
        return None
    name = (tags.get("name") or tags.get("alt_name") or tags.get("ref")
            or tags.get("operator") or tags.get("addr:street")
            or tags.get("description") or "")
    name = name.strip() or f"Unnamed {site_type.title()} Site"
    return {
        "type": "Feature",
        "id":   osm_id,
        "geometry": {
            "type":        "Polygon",
            "coordinates": [[[round(c[0], 5), round(c[1], 5)] for c in coords]],
        },
        "properties": {
            "osm_id":      osm_id,
            "name":        name,
            "site_type":   site_type,
            "osm_tag":     get_osm_tag(tags),
            "area_m2":     round(area_m2),
            "area_ha":     round(area_m2 / 10_000, 2),
            "area_acres":  round(area_m2 / 4_046.86, 1),
            "region":      region_name,
            "operator":    tags.get("operator", ""),
            "addr_city":   tags.get("addr:city", ""),
            "description": tags.get("description", ""),
        },
    }

def parse_response(data, region_name):
    elements = data.get("elements", [])

    # Node coordinate lookup
    nodes = {el["id"]: (el["lon"], el["lat"])
             for el in elements if el["type"] == "node"}

    # Way coordinate + tag lookup (needed for relation member resolution)
    way_coords = {}
    way_tags   = {}
    for el in elements:
        if el["type"] != "way":
            continue
        coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
        if coords:
            way_coords[el["id"]] = coords
            way_tags[el["id"]]   = el.get("tags", {})

    features  = []
    seen_ids  = set()   # stores (osm_type, osm_id) tuples to avoid cross-type collisions

    # ── Relations (multipolygons — large business parks, science campuses etc.) ─
    for el in elements:
        if el["type"] != "relation":
            continue
        tags = el.get("tags", {})
        if not tags:
            continue
        key = ("relation", el["id"])
        if key in seen_ids:
            continue
        # Collect all outer-ring member way coordinates
        all_coords = []
        for member in el.get("members", []):
            if member.get("type") == "way" and member.get("role") in ("outer", ""):
                wid = member.get("ref")
                if wid in way_coords:
                    all_coords.extend(way_coords[wid])
        feat = make_feature(el["id"], tags, all_coords, region_name)
        if feat:
            features.append(feat)
            seen_ids.add(key)
            # Mark member ways as consumed so they don't appear as duplicates
            for member in el.get("members", []):
                if member.get("type") == "way":
                    seen_ids.add(("way", member.get("ref")))

    # ── Ways (standalone polygons) ─────────────────────────────────
    for el in elements:
        key = ("way", el["id"])
        if el["type"] != "way" or key in seen_ids:
            continue
        tags = el.get("tags", {})
        if not tags:
            continue
        coords = way_coords.get(el["id"], [])
        feat = make_feature(el["id"], tags, coords, region_name)
        if feat:
            features.append(feat)
            seen_ids.add(key)

    return features

def fetch_region(region, retries=5):
    print(f"  {region['name']}...", end=" ", flush=True)
    query = overpass_query(region["bbox"])
    for attempt in range(retries):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, timeout=260)
            if r.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"\n    ⏳ Rate limited — waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            features = parse_response(r.json(), region["name"])
            print(f"{len(features)} parcels")
            return features
        except requests.exceptions.Timeout:
            wait = 30 * (attempt + 1)
            print(f"\n    ⏳ Timeout — retrying in {wait}s", flush=True)
            time.sleep(wait)
        except Exception as e:
            wait = 20 * (attempt + 1)
            print(f"\n    ⏳ {e} — retrying in {wait}s", flush=True)
            time.sleep(wait)
    print("FAILED")
    return []

def main():
    print("DC Site Finder — OSM Parcel Fetch (v4)")
    print("=" * 45)
    print("Site types: industrial, brownfield, power, aviation, military, transport, extraction, farmland, commercial")
    print()

    all_features, seen_ids = [], set()

    for region in UK_REGIONS:
        features = fetch_region(region)
        for f in features:
            # Use osm_id string as dedup key (already unique within a fetch run)
            fid = f["properties"]["osm_id"]
            if fid not in seen_ids:
                all_features.append(f)
                seen_ids.add(fid)
        time.sleep(6)

    all_features.sort(key=lambda f: f["properties"]["area_m2"], reverse=True)

    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "fetched_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_features": len(all_features),
            "source":         "OpenStreetMap via Overpass API",
        },
        "features": all_features
    }

    # Write atomically: temp file → rename, so the browser never reads a half-written file
    tmp_file = OUTPUT_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    import os
    os.replace(tmp_file, OUTPUT_FILE)

    size_mb = len(json.dumps(geojson)) / 1_000_000
    print()
    print(f"Total: {len(all_features):,} parcels → {OUTPUT_FILE} ({size_mb:.1f} MB)")
    print()

    # Summary by site type
    by_type = {}
    for feat in all_features:
        t = feat["properties"]["site_type"]
        by_type[t] = by_type.get(t, 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t:<12} {n:>6,}")

if __name__ == "__main__":
    main()
