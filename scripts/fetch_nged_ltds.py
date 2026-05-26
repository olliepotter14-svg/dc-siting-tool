"""
fetch_nged_ltds.py

Aggregates NGED LTDS Table 3a equivalent (primary-substation-level demand,
firm capacity, and 5-year forecast) into GSP-level headroom data, matching
the schema produced by fetch_ukpn_ltds.py.

Input:
    data/nged_gsp_technical_limits.csv  — 2,294 primary substations across
    NGED's four licence areas (EMIDS, SWALES, SWEST, WMIDS) with:
      - Current Year Max Demand (MW)
      - Forecast Year 1..5 (MW)
      - Firm Capacity of Substation (MW)

Output:
    data/nged_ltds_headroom.json  — keyed by normalised GSP name, schema
    mirrors ukpn_ltds_headroom.json so process_dno_headroom.py can
    consume it via the same load_ukpn_ltds()-shaped path.

Aggregation rule (matches UKPN approach in fetch_ukpn_ltds.py:181-197):
    For each GSP Group:
      total_firm        = sum(firm_capacity)
      total_demand      = sum(current_year_max_demand)
      total_forecast_5y = sum(forecast_year_5)
      headroom          = total_firm - total_demand
      committed_headroom = total_firm - total_forecast_5y
      committed_util_%  = total_forecast_5y / total_firm × 100

The committed-utilisation figure becomes the demand-side queue-pressure
floor for NGED substations (same mechanism that fixed City Road, etc.
for UKPN — see process_dno_headroom.py:680-688).

Usage:
    python3 scripts/fetch_nged_ltds.py
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

DATA_DIR  = Path("data")
INPUT     = DATA_DIR / "nged_gsp_technical_limits.csv"
OUT_FILE  = DATA_DIR / "nged_ltds_headroom.json"


def _f(s: str):
    """Parse float, return None for blank / '-' / non-numeric."""
    if s is None:
        return None
    s = s.strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalise_gsp(name: str) -> str:
    """
    Normalise NGED GSP name for matching against our substations file.

    NGED names look like "Berkswell 132kV", "Grange 66", "Cardiff East / Aberthaw".
    Strip voltage suffix, lowercase, collapse whitespace. Split on '/' is
    handled by the loader (emits one entry per side of the slash).
    """
    n = (name or "").lower().strip()
    # Strip voltage suffixes
    for suf in (" 132kv", " 66kv", " 33kv", " 132", " 66", " 33"):
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    return " ".join(n.split())


def process(input_path: Path) -> dict:
    """Aggregate primary-substation rows up to GSP level."""
    by_gsp: dict[str, list[dict]] = defaultdict(list)
    with open(input_path, encoding="utf-8-sig") as f:
        # NGED's header has a stray tab on the first column ('Licence\t').
        # csv.DictReader handles it fine; downstream we use other columns.
        for row in csv.DictReader(f):
            gsp = (row.get("GSP Group") or "").strip()
            if gsp:
                by_gsp[gsp].append(row)

    print(f"  GSP Groups found: {len(by_gsp)}")

    results: dict[str, dict] = {}
    skipped: list[str] = []

    for gsp_name, rows in by_gsp.items():
        firm_vals    = []
        demand_vals  = []
        forecast_vals = []
        rows_kept   = 0

        for r in rows:
            firm = _f(r.get("Firm Capacity of Substation"))
            dem  = _f(r.get("Current Year Max Demand"))
            fy5  = _f(r.get("Forecast Year 5"))
            # Skip rows where firm or demand is missing — can't form a
            # utilisation figure from them. Forecast is allowed to be
            # None (we just won't contribute to committed util for that row).
            if firm is None or dem is None:
                continue
            firm_vals.append(firm)
            demand_vals.append(dem)
            forecast_vals.append(fy5 if fy5 is not None else dem)
            rows_kept += 1

        if not firm_vals or sum(firm_vals) <= 0:
            skipped.append(gsp_name)
            continue

        total_firm     = sum(firm_vals)
        total_demand   = sum(demand_vals)
        total_forecast = sum(forecast_vals)

        headroom_mw           = round(total_firm - total_demand, 1)
        utilisation_pct       = round((total_demand   / total_firm) * 100, 1)
        committed_util_pct    = round((total_forecast / total_firm) * 100, 1)
        committed_headroom_mw = round(total_firm - total_forecast, 1)

        # Licence area (just for traceability — take from any row)
        licence = ""
        for k in rows[0].keys():
            if k.strip().lower() == "licence":
                licence = (rows[0].get(k) or "").strip()
                break

        # Emit one entry per slash-separated GSP name so single-name lookups
        # (e.g. "Iron Acton" from "Iron Acton 132kV", "Cardiff East" from
        # "Cardiff East / Aberthaw") still match. The aggregate is the same
        # across each alias.
        bare = normalise_gsp(gsp_name)
        aliases = [normalise_gsp(part) for part in bare.split("/")]
        # Also include the full bare name without slashes
        aliases.append(bare.replace(" / ", " ").replace("/", " "))
        # De-dup, drop empties
        aliases = sorted({a for a in aliases if a})

        payload = {
            "gsp_raw_name":          gsp_name,
            "licence_area":          licence,
            "firm_capacity_mw":      round(total_firm, 1),
            "peak_demand_mw":        round(total_demand, 1),
            "headroom_mw":           headroom_mw,
            "utilisation_pct":       utilisation_pct,
            "committed_util_pct":    committed_util_pct,
            "committed_headroom_mw": committed_headroom_mw,
            "substation_count":      rows_kept,
            "source":                "NGED LTDS Table 3a (firm capacity − current peak demand; 5-yr forecast as committed pipeline)",
            "quality":               "direct_headroom",
            "dno":                   "NGED",
        }
        for key in aliases:
            results[key] = payload

    if skipped:
        print(f"  Skipped (no usable firm/demand rows): {len(skipped)}")
        for s in skipped:
            print(f"    {s}")

    return results


def match_report(results: dict) -> None:
    """Show coverage for known NGED-served substations from our backlog."""
    targets = [
        "grendon",     # HIGH priority fabricated — 940 parcels
        "coventry",
        "bushbury",
        "iron acton",
        "feckenham",
        "nechells",
        "staythorpe",  # 1,799% queue pressure currently — see if LTDS confirms saturation
        "walpole",
        "rugeley",
        "seabank",     # current proxy to iron acton
    ]
    print("\nMatch check against known NGED-area substations:")
    for t in targets:
        match = next((v for k, v in results.items() if t == k or t in k), None)
        if match:
            h = match["headroom_mw"]
            u = match["utilisation_pct"]
            cu = match["committed_util_pct"]
            ch = match["committed_headroom_mw"]
            flag = "HEADROOM ok" if h > 0 else "CONSTRAINED"
            print(f"  {t:<15} firm={match['firm_capacity_mw']:>6.0f}  "
                  f"hr_now={h:>7.1f} MW  util_now={u:>5.1f}%  "
                  f"util_29={cu:>5.1f}%  hr_29={ch:>7.1f} MW  {flag}")
        else:
            print(f"  {t:<15} NOT MATCHED")


def main():
    print(f"Processing {INPUT}...")
    results = process(INPUT)
    print(f"\n  GSP entries (incl. slash aliases): {len(results)}")

    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved → {OUT_FILE}")

    match_report(results)
    print(f"\nNext: run python3 scripts/process_dno_headroom.py to consume into substations.json")


if __name__ == "__main__":
    main()
