"""
fetch_peeringdb.py

Fetches UK internet exchange points (IXPs) and carrier-neutral colocation
facilities from PeeringDB (https://www.peeringdb.com) and saves as
data/uk_peeringdb.json.

Used for fibre connectivity scoring in the composite scoring model.
Proximity to IXPs and carrier-neutral facilities is the primary indicator
of dark fibre access for data centres.

No API key required for public data.

Usage:
    python3 scripts/fetch_peeringdb.py
"""

import json, os, urllib.request, urllib.error, time

BASE_URL = "https://www.peeringdb.com/api"
OUTPUT   = "data/uk_peeringdb.json"

def fetch(path, attempt=1):
    url = f"{BASE_URL}/{path}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "dc-siting-tool/1.0 (DC land siting research)",
        "Accept":     "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and attempt <= 3:
            wait = 20 * attempt
            print(f"  Rate limited, waiting {wait}s…")
            time.sleep(wait)
            return fetch(path, attempt + 1)
        raise

def main():
    print("DC Site Finder — PeeringDB Fetch")
    print("=" * 40)

    print("Fetching UK internet exchanges (IXPs)…")
    ix_data = fetch("ix?country=GB")["data"]
    print(f"  {len(ix_data)} IXPs returned")

    print("Fetching UK carrier-neutral facilities…")
    fac_data = fetch("fac?country=GB")["data"]
    print(f"  {len(fac_data)} facilities returned")

    # Filter to those with valid coordinates
    exchanges = []
    for x in ix_data:
        lat = x.get("latitude")
        lng = x.get("longitude")
        if lat and lng:
            try:
                exchanges.append({
                    "id":       x["id"],
                    "name":     x.get("name", ""),
                    "city":     x.get("city", ""),
                    "lat":      float(lat),
                    "lng":      float(lng),
                    "networks": x.get("net_count", 0),
                })
            except (ValueError, TypeError):
                pass

    facilities = []
    for x in fac_data:
        lat = x.get("latitude")
        lng = x.get("longitude")
        if lat and lng:
            try:
                facilities.append({
                    "id":   x["id"],
                    "name": x.get("name", ""),
                    "city": x.get("city", ""),
                    "lat":  float(lat),
                    "lng":  float(lng),
                })
            except (ValueError, TypeError):
                pass

    print(f"\n  {len(exchanges)} exchanges with coordinates")
    print(f"  {len(facilities)} facilities with coordinates")

    result = {"exchanges": exchanges, "facilities": facilities}

    tmp = OUTPUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2)
    os.replace(tmp, OUTPUT)

    print(f"\nSaved → {OUTPUT}")

    top = sorted(exchanges, key=lambda x: x["networks"], reverse=True)[:8]
    print("\nTop exchanges by connected networks:")
    for ix in top:
        print(f"  {ix['name']:<40} {ix['city']:<15} {ix['networks']} networks")

if __name__ == "__main__":
    main()
