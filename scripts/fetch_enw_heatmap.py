"""
fetch_enw_heatmap.py

Parses the ENW Heatmap Tool Excel workbook to extract per-GSP demand
headroom — replacing our previous PRY-aggregate coordinate-match proxy
with real published numbers.

Source: data/enw_heatmap.xlsx
  Fetched from https://www.enwl.co.uk/globalassets/get-connected/
              network-information/heat-maps/downloads/heatmaps/
              heatmap-tool---15may-2026.xlsx

Sheet "6) GSP Demand Headroom Data" has columns:
  Substation, GSP, Voltage (kV), GSP Group, Easting, Northing,
  Demand Headroom (MVA) Firm (non inverter based),
  Demand Headroom (MVA) Non Firm (inverter based),
  Battery Storage Headroom N-0

ENW does not publish a forecast horizon in the same sheet, so this is
"current headroom only" — better than the PRY aggregate proxy we were
using but no demand-side queue floor (unlike NGED/UKPN/NPg/SSEN).

Output:
    data/enw_heatmap_headroom.json  — per-GSP firm demand headroom,
    schema-compatible with the other LTDS-style loaders.

Usage:
    python3 scripts/fetch_enw_heatmap.py
"""

import json
from pathlib import Path

import openpyxl

DATA_DIR = Path("data")
XLSX     = DATA_DIR / "enw_heatmap.xlsx"
OUT_FILE = DATA_DIR / "enw_heatmap_headroom.json"
SHEET    = "6) GSP Demand Headroom Data"


def _f(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None


def normalise(name: str) -> str:
    n = (name or "").lower().strip()
    # Strip "(132)", "GSP", trailing voltage
    for suf in (" gsp", " (132)", " (275)", " (400)", " 132", " 275", " 400"):
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    return " ".join(n.split())


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb[SHEET]

    # Header at row 5/6 (merged). Data starts row 7.
    DATA_START = 7
    # Columns (1-indexed): B=Substation, C=GSP, D=Voltage, E=GSP Group,
    # F=Easting, G=Northing, H=Firm headroom, I=Non-firm headroom,
    # J=Battery storage headroom N-0
    results: dict[str, dict] = {}
    for row in ws.iter_rows(min_row=DATA_START, values_only=True):
        sub      = row[1]
        gsp_name = row[2]
        voltage  = row[3]
        gsp_grp  = row[4]
        easting  = row[5]
        northing = row[6]
        firm_hr  = _f(row[7])
        nonfirm_hr = _f(row[8])
        bess_hr  = _f(row[9])

        if not sub or firm_hr is None:
            continue

        # Use the firm (non-inverter) figure as our demand headroom.
        # This is conservative — non-firm includes inverter-based connections
        # that may have curtailment risk.
        key = normalise(str(sub))
        # Also store under the GSP Group name for cross-matching
        alt_key = normalise(str(gsp_grp or gsp_name or ""))

        payload = {
            "gsp_raw_name":          str(sub),
            "gsp_group":             str(gsp_grp) if gsp_grp else None,
            "voltage_kv":            voltage,
            "easting":               easting,
            "northing":              northing,
            "headroom_mw":           round(firm_hr, 1),
            "headroom_nonfirm_mw":   round(nonfirm_hr, 1) if nonfirm_hr is not None else None,
            "bess_headroom_mw":      round(bess_hr, 1) if bess_hr is not None else None,
            "source":                "ENW Heatmap Tool (May 2026) — GSP Demand Headroom sheet, firm (non-inverter)",
            "quality":               "direct_headroom",
            "dno":                   "ENW",
            "capacity_mw":           None,   # not separately published
        }
        results[key] = payload
        if alt_key and alt_key != key:
            results[alt_key] = payload

    print(f"  ENW GSPs: {sum(1 for v in results.values() if v) // 1} entries (incl. aliases)")
    unique = {id(v): v for v in results.values()}
    print(f"  Unique payloads: {len(unique)}")

    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved → {OUT_FILE}")

    print("\nENW GSP demand headroom (firm, non-inverter):")
    seen = set()
    for k, v in results.items():
        if id(v) in seen: continue
        seen.add(id(v))
        hr = v["headroom_mw"]
        flag = "OVERLOADED" if hr < 0 else ("CONSTRAINED" if hr < 50 else "ok")
        print(f"  {v['gsp_raw_name'][:35]:<35}  firm_hr={hr:>8.1f} MVA  {flag}")


if __name__ == "__main__":
    main()
