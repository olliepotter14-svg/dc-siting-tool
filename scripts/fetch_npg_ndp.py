"""
fetch_npg_ndp.py

Builds an LTDS-style committed-headroom dataset for Northern Powergrid GSPs
from the NPg NDP Demand Headroom dataset (year-by-year forecasts 2026-2050
across three DFES 2026 scenarios).

Source CSV: data/npg_ndp_demand_headroom.csv
  Fetched from https://northernpowergrid.opendatasoft.com/api/explore/v2.1/
              catalog/datasets/npg_ndp_demand_headroom/exports/csv
  Per-primary-substation, with demand_headroom_capacity_mw_<year> columns
  for 2026..2035, 2040, 2045, 2050.

Scenario chosen: "DFES 2026 - Holistic Transition" — middle-of-the-road
electrification path (vs Electric Engagement = fastest, Hydrogen Evolution
= H2-heavy). Matches the way UK system planners typically pick a single
central case for capacity planning.

Output schema matches the UKPN/NGED LTDS loaders so process_dno_headroom.py
consumes it via the same pattern:
  headroom_mw         = sum(demand_headroom_2026) across primaries  → "now"
  committed_headroom_mw = sum(demand_headroom_2029) across primaries → "post-pipeline"
  firm_capacity_mw    = headroom_2026 + assumed_peak_demand
                        (NDP gives headroom only; we cross-join firm from
                        the existing npg_gsp_heatmap.csv where possible)
  committed_util_pct  = (assumed_demand_2029 / firm) × 100
                        used as queue-pressure floor

Usage:
    python3 scripts/fetch_npg_ndp.py
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

DATA_DIR  = Path("data")
NDP_FILE  = DATA_DIR / "npg_ndp_demand_headroom.csv"
HEATMAP   = DATA_DIR / "npg_gsp_heatmap.csv"   # for firm capacity lookup
OUT_FILE  = DATA_DIR / "npg_ndp_committed.json"

SCENARIO  = "DFES 2026 - Holistic Transition"
HORIZON   = "2030"   # year used as the "committed pipeline" reference


def _f(s):
    if s is None: return None
    s = str(s).strip()
    if not s: return None
    try: return float(s)
    except ValueError: return None


def normalise(name: str) -> str:
    return " ".join((name or "").lower().strip().split())


def load_heatmap_firm() -> dict:
    """Map normalised GSP name → firm_cap (MVA) from npg_gsp_heatmap.csv."""
    firm = {}
    with open(HEATMAP, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row.get("typetable", "").upper() != "GSP":
                continue
            name = row.get("psp_name", "").strip()
            fc = _f(row.get("firm_cap"))
            if name and fc:
                firm[normalise(name)] = fc
    print(f"  Firm capacities from heatmap: {len(firm)}")
    return firm


def process() -> dict:
    firm_lookup = load_heatmap_firm()

    # Aggregate NDP rows by GSP group, scenario filter
    by_gsp: dict[str, list[dict]] = defaultdict(list)
    with open(NDP_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("scenario_name") != SCENARIO:
                continue
            gsp = (row.get("gsp_group") or "").strip()
            if gsp:
                by_gsp[gsp].append(row)

    print(f"  GSP groups (Holistic Transition): {len(by_gsp)}")

    results: dict[str, dict] = {}
    for gsp_name, rows in by_gsp.items():
        def sum_year(yr):
            return sum(_f(r.get(f"demand_headroom_capacity_mw_{yr}")) or 0 for r in rows)

        headroom_now   = sum_year("2026")
        headroom_horiz = sum_year(HORIZON)
        headroom_2035  = sum_year("2035")
        headroom_2050  = sum_year("2050")

        key = normalise(gsp_name)
        firm = firm_lookup.get(key)

        # Compute committed util only if we have firm capacity
        committed_util_pct = None
        utilisation_pct = None
        peak_demand_mw = None
        if firm and firm > 0:
            # demand_at_year ≈ firm − headroom_at_year
            peak_demand_mw      = round(firm - headroom_now, 1)
            committed_demand    = firm - headroom_horiz
            utilisation_pct     = round(max(0, peak_demand_mw) / firm * 100, 1)
            committed_util_pct  = round(max(0, committed_demand) / firm * 100, 1)

        results[key] = {
            "gsp_raw_name":          gsp_name,
            "scenario":              SCENARIO,
            "firm_capacity_mw":      round(firm, 1) if firm else None,
            "peak_demand_mw":        peak_demand_mw,
            "headroom_mw":           round(headroom_now,   1),
            "headroom_2030_mw":      round(headroom_horiz, 1),
            "headroom_2035_mw":      round(headroom_2035,  1),
            "headroom_2050_mw":      round(headroom_2050,  1),
            "utilisation_pct":       utilisation_pct,
            "committed_util_pct":    committed_util_pct,
            "committed_headroom_mw": round(headroom_horiz, 1),
            "primary_count":         len(rows),
            "source": (
                f"NPg NDP Demand Headroom dataset, {SCENARIO} scenario, "
                f"summed across {len(rows)} primary substations; "
                f"committed reference year = {HORIZON}"
            ),
            "quality":               "direct_headroom",
            "dno":                   "NPG",
        }

    return results


def main():
    print(f"Processing {NDP_FILE}...")
    results = process()
    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved → {OUT_FILE}")

    print("\nMatch check (selected NPg GSPs — current vs 2030 vs 2050 headroom):")
    print(f"  {'GSP':<22} {'firm':>6} {'hr_2026':>8} {'hr_2030':>8} {'hr_2050':>8} {'util_now':>9} {'util_30':>8}")
    print("  " + "-" * 80)
    for name in ["stella north","stella south","norton","keadby","drax",
                 "skelton grange","saltend north","bradford west","creyke beck",
                 "grimsby west","west melton  thorpe marsh"]:
        match = next((v for k, v in results.items() if k == name or name in k), None)
        if match:
            firm = match["firm_capacity_mw"] or 0
            print(f"  {match['gsp_raw_name'][:22]:<22} {firm:>6.0f}  "
                  f"{match['headroom_mw']:>7.0f}  {match['headroom_2030_mw']:>7.0f}  "
                  f"{match['headroom_2050_mw']:>7.0f}  "
                  f"{match.get('utilisation_pct','-') or '-':>8}  "
                  f"{match.get('committed_util_pct','-') or '-':>7}")


if __name__ == "__main__":
    main()
