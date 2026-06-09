#!/usr/bin/env python3
"""
Build data/markets.json by merging:
  - data/countries.geo.json   (country identities + capital + DC metro anchors)
  - data/raw/curated_overrides.json  (manually curated factor values per ISO-2)
  - data/raw/*.json           (one file per public dataset; populated by fetch_*.py
                               scripts in subsequent features)

Output schema for each country:
  {
    iso2, name, flag, region,
    anchors: { capital: {name,lon,lat}, dc_metro: {name,lon,lat} },
    factors: {
      <factor_id>: { value, year, source, url, note? },
      ...
    }
  }

Factors with no value for a country are omitted entirely. The UI renders that
as '— no data' per the missing-data convention in the plan.

Run from anywhere — paths are resolved relative to this script.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COUNTRIES_PATH = ROOT / "data" / "countries.geo.json"
RAW_DIR        = ROOT / "data" / "raw"
OUTPUT_PATH    = ROOT / "data" / "markets.json"

# Map of factor_id → which raw file it lives in. Curated overrides always win
# when both a fetch script output and a curated override exist for the same
# (country, factor) pair.
RAW_SOURCES: dict[str, str] = {
    "power_per_capita_kwh":      "ember_per_capita.json",        # F7
    "carbon_intensity_gco2_kwh": "ember_carbon_intensity.json",  # F14
    "power_cost_usd_kwh":        "eurostat_power_cost.json",     # F8 (EU/EFTA only)
    # rd_techs_per_million / tertiary_grad_pct: now curated-only, refreshed from the
    # 2026 'Inputs' spreadsheet (Our World in Data / UN). Dropped from the fetch merge
    # so the 8 markets absent from that dataset render 'no data' instead of mixing an
    # older World Bank vintage (rd_techs) or a different metric (tertiary attainment %
    # vs STEM-graduate share) into the same factor.
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if not COUNTRIES_PATH.exists():
        print(f"ERROR: {COUNTRIES_PATH} not found", file=sys.stderr)
        return 1

    countries_doc = load_json(COUNTRIES_PATH)
    curated = load_json(RAW_DIR / "curated_overrides.json") if (RAW_DIR / "curated_overrides.json").exists() else {}

    raw_data: dict[str, dict] = {}
    for factor_id, filename in RAW_SOURCES.items():
        fp = RAW_DIR / filename
        if fp.exists():
            raw_data[factor_id] = load_json(fp)
        else:
            print(f"  (skipping {factor_id}: {filename} not present yet)")

    markets = []
    factor_coverage: dict[str, int] = {}

    for c in countries_doc["countries"]:
        iso2 = c["iso2"]
        record = {
            "iso2":    iso2,
            "name":    c["name"],
            "flag":    c["flag"],
            "region":  c["region"],
            "anchors": c["anchors"],
            "factors": {},
        }

        # Curated overrides take priority. Skip the per-factor _meta block.
        for factor_id, factor_block in curated.items():
            if factor_id.startswith("_"):
                continue
            entry = factor_block.get(iso2)
            if entry is None:
                continue
            record["factors"][factor_id] = entry
            factor_coverage[factor_id] = factor_coverage.get(factor_id, 0) + 1

        # Raw fetched data fills in only where the curated override is missing.
        for factor_id, blob in raw_data.items():
            if factor_id in record["factors"]:
                continue
            entry = blob.get(iso2) if isinstance(blob, dict) else None
            if entry is None:
                continue
            record["factors"][factor_id] = entry
            factor_coverage[factor_id] = factor_coverage.get(factor_id, 0) + 1

        markets.append(record)

    out = {
        "_meta": {
            "generated_by": "scripts/build_markets_dataset.py",
            "country_count": len(markets),
            "factor_coverage": factor_coverage,
        },
        "markets": markets,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} — {len(markets)} countries")
    if factor_coverage:
        print("Factor coverage:")
        for factor_id, count in sorted(factor_coverage.items()):
            print(f"  {factor_id:30s} {count:3d} / {len(markets)} countries")
    else:
        print("No factor data populated yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
