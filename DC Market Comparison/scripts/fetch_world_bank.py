#!/usr/bin/env python3
"""
Fetch labour / R&D indicators from the World Bank Indicators API.

Writes two files into data/raw/:
  - worldbank_rd_techs.json      (F13a — R&D technicians per million people)
  - worldbank_tertiary.json      (F13b — tertiary educational attainment %)

The WB API is public, free, and stable.
Docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE.parent / "data" / "raw"

# WB API uses ISO-3, our schema uses ISO-2. Map across our EMEA country set.
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

REQ_HEADERS = {"User-Agent": "dc-market-comparison/0.1 (research)"}

INDICATORS = [
    {
        "id": "SP.POP.TECH.RD.P6",   # Technicians in R&D (per million people)
        "out_file": "worldbank_rd_techs.json",
        "source": "World Bank Indicators — Technicians in R&D (per million people, SP.POP.TECH.RD.P6)",
        "url": "https://data.worldbank.org/indicator/SP.POP.TECH.RD.P6",
        "date_range": "2015:2023",
    },
    {
        "id": "SE.TER.CUAT.BA.ZS",   # Educational attainment, ≥ Bachelor's, % of pop ≥25
        "out_file": "worldbank_tertiary.json",
        "source": "World Bank Indicators — Educational attainment ≥ Bachelor's (% of pop 25+, SE.TER.CUAT.BA.ZS)",
        "url": "https://data.worldbank.org/indicator/SE.TER.CUAT.BA.ZS",
        "date_range": "2015:2023",
    },
]


def fetch_indicator(indicator_id: str, date_range: str) -> list[dict]:
    """Returns a flat list of [{countryiso3code, date, value}, ...] across all countries."""
    rows: list[dict] = []
    page = 1
    while True:
        url = (
            f"https://api.worldbank.org/v2/country/all/indicator/{indicator_id}"
            f"?format=json&date={date_range}&per_page=10000&page={page}"
        )
        print(f"  → {url}")
        req = urllib.request.Request(url, headers=REQ_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        if not isinstance(doc, list) or len(doc) < 2:
            print(f"  unexpected response shape: {doc[:1]}", file=sys.stderr)
            break
        meta, batch = doc[0], doc[1] or []
        rows.extend(batch)
        if page >= meta.get("pages", 1):
            break
        page += 1
    return rows


def latest_per_country(rows: list[dict], source: str, url: str) -> dict:
    out: dict[str, dict] = {}
    for r in rows:
        iso3 = r.get("countryiso3code") or ""
        if iso3 not in ISO3_TO_ISO2:
            continue
        val = r.get("value")
        date_str = r.get("date")
        if val is None or date_str is None:
            continue
        try:
            year = int(date_str)
            val = float(val)
        except (ValueError, TypeError):
            continue
        iso2 = ISO3_TO_ISO2[iso3]
        prev = out.get(iso2)
        if prev is None or year > prev["year"]:
            out[iso2] = {"value": val, "year": year, "source": source, "url": url}
    return out


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for ind in INDICATORS:
        print(f"Fetching {ind['id']}…")
        try:
            rows = fetch_indicator(ind["id"], ind["date_range"])
        except Exception as e:
            print(f"  failed: {e}", file=sys.stderr)
            return 1
        latest = latest_per_country(rows, ind["source"], ind["url"])
        out_path = RAW_DIR / ind["out_file"]
        out_path.write_text(json.dumps(latest, indent=2), encoding="utf-8")
        print(f"  wrote {out_path.name} — {len(latest)} EMEA countries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
