"""
fetch_missing_regions.py

Fetches only the regions missing from the initial run and merges into the existing GeoJSON.
"""

import json
import time
import math
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
EXISTING_FILE = "data/uk_industrial_parcels.geojson"
OUTPUT_FILE = "data/uk_industrial_parcels.geojson"

MIN_AREA_M2 = 8094

MISSING_REGIONS = [
    {"name": "East of England", "bbox": "51.5,-0.5,53.0,1.8"},
    {"name": "South East",      "bbox": "50.7,-1.5,51.5,1.5"},
    {"name": "East Midlands",   "bbox": "52.0,-2.0,53.3,0.0"},
    {"name": "West Midlands",   "bbox": "51.8,-3.2,53.0,-1.2"},
    {"name": "North West",      "bbox": "53.0,-3.4,54.8,-1.8"},
    {"name": "North East",      "bbox": "54.5,-2.5,55.9,-0.8"},
    {"name": "Wales",           "bbox": "51.3,-5.3,53.5,-2.6"},
    {"name": "Scotland North",  "bbox": "56.5,-7.6,58.7,-2.0"},
]

def overpass_query(bbox):
    return f"""
[out:json][timeout:180];
(
  way["landuse"="industrial"]({bbox});
  relation["landuse"="industrial"]({bbox});
  way["landuse"="brownfield"]({bbox});
  relation["landuse"="brownfield"]({bbox});
);
out body;
>;
out skel qt;
"""

def calculate_polygon_area(coords):
    if len(coords) < 3:
        return 0
    lat_mid = sum(c[1] for c in coords) / len(coords)
    lat_rad = math.radians(lat_mid)
    m_per_deg_lat = 111320
    m_per_deg_lon = 111320 * math.cos(lat_rad)
    n = len(coords)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        x1 = coords[i][0] * m_per_deg_lon
        y1 = coords[i][1] * m_per_deg_lat
        x2 = coords[j][0] * m_per_deg_lon
        y2 = coords[j][1] * m_per_deg_lat
        area += x1 * y2 - x2 * y1
    return abs(area) / 2

def m2_to_acres(m2): return m2 / 4046.86
def m2_to_ha(m2): return m2 / 10000

def parse_overpass_response(data, region_name):
    nodes = {}
    for el in data.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
    features = []
    for el in data.get("elements", []):
        if el["type"] != "way":
            continue
        if "tags" not in el or "landuse" not in el.get("tags", {}):
            continue
        node_ids = el.get("nodes", [])
        coords = [nodes[nid] for nid in node_ids if nid in nodes]
        if len(coords) < 4:
            continue
        area_m2 = calculate_polygon_area(coords)
        if area_m2 < MIN_AREA_M2:
            continue
        tags = el.get("tags", {})
        land_use = tags.get("landuse", "unknown")
        name = tags.get("name", tags.get("ref", f"Unnamed {land_use.title()} Site"))
        features.append({
            "type": "Feature",
            "id": el["id"],
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "osm_id": el["id"],
                "name": name,
                "land_use": land_use,
                "area_m2": round(area_m2),
                "area_ha": round(m2_to_ha(area_m2), 2),
                "area_acres": round(m2_to_acres(area_m2), 1),
                "region": region_name,
                "operator": tags.get("operator", ""),
                "addr_city": tags.get("addr:city", ""),
                "description": tags.get("description", ""),
            }
        })
    return features

def fetch_region(region, retries=5):
    print(f"  Fetching {region['name']}...")
    query = overpass_query(region["bbox"])
    for attempt in range(retries):
        try:
            response = requests.post(OVERPASS_URL, data={"data": query}, timeout=200)
            if response.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"    ⏳ Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            features = parse_overpass_response(data, region["name"])
            print(f"    → {len(features)} parcels")
            return features
        except requests.exceptions.Timeout:
            wait = 30 * (attempt + 1)
            print(f"    ⏳ Timeout — waiting {wait}s (attempt {attempt+1}/{retries})")
            time.sleep(wait)
        except Exception as e:
            wait = 20 * (attempt + 1)
            print(f"    ⏳ Error: {e} — retrying in {wait}s")
            time.sleep(wait)
    print(f"    ✗ Failed after {retries} attempts")
    return []

def main():
    print("DC Site Finder — Fetching missing regions")
    print("=" * 45)

    # Load existing data
    with open(EXISTING_FILE) as f:
        existing = json.load(f)

    seen_ids = {feat["id"] for feat in existing["features"]}
    existing_count = len(existing["features"])
    print(f"Existing parcels: {existing_count}")
    print()

    new_features = []
    for region in MISSING_REGIONS:
        features = fetch_region(region)
        for feat in features:
            if feat["id"] not in seen_ids:
                new_features.append(feat)
                seen_ids.add(feat["id"])
        time.sleep(8)  # Polite delay between regions

    print()
    print(f"New parcels fetched: {len(new_features)}")
    total = existing_count + len(new_features)
    print(f"Total after merge: {total}")

    # Merge and sort by area
    all_features = existing["features"] + new_features
    all_features.sort(key=lambda f: f["properties"]["area_m2"], reverse=True)

    merged = {
        "type": "FeatureCollection",
        "metadata": {
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_features": total,
            "land_use_types": ["industrial", "brownfield"],
            "min_area_acres": 2.0,
            "source": "OpenStreetMap via Overpass API"
        },
        "features": all_features
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, separators=(",", ":"))

    size_mb = len(json.dumps(merged)) / 1_000_000
    print(f"Saved to {OUTPUT_FILE} ({size_mb:.1f} MB)")

    # Summary by region
    print()
    by_region = {}
    for feat in all_features:
        r = feat["properties"]["region"]
        by_region[r] = by_region.get(r, 0) + 1
    for r, count in sorted(by_region.items()):
        print(f"  {r}: {count}")

if __name__ == "__main__":
    main()
