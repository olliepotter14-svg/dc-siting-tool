"""
fetch_powerlines.py

Fetches UK high-voltage transmission lines (400kV and 275kV) from OSM via
Overpass API and saves as data/uk_powerlines.geojson.

Only supergrid lines are fetched — these are the visually distinctive routes
that carry power between major substations and matter for DC siting context.
132kV is excluded to keep the data manageable and the map uncluttered.

Usage:
    python3 scripts/fetch_powerlines.py
"""

import json, math, time, os, urllib.request, urllib.error

OUTPUT = "data/uk_powerlines.geojson"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# 400kV and 275kV only — UK supergrid
QUERY = """
[out:json][timeout:120];
(
  way["power"="line"]["voltage"~"400000|275000"](49.5,-8.5,61.0,2.5);
);
out geom;
"""

def fetch(query, attempt=1):
    data = query.encode("utf-8")
    req  = urllib.request.Request(OVERPASS_URL, data=data,
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (429, 504) and attempt <= 4:
            wait = 30 * attempt
            print(f"  Rate-limited ({e.code}), waiting {wait}s …")
            time.sleep(wait)
            return fetch(query, attempt + 1)
        raise

def parse_voltage(raw):
    """Return the highest voltage value from a raw OSM voltage string."""
    parts = str(raw).replace(";", ",").split(",")
    vals  = []
    for p in parts:
        try: vals.append(int(p.strip()))
        except ValueError: pass
    return max(vals) if vals else 0

def round_coord(c, dp=3):
    return round(c, dp)

def main():
    print("DC Site Finder — Powerlines Fetch")
    print("=" * 40)

    print("Querying Overpass …")
    t0  = time.time()
    raw = fetch(QUERY)
    elements = raw.get("elements", [])
    print(f"  {len(elements)} ways received in {time.time()-t0:.0f}s")

    features = []
    skipped  = 0
    for el in elements:
        if el.get("type") != "way":
            continue
        geom = el.get("geometry", [])
        if len(geom) < 2:
            skipped += 1
            continue

        coords  = [[round_coord(n["lon"]), round_coord(n["lat"])] for n in geom]
        voltage = parse_voltage(el.get("tags", {}).get("voltage", "0"))
        name    = el.get("tags", {}).get("name", "")
        ref     = el.get("tags", {}).get("ref",  "")

        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "osm_id":   el["id"],
                "voltage":  voltage,
                "name":     name,
                "ref":      ref,
            }
        })

    print(f"  {len(features)} valid LineString features ({skipped} skipped)")

    # Breakdown by voltage
    v_counts = {}
    for f in features:
        v = f["properties"]["voltage"]
        v_counts[v] = v_counts.get(v, 0) + 1
    for v, n in sorted(v_counts.items(), reverse=True):
        print(f"    {v//1000:>4}kV : {n} ways")

    geojson = {"type": "FeatureCollection", "features": features}
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT)

    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"\nSaved → {OUTPUT}  ({size_kb:.0f} KB)")

if __name__ == "__main__":
    main()
