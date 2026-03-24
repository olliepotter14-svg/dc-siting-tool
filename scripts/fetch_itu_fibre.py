"""
fetch_itu_fibre.py

Downloads UK backbone fibre routes from the ITU BBmaps WFS service.
Data: terrestrial optical fibre transmission links (LineString geometries).

Source: ITU Broadband Mapping Programme
  WFS: https://bbmaps.itu.int/geoserver/itu-geocatalogue/wfs
  Layer: itu-geocatalogue:trx_geocatalogue
  Properties: uid, type_inf (e.g. "Fibre Operational"), status

Output: data/uk_fibre_routes.geojson

Usage:
    python3 scripts/fetch_itu_fibre.py
"""

import json, os, time, subprocess

OUTPUT = "data/uk_fibre_routes.geojson"

# UK bounding box (generous — clips at Isle of Man, Shetland, Channel Islands)
UK_BBOX = "-9,49,2,61"

WFS_URL = (
    "https://bbmaps.itu.int/geoserver/itu-geocatalogue/wfs"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames=itu-geocatalogue:trx_geocatalogue"
    f"&bbox={UK_BBOX},EPSG:4326"
    "&outputFormat=application/json"
)


def fetch():
    print("Fetching UK fibre routes from ITU BBmaps WFS…")
    # Use curl — ITU server requires TLS 1.2 which Python 3.9's urllib struggles with
    result = subprocess.run(
        ["curl", "-s", "--max-time", "120",
         "-H", "User-Agent: dc-siting-tool/1.0",
         "-H", "Accept: application/json",
         WFS_URL],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def main():
    print("DC Site Finder — ITU Backbone Fibre Route Fetch")
    print("=" * 50)
    t0 = time.time()

    data = fetch()
    features = data.get("features", [])
    total    = data.get("totalFeatures", len(features))

    print(f"Downloaded: {len(features):,} of {total:,} features")

    # Count by type
    types = {}
    for f in features:
        t = f["properties"].get("type_inf", "Unknown")
        types[t] = types.get(t, 0) + 1
    for t, n in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {n:,}")

    # Keep only operational fibre (filter out planned/microwave)
    operational = [f for f in features
                   if "Fibre" in f["properties"].get("type_inf", "")
                   and f["properties"].get("status") == "Operational"]
    print(f"\nOperational fibre routes: {len(operational):,}")

    geojson = {
        "type":     "FeatureCollection",
        "features": operational,
    }

    tmp = OUTPUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT)

    size_kb = os.path.getsize(OUTPUT) / 1000
    print(f"\nSaved → {OUTPUT}  ({size_kb:.0f} KB)")
    print(f"Total time: {time.time() - t0:.1f}s")
    print("\nRun  python3 scripts/enrich_fibre_routes.py  to score parcels.")


if __name__ == "__main__":
    main()
