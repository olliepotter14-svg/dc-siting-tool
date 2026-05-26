"""
fetch_ea_register.py

Parses NESO's Existing Agreements (EA) Register — the post-Connections-Reform
"Gate 2" national register of all consented connection projects across the
UK transmission network.

Source: data/neso_ea_register.xlsx
  Manually downloaded from NESO connections portal. 3,506 projects,
  ~494 GW committed capacity, 1,019 unique connection points.
  Columns: Project Name, Associated Installed Capacity (MW),
           Existing Connection Date, Existing Connection Point,
           Expressed an interest in Gate 1 agreement with reservation,
           Technology Type.

Aggregation: per normalised connection point, sum MW with subtotals by
technology type. Demand projects are isolated (Transmission Connected
Demand) — this is the demand-side queue we've been missing nationally
outside of UKPN/NGED LTDS coverage.

Output:
  data/ea_register_by_sub.json — keyed by normalised connection-point
  name, with totals per substation:
    total_mw, project_count, earliest_date, latest_date,
    demand_mw, generation_mw, battery_mw, by_type{},
    raw_names[]

Usage:
    python3 scripts/fetch_ea_register.py
"""

import json
import re
from collections import defaultdict, Counter
from pathlib import Path

import openpyxl

DATA_DIR = Path("data")
XLSX     = DATA_DIR / "neso_ea_register.xlsx"
OUT_FILE = DATA_DIR / "ea_register_by_sub.json"
SHEET    = "Sheet1"
DATA_START_ROW = 6

# Tech-type buckets for subtotals
DEMAND_TYPES = {"transmission connected demand"}
GEN_TYPES    = {"solar", "onshore wind", "offshore wind", "unabated gas",
                "low carbon dispatchable power", "nuclear", "tidal",
                "run-of-river hydro", "interconnector", "unaligned"}
STORAGE_TYPES = {"battery", "ldes", "liquid air energy storage (laes)"}


def norm_connection_point(s: str) -> str:
    """
    Normalise a connection-point name from the EA register so it can be
    matched against our substation names. The register has very verbose
    naming: 'GRENDON 132kV S STN', 'Indian Queens S.G.P.', 'Bramley
    275/132kV Substation', etc.

    Strategy: strip voltage descriptors, substation suffixes, GSP markers,
    punctuation; collapse whitespace.
    """
    n = (s or "").lower().strip()
    # Strip multi-voltage suffix patterns like " 275/132/33kv"
    n = re.sub(r"\s+\d+(?:\s*/\s*\d+)*\s*k?v\b", " ", n)
    # Strip well-known suffixes (longest first)
    for suf in [
        "windfarm 132 33kv", "windfarm 132 11kv", "windfarm 33kv", "windfarm 132kv",
        " s.g.p.", " s.s.p.", " sgp", " ssp", " gsp",
        " 132kv s stn", " 275kv s stn", " 400kv s stn",
        " 132kv substation", " 275kv substation", " 400kv substation",
        " substation", " s stn",
        " west", " east", " north", " south", " main",
        " 132kv", " 275kv", " 400kv", " 33kv", " 11kv", " 66kv", " 132", " 275", " 400",
    ]:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    # Strip leading "the "
    if n.startswith("the "):
        n = n[4:]
    # Strip punctuation except numbers/letters/space, collapse ws
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = " ".join(n.split())
    return n


def categorise(tech_type: str) -> str:
    t = (tech_type or "").lower().strip()
    if t in DEMAND_TYPES:   return "demand"
    if t in STORAGE_TYPES:  return "battery"
    if t in GEN_TYPES:      return "generation"
    return "other"


def main():
    print(f"Parsing {XLSX}...")
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb[SHEET]

    agg: dict = defaultdict(lambda: {
        "total_mw":      0.0,
        "demand_mw":     0.0,
        "generation_mw": 0.0,
        "battery_mw":    0.0,
        "other_mw":      0.0,
        "project_count": 0,
        "by_type":       Counter(),
        "earliest":      None,
        "latest":        None,
        "raw_names":     set(),
    })

    skipped = 0
    for row in ws.iter_rows(min_row=DATA_START_ROW, values_only=True):
        if not row or len(row) < 6:
            continue
        project, mw_raw, date, cp_raw, gate1, tech = row[:6]
        if not cp_raw:
            skipped += 1
            continue
        try:
            mw = float(mw_raw or 0)
        except (ValueError, TypeError):
            mw = 0.0

        key = norm_connection_point(str(cp_raw))
        if not key:
            skipped += 1
            continue

        bucket = categorise(str(tech or ""))
        a = agg[key]
        a["total_mw"]      += mw
        a[f"{bucket}_mw"]  += mw
        a["project_count"] += 1
        a["by_type"][str(tech or "Unknown")] += mw
        a["raw_names"].add(str(cp_raw))
        if date:
            if a["earliest"] is None or date < a["earliest"]:
                a["earliest"] = date
            if a["latest"] is None or date > a["latest"]:
                a["latest"] = date

    # Serialise to JSON-safe
    out = {}
    for key, a in agg.items():
        out[key] = {
            "total_mw":      round(a["total_mw"],      1),
            "demand_mw":     round(a["demand_mw"],     1),
            "generation_mw": round(a["generation_mw"], 1),
            "battery_mw":    round(a["battery_mw"],    1),
            "other_mw":      round(a["other_mw"],      1),
            "project_count": a["project_count"],
            "by_type":       {k: round(v, 1) for k, v in a["by_type"].most_common()},
            "earliest":      a["earliest"].isoformat() if a["earliest"] else None,
            "latest":        a["latest"].isoformat()   if a["latest"]   else None,
            "raw_names":     sorted(a["raw_names"]),
        }

    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print(f"  Connection points aggregated: {len(out)} (skipped {skipped} rows)")
    print(f"  Saved → {OUT_FILE}")

    # ── Top-N reports ────────────────────────────────────────────────
    print("\nTop 15 connection points by TOTAL committed MW:")
    by_total = sorted(out.items(), key=lambda x: -x[1]["total_mw"])
    for k, v in by_total[:15]:
        print(f"  {k:<30} {v['total_mw']:>7.0f} MW  ({v['project_count']:>2} projects, "
              f"dem={v['demand_mw']:>5.0f}, gen={v['generation_mw']:>5.0f}, "
              f"bess={v['battery_mw']:>5.0f})")

    print("\nTop 15 by DEMAND-side committed MW (the new signal):")
    by_demand = sorted([(k,v) for k,v in out.items() if v['demand_mw']>0],
                       key=lambda x: -x[1]["demand_mw"])
    for k, v in by_demand[:15]:
        print(f"  {k:<30} {v['demand_mw']:>7.0f} MW demand  "
              f"({v['project_count']} projects total)")


if __name__ == "__main__":
    main()
