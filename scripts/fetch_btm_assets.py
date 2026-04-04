"""
fetch_btm_assets.py

Fetches HV substation assets from DNO Open Data portals.
Produces data/uk_btm_assets.json — used by enrich_power_scores.py for
behind-the-meter (BTM) power scoring.

Coverage:
  Phase 1: UKPN   — London, South East, East England (EPN/SPN/LPN)
  Phase 2: SPEN   — Scotland (SPD) + Wales/NW England (SPM)
  Phase 3: NPg    — Yorkshire + North East England (no auth required)
  Phase 4: ENW    — NW England (auth required, portal TBC)
             SSEN  — South England + Scottish Highlands (no opendatasoft portal found)
             NGED  — Midlands + South West + South Wales (no opendatasoft portal found)

Voltage thresholds:
  ≥132kV  → hv_substation_132  (Grid Supply Points / transmission interface)
    66kV  → hv_substation_66   (UKPN-area legacy industrial tier, rare)
    <66kV → excluded           (too common, dilutes BTM signal)

Usage:
    python3 scripts/fetch_btm_assets.py

API keys: stored in ~/.claude/projects/.../memory/reference_api_keys.md
          NEVER commit keys to git.
"""

import csv
import json
import math
import os
import subprocess
import time
import urllib.request

OUT_FILE = "data/uk_btm_assets.json"
PAGE_SIZE = 100

# ── UKPN credentials ───────────────────────────────────────────────
UKPN_KEY  = "677496f0f0ca22854e1f1436faf14bd1c279b1316f658304899cbbeb"
UKPN_BASE = "https://ukpowernetworks.opendatasoft.com/api/explore/v2.1/catalog/datasets"
UKPN_DATASETS = [
    "ukpn-primary-transformers",   # 33kV / 66kV primaries
    "ukpn-grid-transformers",      # 132kV grid substations
]

# ── NGED credentials (CKAN portal) ──────────────────────────────
NGED_TOKEN = ("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJuZVZNVW9Zem"
              "NEanBieHpiVHo3R2JKNVR5cVh0eFIwRVFlZFZiSk9KLWRmU0R2UWZFN29w"
              "RDNfOERKcjkzd0hRekpSQk45NFptQUt0RjNtLSIsImlhdCI6MTc3NTI0MjA1"
              "OX0.Z0PdwNojgid9AbyynbTdBOriQbqwmbGCU-dCjiVn00g")
NGED_CKAN  = "https://connecteddata.nationalgrid.co.uk/api/3/action"
NGED_CAP_RID = "d1895bd3-d9d2-4886-a0a3-b7eadd9ab6c2"  # network capacity map

# ── Northern Powergrid credentials ────────────────────────────────
NPG_BASE = "https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/datasets"
# No auth required — public portal
# Filter: type in (GSP, BSP) AND pvoltage >= 66 to exclude 33kV/11kV primaries

# ── ENW credentials ─────────────────────────────────────────────────
ENW_KEY  = "fa41a277161a3cfd8a47f73be78e93c5e962efc46a71940bdad7ade2"
ENW_BASE = "https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets"

# ── SPEN credentials ───────────────────────────────────────────────
SPEN_KEY  = "f2254665c4cc8118f84df6c1d561e42c3441640398dd6b4ad226e766"
SPEN_BASE = "https://spenergynetworks.opendatasoft.com/api/explore/v2.1/catalog/datasets"
# DFES polygon datasets contain GSP-level centroids with lat/lng
SPEN_DFES_DATASETS = [
    ("spm-dfes-site-forecasts-polygons", "SPM"),   # SP Manweb: Wales + NW England
    ("spd-dfes-site-forecasts-polygons", "SPD"),   # SP Distribution: Scotland
]


# ── SSEN — downloaded CSV (Cloudflare blocks API access) ───────────
SSEN_CSV = "data/ssen_substation_locations.csv"
# Filter: Class contains "132kV" OR (Type is Grid/Bulk Supply pt AND Class is Transmission)
# Coordinates in BNG (Easting/Northing) → need conversion to WGS84


def bng_to_wgs84(easting, northing):
    """Convert British National Grid (OSGB36) to WGS84 lat/lng. ~5m accuracy."""
    a, b = 6377563.396, 6356256.909
    F0 = 0.9996012717
    lat0, lon0 = math.radians(49), math.radians(-2)
    N0, E0 = -100000, 400000
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)

    lat = lat0
    M = 0
    for _ in range(20):
        lat = (northing - N0 - M) / (a * F0) + lat
        Ma = (1 + n + 1.25 * n**2 + 1.25 * n**3) * (lat - lat0)
        Mb = (3*n + 3*n**2 + 2.625*n**3) * math.sin(lat-lat0) * math.cos(lat+lat0)
        Mc = (1.875*n**2 + 1.875*n**3) * math.sin(2*(lat-lat0)) * math.cos(2*(lat+lat0))
        Md = (35/24)*n**3 * math.sin(3*(lat-lat0)) * math.cos(3*(lat+lat0))
        M = b * F0 * (Ma - Mb + Mc - Md)
        if abs(northing - N0 - M) < 0.00001:
            break

    sinLat = math.sin(lat)
    cosLat = math.cos(lat)
    tanLat = math.tan(lat)
    nu  = a * F0 / math.sqrt(1 - e2 * sinLat**2)
    rho = a * F0 * (1 - e2) / (1 - e2 * sinLat**2)**1.5
    eta2 = nu / rho - 1
    dE = easting - E0

    VII  = tanLat / (2 * rho * nu)
    VIII = tanLat / (24 * rho * nu**3) * (5 + 3*tanLat**2 + eta2 - 9*tanLat**2*eta2)
    IX   = tanLat / (720 * rho * nu**5) * (61 + 90*tanLat**2 + 45*tanLat**4)
    X    = 1 / (cosLat * nu)
    XI   = 1 / (6 * cosLat * nu**3) * (nu/rho + 2*tanLat**2)
    XII  = 1 / (120 * cosLat * nu**5) * (5 + 28*tanLat**2 + 24*tanLat**4)

    return (math.degrees(lat - VII*dE**2 + VIII*dE**4 - IX*dE**6),
            math.degrees(lon0 + X*dE - XI*dE**3 + XII*dE**5))


# ── UKPN voltage classification ────────────────────────────────────
def classify_voltage(voltage_kv):
    if voltage_kv is None:
        return None
    if voltage_kv >= 132:
        return "hv_substation_132"
    if voltage_kv >= 66:
        return "hv_substation_66"
    return None   # <66kV — excluded


def fetch_paginated(url_template, total_key="total_count", results_key="results"):
    """Generic paginator for OpenDataSoft APIs."""
    records = []
    offset  = 0
    total   = None

    while True:
        url = url_template.format(offset=offset)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"  ERROR at offset={offset}: {e}")
            break

        if total is None:
            total = data.get(total_key, 0)

        batch = data.get(results_key, [])
        records.extend(batch)
        offset += len(batch)

        if not batch or offset >= total:
            break

        time.sleep(0.2)

    return records, total


# ─────────────────────────────────────────────────────────────────────
# PHASE 1: UKPN
# ─────────────────────────────────────────────────────────────────────
def fetch_ukpn():
    print("\n── Phase 1: UKPN (London / South East / East England) ──")
    all_records = []
    for ds_id in UKPN_DATASETS:
        print(f"  Fetching {ds_id}…")
        url_tpl = (f"{UKPN_BASE}/{ds_id}/records/"
                   f"?limit={PAGE_SIZE}&offset={{offset}}&apikey={UKPN_KEY}")
        recs, total = fetch_paginated(url_tpl)
        print(f"  → {len(recs)} / {total} records")
        all_records.extend(recs)

    # De-duplicate by sitefunctionallocation
    seen = {}
    for rec in all_records:
        site_id = rec.get("sitefunctionallocation", "")
        if not site_id or site_id in seen:
            continue
        seen[site_id] = rec

    assets = []
    skipped = 0
    for site_id, rec in seen.items():
        voltage = rec.get("primary_winding_voltage") or rec.get("operationalvoltage")
        asset_type = classify_voltage(voltage)
        if asset_type is None:
            skipped += 1
            continue

        coords = rec.get("spatial_coordinates") or {}
        lat = coords.get("lat")
        lng = coords.get("lon")
        if lat is None or lng is None:
            continue

        assets.append({
            "lat":        float(lat),
            "lng":        float(lng),
            "name":       rec.get("sitedesc") or rec.get("functionallocationname") or site_id,
            "type":       asset_type,
            "voltage_kv": int(voltage) if voltage else None,
            "onan_kva":   rec.get("onanrating_kva"),
            "dno":        rec.get("dno") or "UKPN",
            "source":     "ukpn",
        })

    by_type = {}
    for a in assets:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
    print(f"  UKPN assets retained: {len(assets)} "
          f"({by_type.get('hv_substation_132', 0)} × 132kV, "
          f"{by_type.get('hv_substation_66', 0)} × 66kV)")
    return assets


# ─────────────────────────────────────────────────────────────────────
# PHASE 2: SPEN
# ─────────────────────────────────────────────────────────────────────
def fetch_spen():
    """
    Fetch SPEN 132kV Grid Supply Points from the DFES polygon datasets.
    Each polygon has a centroid (geo_point_2d) and substation_level field.
    We keep only GSP-level records (= 132kV interface with transmission).
    SPEN does not use 66kV (uses 132 → 33kV stepping), so no 66kV tier here.
    """
    print("\n── Phase 2: SPEN (Scotland / Wales / NW England) ──")
    assets = []
    seen_names = set()

    for ds_id, licence_area in SPEN_DFES_DATASETS:
        print(f"  Fetching {ds_id} ({licence_area})…")
        url_tpl = (f"{SPEN_BASE}/{ds_id}/records/"
                   f"?limit={PAGE_SIZE}&offset={{offset}}&apikey={SPEN_KEY}")
        recs, total = fetch_paginated(url_tpl)
        gsps = [r for r in recs if r.get("substation_level") == "GSP"]
        print(f"  → {total} total records, {len(gsps)} GSPs")

        for rec in gsps:
            name = rec.get("substation_name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            pt = rec.get("geo_point_2d", {})
            lat = pt.get("lat")
            lng = pt.get("lon")
            if lat is None or lng is None:
                continue

            assets.append({
                "lat":        float(lat),
                "lng":        float(lng),
                "name":       name,
                "type":       "hv_substation_132",
                "voltage_kv": 132,
                "onan_kva":   None,
                "dno":        licence_area,
                "source":     "spen",
            })

    print(f"  SPEN assets retained: {len(assets)} × 132kV GSPs")
    return assets


# ─────────────────────────────────────────────────────────────────────
# PHASE 3: ENW (Electricity North West)
# ─────────────────────────────────────────────────────────────────────
def fetch_enw():
    """
    Fetch GSP-level substations from ENW's substation hierarchy dataset.
    Covers Greater Manchester, Lancashire, Cumbria, Cheshire, Merseyside.
    Filter: substation_group == "GSP" (all are 132kV+ infeed).
    ENW has no 66kV tier — uses 132kV → 33kV stepping.
    GSPs only have numeric IDs, no human-readable names.
    """
    print("\n── Phase 3: ENW (Greater Manchester / Lancashire / Cumbria) ──")

    import urllib.parse
    where = urllib.parse.quote('substation_group="GSP"')
    url_tpl = (f"{ENW_BASE}/sp-enw-substation-hierarchy/records/"
               f"?limit={PAGE_SIZE}&offset={{offset}}"
               f"&where={where}&apikey={ENW_KEY}")

    recs, total = fetch_paginated(url_tpl)
    print(f"  → {total} GSP records")

    assets = []
    for rec in recs:
        pt = rec.get("geopoint") or {}
        lat = pt.get("lat")
        lng = pt.get("lon")
        if lat is None or lng is None:
            continue

        assets.append({
            "lat":        float(lat),
            "lng":        float(lng),
            "name":       f"ENW GSP {rec.get('substation_number', '?')}",
            "type":       "hv_substation_132",
            "voltage_kv": 132,
            "onan_kva":   None,
            "dno":        "ENW",
            "source":     "enw",
        })

    print(f"  ENW assets retained: {len(assets)} × 132kV GSPs")
    return assets


# ─────────────────────────────────────────────────────────────────────
# PHASE 4: Northern Powergrid
# ─────────────────────────────────────────────────────────────────────
def fetch_npg():
    """
    Fetch HV substation nodes from Northern Powergrid's heatmap dataset.
    Covers Yorkshire (NPgY) and North East (NPgNE) licence areas.

    Dataset: heatmapsubstationareas
    Filter: type in (GSP, BSP) AND pvoltage >= 66
      GSP 132kV → hv_substation_132
      GSP  66kV → hv_substation_66   (legacy 66kV GSPs in NPg area)
      BSP  66kV → hv_substation_66   (bulk supply points at 66kV — rare)
    No API key required.
    """
    print("\n── Phase 3: Northern Powergrid (Yorkshire / North East) ──")

    where = 'type in ("GSP","BSP") AND pvoltage >= 66'
    import urllib.parse
    url_tpl = (f"{NPG_BASE}/heatmapsubstationareas/records/"
               f"?limit={PAGE_SIZE}&offset={{offset}}"
               f"&where={urllib.parse.quote(where)}")

    recs, total = fetch_paginated(url_tpl)
    print(f"  → {total} HV records (GSP+BSP ≥66kV)")

    assets = []
    for rec in recs:
        loc = rec.get("substation_location") or {}
        lat = loc.get("lat")
        lng = loc.get("lon")
        if lat is None or lng is None:
            continue

        voltage = rec.get("pvoltage")
        asset_type = classify_voltage(int(voltage) if voltage else 0)
        if asset_type is None:
            continue

        assets.append({
            "lat":        float(lat),
            "lng":        float(lng),
            "name":       rec.get("name", ""),
            "type":       asset_type,
            "voltage_kv": int(voltage) if voltage else None,
            "onan_kva":   None,
            "dno":        f"NPg{rec.get('licence_area', '')}",
            "source":     "npg",
        })

    by_type = {}
    for a in assets:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
    print(f"  NPg assets retained: {len(assets)} "
          f"({by_type.get('hv_substation_132', 0)} × 132kV, "
          f"{by_type.get('hv_substation_66', 0)} × 66kV)")
    return assets


# ─────────────────────────────────────────────────────────────────────
# PHASE 5: NGED (National Grid Electricity Distribution)
# ─────────────────────────────────────────────────────────────────────
def fetch_nged():
    """
    Fetch BSP (Bulk Supply Point) substations from NGED's CKAN network capacity dataset.
    Covers: East Midlands, West Midlands, South West, South Wales.
    BSPs are 132kV/33kV interface points — the relevant tier for BTM detection.
    No GSP type in this dataset (they're upstream, National Grid-operated).
    """
    print("\n── Phase 5: NGED (Midlands / South West / South Wales) ──")

    assets = []
    offset = 0
    total  = None
    import urllib.parse

    while True:
        filters = urllib.parse.quote(json.dumps({"type": "BSP"}))
        url = (f"{NGED_CKAN}/datastore_search"
               f"?resource_id={NGED_CAP_RID}"
               f"&filters={filters}&limit={PAGE_SIZE}&offset={offset}")
        try:
            # Use curl — urllib gets Cloudflare-blocked on this endpoint
            result = subprocess.run(
                ["curl", "-s", "--max-time", "30",
                 "-H", f"Authorization: {NGED_TOKEN}", url],
                capture_output=True, text=True)
            data = json.loads(result.stdout)
        except Exception as e:
            print(f"  ERROR at offset={offset}: {e}")
            break

        result_data = data.get("result", {})
        if total is None:
            total = result_data.get("total", 0)

        recs = result_data.get("records", [])
        for rec in recs:
            lat = rec.get("latitude")
            lng = rec.get("longitude")
            if lat is None or lng is None or lat == "" or lng == "":
                continue
            assets.append({
                "lat":        float(lat),
                "lng":        float(lng),
                "name":       rec.get("name", ""),
                "type":       "hv_substation_132",
                "voltage_kv": 132,
                "onan_kva":   None,
                "dno":        f"NGED {rec.get('area', '')}".strip(),
                "source":     "nged",
            })

        offset += len(recs)
        print(f"  {offset}/{total} BSPs fetched")
        if not recs or offset >= total:
            break
        time.sleep(0.2)

    print(f"  NGED assets retained: {len(assets)} × 132kV BSPs")
    return assets


# ─────────────────────────────────────────────────────────────────────
# PHASE 6: SSEN (from downloaded CSV — Cloudflare blocks API)
# ─────────────────────────────────────────────────────────────────────
def fetch_ssen():
    """
    Load SSEN substation locations from a manually downloaded CSV.
    SSEN covers: SEPD (South England: Hampshire, Berkshire, Oxfordshire, etc.)
                 SHEPD (Scottish Highlands & Islands)

    Filter: Class contains '132kV' OR (Type is Grid/Bulk Supply pt AND
            Class is Transmission). These represent 132kV grid infrastructure.

    Coordinates are British National Grid (Easting/Northing) → convert to WGS84.
    De-duplicate by rounding to ~100m grid to collapse co-located records.
    """
    print("\n── Phase 5: SSEN (South England / Scottish Highlands) ──")

    if not os.path.exists(SSEN_CSV):
        print(f"  WARNING: {SSEN_CSV} not found — download from:")
        print("    https://data.ssen.co.uk/@ssen-distribution/ssen-substation-data")
        print("  Then copy CSV to data/ssen_substation_locations.csv")
        return []

    with open(SSEN_CSV) as f:
        reader = csv.DictReader(f)
        raw = []
        for row in reader:
            t = row.get("Type", "")
            c = row.get("Class", "")
            # Keep 132kV+ infrastructure
            if "132" not in c and not (t in ("Grid/Bulk Supply pt", "Supergrid")
                                       and c == "Transmission"):
                continue
            try:
                e = float(row.get("Location X (m)", 0))
                n = float(row.get("Location Y (m)", 0))
            except (ValueError, TypeError):
                continue
            if e == 0 or n == 0:
                continue
            raw.append((row, e, n))

    print(f"  Raw 132kV+ records: {len(raw)}")

    # De-duplicate by rounding to ~100m grid
    seen = {}
    assets = []
    for row, easting, northing in raw:
        grid_key = (round(easting, -2), round(northing, -2))
        if grid_key in seen:
            continue
        seen[grid_key] = True

        lat, lng = bng_to_wgs84(easting, northing)
        locality = row.get("Locality", "").strip()
        owner    = row.get("Owner Name", "SSEN").strip()
        sub_type = row.get("Type", "")

        assets.append({
            "lat":        round(lat, 6),
            "lng":        round(lng, 6),
            "name":       f"{locality} ({sub_type})" if locality else sub_type,
            "type":       "hv_substation_132",
            "voltage_kv": 132,
            "onan_kva":   None,
            "dno":        owner,
            "source":     "ssen",
        })

    print(f"  SSEN assets retained (de-duped ~100m): {len(assets)} × 132kV")
    return assets


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def main():
    print("DC Site Finder — BTM Asset Fetch (6 DNOs)")
    print("=" * 65)

    ukpn_assets = fetch_ukpn()
    spen_assets = fetch_spen()
    enw_assets  = fetch_enw()
    npg_assets  = fetch_npg()
    nged_assets = fetch_nged()
    ssen_assets = fetch_ssen()

    all_assets = ukpn_assets + spen_assets + enw_assets + npg_assets + nged_assets + ssen_assets
    print(f"\nTotal assets: {len(all_assets)}")

    # ── Summary by source + type ───────────────────────────────────
    by_source = {}
    for a in all_assets:
        key = f"{a['source'].upper()} {a['type']}"
        by_source[key] = by_source.get(key, 0) + 1
    print("\nBreakdown:")
    label_map = {
        "hv_substation_132": "132kV grid substations",
        "hv_substation_66":  "66kV primary substations",
    }
    for k, n in sorted(by_source.items()):
        src, typ = k.split(" ", 1)
        print(f"  {src:<6}  {label_map.get(typ, typ):<35} {n:>4}")

    # ── Save ───────────────────────────────────────────────────────
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(all_assets, f, separators=(",", ":"))
    os.replace(tmp, OUT_FILE)

    size_kb = os.path.getsize(OUT_FILE) / 1024
    print(f"\nSaved: {OUT_FILE} ({size_kb:.1f} KB, {len(all_assets)} sites)")
    print("\nSample records:")
    for a in all_assets[:3]:
        print(f"  [{a['source'].upper():<4}] {a['name']:<40} {a['type']}  {a['voltage_kv']}kV  "
              f"({a['lat']:.4f}, {a['lng']:.4f})")

    print("\nNext step: python3 scripts/enrich_power_scores.py")


if __name__ == "__main__":
    main()
