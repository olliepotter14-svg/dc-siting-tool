#!/usr/bin/env python3
"""Fetch non-household electricity prices from Eurostat NRG_PC_205.

Pulls the most-recent half-year, band IE (consumption 20,000 - 69,999 MWh —
the band that best approximates hyperscale DC load), EUR/kWh excluding taxes.

Output: data/raw/eurostat_power_cost.json — keyed by ISO-2, schema matches
the rest of data/raw/*.json so build_markets_dataset.py picks it up.

Values are converted EUR → USD using a fixed rate documented in the note,
so the result is reproducible and the conversion is auditable. To refresh,
re-run this script — no auth needed.
"""

from __future__ import annotations
import json, sys, urllib.request
from pathlib import Path

API = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/NRG_PC_205"
    "?format=JSON&time={time}&nrg_cons={band}&currency=EUR&unit=KWH&tax=X_TAX"
)
TIME = "2024-S2"           # latest published half-year
BAND = "MWH20000-69999"    # band IE — large industrial
EUR_USD_RATE = 1.08        # ECB reference rate 2024 average; documented in note

HERE = Path(__file__).resolve().parent
OUT  = HERE.parent / "data" / "raw" / "eurostat_power_cost.json"

# UK isn't in Eurostat post-Brexit; map remaining ISO-2 codes we use to
# Eurostat's geo codes (mostly identical, but EL=Greece, UK=United Kingdom).
EUROSTAT_TO_ISO2 = {"EL": "GR", "UK": "GB"}


def main() -> int:
    url = API.format(time=TIME, band=BAND)
    print(f"GET {url}")
    with urllib.request.urlopen(url, timeout=30) as r:
        doc = json.load(r)

    if "error" in doc:
        print("API error:", doc["error"], file=sys.stderr)
        return 1

    geo_index = doc["dimension"]["geo"]["category"]["index"]
    geo_label = doc["dimension"]["geo"]["category"]["label"]
    values    = doc["value"]

    out: dict[str, dict] = {}
    for geo, idx in geo_index.items():
        v = values.get(str(idx))
        if v is None:
            continue
        usd_per_kwh = round(v * EUR_USD_RATE, 4)
        iso2 = EUROSTAT_TO_ISO2.get(geo, geo)
        out[iso2] = {
            "value": usd_per_kwh,
            "year": 2024,
            "source": f"Eurostat NRG_PC_205, band IE (20,000–69,999 MWh) — {TIME}, EUR×{EUR_USD_RATE}",
            "url": f"https://ec.europa.eu/eurostat/databrowser/view/nrg_pc_205/default/table?lang=en",
            "evidence_url": url,
            "confidence": "verified",
            "note": f"Auto-fetched from Eurostat API; {v} EUR/kWh × {EUR_USD_RATE} USD/EUR = {usd_per_kwh}.",
        }
        print(f"  {iso2:>3}  {geo_label.get(geo, geo):<30}  {v} EUR/kWh -> ${usd_per_kwh}/kWh")

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(HERE.parent)} — {len(out)} countries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
