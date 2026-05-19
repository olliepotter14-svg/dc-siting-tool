#!/usr/bin/env python3
"""
Fetch per-country electricity statistics from Our World in Data (Ember-derived).

Writes two files into data/raw/:
  - ember_per_capita.json       (F7 — kWh / capita / year, most recent year)
  - ember_carbon_intensity.json (F14 — gCO2 / kWh, most recent year)

Both keyed by ISO-2, with {value, year, source, url, note?}.

Data source: Our World in Data — they publish a curated Ember-sourced CSV
with stable URLs and machine-friendly schema. Run any time to refresh:

    python3 scripts/fetch_ember.py

Then re-run scripts/build_markets_dataset.py to merge into markets.json.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE.parent / "data" / "raw"

# ISO-3 → ISO-2 for the EMEA country set tracked by this project.
# (OWID/Ember publish with ISO-3 codes; we re-key to ISO-2 to match our schema.)
ISO3_TO_ISO2 = {
    "GBR":"GB", "IRL":"IE", "FRA":"FR", "DEU":"DE", "NLD":"NL",
    "BEL":"BE", "LUX":"LU", "CHE":"CH", "AUT":"AT",
    "SWE":"SE", "NOR":"NO", "DNK":"DK", "FIN":"FI", "ISL":"IS",
    "ESP":"ES", "PRT":"PT", "ITA":"IT", "GRC":"GR", "MLT":"MT", "CYP":"CY",
    "POL":"PL", "CZE":"CZ", "SVK":"SK", "HUN":"HU", "ROU":"RO", "BGR":"BG",
    "HRV":"HR", "SVN":"SI", "SRB":"RS", "EST":"EE", "LVA":"LV", "LTU":"LT",
    "ARE":"AE", "SAU":"SA", "QAT":"QA", "BHR":"BH", "KWT":"KW", "OMN":"OM",
    "ISR":"IL", "TUR":"TR", "JOR":"JO",
    "ZAF":"ZA", "EGY":"EG", "MAR":"MA", "NGA":"NG", "KEN":"KE",
    "TUN":"TN", "DZA":"DZ",
}

PER_CAPITA_URL = "https://ourworldindata.org/grapher/per-capita-electricity-generation.csv?v=1&csvType=full&useColumnShortNames=true"
CARBON_URL     = "https://ourworldindata.org/grapher/carbon-intensity-electricity.csv?v=1&csvType=full&useColumnShortNames=true"

REQ_HEADERS = {"User-Agent": "dc-market-comparison/0.1 (research)"}


def fetch_csv(url: str) -> list[dict]:
    print(f"  → {url}")
    req = urllib.request.Request(url, headers=REQ_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def latest_value(rows: list[dict], value_col: str, source: str, url: str) -> dict:
    """Pick the most recent year per country for the given value column."""
    out: dict[str, dict] = {}
    for row in rows:
        iso3 = row.get("Code") or row.get("code")
        if not iso3 or iso3 not in ISO3_TO_ISO2:
            continue
        try:
            year = int(row.get("Year") or row.get("year"))
            val  = float(row[value_col])
        except (ValueError, TypeError, KeyError):
            continue
        iso2 = ISO3_TO_ISO2[iso3]
        prev = out.get(iso2)
        if prev is None or year > prev["year"]:
            out[iso2] = {"value": val, "year": year, "source": source, "url": url}
    return out


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching per-capita electricity generation…")
    try:
        rows = fetch_csv(PER_CAPITA_URL)
    except Exception as e:
        print(f"  failed: {e}", file=sys.stderr)
        return 1

    # OWID short column names start with 'per_capita_electricity'.
    value_cols = [k for k in rows[0].keys() if k not in ("Entity","Code","Year") and "Entity" not in k]
    print(f"  CSV columns: {list(rows[0].keys())}")
    # Pick whichever column actually carries the per-capita kWh number.
    pc_col = next((c for c in value_cols if "capita" in c.lower() or "kwh" in c.lower()), value_cols[0])
    per_capita = latest_value(
        rows, pc_col,
        source="Our World in Data (Ember 'Yearly Electricity Data')",
        url="https://ourworldindata.org/grapher/per-capita-electricity-generation",
    )
    out_pc = RAW_DIR / "ember_per_capita.json"
    out_pc.write_text(json.dumps(per_capita, indent=2), encoding="utf-8")
    print(f"  wrote {out_pc.name} — {len(per_capita)} EMEA countries")

    print("Fetching carbon intensity of electricity…")
    try:
        rows = fetch_csv(CARBON_URL)
    except Exception as e:
        print(f"  failed: {e}", file=sys.stderr)
        return 1
    value_cols = [k for k in rows[0].keys() if k not in ("Entity","Code","Year")]
    print(f"  CSV columns: {list(rows[0].keys())}")
    ci_col = next((c for c in value_cols if "carbon" in c.lower() or "co2" in c.lower() or "gco2" in c.lower()), value_cols[0])
    carbon = latest_value(
        rows, ci_col,
        source="Our World in Data (Ember 'Carbon intensity of electricity')",
        url="https://ourworldindata.org/grapher/carbon-intensity-electricity",
    )
    out_ci = RAW_DIR / "ember_carbon_intensity.json"
    out_ci.write_text(json.dumps(carbon, indent=2), encoding="utf-8")
    print(f"  wrote {out_ci.name} — {len(carbon)} EMEA countries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
