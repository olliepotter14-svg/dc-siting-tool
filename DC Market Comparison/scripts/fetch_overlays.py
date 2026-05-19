#!/usr/bin/env python3
"""
Fetch the three EMEA map overlay datasets:

  - data/overlay_ixps.geojson      PeeringDB IXPs (fibre connectivity proxy)  — F20
  - data/overlay_grid.geojson      OSM HV transmission lines (>=220kV)        — F21
  - data/overlay_dc_sites.geojson  PeeringDB facilities (operational DC sites) — F22

All three are written as compact GeoJSON FeatureCollections ready for
direct `addSource` in markets.js. Re-run any time to refresh; the script
is idempotent.

Sources:
  - PeeringDB API: https://www.peeringdb.com/apidocs/
  - OSM Overpass: https://overpass-api.de/

The OSM grid query can take 60-120s depending on Overpass load.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# EMEA country ISO-2 set (matches countries.geo.json).
EMEA_ISO2 = {
    "GB","IE","FR","DE","NL","BE","LU","CH","AT",
    "SE","NO","DK","FI","IS",
    "ES","PT","IT","GR","MT","CY",
    "PL","CZ","SK","HU","RO","BG","HR","SI","RS","EE","LV","LT",
    "AE","SA","QA","BH","KW","OM","IL","TR","JO",
    "ZA","EG","MA","NG","KE","TN","DZ",
}

REQ_HEADERS = {"User-Agent": "dc-market-comparison/0.1 (research)"}


def http_get_json(url: str, timeout: int = 60) -> dict:
    print(f"  → {url[:120]}{'…' if len(url) > 120 else ''}")
    req = urllib.request.Request(url, headers=REQ_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ──────────────────────────────────────────────────────────────────
# PeeringDB — IXPs and facilities
# ──────────────────────────────────────────────────────────────────

def fetch_peeringdb_ixps() -> dict:
    """All IXs whose country is in EMEA. PeeringDB IXs have lat/lng on their
    primary facility but the IX endpoint itself doesn't carry coords — we use
    the facility coords via fac_set. To keep this single-call lightweight we
    instead query the 'ixlan' or fall back to city-level approx."""
    # Simpler: fetch IX list (has city, country); join with facilities for coords.
    print("Fetching PeeringDB IXPs…")
    ixs = http_get_json("https://www.peeringdb.com/api/ix?depth=0&limit=2000")["data"]
    facs = http_get_json("https://www.peeringdb.com/api/fac?depth=0&limit=20000")["data"]
    # Build country -> first-fac-with-coords lookup as a fallback positioning.
    fac_by_country: dict[str, list] = {}
    for f in facs:
        if f.get("country") in EMEA_ISO2 and f.get("latitude") and f.get("longitude"):
            fac_by_country.setdefault(f["country"], []).append(f)

    features = []
    for ix in ixs:
        cc = ix.get("country")
        if cc not in EMEA_ISO2:
            continue
        # PeeringDB IX records have city but not lat/lng directly. Use the
        # first facility in the same country as an approximate marker.
        candidates = fac_by_country.get(cc, [])
        if not candidates:
            continue
        # Prefer fac with the same city name, else fall back to first
        city = (ix.get("city") or "").strip().lower()
        chosen = next((f for f in candidates if (f.get("city") or "").strip().lower() == city), candidates[0])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(chosen["longitude"]), float(chosen["latitude"])]},
            "properties": {
                "name":     ix.get("name"),
                "city":     ix.get("city"),
                "country":  cc,
                "members":  ix.get("net_count"),
                "url":      f"https://www.peeringdb.com/ix/{ix.get('id')}",
            },
        })
    return {"type": "FeatureCollection", "features": features}


def fetch_peeringdb_facilities() -> dict:
    """All carrier-neutral DC facilities in PeeringDB located in EMEA."""
    print("Fetching PeeringDB facilities…")
    facs = http_get_json("https://www.peeringdb.com/api/fac?depth=0&limit=20000")["data"]
    features = []
    for f in facs:
        cc = f.get("country")
        if cc not in EMEA_ISO2:
            continue
        if not (f.get("latitude") and f.get("longitude")):
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(f["longitude"]), float(f["latitude"])]},
            "properties": {
                "name":     f.get("name"),
                "city":     f.get("city"),
                "country":  cc,
                "status":   "operational",   # PeeringDB lists existing facilities
                "url":      f"https://www.peeringdb.com/fac/{f.get('id')}",
            },
        })
    return {"type": "FeatureCollection", "features": features}


# ──────────────────────────────────────────────────────────────────
# OSM Overpass — high-voltage transmission
# ──────────────────────────────────────────────────────────────────

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Bounding box for EMEA (lon_min, lat_min, lon_max, lat_max). Generous so we
# pick up the Nordics and South Africa. Overpass clamps internally.
EMEA_BBOX = "-30,-40,70,72"

# Narrowed to >=380kV to keep the response under Overpass's payload limits
# for the EMEA bbox. Still captures Europe's primary transmission backbone.
GRID_QUERY = f"""
[out:json][timeout:180];
(
  way["power"="line"]["voltage"~"^(380000|400000|500000|750000)$"]({EMEA_BBOX});
);
out geom;
"""


def fetch_osm_grid() -> dict:
    """Pulls >=220kV transmission line geometries from OSM Overpass."""
    print("Fetching OSM HV transmission grid (this can take 60-120s)…")
    body = urllib.parse.urlencode({"data": GRID_QUERY}).encode("utf-8")
    last_err = None
    for url in OVERPASS_URLS:
        try:
            print(f"  → {url}")
            req = urllib.request.Request(url, data=body, headers=REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=150) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            print(f"     failed: {e}")
            last_err = e
            time.sleep(2)
    else:
        raise RuntimeError(f"All Overpass endpoints failed: {last_err}")

    features = []
    for el in doc.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        coords = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "voltage": el.get("tags", {}).get("voltage"),
                "operator": el.get("tags", {}).get("operator"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


# ──────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────

def write_geojson(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")
    n = len(doc.get("features", []))
    print(f"  wrote {path.name} — {n} features")


def main() -> int:
    targets = sys.argv[1:] or ["ixps", "dc_sites", "grid"]

    if "ixps" in targets:
        try:
            doc = fetch_peeringdb_ixps()
            write_geojson(DATA_DIR / "overlay_ixps.geojson", doc)
        except Exception as e:
            print(f"  IXPs failed: {e}", file=sys.stderr)

    if "dc_sites" in targets:
        try:
            doc = fetch_peeringdb_facilities()
            write_geojson(DATA_DIR / "overlay_dc_sites.geojson", doc)
        except Exception as e:
            print(f"  DC sites failed: {e}", file=sys.stderr)

    if "grid" in targets:
        try:
            doc = fetch_osm_grid()
            write_geojson(DATA_DIR / "overlay_grid.geojson", doc)
        except Exception as e:
            print(f"  Grid failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
