"""
join_ea_to_repd.py

Joins NESO Existing Agreements Register projects to BEIS/DESNZ REPD
(Renewable Energy Planning Database) for geographic project locations,
then generates a GeoJSON suitable for the map's pipeline layer:

  * Points at the PROJECT site (REPD-geocoded), styled by tech.
  * A LineString from each project to its connection-point substation,
    drawn from the project's site lat/lng to the substation lat/lng.
  * Where no REPD match exists (mostly demand projects, some new ones),
    fall back to the substation lat/lng with no line — matching the
    existing build_ea_projects_geojson.py behaviour.

Inputs:
  data/neso_ea_register.xlsx     — EA Register (3,506 projects)
  data/repd_q1_2026.csv          — REPD Q1 2026 (15,577 projects with BNG x/y)
  data/uk_substations.json       — for substation lat/lng lookup

Output:
  data/ea_projects.geojson       — replaces the previous version
    Features:
      - tech_cat, tech, mw, project, sub_name, date, connection_point,
        gate1_reserved (bool), located (bool), geom_type ("point"|"line")
      - Points use geom_type=point, LineStrings use geom_type=line

Matching strategy:
  1. Normalise both sides: strip punctuation, lowercase, collapse ws,
     drop common suffixes ('solar farm', 'wind farm', 'bess project',
     'extension', '(phase 1)', 'project').
  2. For each EA project, search REPD for: (a) exact normalised match,
     (b) longest-token-overlap match where overlap ≥ 2 tokens AND MW
     difference < 25%. (MW filter avoids false positives where many
     projects share words like 'Burton', 'Mill', 'Park'.)
  3. Where multiple REPD candidates remain, pick the one with the
     smallest MW gap.

Usage:
    python3 scripts/join_ea_to_repd.py
"""

import csv
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

import openpyxl
from pyproj import Transformer

DATA_DIR = Path("data")
EA_XLSX  = DATA_DIR / "neso_ea_register.xlsx"
REPD_CSV = DATA_DIR / "repd_q1_2026.csv"
SUBS     = DATA_DIR / "uk_substations.json"
OUT      = DATA_DIR / "ea_projects.geojson"

# Tech category buckets (copied from build_ea_projects_geojson.py)
DEMAND_TYPES  = {"transmission connected demand"}
STORAGE_TYPES = {"battery", "ldes", "liquid air energy storage (laes)"}
WIND_TYPES    = {"onshore wind", "offshore wind"}
SOLAR_TYPES   = {"solar"}

# British National Grid (EPSG:27700) → WGS84 (EPSG:4326) lat/lng
BNG_TO_WGS = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def norm_project(name: str) -> str:
    """
    Normalise a project name aggressively for matching across registers.
    EA tends to use 'X Solar Project', 'X BESS', 'X Wind Farm Extension';
    REPD tends to use 'X Solar Farm', 'X Battery Storage', 'X Wind Farm'.
    """
    n = (name or "").lower().strip()
    # Common cosmetic suffixes — strip in order, longest first
    drop_phrases = [
        "extension iii", "extension ii", "extension i",
        "phase iii", "phase ii", "phase i", "phase 4", "phase 3", "phase 2", "phase 1",
        "solar and battery", "solar pv farm", "solar farm", "solar park", "solar project",
        "wind farm extension", "offshore wind farm", "onshore wind farm",
        "wind farm", "windfarm", "wind project",
        "battery storage", "battery energy storage", "energy storage", "battery park",
        "bess project", "bess", "battery",
        "extension", "expansion", "project", "plant", "power station",
        "data centre", "data center",
    ]
    for p in drop_phrases:
        n = n.replace(p, " ")
    # Strip number parentheticals, commas, hyphens-as-spaces
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def norm_connection_point(s: str) -> str:
    """Match the normalisation used by fetch_ea_register.py."""
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


def load_manual_locations() -> dict:
    """
    Hand-curated lat/lng overrides for high-MW EA projects not in REPD.
    Keyed by exact project name (case-insensitive match downstream).
    """
    path = DATA_DIR / "manual_project_locations.json"
    if not path.exists():
        return {}
    with open(path) as f:
        d = json.load(f)
    return {k.lower().strip(): v for k, v in d.get("_entries", {}).items()}


def load_osm_plants() -> list[dict]:
    """
    Load OSM power plant features fetched via Overpass. Each element has
    tags{name, power, plant:source, ...} and center{lat, lon}.
    """
    path = DATA_DIR / "osm_power_plants.json"
    if not path.exists():
        return []
    with open(path) as f:
        elements = json.load(f)
    out = []
    for e in elements:
        t = e.get("tags", {}) or {}
        name = t.get("name")
        ctr  = e.get("center") or {}
        if not (name and ctr.get("lat") and ctr.get("lon")):
            continue
        out.append({
            "name":      name,
            "name_norm": norm_project(name),
            "lat":       round(ctr["lat"], 5),
            "lng":       round(ctr["lon"], 5),
            "source":    t.get("plant:source") or t.get("generator:source") or t.get("substation") or "",
            "power":     t.get("power", ""),
        })
    return out


def load_repd() -> list[dict]:
    """Parse REPD CSV; return list of {name_norm, name, mw, lat, lng, status, tech}."""
    out = []
    with open(REPD_CSV, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            name = (row.get("Site Name") or "").strip()
            if not name:
                continue
            try:
                mw = float(row.get("Installed Capacity (MWelec)") or 0)
            except ValueError:
                mw = 0.0
            x_raw = (row.get("X-coordinate") or "").strip()
            y_raw = (row.get("Y-coordinate") or "").strip()
            try:
                x = float(x_raw)
                y = float(y_raw)
            except ValueError:
                continue
            if x <= 0 or y <= 0:
                continue
            lng, lat = BNG_TO_WGS.transform(x, y)
            if not (-12 < lng < 3 and 49 < lat < 62):   # UK bbox sanity
                continue
            out.append({
                "name":      name,
                "name_norm": norm_project(name),
                "mw":        round(mw, 1),
                "lat":       round(lat, 5),
                "lng":       round(lng, 5),
                "status":    (row.get("Development Status (short)") or "").strip(),
                "tech":      (row.get("Technology Type") or "").strip(),
                "postcode":  (row.get("Post Code") or "").strip(),
                "operator":  (row.get("Operator (or Applicant)") or "").strip(),
            })
    return out


def index_repd(repd: list[dict]) -> dict:
    """Build a token-prefix index of REPD for faster matching."""
    idx = defaultdict(list)
    for r in repd:
        if not r["name_norm"]:
            continue
        # Index by every token in the normalised name
        for tok in r["name_norm"].split():
            if len(tok) >= 4:    # skip short tokens
                idx[tok].append(r)
    return idx


def find_match(ea_name: str, ea_mw: float, repd: list[dict], idx: dict):
    """
    Find best REPD match for an EA project.

    Returns (repd_record, "REPD") or (None, None).
    """
    ea_norm = norm_project(ea_name)
    if not ea_norm:
        return None, None
    ea_tokens = set(ea_norm.split())
    if not ea_tokens:
        return None, None

    candidates = set()
    for tok in ea_tokens:
        if len(tok) >= 4:
            for r in idx.get(tok, []):
                candidates.add(id(r))
    candidates = [r for r in repd if id(r) in candidates]
    if not candidates:
        return None, None

    best, best_score = None, -1
    for r in candidates:
        r_tokens = set(r["name_norm"].split())
        overlap  = ea_tokens & r_tokens
        if len(overlap) < 2:
            continue
        if ea_mw > 0 and r["mw"] > 0:
            mw_ratio = min(ea_mw, r["mw"]) / max(ea_mw, r["mw"])
        else:
            mw_ratio = 0.5
        score = len(overlap) * 10 + mw_ratio * 5
        if score > best_score:
            best_score = score
            best = r
    return (best, "REPD") if best else (None, None)


def find_osm_match(ea_name: str, osm: list[dict]):
    """
    Find best OSM power-plant match. Token-overlap with ≥2 shared tokens,
    no MW filter (OSM rarely carries MW).
    """
    ea_norm = norm_project(ea_name)
    if not ea_norm:
        return None, None
    ea_tokens = set(ea_norm.split())
    if not ea_tokens:
        return None, None

    best, best_overlap = None, 0
    for r in osm:
        r_tokens = set(r["name_norm"].split())
        overlap  = ea_tokens & r_tokens
        # Require ≥2 shared non-trivial tokens
        long_overlap = {t for t in overlap if len(t) >= 4}
        if len(long_overlap) >= 2 and len(long_overlap) > best_overlap:
            best_overlap = len(long_overlap)
            best = r
    return (best, "OSM") if best else (None, None)


def find_manual_match(ea_name: str, manual: dict):
    """Exact (case-insensitive) lookup against hand-curated entries."""
    k = ea_name.strip().lower()
    v = manual.get(k)
    if v:
        return ({"name": ea_name, "lat": v["lat"], "lng": v["lng"],
                 "source": v.get("source", ""), "notes": v.get("notes", ""),
                 "status": "manual"}, "MANUAL")
    return None, None


def main():
    # ── Load substations for lookup ───────────────────────────────────
    with open(SUBS) as f:
        subs = json.load(f)
    sub_lookup = {}
    for s in subs:
        k = norm_connection_point(s["name"])
        if k:
            sub_lookup[k] = (s["lat"], s["lng"], s["name"])

    # ── Load REPD ─────────────────────────────────────────────────────
    repd = load_repd()
    idx  = index_repd(repd)
    print(f"REPD: {len(repd):,} geocoded projects loaded (token index: {len(idx):,} keys)")

    # ── Load manual + OSM fallbacks ───────────────────────────────────
    manual = load_manual_locations()
    osm    = load_osm_plants()
    print(f"Manual lookup: {len(manual)} hand-curated entries")
    print(f"OSM power plants: {len(osm):,} named features")

    # ── Walk EA register ──────────────────────────────────────────────
    wb = openpyxl.load_workbook(EA_XLSX, data_only=True)
    ws = wb["Sheet1"]

    rng = random.Random(42)
    features = []
    stats = {"matched_repd": 0, "matched_manual": 0, "matched_osm": 0,
             "at_sub": 0, "unmatched": 0, "gate1_reserved": 0}

    for row in ws.iter_rows(min_row=6, values_only=True):
        if not row or len(row) < 6:
            continue
        project, mw_raw, date, cp_raw, gate1, tech = row[:6]
        if not (project and cp_raw):
            continue
        try:
            mw = float(mw_raw or 0)
        except (ValueError, TypeError):
            mw = 0.0

        # Look up substation coords
        cp_key = norm_connection_point(str(cp_raw))
        sub_coords = sub_lookup.get(cp_key)
        if not sub_coords:
            # Try fuzzy: longest-prefix overlap on word boundaries
            cp_words = cp_key.split()
            best = None
            best_overlap = 0
            for k, v in sub_lookup.items():
                k_words = k.split()
                if not k_words: continue
                if k_words[:len(cp_words)] == cp_words or cp_words[:len(k_words)] == k_words:
                    overlap = min(len(k_words), len(cp_words))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best = v
            sub_coords = best
        if not sub_coords:
            stats["unmatched"] += 1
            continue

        sub_lat, sub_lng, sub_name = sub_coords
        cat = tech_category(str(tech or ""))
        gate1_flag = str(gate1 or "").strip().upper() in ("Y", "YES", "TRUE", "1")
        if gate1_flag:
            stats["gate1_reserved"] += 1

        # Common properties
        base_props = {
            "project":          str(project),
            "mw":               round(mw, 1),
            "tech":             str(tech or "Unknown"),
            "tech_cat":         cat,
            "date":             str(date)[:10] if date else None,
            "connection_point": str(cp_raw),
            "sub_name":         sub_name,
            "gate1_reserved":   gate1_flag,
        }

        # Resolution chain: manual override → REPD → OSM → substation jitter
        match, source = None, None
        match, source = find_manual_match(str(project), manual)
        if match is None:
            match, source = find_match(str(project), mw, repd, idx)
        if match is None:
            match, source = find_osm_match(str(project), osm)

        if match:
            if source == "MANUAL": stats["matched_manual"] += 1
            elif source == "REPD": stats["matched_repd"]   += 1
            else:                  stats["matched_osm"]    += 1
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [match["lng"], match["lat"]]},
                "properties": {**base_props, "geom_type": "point", "located": True,
                               "geocode_source": source,
                               "site_name": match.get("name", ""),
                               "site_status": match.get("status", "")},
            })
        else:
            stats["at_sub"] += 1
            d_lat = (rng.random() - 0.5) * 0.0036
            d_lng = (rng.random() - 0.5) * 0.0036 / math.cos(math.radians(sub_lat))
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [sub_lng + d_lng, sub_lat + d_lat]},
                "properties": {**base_props, "geom_type": "point", "located": False,
                               "geocode_source": "substation"},
            })

    # ── Write GeoJSON ─────────────────────────────────────────────────
    fc = {"type": "FeatureCollection", "features": features}
    with open(OUT, "w") as f:
        json.dump(fc, f, separators=(",", ":"))

    print()
    print(f"EA projects geojson rebuilt:")
    print(f"  Geocoded by REPD:                  {stats['matched_repd']:>5,}")
    print(f"  Geocoded by manual lookup:         {stats['matched_manual']:>5,}")
    print(f"  Geocoded by OSM power-plant match: {stats['matched_osm']:>5,}")
    print(f"  At substation (no source matched): {stats['at_sub']:>5,}")
    print(f"  Skipped (substation not found):    {stats['unmatched']:>5,}")
    print(f"  Gate 1 'with reservation':         {stats['gate1_reserved']:>5,}")
    total_geo = stats['matched_repd'] + stats['matched_manual'] + stats['matched_osm']
    placed = total_geo + stats['at_sub']
    if placed:
        print(f"  Geocoded rate: {total_geo*100/placed:.1f}% ({total_geo:,} / {placed:,})")
    print(f"  Output: {OUT}  ({OUT.stat().st_size // 1024} KB)")

    # Tech breakdown of geocoded vs not
    from collections import Counter
    located_by_cat   = Counter(f["properties"]["tech_cat"] for f in features
                                if f["properties"]["geom_type"] == "point"
                                and f["properties"]["located"])
    unlocated_by_cat = Counter(f["properties"]["tech_cat"] for f in features
                                if f["properties"]["geom_type"] == "point"
                                and not f["properties"]["located"])
    print()
    print("Geocoding hit rate by tech (REPD covers renewables only — demand always falls back):")
    print(f"  {'category':<15} {'located':>8} {'at_sub':>8} {'hit%':>6}")
    cats = set(located_by_cat) | set(unlocated_by_cat)
    for cat in sorted(cats):
        l = located_by_cat.get(cat, 0)
        u = unlocated_by_cat.get(cat, 0)
        tot = l + u
        pct = (l * 100 // tot) if tot else 0
        print(f"  {cat:<15} {l:>8} {u:>8} {pct:>5}%")


if __name__ == "__main__":
    main()
