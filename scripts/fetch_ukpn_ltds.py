"""
fetch_ukpn_ltds.py

Downloads UKPN Long Term Development Statement (LTDS) Table 3a from the
UK Power Networks Open Data Portal.

Table 3a contains:
  - firm_capacity_mw  : usable capacity under N-1 security standards (not nameplate)
  - maximum_demand_24_25_mw : observed peak demand 2024/25
  - Headroom = firm_capacity_mw - maximum_demand_24_25_mw (what a connection engineer quotes)

This replaces the asset_limit_proxy calculation (transformer nameplate - max observed)
that currently overstates headroom for London substations like City Road and St Johns Wood.

Usage:
    # Option A: API key (register free at ukpowernetworks.opendatasoft.com)
    python3 scripts/fetch_ukpn_ltds.py --api-key YOUR_API_KEY

    # Option B: Manual download (no code required)
    # 1. Register at: https://ukpowernetworks.opendatasoft.com/
    # 2. Go to: https://ukpowernetworks.opendatasoft.com/explore/dataset/ltds-table-3a-load-data-observed/export/
    # 3. Export as CSV, save to: data/ukpn_ltds_table3a_raw.csv
    # 4. Run: python3 scripts/fetch_ukpn_ltds.py --from-file data/ukpn_ltds_table3a_raw.csv

Output:
    data/ukpn_ltds_headroom.json  — headroom by GSP name, ready for process_dno_headroom.py
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA_DIR  = Path("data")
API_BASE  = "https://ukpowernetworks.opendatasoft.com/api/explore/v2.1/catalog/datasets"
DATASET   = "ltds-table-3a-load-data-observed"
OUT_FILE  = DATA_DIR / "ukpn_ltds_headroom.json"

# Columns we need from the dataset
SELECT_COLS = ",".join([
    "gridsupplypoint",
    "substation",
    "season",
    "maximum_demand_24_25_mw",
    "firm_capacity_mw",
    "unutilised_capacity_percent",
    "licencearea",
    "functional_location",
])


def fetch_via_api(api_key: str) -> list[dict]:
    """Download all records from UKPN OpenDataSoft API using an API key."""
    records = []
    limit   = 100
    offset  = 0

    print(f"Fetching LTDS Table 3a via API...")
    while True:
        url = (
            f"{API_BASE}/{DATASET}/records"
            f"?limit={limit}&offset={offset}"
            f"&select={SELECT_COLS}"
            f"&apikey={api_key}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "dc-siting-tool/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
        except Exception as e:
            print(f"  API error at offset {offset}: {e}")
            sys.exit(1)

        batch = data.get("results", [])
        records.extend(batch)
        total = data.get("total_count", 0)
        print(f"  {len(records):>5} / {total} records")

        if len(batch) < limit or len(records) >= total:
            break
        offset += limit
        time.sleep(0.3)  # respect rate limit

    return records


def load_from_csv(filepath: str) -> list[dict]:
    """Load records from a manually downloaded CSV file."""
    records = []
    with open(filepath, encoding="utf-8-sig") as f:
        # OpenDataSoft CSVs use semicolon delimiter
        dialect = "excel" if "," in f.read(500) else None
        f.seek(0)
        if dialect:
            reader = csv.DictReader(f)
        else:
            reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            records.append(dict(row))
    print(f"Loaded {len(records):,} rows from {filepath}")
    return records


def normalise_gsp(name: str) -> str:
    """Normalise GSP name for matching."""
    return (name or "").lower().strip().replace("-", " ").replace("_", " ")


def process_records(records: list[dict]) -> dict:
    """
    Aggregate LTDS Table 3a records by Grid Supply Point.

    Strategy:
    - Use Winter season records (more conservative / binding constraint)
    - For each GSP, sum substation demands to get total GSP demand
    - GSP firm capacity is the max firm_capacity_mw across substations feeding it
      (the GSP transformer rating, not individual feeder ratings)
    - Headroom = firm_capacity_mw - total_demand_mw

    Output: dict keyed by normalised GSP name with headroom data.
    """
    # Separate winter records
    winter = [r for r in records
              if "winter" in str(r.get("season", "")).lower()]
    if not winter:
        print("WARNING: No winter records found — using all records")
        winter = records

    print(f"  Winter records: {len(winter):,} of {len(records):,} total")

    # Group by GSP
    by_gsp: dict[str, list[dict]] = defaultdict(list)
    for r in winter:
        gsp = str(r.get("gridsupplypoint") or r.get("gsp") or "").strip()
        if gsp:
            by_gsp[gsp].append(r)

    print(f"  Grid Supply Points found: {len(by_gsp)}")

    results = {}
    for gsp_name, rows in by_gsp.items():
        demands  = []
        caps     = []
        utilised = []
        for r in rows:
            try:
                d = float(r.get("maximum_demand_24_25_mw") or 0)
                demands.append(d)
            except (ValueError, TypeError):
                pass
            try:
                c = float(r.get("firm_capacity_mw") or 0)
                if c > 0:
                    caps.append(c)
            except (ValueError, TypeError):
                pass
            try:
                u = float(r.get("unutilised_capacity_percent") or 0)
                utilised.append(u)
            except (ValueError, TypeError):
                pass

        if not demands or not caps:
            continue

        total_demand   = sum(demands)
        # Firm capacity at GSP level = sum of firm capacities of constituent substations
        # (they share the GSP transformer, so total firm = sum of feeder firms)
        total_firm     = sum(caps)
        headroom_mw    = round(total_firm - total_demand, 1)
        utilisation    = round((total_demand / total_firm * 100) if total_firm > 0 else 0, 1)
        licence_area   = rows[0].get("licencearea", "")

        key = normalise_gsp(gsp_name)
        results[key] = {
            "gsp_raw_name":     gsp_name,
            "licence_area":     licence_area,
            "firm_capacity_mw": round(total_firm, 1),
            "peak_demand_mw":   round(total_demand, 1),
            "headroom_mw":      headroom_mw,
            "utilisation_pct":  utilisation,
            "substation_count": len(rows),
            "source":           "UKPN LTDS Table 3a (firm capacity, N-1 security standard)",
            "quality":          "direct_headroom",
            "dno":              "UKPN",
        }

    return results


def match_report(results: dict) -> None:
    """Show which of our known problematic London substations were matched."""
    targets = [
        "city road", "st johns wood", "barking", "new cross",
        "beddington", "west weybridge", "west ham", "wimbledon",
        "sundon", "walpole", "grain", "spalding",
    ]
    print("\nMatch check for previously asset_limit_proxy substations:")
    for t in targets:
        key = normalise_gsp(t)
        # Partial match
        match = next((v for k, v in results.items() if t in k), None)
        if match:
            h = match["headroom_mw"]
            f = match["firm_capacity_mw"]
            d = match["peak_demand_mw"]
            u = match["utilisation_pct"]
            flag = "✓ HEADROOM" if h > 0 else "⚠ CONSTRAINED"
            print(f"  {t:<20} firm={f:>7.1f} demand={d:>7.1f} headroom={h:>8.1f} MW  util={u:>5.1f}%  {flag}")
        else:
            print(f"  {t:<20} NOT MATCHED")


def main():
    parser = argparse.ArgumentParser(description="Fetch UKPN LTDS Table 3a demand headroom")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--api-key",   help="OpenDataSoft API key from ukpowernetworks.opendatasoft.com")
    group.add_argument("--from-file", help="Path to manually downloaded CSV file")
    args = parser.parse_args()

    if args.api_key:
        records = fetch_via_api(args.api_key)
    else:
        records = load_from_csv(args.from_file)

    print("\nProcessing records...")
    results = process_records(records)

    OUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved {len(results)} GSP headroom entries → {OUT_FILE}")
    match_report(results)
    print(f"\nNext step: run python3 scripts/process_dno_headroom.py to incorporate into substations.json")


if __name__ == "__main__":
    main()
