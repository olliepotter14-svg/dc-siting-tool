"""
fetch_ssen_ltds.py

Builds an LTDS-style demand-headroom + committed-pipeline dataset for SSEN
substations from the already-on-disk SSEN Headroom Dashboard CSV.

SSEN publishes columns we weren't using:
  - Contracted Demand Excl BESS (MVA)  — committed demand pipeline
  - Contracted BESS Demand (MVA)       — committed battery storage demand
  - Substation Demand RAG Status       — SSEN's own constraint status

Computed (mirrors UKPN/NGED LTDS schema so process_dno_headroom.py consumes
it the same way):
  firm_capacity_mw      = (n−1) × per-transformer nameplate rating
  peak_demand_mw        = Maximum Observed Gross Demand (MVA)
  headroom_mw           = firm − peak_demand
  committed_demand_mw   = peak + contracted (excl BESS) + contracted BESS
  committed_headroom_mw = firm − committed_demand_mw
  committed_util_pct    = committed_demand_mw / firm × 100  (used as queue floor)

The committed-utilisation figure becomes the demand-side queue-pressure
floor for SSEN substations — the same mechanism as UKPN LTDS and NGED LTDS.

Usage:
    python3 scripts/fetch_ssen_ltds.py
"""

import csv
import json
import re
from pathlib import Path

DATA_DIR = Path("data")
INPUT    = DATA_DIR / "ssen_headroom_dashboard.csv"
OUT_FILE = DATA_DIR / "ssen_ltds_headroom.json"


def _f(s):
    """Parse float, return None for blank / 'N/A' / '-' / non-numeric."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.upper() in ("N/A", "NA", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_nameplate(nm: str):
    """'3 x 120MVA' → 360.0 (total nameplate, not firm)"""
    nums = re.findall(r"(\d+)\s*[Xx]\s*(\d+(?:\.\d+)?)\s*MVA", nm or "", re.I)
    if not nums:
        return None, 0
    total = sum(int(n) * float(m) for n, m in nums)
    n_tx  = int(nums[0][0])
    return total, n_tx


def firm_capacity(nameplate_mva: float, n_tx: int):
    """N-1 firm = (n-1) × per-transformer rating."""
    if not nameplate_mva or n_tx <= 0:
        return None
    if n_tx == 1:
        return nameplate_mva
    per_tx = nameplate_mva / n_tx
    return per_tx * (n_tx - 1)


def normalise(name: str) -> str:
    n = (name or "").lower().strip()
    if n.endswith(" gsp"):
        n = n[:-4].strip()
    return " ".join(n.split())


def process(input_path: Path) -> dict:
    results: dict[str, dict] = {}
    skipped = 0

    with open(input_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("Substation Type", "").strip() != "GSP":
                continue

            name      = row.get("Substation", "").strip()
            licence   = row.get("Map / License Area", "").strip()
            nameplate_str = row.get("Transformer Nameplate Ratings", "")
            peak_dem  = _f(row.get("Maximum Observed Gross Demand (MVA)"))
            contracted = _f(row.get("Contracted Demand Excl BESS (MVA)"))
            contracted_bess = _f(row.get("Contracted BESS Demand (MVA)"))
            rag       = row.get("Substation Demand RAG Status", "").strip()
            constraint = row.get("Demand Constraint", "").strip()
            tech_agreed = row.get("Technical Limits Agreed at GSP", "").strip()

            nameplate, n_tx = parse_nameplate(nameplate_str)
            firm = firm_capacity(nameplate, n_tx)

            # Need at least firm capacity + peak demand to form a headroom view
            if firm is None or peak_dem is None:
                skipped += 1
                continue

            contracted     = contracted or 0.0
            contracted_bess = contracted_bess or 0.0
            committed_demand = peak_dem + contracted + contracted_bess

            headroom_mw          = round(firm - peak_dem, 1)
            committed_headroom   = round(firm - committed_demand, 1)
            utilisation_pct      = round((peak_dem / firm) * 100, 1) if firm > 0 else 0
            committed_util_pct   = round((committed_demand / firm) * 100, 1) if firm > 0 else 0

            shared = "shared" in (nameplate_str or "").lower()

            key = normalise(name)
            results[key] = {
                "gsp_raw_name":          name,
                "licence_area":          licence,
                "firm_capacity_mw":      round(firm, 1),
                "peak_demand_mw":        round(peak_dem, 1),
                "contracted_demand_mw":  round(contracted, 1),
                "contracted_bess_mw":    round(contracted_bess, 1),
                "headroom_mw":           headroom_mw,
                "utilisation_pct":       utilisation_pct,
                "committed_util_pct":    committed_util_pct,
                "committed_headroom_mw": committed_headroom,
                "ssen_rag":              rag,
                "demand_constraint":     constraint,
                "tech_limits_agreed":    tech_agreed,
                "source": (
                    "SSEN Headroom Dashboard: firm capacity (N-1 from nameplate) − peak demand; "
                    "committed pipeline = peak + contracted demand (excl & incl BESS)"
                    + (" — SHARED SITE" if shared else "")
                ),
                "quality":               "direct_headroom",
                "dno":                   "SSEN",
            }

    if skipped:
        print(f"  Skipped (missing firm or peak demand): {skipped}")
    return results


def match_report(results: dict):
    """Show coverage for known SSEN-served substations."""
    targets = [
        "amersham", "bramley", "didcot", "culham",          # SEPD Thames Valley
        "fleet", "lovedean", "marchwood", "nursling",        # SEPD South Coast
        "beauly", "blackhillock", "dounreay",                # SHEPD Highlands
        "torness", "kilmarnock south",                       # cross-border edge cases
    ]
    print("\nMatch check against known SSEN-area substations:")
    for t in targets:
        match = next((v for k, v in results.items() if t == k or t in k), None)
        if match:
            h = match["headroom_mw"]
            u = match["utilisation_pct"]
            cu = match["committed_util_pct"]
            ch = match["committed_headroom_mw"]
            rag = match["ssen_rag"]
            print(f"  {t:<18} firm={match['firm_capacity_mw']:>6.0f}  "
                  f"hr_now={h:>7.1f}  util_now={u:>5.1f}%  "
                  f"committed={cu:>5.1f}%  hr_committed={ch:>7.1f}  RAG={rag}")
        else:
            print(f"  {t:<18} NOT MATCHED")


def main():
    print(f"Processing {INPUT}...")
    results = process(INPUT)
    print(f"  GSP entries: {len(results)}")

    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Saved → {OUT_FILE}")

    match_report(results)


if __name__ == "__main__":
    main()
