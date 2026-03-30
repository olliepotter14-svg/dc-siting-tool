"""
process_dno_headroom.py

Consolidates real DNO headroom/capacity data from 6 UK distribution networks
and updates uk_substations.json with sourced figures.

Data sources (by quality tier):
  GREEN  UKPN  — technical limits agreed at T/D boundary (23/60 GSPs)
  GREEN  NPG   — published demand headroom (demhr) in heatmap dataset
  AMBER  UKPN  — asset import limit minus max observed (37/60 GSPs)
  AMBER  SSEN  — nameplate capacity minus max observed demand
  AMBER  NGED  — technical import limit (no demand data, capacity proxy only)
  AMBER  SPEN  — technical import limit (no demand data, capacity proxy only)
  RED    ENW   — aggregated PRY (primary) demand headroom (indirect proxy)

Fields written to each substation:
  estimated_headroom_mva  — best available headroom in MVA (replaces fabricated value)
  headroom_capacity_mva   — total substation capacity (where sourced)
  headroom_source         — data source description
  headroom_data_quality   — "agreed_technical_limits" | "direct_headroom" |
                            "asset_limit_proxy" | "nameplate_proxy" |
                            "technical_limit_only" | "pry_aggregate" | "fabricated"
  headroom_updated        — True if replaced, False if left as-is

Run:
    python3 scripts/process_dno_headroom.py
"""

import json, csv, re, math
from pathlib import Path

DATA_DIR = Path("data")
SUBS_FILE = DATA_DIR / "uk_substations.json"

# ── Name normalisation ──────────────────────────────────────────────────
def norm(name: str) -> str:
    """Lowercase, strip common suffixes, remove punctuation."""
    n = name.lower().strip()
    for suffix in [" gsp", " grid", " (epn)", " (lpn)", " (spn)", " 1", " 2", " 3"]:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    n = re.sub(r"[^a-z0-9 ]", "", n)   # remove punctuation
    n = re.sub(r"\s+", " ", n).strip()
    return n

# Manual override map: our substation name → DNO dataset name
# (only needed where normalised names still don't match)
NAME_MAP = {
    # ── Existing name corrections ──────────────────────────────────────
    "ratcliffe-on-soar":    "ratcliffe",
    "hawthorne pit":        "hawthorn pit",
    "hawthorn pit grid":    "hawthorn pit",
    "hams hall":            "bustleholm",        # NGED GSP serving Hams Hall area
    "iron acton":           "iron acton swe",    # NGED uses "Iron Acton (SWe)"
    "coventry":             "coventry",
    "bushbury":             "bushbury",
    "feckenham":            "feckenham",
    "nechells":             "nechells east",
    "ironbridge":           "ironbridge and shrewsbury",
    "barking":              "barking west",      # UKPN split into EPN/LPN
    "beddington":           "beddington",
    "wimbledon":            "wimbledon 1",       # UKPN has Wimbledon 1 & 2
    "bramley":              "bramley basi",      # SSEN split
    "south manchester":     "south manchester",  # UKPN
    "west weybridge":       "weybridge",

    # ── NGED coordinate-derived proxies (NGET sub name ≠ NGED GSP name) ──
    # Verified by centroid proximity: distribution-substations.csv → nged_gsp_headroom.csv
    "seabank":              "iron acton swe",   # NGED Iron Acton (SWe) 13.5km — Avonmouth 400kV
    "walham":               "iron acton swe",   # NGED Iron Acton (SWe) 27.6km — Gloucester 400kV
    "corby":                "grendon",          # NGED Grendon 15.6km — Northants 400kV
    "high marnham":         "staythorpe",       # NGED Staythorpe 10.6km — Notts 400kV
    "cottam":               "staythorpe",       # NGED Staythorpe 19.2km — Notts 400kV (same supply area)
    "cilfynydd":            "upper boat",       # NGED Upper Boat 3.1km — Pontypridd 275kV
    "imperial park":        "uskmouth",         # NGED Uskmouth 8.7km — Newport 275kV
    "spalding north":       "walpole",          # NGED Walpole 2.4km — Lincolnshire/Fenland 400kV
    "rugeley":              "bushbury",         # NGED Bushbury 21.4km — closest NGED GSP (Staffs 400kV)
    "hinkley point":        "taunton",          # NGED Taunton 23.3km — nearest Somerset GSP (400kV)

    # ── SPEN SPM coordinate-derived proxies ──────────────────────────────
    "deeside":              "connahs quay",     # SPEN SPM 4.2km — Flintshire 400kV (very close)
    "whitegate":            "frodsham",         # SPEN SPM 22.8km — Cheshire 275kV
    "wylfa":                "pentir",           # SPEN SPM 52.5km — Anglesey (no closer GSP exists)
    "trawsfynydd":          "pentir",           # SPEN SPM 32.5km — Snowdonia (nearest licensed GSP)

    # ── SSEN SEPD coordinate-derived proxies ─────────────────────────────
    "didcot":               "cowley",           # SSEN SEPD — Cowley GSP is the Thames Valley 400kV feed
    "culham":               "cowley",           # SSEN SEPD — Cowley GSP 5.7km from Culham 400kV

    # ── UKPN coordinate-derived proxies ──────────────────────────────────
    "grain":                "kingsnorth",       # UKPN SPN — Kingsnorth GSP near Hoo Peninsula, Kent
    "broxbourne":           "rye house",        # UKPN EPN — Rye House GSP ~3km from Broxbourne
    "waltham cross":        "rye house",        # UKPN EPN — Rye House GSP nearest to Waltham Cross area
    "dungeness":            "sellindge",        # UKPN SPN — Sellindge GSP 21km, Kent; Dungeness is NGET 400kV only
    "sizewell":             "bramford",         # UKPN EPN — Bramford 63.6km; no GSP within 50km of Suffolk coast
}

def resolve(our_name: str, lookup: dict):
    """Find best match in lookup for a substation name."""
    n = norm(our_name)
    # Try override map first
    mapped = NAME_MAP.get(n, n)
    if mapped in lookup:
        return mapped, lookup[mapped]
    # Direct normalised match
    if n in lookup:
        return n, lookup[n]
    # Partial prefix match (e.g. "bicker fen" matches "bicker fen")
    for k, v in lookup.items():
        if k.startswith(n) or n.startswith(k):
            return k, v
    return None, None


# ── Load UKPN ───────────────────────────────────────────────────────────
def load_ukpn() -> dict:
    lookup = {}
    with open(DATA_DIR / "ukpn_gsp_processed.json") as f:
        recs = json.load(f)
    for r in recs:
        gsp = r["gsp"]
        n = norm(gsp)
        quality = ("agreed_technical_limits" if r.get("tech_limits") == "GREEN"
                   else "asset_limit_proxy")
        hw = r["headroom_mw"]
        lookup[n] = {
            "headroom_mw":      round(hw, 1) if hw is not None else None,
            "capacity_mw":      None,  # not separately tracked for UKPN
            "max_demand_mw":    round(r["max_observed_mw"], 1),
            "source":           f"UKPN GSP Overview ({quality.replace('_',' ')})",
            "quality":          quality,
            "dno":              "UKPN",
            "raw_name":         gsp,
        }
    print(f"  UKPN: {len(lookup)} GSPs loaded")
    return lookup


# ── Load NPG ────────────────────────────────────────────────────────────
def load_npg() -> dict:
    lookup = {}
    with open(DATA_DIR / "npg_gsp_heatmap.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("typetable", "").upper() != "GSP":
                continue
            name = row.get("psp_name", "").strip()
            if not name:
                continue
            demhr = row.get("demhr", "")
            firm  = row.get("firm_cap", "")
            maxd  = row.get("maxdemand", "")
            try:
                headroom = float(demhr) if demhr else None
                capacity = float(firm)  if firm  else None
                max_dem  = float(maxd)  if maxd  else None
            except (ValueError, TypeError):
                continue
            n = norm(name)
            lookup[n] = {
                "headroom_mw":   round(headroom, 1) if headroom is not None else None,
                "capacity_mw":   round(capacity, 1) if capacity is not None else None,
                "max_demand_mw": round(max_dem,  1) if max_dem  is not None else None,
                "source":        "Northern Powergrid GSP Heatmap (direct demand headroom)",
                "quality":       "direct_headroom",
                "dno":           "NPG",
                "raw_name":      name,
            }
    print(f"  NPG:  {len(lookup)} GSPs loaded")
    return lookup


# ── Load SSEN ───────────────────────────────────────────────────────────
def parse_nameplate(nm: str):
    """'3 x 120MVA' → 360.0 (total nameplate, not firm)"""
    nums = re.findall(r"(\d+)\s*[Xx]\s*(\d+)\s*MVA", nm, re.I)
    if not nums:
        return None
    total = sum(int(n) * int(m) for n, m in nums)
    return float(total)

def ssen_firm_capacity(nameplate_mva, num_transformers):
    """Firm = (n-1) × per-transformer rating — standard n-1 security."""
    if num_transformers <= 1:
        return nameplate_mva
    per_tx = nameplate_mva / num_transformers
    return per_tx * (num_transformers - 1)

def load_ssen() -> dict:
    lookup = {}
    with open(DATA_DIR / "ssen_headroom_dashboard.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Substation Type", "").strip() != "GSP":
                continue
            name = row.get("Substation", "").strip()
            # Strip " GSP" suffix
            if name.upper().endswith(" GSP"):
                name = name[:-4].strip()
            nm_str = row.get("Transformer Nameplate Ratings", "").strip()
            max_d_str = row.get("Maximum Observed Gross Demand (MVA)", "").strip()
            try:
                max_d = float(max_d_str) if max_d_str and max_d_str != "N/A" else None
            except ValueError:
                max_d = None
            nameplate = parse_nameplate(nm_str)
            if nameplate is None or max_d is None:
                continue
            # Count transformers
            nums = re.findall(r"(\d+)\s*[Xx]\s*\d+\s*MVA", nm_str, re.I)
            n_tx = int(nums[0]) if nums else 1
            firm = ssen_firm_capacity(nameplate, n_tx)
            headroom = firm - max_d
            n = norm(name)
            shared = "shared" in nm_str.lower()
            lookup[n] = {
                "headroom_mw":   round(max(headroom, 0), 1),
                "capacity_mw":   round(firm, 1),
                "max_demand_mw": round(max_d, 1),
                "source":        "SSEN Headroom Dashboard (nameplate firm capacity − max demand)"
                                 + (" — SHARED SITE" if shared else ""),
                "quality":       "nameplate_proxy",
                "dno":           "SSEN",
                "raw_name":      name,
            }
    print(f"  SSEN: {len(lookup)} GSPs loaded")
    return lookup


# ── Load NGED ───────────────────────────────────────────────────────────
def load_nged() -> dict:
    """NGED: import TL MW (negative sign convention) → capacity only."""
    lookup = {}
    with open(DATA_DIR / "nged_gsp_headroom.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # Group by GSP name, take winter rows
    from collections import defaultdict
    gsp_rows = defaultdict(list)
    for r in rows:
        gn = r.get("GSP Name", "").strip()
        if r.get("Season", "") == "Winter" and gn:
            gsp_rows[gn].append(r)
    for gsp_name, winter_rows in gsp_rows.items():
        # Prefer Import TL MW (direct import capacity limit).
        # Some GSPs are generation-only (e.g. former power stations) and only
        # have Export CAFPL MVA.  Use that as an upper-bound capacity proxy.
        import_tls, export_caps = [], []
        for r in winter_rows:
            imp = r.get("Import TL MW", "").strip()
            exp = (r.get("Export CAFPL MVA", "") or r.get("Import CAFPL MVA", "")).strip()
            if imp:
                try: import_tls.append(abs(float(imp)))
                except ValueError: pass
            if exp:
                try: export_caps.append(abs(float(exp)))
                except ValueError: pass

        if import_tls:
            capacity = max(import_tls)
            source   = "NGED GSP Technical Limits (import TL only, no demand data)"
            quality  = "technical_limit_only"
        elif export_caps:
            capacity = max(export_caps)
            source   = "NGED GSP Export Capacity (generation-only GSP; import capacity unknown)"
            quality  = "technical_limit_only"
        else:
            continue

        n = norm(gsp_name)
        lookup[n] = {
            "headroom_mw":   None,
            "capacity_mw":   round(capacity, 1),
            "max_demand_mw": None,
            "source":        source,
            "quality":       quality,
            "dno":           "NGED",
            "raw_name":      gsp_name,
        }
    print(f"  NGED: {len(lookup)} GSPs loaded")
    return lookup


# ── Load SPEN SPM ────────────────────────────────────────────────────────
def load_enw_by_coords(subs: list) -> dict:
    """
    ENW substations are only available by GSP number, not name.
    Match our substations to nearest ENW GSP centroid by coordinate (≤15 km).
    Returns a lookup keyed by SUBSTATION NAME (not normalised GSP name).
    """
    with open(DATA_DIR / "enw_gsp_pry_aggregated.json") as f:
        enw = json.load(f)

    # Build ENW centroids from PRY aggregates (lat/lon from earlier fetch)
    # Re-fetch centroids using a live call if needed; here we use stored JSON
    results = {}
    for sub in subs:
        if sub.get("headroom_updated"):
            continue   # already matched by name
        slat, slng = sub.get("lat"), sub.get("lng")
        if slat is None or slng is None:
            continue
        best_dist = 999
        best_gsp  = None
        for gsp_num, gdata in enw.items():
            glat, glon = gdata.get("lat"), gdata.get("lon")
            if glat is None:
                continue
            dist_km = math.sqrt((slat - glat) ** 2 + (slng - glon) ** 2) * 111
            if dist_km < best_dist:
                best_dist = dist_km
                best_gsp  = (gsp_num, gdata)
        if best_gsp and best_dist <= 15:
            gsp_num, gdata = best_gsp
            hr = gdata["total_dem_hr_firm_mw"]
            results[sub["name"]] = {
                "headroom_mw":   round(hr, 1) if hr is not None else None,
                "capacity_mw":   None,
                "max_demand_mw": None,
                "source":        f"ENW PRY Heatmap aggregate (GSP# {gsp_num}, {gdata['pry_count']} primary subs, {best_dist:.1f} km)",
                "quality":       "pry_aggregate",
                "dno":           "ENW",
                "raw_name":      f"ENW GSP {gsp_num}",
            }
    print(f"  ENW:  {len(results)} substations matched by coordinate")
    return results


def load_npg_by_coords(subs: list, radius_km: float = 15.0) -> dict:
    """
    Match unmatched substations to the nearest NPG GSP by coordinate.

    NPG's heatmap CSV has a 'substation_location' field with 'lat, lng' which
    we use for proximity matching.  This catches NGET transmission nodes whose
    names differ from the downstream NPG distribution GSP (e.g. 'Stella West'
    NGET → 'Stella North' NPG at 1.4 km).

    Returns a lookup keyed by our SUBSTATION NAME.
    """
    npg_gsps = []
    with open(DATA_DIR / "npg_gsp_heatmap.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row.get("typetable", "").upper() != "GSP":
                continue
            loc = row.get("substation_location", "").strip()
            if not loc or "," not in loc:
                continue
            try:
                glat, glng = (float(x) for x in loc.split(",", 1))
                demhr = float(row["demhr"]) if row.get("demhr", "").strip() else None
                firm  = float(row["firm_cap"]) if row.get("firm_cap", "").strip() else None
                npg_gsps.append({
                    "name": row["psp_name"].strip(),
                    "lat": glat, "lng": glng,
                    "demhr": demhr, "firm": firm,
                })
            except (ValueError, KeyError):
                continue

    results = {}
    for sub in subs:
        if sub.get("headroom_updated"):
            continue
        slat, slng = sub.get("lat"), sub.get("lng")
        if slat is None or slng is None:
            continue
        best_dist, best_gsp = radius_km, None
        for g in npg_gsps:
            d = math.sqrt((slat - g["lat"]) ** 2 + (slng - g["lng"]) ** 2) * 111
            if d < best_dist:
                best_dist, best_gsp = d, g
        if best_gsp:
            # Prefer direct headroom (demhr); fall back to firm capacity
            hr  = best_gsp["demhr"] if best_gsp["demhr"] is not None else None
            cap = best_gsp["firm"]
            results[sub["name"]] = {
                "headroom_mw":   round(hr,  1) if hr  is not None else None,
                "capacity_mw":   round(cap, 1) if cap is not None else None,
                "max_demand_mw": None,
                "source":        (f"NPG GSP Heatmap coord-match: '{best_gsp['name']}' "
                                  f"({best_dist:.1f} km — NGET/NPG name differs)"),
                "quality":       "direct_headroom" if hr is not None else "nameplate_proxy",
                "dno":           "NPG",
                "raw_name":      best_gsp["name"],
            }
    print(f"  NPG coord-match: {len(results)} substations matched within {radius_km:.0f} km")
    return results


def load_spen_spd_utilisation() -> dict:
    """
    Load SPEN SPD Historic Substation Utilisation 2024.
    Fields: Grid Supply Point, Firm Capacity (MVA) 2024, Available Capacity (MVA) 2024.
    Available Capacity = Firm Capacity – Peak Utilisation — this is genuine demand headroom.

    GSP name mapping: NGET substation name → SPD distribution GSP name.
    Where no direct match exists we use the nearest distribution GSP.
    """
    # NGET transmission sub → SPD distribution GSP name in the utilisation file
    SPD_UTIL_MAP = {
        # Direct name matches
        "bonnybridge":  "Bonnybridge",
        "cockenzie":    "Cockenzie",
        "devol moor":   "Devol Moor",
        "eccles":       "Eccles",
        "erskine":      "Erskine",
        "glenrothes":   "Glenrothes",
        "kaimes":       "Kaimes",
        "strathaven":   "Strathaven",
        "westfield":    "Westfield",
        # Grangemouth: two sub-GSPs (A and C); combine them
        "grangemouth":  ["Grangemouth A", "Grangemouth C"],
        # Coordinate proxies — nearest distribution GSP with real headroom data
        "inverkip":     "Spango Valley",    # 9km W — Inverclyde/Renfrewshire border
        "kincardine":   "Devonside",        # 12km E — Clackmannanshire (same 132kV group)
        "longannet":    "Devonside",        # 10km E — ex-coal station, same 132kV area
        "torness":      "Dunbar A",         # 8km N  — East Lothian coast
        # Remaining 4 have no credible close GSP proxy — stay fabricated:
        # Clydes Mill, Elvanfoot, Tealing, Hunterston (Farm sub is too small / wrong node)
    }

    # Aggregate firm and available capacity per GSP from the CSV
    gsp_data: dict = {}
    with open(DATA_DIR / "spen_spd_utilisation_2024.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gsp = row["Grid Supply Point"].strip()
            firm = row.get("Firm Capacity (MVA) 2024", "").strip()
            avail = row.get("Available Capacity (MVA) 2024", "").strip()
            try:
                firm_val = float(firm)
                avail_val = float(avail)
            except ValueError:
                continue
            if gsp not in gsp_data:
                gsp_data[gsp] = {"firm": 0.0, "avail": 0.0}
            gsp_data[gsp]["firm"]  += firm_val
            gsp_data[gsp]["avail"] += avail_val

    lookup: dict = {}
    for sub_norm, gsp_ref in SPD_UTIL_MAP.items():
        # Support single GSP or list of GSPs to combine
        gsp_list = gsp_ref if isinstance(gsp_ref, list) else [gsp_ref]
        matching = [gsp_data[g] for g in gsp_list if g in gsp_data]
        if not matching:
            continue
        total_firm  = sum(g["firm"]  for g in matching)
        total_avail = sum(g["avail"] for g in matching)
        headroom = round(total_avail, 1) if total_avail > 0 else 0.0
        label = " + ".join(gsp_list)
        proxy_note = "" if len(gsp_list) == 1 and gsp_ref == sub_norm.title() else f" (proxy for {sub_norm.title()})"
        lookup[sub_norm] = {
            "headroom_mw":   headroom,
            "capacity_mw":   round(total_firm, 1),
            "max_demand_mw": round(total_firm - total_avail, 1),
            "source":        f"SPEN SPD Substation Utilisation 2024 — {label}{proxy_note}",
            "quality":       "direct_headroom",
            "dno":           "SPEN SPD",
            "raw_name":      label,
        }

    print(f"  SPEN SPD utilisation: {len(lookup)} GSPs loaded")
    return lookup


def load_spen_spm():
    lookup = {}
    with open(DATA_DIR / "spen_spm_technical_limits.json") as f:
        recs = json.load(f)
    for r in recs:
        name = r.get("gsp_name", "").strip()
        wlim = r.get("gsp_technical_import_limit_winter_mw_01_dec_28_feb")
        if not name or wlim is None:
            continue
        capacity = abs(float(wlim))
        n = norm(name)
        lookup[n] = {
            "headroom_mw":   None,
            "capacity_mw":   round(capacity, 1),
            "max_demand_mw": None,
            "source":        "SPEN SPM Technical Limits (winter import limit, no demand data)",
            "quality":       "technical_limit_only",
            "dno":           "SPEN",
            "raw_name":      name,
        }
    print(f"  SPEN: {len(lookup)} GSPs loaded")
    return lookup


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    print("Building DNO headroom lookup...")
    # Priority order: best source first
    lookups = {}
    lookups.update(load_spen_spm())              # AMBER - lowest priority
    lookups.update(load_spen_spd_utilisation()) # GREEN - real 2024 available capacity
    lookups.update(load_nged())                 # AMBER
    lookups.update(load_ssen())                 # AMBER (better — has demand side)
    lookups.update(load_npg())                  # GREEN - direct headroom
    lookups.update(load_ukpn())                 # GREEN (best)

    # Save master lookup
    out_path = DATA_DIR / "dno_gsp_headroom.json"
    with open(out_path, "w") as f:
        json.dump({k: v for k, v in sorted(lookups.items())}, f, indent=2)
    print(f"\nMaster lookup: {len(lookups)} GSPs → {out_path}")

    # ── Update uk_substations.json ────────────────────────────────────
    with open(SUBS_FILE) as f:
        subs = json.load(f)

    # First pass: name-based matching
    matched = 0
    quality_counts = {}

    for sub in subs:
        key, data = resolve(sub["name"], lookups)
        if data:
            headroom = data["headroom_mw"]
            capacity = data["capacity_mw"]

            # Use capacity as headroom proxy if headroom not available
            if headroom is None and capacity is not None:
                headroom = capacity   # upper bound — no demand subtracted
                note = " (capacity upper bound, demand unknown)"
            else:
                note = ""

            sub["estimated_headroom_mva"] = headroom
            if capacity:
                sub["headroom_capacity_mva"] = capacity
            sub["headroom_source"]       = data["source"] + note
            sub["headroom_data_quality"] = data["quality"]
            sub["headroom_dno"]          = data["dno"]
            # Only mark updated if we actually have a usable headroom value.
            # If both headroom and capacity are None (e.g. UKPN 'N/A' import limit)
            # leave headroom_updated = False so it appears in the resolution backlog.
            sub["headroom_updated"] = (headroom is not None)
            if sub["headroom_updated"]:
                matched += 1
            q = data["quality"]
            quality_counts[q] = quality_counts.get(q, 0) + 1
        else:
            sub["headroom_updated"] = False

    # Second pass: ENW coordinate matching for still-unmatched substations
    enw_lookup = load_enw_by_coords(subs)
    for sub in subs:
        if sub.get("headroom_updated"):
            continue
        data = enw_lookup.get(sub["name"])
        if data:
            headroom = data["headroom_mw"]
            sub["estimated_headroom_mva"] = headroom
            sub["headroom_source"]        = data["source"]
            sub["headroom_data_quality"]  = data["quality"]
            sub["headroom_dno"]           = data["dno"]
            sub["headroom_updated"]       = True
            matched += 1
            q = data["quality"]
            quality_counts[q] = quality_counts.get(q, 0) + 1

    # Third pass: NPG coordinate matching (NGET names often differ from NPG
    # distribution GSP names — e.g. 'Stella West' → 'Stella North')
    npg_coord_lookup = load_npg_by_coords(subs, radius_km=15.0)
    for sub in subs:
        if sub.get("headroom_updated"):
            continue
        data = npg_coord_lookup.get(sub["name"])
        if data:
            headroom = data["headroom_mw"]
            capacity = data["capacity_mw"]
            if headroom is None and capacity is not None:
                headroom = capacity
                data["source"] += " (capacity upper bound, demand unknown)"
            sub["estimated_headroom_mva"] = headroom
            if capacity:
                sub["headroom_capacity_mva"] = capacity
            sub["headroom_source"]        = data["source"]
            sub["headroom_data_quality"]  = data["quality"]
            sub["headroom_dno"]           = data["dno"]
            sub["headroom_updated"]       = True
            matched += 1
            q = data["quality"]
            quality_counts[q] = quality_counts.get(q, 0) + 1

    # Mark remaining as fabricated
    unmatched = []
    for sub in subs:
        if not sub.get("headroom_updated"):
            sub["headroom_data_quality"] = "fabricated"
            unmatched.append(sub["name"])

    # ── Recalculate scores_real + real_queue_pressure_pct ────────────
    # For all headroom_updated substations — including those with zero or
    # negative headroom, which should score 0 (not keep stale inflated scores).
    #   headroom_score       = min(100, (headroom_mva / required_mw) * 50)
    #   real_queue_pressure  = (tec_queue_mw / headroom_mva) * 100  (999 if hr<=0)
    #   queue_score          = max(0, 100 - real_queue_pressure)  capped 0–100
    #   total_score = 0.30×headroom + 0.30×queue + 0.20×voltage + 0.10×gsp + 0.10×upgrade
    headroom_recalc = 0
    for sub in subs:
        if not sub.get("headroom_updated"):
            continue
        headroom = sub.get("estimated_headroom_mva")
        # Treat None or negative as zero (saturated / no data)
        hr_eff = headroom if (headroom is not None and headroom > 0) else 0.0

        # Recalculate queue pressure using real headroom
        tec_queue = sub.get("tec_queue_mw", 0) or 0
        if hr_eff > 0:
            new_queue_pct = round((tec_queue / hr_eff) * 100, 1)
        else:
            new_queue_pct = 999.0   # saturated / unknown capacity
        sub["real_queue_pressure_pct"] = new_queue_pct
        new_queue_score = round(max(0.0, min(100.0, 100 - new_queue_pct)), 1)

        scores_real = sub.get("scores_real", {})
        for mw_str in ("20", "50", "100"):
            mw = int(mw_str)
            if mw_str not in scores_real:
                continue
            s = scores_real[mw_str]
            new_hs = round(max(0.0, min(100.0, (hr_eff / mw) * 50)), 1)
            s["headroom_score"] = new_hs
            s["queue_score"]    = new_queue_score
            s["real_queue_pressure"] = new_queue_pct
            s["total_score"] = round(
                0.30 * s["headroom_score"] +
                0.30 * s["queue_score"] +
                0.20 * s.get("voltage_score", 0) +
                0.10 * s.get("gsp_score", 0) +
                0.10 * s.get("upgrade_score", 0),
                1
            )
            s["can_support"] = hr_eff >= mw
        headroom_recalc += 1
    print(f"\n  scores_real + queue_pressure recalculated for {headroom_recalc} substations")

    # ── Cleanup: zero out headroom_score for any sub with None/≤0 headroom ─
    # These subs may have stale inflated scores_real from before real data
    # was loaded (e.g. Grendon: UKPN has no import limit → headroom=None).
    zeroed = 0
    for sub in subs:
        hr = sub.get("estimated_headroom_mva")
        if hr is not None and hr > 0:
            continue   # valid headroom — scores already handled above
        scores_real = sub.get("scores_real", {})
        if not scores_real:
            continue
        changed = False
        for mw_str in ("20", "50", "100"):
            s = scores_real.get(mw_str, {})
            if not s:
                continue
            if s.get("headroom_score", 0) > 0 or s.get("can_support", False):
                s["headroom_score"] = 0.0
                s["can_support"] = False
                s["total_score"] = round(
                    0.30 * 0.0 +
                    0.30 * s.get("queue_score", 0) +
                    0.20 * s.get("voltage_score", 0) +
                    0.10 * s.get("gsp_score", 0) +
                    0.10 * s.get("upgrade_score", 0),
                    1
                )
                changed = True
        if changed:
            zeroed += 1
    if zeroed:
        print(f"  headroom_score zeroed for {zeroed} subs with None/≤0 headroom (stale scores cleared)")

    # Save updated substations
    tmp = str(SUBS_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(subs, f, indent=2)
    Path(tmp).replace(SUBS_FILE)

    print(f"\nSubstation updates:")
    print(f"  Matched:   {matched}/{len(subs)}")
    print(f"  Unmatched: {len(unmatched)}")
    print(f"\nData quality breakdown:")
    for q, n in sorted(quality_counts.items()):
        print(f"  {q:<35} {n:>3}")
    if unmatched:
        print(f"\nUnmatched substations (still using fabricated headroom):")
        for name in sorted(unmatched):
            print(f"  {name}")
    print(f"\nSaved: {SUBS_FILE}")
    print(f"\nNext: generating resolution backlog for {len(unmatched)} unmatched substations...")
    generate_resolution_report(subs, lookups)


# ── Resolution backlog ────────────────────────────────────────────────────

# Map each UK substation to its downstream distribution DNO using rough
# geographic bounding boxes. These are the organisations whose open data
# would contain real headroom figures for each NGET node.
_DNO_REGIONS = [
    # (lat_min, lat_max, lng_min, lng_max, dno, data_status, fetch_hint)
    #
    # Evaluation order matters — more specific regions first.
    # SPEN SPD covers central Scotland (NOT loaded — we only have SPM/Merseyside).
    # Fetch from: https://www.spenergynetworks.co.uk/pages/network_planning.aspx
    #   → "Long-Term Development Statement" → GSP technical import limits
    (54.5, 57.5, -6.5, -1.5, "SPEN SPD",  "NOT_LOADED",
     "SPEN SPD (Scotland) technical limits not yet fetched. "
     "Download from spenergynetworks.co.uk → LTDS → GSP winter import limits. "
     "Similar format to spen_spm_technical_limits.json."),
    # SSEN SHEPD — North Scotland (loaded via ssen_headroom_dashboard.csv)
    (56.5, 62.0, -8.0,  0.0, "SSEN SHEPD", "loaded",
     "ssen_headroom_dashboard.csv — filter Substation Type=GSP; "
     "check for grid reference match if name lookup fails"),
    # SPEN SPM — Merseyside, Cheshire, North Wales (loaded)
    (52.0, 54.5, -5.5, -2.0, "SPEN SPM",  "loaded",
     "spen_spm_technical_limits.json — winter import limit, match by name"),
    # ENW — North West England: Lancashire, Cumbria (loaded via coordinate match)
    (53.0, 55.0, -3.6, -1.8, "ENW",        "loaded",
     "enw_gsp_pry_aggregated.json — coordinate-based match; "
     "if still unmatched, download fresh ENW GSP heatmap from enwl.co.uk"),
    # NPG — Yorkshire + North East England (loaded)
    (53.0, 56.0, -2.5,  0.3, "NPG",        "loaded",
     "npg_gsp_heatmap.csv — direct demand headroom; "
     "note NGET sub names often differ from NPG distribution names "
     "(e.g. 'Stella West' NGET → 'Stella North'/'Stella South' NPG)"),
    # UKPN — London, South East, East England (loaded)
    (51.2, 53.5, -0.8,  1.8, "UKPN",       "loaded",
     "ukpn_gsp_processed.json — agreed technical limits; "
     "check UKPN Open Data portal for alternate site names"),
    # SSEN SEPD — South England, Hampshire, Thames Valley (loaded)
    (50.0, 52.5, -1.5,  1.7, "SSEN SEPD",  "loaded",
     "ssen_headroom_dashboard.csv — filter Substation Type=GSP; "
     "Thames Valley 400kV subs (Didcot, Culham) feed SSEN SEPD distribution"),
    # NGED — Midlands, South West England, Wales (loaded)
    (50.0, 54.0, -5.5, -0.5, "NGED",       "loaded",
     "nged_gsp_headroom.csv — technical import limits; "
     "NGET site names often differ from NGED GSP names "
     "(e.g. 'Rugeley' NGET may appear as 'Bishops Wood' or similar in NGED)"),
]

def _infer_dno(lat: float, lng: float) -> tuple[str, str, str]:
    """Return (dno_name, data_status, fetch_hint) for a lat/lng."""
    for lat_min, lat_max, lng_min, lng_max, dno, status, hint in _DNO_REGIONS:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return dno, status, hint
    return "Unknown", "not_loaded", "Check Ofgem DNO area map"


def _name_near_misses(sub_name: str, lookups: dict, top_n: int = 3) -> list[dict]:
    """
    Find the closest DNO dataset entries to sub_name using substring matching.
    Returns up to top_n hits sorted by match quality.

    Requires at least one shared word token to avoid spurious short-string
    substring matches (e.g. "Tealing" containing "ealing").
    """
    query = norm(sub_name)
    query_words = set(query.split())
    hits = []
    for key, data in lookups.items():
        raw = data.get("raw_name", key)
        key_words = set(key.split())
        word_overlap = len(query_words & key_words)
        substring_hit = (query in key or key in query)
        # Only count as a near-miss if at least one whole word matches
        if substring_hit and word_overlap >= 1:
            hits.append({
                "dno":          data.get("dno", "?"),
                "dataset_name": raw,
                "norm_key":     key,
                "headroom_mva": data.get("headroom_mw") or data.get("capacity_mw"),
                "match_type":   "substring",
                "overlap_words": word_overlap,
            })
    hits.sort(key=lambda h: -h["overlap_words"])
    return hits[:top_n]


def _suggested_action(sub: dict, near_misses: list, dno: str, dno_status: str) -> tuple[str, str]:
    """
    Return (suggested_action, resolution_priority).
    Priority is HIGH if the sub has high current score (fabricated headroom
    making it look better than it really is) or many parcels as best_sub.
    """
    parcels = sub.get("_parcels_as_best_sub", 0)
    score50 = sub.get("scores_real", {}).get("50", {}).get("total_score", 0)
    queue_pct = sub.get("real_queue_pressure_pct", 0)

    if near_misses:
        action = (f"Add NAME_MAP entry: '{norm(sub['name'])}' → "
                  f"'{near_misses[0]['norm_key']}' "
                  f"({near_misses[0]['dno']} — {near_misses[0]['dataset_name']})")
    elif dno_status == "loaded":
        action = f"Manual name search in {dno} dataset — sub may use different grid name"
    else:
        action = f"Fetch {dno} headroom data (not yet downloaded)"

    # Priority
    # HIGH: many parcels rely on this sub AND score looks inflated
    #       (score≥70 with fabricated headroom means we can't trust it)
    #       OR a very large number of parcels regardless of score
    if (parcels >= 100 and score50 >= 70) or parcels >= 500:
        priority = "HIGH"
    elif parcels >= 50 or score50 >= 80:
        priority = "MEDIUM"
    else:
        priority = "LOW"     # remote/ex-power-station, few parcels nearby

    return action, priority


def generate_resolution_report(subs: list, lookups: dict):
    """
    Produce a prioritised resolution backlog for all substations that still
    carry fabricated headroom.  Writes data/resolution_backlog.json and
    prints a summary table.

    For each unmatched sub the report records:
      parcels_as_best_sub  — how many of the 63k parcels use this as best_sub
      inferred_dno         — downstream DNO inferred from geography
      name_near_misses     — DNO dataset entries whose name overlaps (quick wins)
      suggested_action     — specific next step to resolve
      resolution_priority  — HIGH / MEDIUM / LOW
    """
    import os

    # ── Count parcel reliance on each unmatched sub ───────────────────
    parcels_file = DATA_DIR / "uk_industrial_parcels.geojson"
    best_sub_counts: dict[str, int] = {}
    if parcels_file.exists():
        print("  Loading parcels to count best_sub reliance... ", end="", flush=True)
        with open(parcels_file) as f:
            parcel_data = json.load(f)
        for feat in parcel_data["features"]:
            bsn = feat["properties"].get("best_sub_name")
            if bsn:
                best_sub_counts[bsn] = best_sub_counts.get(bsn, 0) + 1
        print(f"{sum(best_sub_counts.values()):,} parcel links indexed")
    else:
        print("  (parcels file not found — parcel counts will be 0)")

    # ── Build report entries ──────────────────────────────────────────
    unmatched_subs = [s for s in subs if not s.get("headroom_updated")]
    backlog = []

    for sub in unmatched_subs:
        sub["_parcels_as_best_sub"] = best_sub_counts.get(sub["name"], 0)
        dno, dno_status, fetch_hint = _infer_dno(sub["lat"], sub["lng"])
        near_misses = _name_near_misses(sub["name"], lookups)
        action, priority = _suggested_action(sub, near_misses, dno, dno_status)

        entry = {
            "name":               sub["name"],
            "voltage_kv":         sub.get("voltage_kv"),
            "lat":                sub["lat"],
            "lng":                sub["lng"],
            "tec_queue_mw":       sub.get("tec_queue_mw", 0),
            "fabricated_headroom_mva": sub.get("estimated_headroom_mva", 0),
            "current_score_50":   sub.get("scores_real", {}).get("50", {}).get("total_score", 0),
            "queue_pressure_pct": sub.get("real_queue_pressure_pct", 0),
            "parcels_as_best_sub": sub["_parcels_as_best_sub"],
            "inferred_dno":       dno,
            "dno_data_status":    dno_status,
            "fetch_hint":         fetch_hint,
            "name_near_misses":   near_misses,
            "suggested_action":   action,
            "resolution_priority": priority,
        }
        backlog.append(entry)
        # Write priority back to substation record
        sub["resolution_priority"] = priority
        sub.pop("_parcels_as_best_sub", None)

    # Sort: HIGH first, then by parcels desc, then by score desc
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    backlog.sort(key=lambda e: (
        priority_order[e["resolution_priority"]],
        -e["parcels_as_best_sub"],
        -e["current_score_50"],
    ))

    # ── Save backlog JSON ─────────────────────────────────────────────
    out_path = DATA_DIR / "resolution_backlog.json"
    with open(out_path, "w") as f:
        json.dump({
            "generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "total_unmatched": len(backlog),
            "summary": {
                "HIGH":   sum(1 for e in backlog if e["resolution_priority"] == "HIGH"),
                "MEDIUM": sum(1 for e in backlog if e["resolution_priority"] == "MEDIUM"),
                "LOW":    sum(1 for e in backlog if e["resolution_priority"] == "LOW"),
            },
            "substations": backlog,
        }, f, indent=2)

    # ── Re-save substations with resolution_priority written ─────────
    tmp = str(DATA_DIR / "uk_substations.json") + ".tmp"
    with open(tmp, "w") as f:
        json.dump(subs, f, indent=2)
    Path(tmp).replace(DATA_DIR / "uk_substations.json")

    # ── Print summary table ───────────────────────────────────────────
    print()
    print("=" * 80)
    print("RESOLUTION BACKLOG — unmatched substations ranked by priority")
    print("=" * 80)
    print(f"  {'Sub':<22} {'kV':>4}  {'Parcels':>7}  {'Sc50':>5}  {'Q%':>6}  {'Pri':>6}  Action")
    print(f"  {'-'*22} {'-'*4}  {'-'*7}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*30}")
    for e in backlog:
        nm = e["name_near_misses"]
        action_short = (f"→ map to '{nm[0]['norm_key']}' ({nm[0]['dno']})"
                        if nm else e["suggested_action"][:50])
        print(f"  {e['name']:<22} {e['voltage_kv']:>4.0f}  {e['parcels_as_best_sub']:>7,}  "
              f"{e['current_score_50']:>5.1f}  {e['queue_pressure_pct']:>6.1f}  "
              f"{e['resolution_priority']:>6}  {action_short}")

    print()
    highs = [e for e in backlog if e["resolution_priority"] == "HIGH"]
    if highs:
        print(f"HIGH priority ({len(highs)} subs) — fabricated headroom may be inflating scores")
        print("  for parcels that developers will actually look at. Fix these first.")
    meds = [e for e in backlog if e["resolution_priority"] == "MEDIUM"]
    if meds:
        print(f"MEDIUM priority ({len(meds)} subs) — moderate parcel impact or high current score.")
    lows = [e for e in backlog if e["resolution_priority"] == "LOW"]
    if lows:
        print(f"LOW priority ({len(lows)} subs) — mostly remote ex-power-station sites,")
        print("  few parcels use them as best_sub. Accept fabricated headroom for now.")

    print(f"\nFull backlog: {out_path}")
    print(f"To fix a name mismatch: add the mapping to NAME_MAP in process_dno_headroom.py,")
    print(f"then re-run: python3 scripts/process_dno_headroom.py")
    print(f"             python3 scripts/enrich_power_scores.py")
    print(f"             python3 scripts/enrich_composite_scores.py")
