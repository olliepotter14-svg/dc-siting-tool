"""
fetch_flood_zones.py

Fetches EA Flood Map for Planning flood zone polygons (Zone 2 and Zone 3)
for England from the Environment Agency OGC API Features service and
saves as data/uk_flood_zones.geojson.

Zone classifications:
  Zone 1  = Low risk (<0.1% annual probability)  — default, not fetched
  Zone 2  = Medium risk (0.1–1%)                 — fetched, tagged zone=2
  Zone 3a = High risk (>=1%)                     — fetched, tagged zone=3
  Zone 3b = Functional floodplain (>=3.3%)       — not separately available in
             national API; treated as Zone 3 here (local authority data needed
             for 3b distinction)

EA data covers England only. Scottish (SEPA) and Welsh (NRW) parcels
will default to Zone 1 in the enrichment step.

The output file is used by enrich_composite_scores.py for spatial join.

Usage:
    python3 scripts/fetch_flood_zones.py
Expected runtime: 5–20 minutes depending on EA server load.
"""

import json, os, math, time, urllib.request, urllib.error, urllib.parse

OUTPUT = "data/uk_flood_zones.geojson"

# EA OGC API Features base — discover collection name dynamically
EA_BASE = "https://environment.data.gov.uk/spatialdata"

# Single combined collection for flood zones 2 and 3
# Collection: Flood_Zones_2_3_Rivers_and_Sea
# Property flood_zone = "FZ2" | "FZ3"
EA_COLLECTION_BASE = (
    "https://environment.data.gov.uk/spatialdata"
    "/flood-map-for-planning-flood-zones"
    "/ogc/features/v1/collections"
    "/Flood_Zones_2_3_Rivers_and_Sea/items"
)

# England bounding box (west, south, east, north) in WGS84
ENGLAND_BBOX = (-5.7, 49.9, 1.8, 55.8)

PAGE_SIZE = 1000
REQUEST_DELAY = 0.3  # seconds between requests — be polite to EA servers


def fetch_json(url, attempt=1):
    req = urllib.request.Request(url, headers={
        "User-Agent": "dc-siting-tool/1.0",
        "Accept":     "application/geo+json, application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (429, 503, 504) and attempt <= 4:
            wait = 30 * attempt
            print(f"    HTTP {e.code} — waiting {wait}s…")
            time.sleep(wait)
            return fetch_json(url, attempt + 1)
        print(f"    HTTP error {e.code}: {url}")
        raise
    except Exception as e:
        if attempt <= 3:
            print(f"    Error ({e}), retrying in 15s…")
            time.sleep(15)
            return fetch_json(url, attempt + 1)
        raise


def fetch_all_features():
    """Fetch all Zone 2 + 3 features from the combined EA collection, paginating."""
    print("\nFetching flood zone polygons (combined Zone 2 + 3)…")

    w, s, e, n = ENGLAND_BBOX
    bbox_str   = f"{w},{s},{e},{n}"
    features   = []
    offset     = 0
    page       = 0

    while True:
        url = (
            f"{EA_COLLECTION_BASE}"
            f"?bbox={bbox_str}"
            f"&limit={PAGE_SIZE}"
            f"&offset={offset}"
            f"&f=application/geo%2Bjson"
        )
        time.sleep(REQUEST_DELAY)
        data = fetch_json(url)

        batch = data.get("features", [])
        if not batch:
            break

        # Normalise the flood_zone property to integer (FZ2→2, FZ3→3)
        for feat in batch:
            raw = feat.get("properties", {}).get("flood_zone", "")
            feat["properties"]["flood_zone"] = 3 if "3" in str(raw) else 2

        features.extend(batch)
        page   += 1
        offset += len(batch)

        total_hint = data.get("numberMatched") or "?"
        print(f"  page {page:>3} — {len(features):>6,} features  (matched: {total_hint})")

        if len(batch) < PAGE_SIZE:
            break

    return features


def main():
    print("DC Site Finder — EA Flood Zone Fetch")
    print("=" * 45)
    t0 = time.time()

    all_features = fetch_all_features()
    print(f"\nTotal features: {len(all_features):,}")

    by_zone = {}
    for f in all_features:
        z = f["properties"].get("flood_zone", "?")
        by_zone[z] = by_zone.get(z, 0) + 1
    for z, n in sorted(by_zone.items()):
        print(f"  Zone {z}: {n:,} features")

    geojson = {"type": "FeatureCollection", "features": all_features}
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT)

    size_mb = os.path.getsize(OUTPUT) / 1e6
    print(f"\nSaved → {OUTPUT}  ({size_mb:.1f} MB)")
    print(f"Total time: {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
