"""
build_ea_projects_geojson.py

Builds a per-project GeoJSON for the EA Register map layer.

Each project in the EA Register has a connection-point name but no
coordinates. We position each project at the lat/lng of its matched
UK substation (from uk_substations.json), and use the same fuzzy
name-matching logic as apply_ea_register() in process_dno_headroom.py.

Projects that don't match any of our 134 substations are dropped (they
mostly sit at minor connection nodes or named cable-route points
outside our substation universe).

For visual variety on the map, projects at the same substation are
"jittered" by a small random offset (~200m) so they don't render as
a single overlapping dot.

Output:
    data/ea_projects.geojson — FeatureCollection of Points

Usage:
    python3 scripts/build_ea_projects_geojson.py
"""

import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

import openpyxl

DATA_DIR = Path("data")
XLSX     = DATA_DIR / "neso_ea_register.xlsx"
SUBS     = DATA_DIR / "uk_substations.json"
OUT      = DATA_DIR / "ea_projects.geojson"
SHEET    = "Sheet1"
DATA_START = 6

DEMAND_TYPES  = {"transmission connected demand"}
STORAGE_TYPES = {"battery", "ldes", "liquid air energy storage (laes)"}
WIND_TYPES    = {"onshore wind", "offshore wind"}
SOLAR_TYPES   = {"solar"}


def _norm(s: str) -> str:
    n = (s or "").lower().strip()
    n = re.sub(r"\s+\d+(?:\s*/\s*\d+)*\s*k?v\b", " ", n)
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
    if n.startswith("the "):
        n = n[4:]
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(n.split())


def tech_category(t: str) -> str:
    tl = (t or "").lower().strip()
    if tl in DEMAND_TYPES:   return "demand"
    if tl in STORAGE_TYPES:  return "battery"
    if tl in WIND_TYPES:     return "wind"
    if tl in SOLAR_TYPES:    return "solar"
    if tl == "unabated gas": return "gas"
    if tl == "nuclear":      return "nuclear"
    if tl == "interconnector": return "interconnector"
    return "other"


def main():
    # Build sub lookup: normalised name → (lat, lng, real_name)
    with open(SUBS) as f:
        subs = json.load(f)
    sub_lookup = {}
    for s in subs:
        k = _norm(s["name"])
        if k:
            sub_lookup[k] = (s["lat"], s["lng"], s["name"])

    # Load EA projects
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb[SHEET]

    features = []
    matched = 0
    unmatched = 0
    rng = random.Random(42)   # deterministic jitter

    for row in ws.iter_rows(min_row=DATA_START, values_only=True):
        if not row or len(row) < 6:
            continue
        project, mw_raw, date, cp_raw, gate1, tech = row[:6]
        if not (project and cp_raw):
            unmatched += 1
            continue
        try:
            mw = float(mw_raw or 0)
        except (ValueError, TypeError):
            mw = 0.0

        cp_key = _norm(str(cp_raw))
        # Fuzzy match: exact, then longest word-prefix overlap
        best = None
        if cp_key in sub_lookup:
            best = sub_lookup[cp_key]
        else:
            cp_words = cp_key.split()
            best_overlap = 0
            for k, v in sub_lookup.items():
                k_words = k.split()
                if not k_words: continue
                # check word-prefix overlap (k starts with cp, or cp starts with k)
                if k_words[:len(cp_words)] == cp_words or cp_words[:len(k_words)] == k_words:
                    overlap = min(len(k_words), len(cp_words))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best = v
        if best is None:
            unmatched += 1
            continue

        lat, lng, sub_name = best
        # Jitter by up to ~200m so co-located projects don't overlap
        d_lat = (rng.random() - 0.5) * 0.0036   # ~200m N/S
        d_lng = (rng.random() - 0.5) * 0.0036 / math.cos(math.radians(lat))
        matched += 1

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng + d_lng, lat + d_lat]},
            "properties": {
                "project":      str(project),
                "mw":           round(mw, 1),
                "tech":         str(tech or "Unknown"),
                "tech_cat":     tech_category(str(tech or "")),
                "date":         str(date)[:10] if date else None,
                "connection_point": str(cp_raw),
                "sub_name":     sub_name,
            },
        })

    fc = {"type": "FeatureCollection", "features": features}
    with open(OUT, "w") as f:
        json.dump(fc, f, separators=(",", ":"))

    print(f"EA projects geojson built:")
    print(f"  Matched (have coords): {matched}")
    print(f"  Unmatched (skipped):   {unmatched}")
    print(f"  Output: {OUT}  ({Path(OUT).stat().st_size//1024} KB)")

    from collections import Counter
    cats = Counter(f["properties"]["tech_cat"] for f in features)
    mws  = defaultdict(float)
    for f in features:
        mws[f["properties"]["tech_cat"]] += f["properties"]["mw"]
    print(f"\nTech mix (count → MW):")
    for cat, n in cats.most_common():
        print(f"  {cat:<15} {n:>5} projects  {mws[cat]:>9.0f} MW")


if __name__ == "__main__":
    main()
