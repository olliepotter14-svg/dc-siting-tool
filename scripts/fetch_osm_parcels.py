"""
fetch_osm_parcels.py  (v2)

Fetches all DC-relevant land parcel types from OpenStreetMap via the Overpass API.
Saves as data/uk_industrial_parcels.geojson

Site types fetched:
  industrial  — landuse=industrial
  brownfield  — landuse=brownfield
  power       — power=plant (active + disused)
  aviation    — aeroway=aerodrome (active + disused)
  military    — landuse=military (active + surplus)
  transport   — landuse=railway, landuse=port
  extraction  — landuse=quarry
  farmland    — landuse=farmland (>100 acres only — hyperscale threshold)
  commercial  — landuse=retail, landuse=commercial

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
    "aviation":    20_235,   # 5 acres
    "military":    20_235,   # 5 acres
    "transport":   20_235,   # 5 acres
    "extraction":  20_235,   # 5 acres
    "farmland":   404_686,   # 100 acres — hyperscale threshold
    "commercial":  20_235,   # 5 acres
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
    {"name": "Scotland North",   "bbox": "56.5,-7.6,58.7,-2.0"},
]

def overpass_query(bbox):
    """Single combined query covering all site types — one round trip per region."""
    return f"""
[out:json][timeout:240];
(
  way["landuse"~"^(industrial|brownfield|military|quarry|port|railway|farmland|retail|commercial)$"]({bbox});
  relation["landuse"~"^(industrial|brownfield|military|quarry|port|railway|farmland|retail|commercial)$"]({bbox});
  way["power"="plant"]({bbox});
  relation["power"="plant"]({bbox});
  way["aeroway"="aerodrome"]({bbox});
  relation["aeroway"="aerodrome"]({bbox});
);
out body;
>;
out skel qt;
"""

def get_site_type(tags):
    """Map OSM tags to display site type."""
    power   = tags.get("power",   "")
    aeroway = tags.get("aeroway", "")
    landuse  = tags.get("landuse",  "")

    if power    == "plant":             return "power"
    if aeroway  == "aerodrome":         return "aviation"
    return {
        "industrial":  "industrial",
        "brownfield":  "brownfield",
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

def parse_response(data, region_name):
    nodes = {el["id"]: (el["lon"], el["lat"])
             for el in data.get("elements", []) if el["type"] == "node"}

    features = []
    for el in data.get("elements", []):
        if el["type"] != "way":
            continue
        tags = el.get("tags", {})
        if not tags:
            continue

        site_type = get_site_type(tags)
        if site_type == "other":
            continue

        coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
        if len(coords) < 4:
            continue

        area_m2 = calculate_area(coords)
        if area_m2 < MIN_AREA.get(site_type, 8_094):
            continue

        name = tags.get("name") or tags.get("ref") or tags.get("operator") or ""
        name = name.strip() or f"Unnamed {site_type.title()} Site"

        features.append({
            "type": "Feature",
            "id":   el["id"],
            "geometry": {
                "type":        "Polygon",
                "coordinates": [[[round(c[0], 5), round(c[1], 5)] for c in coords]]
            },
            "properties": {
                "osm_id":     el["id"],
                "name":       name,
                "site_type":  site_type,
                "osm_tag":    get_osm_tag(tags),
                "area_m2":    round(area_m2),
                "area_ha":    round(area_m2 / 10_000, 2),
                "area_acres": round(area_m2 / 4_046.86, 1),
                "region":     region_name,
                "operator":   tags.get("operator", ""),
                "addr_city":  tags.get("addr:city", ""),
                "description": tags.get("description", ""),
            }
        })
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
    print("DC Site Finder — OSM Parcel Fetch (v2)")
    print("=" * 45)
    print("Site types: industrial, brownfield, power, aviation, military, transport, extraction, farmland, commercial")
    print()

    all_features, seen_ids = [], set()

    for region in UK_REGIONS:
        features = fetch_region(region)
        for f in features:
            if f["id"] not in seen_ids:
                all_features.append(f)
                seen_ids.add(f["id"])
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
