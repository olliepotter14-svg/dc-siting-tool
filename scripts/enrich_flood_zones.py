"""
enrich_flood_zones.py  (v2 — resumable, polite)

Adds flood_zone and hard_excluded to every parcel by querying the EA OGC API
in 0.1°×0.1° grid cells with a slow request rate to avoid rate-limiting.

Strategy:
  • 5 s delay between API requests (polite — avoids EA DNS blocks)
  • Checkpoint file (data/flood_checkpoint.json) saves progress after each cell
  • DNS/network errors: sleep 10 min then retry same cell (never give up)
  • Parcel file saved every 200 cells so partial progress is preserved
  • Run again after interruption — already-done cells are skipped instantly

Estimated runtime: 6–10 hours for 40k parcels (UK-wide).
Run overnight; you can interrupt and resume at any time.

Usage:
    python3 scripts/enrich_flood_zones.py
"""

import json, math, time, os, urllib.request, urllib.error, socket

PARCELS_FILE    = "data/uk_industrial_parcels.geojson"
OUTPUT_FILE     = "data/uk_industrial_parcels.geojson"
CHECKPOINT_FILE = "data/flood_checkpoint.json"

EA_ITEMS = (
    "https://environment.data.gov.uk/spatialdata"
    "/flood-map-for-planning-flood-zones"
    "/ogc/features/v1/collections"
    "/Flood_Zones_2_3_Rivers_and_Sea/items"
)

CELL_DEG      = 0.1     # ~10 km grid cells
PAGE_SIZE     = 1000
REQ_DELAY     = 5.0     # seconds between requests — very polite
DNS_WAIT      = 600     # seconds to sleep when DNS-blocked (10 min)
SAVE_INTERVAL = 200     # save parcel file every N cells

# EA flood data covers England only.
# Cells clearly outside England are assigned Zone 1 without an API call.
def is_england(lat, lng):
    """True if (lat, lng) is approximately in England (EA coverage area)."""
    if lat > 55.8:                         return False  # Scotland
    if lat > 55.0 and lng < -2.0:          return False  # Scottish borders/highlands
    if lat < 53.5 and lng < -3.0:          return False  # Wales
    if lng < -5.5 and lat > 54.0:          return False  # Northern Ireland
    return True


# ── Geometry helpers ───────────────────────────────────────────────

def centroid(coords):
    x = sum(c[0] for c in coords) / len(coords)
    y = sum(c[1] for c in coords) / len(coords)
    return y, x  # lat, lng

def _flat_coords(geom):
    gtype  = geom.get("type", "")
    coords = geom.get("coordinates", [])
    result = []
    if gtype == "Polygon":
        for ring in coords:
            result.extend(ring)
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                result.extend(ring)
    return result

def _precompute_bbox(feat):
    coords = _flat_coords(feat.get("geometry") or {})
    if not coords:
        return None
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lngs), min(lats), max(lngs), max(lats))

def _point_in_ring(lng, lat, ring):
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside

def point_in_feature(lng, lat, feat):
    bbox = feat.get("_bbox")
    if bbox and (lng < bbox[0] or lng > bbox[2] or lat < bbox[1] or lat > bbox[3]):
        return False
    geom   = feat.get("geometry") or {}
    gtype  = geom.get("type", "")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = coords
    else:
        return False
    for rings in polys:
        if not rings:
            continue
        if _point_in_ring(lng, lat, rings[0]):
            if not any(_point_in_ring(lng, lat, hole) for hole in rings[1:]):
                return True
    return False

def determine_zone(lng, lat, cell_features):
    """Return 1, 2, or 3 for the highest flood zone the point falls in."""
    found_z2 = False
    for feat in cell_features:
        fz = feat.get("properties", {}).get("flood_zone", 2)
        if point_in_feature(lng, lat, feat):
            if fz == 3:
                return 3
            found_z2 = True
    return 2 if found_z2 else 1


# ── API ────────────────────────────────────────────────────────────

def _do_fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "dc-siting-tool/1.0",
        "Accept":     "application/geo+json, application/json",
    })
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_json_resilient(url):
    """Fetch URL with unlimited DNS-block recovery and limited HTTP retries."""
    http_attempts = 0
    while True:
        try:
            time.sleep(REQ_DELAY)
            return _do_fetch(url)
        except (socket.gaierror, OSError) as e:
            msg = str(e).lower()
            if "nodename" in msg or "name or service" in msg or "dns" in msg or "getaddrinfo" in msg:
                print(f"\n  ⚠ DNS block detected — sleeping {DNS_WAIT//60} min and retrying…")
                time.sleep(DNS_WAIT)
            elif "remote end closed" in msg or "connection reset" in msg or "connection aborted" in msg:
                # EA API drops connections periodically — sleep and retry indefinitely
                print(f"\n  ⚠ Connection dropped — sleeping 60s and retrying…", flush=True)
                time.sleep(60)
            else:
                http_attempts += 1
                if http_attempts > 4:
                    raise
                time.sleep(30 * http_attempts)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 504):
                http_attempts += 1
                wait = 60 * http_attempts
                print(f"  HTTP {e.code} — waiting {wait}s…")
                time.sleep(wait)
            else:
                raise
        except Exception:
            http_attempts += 1
            if http_attempts > 3:
                raise
            time.sleep(30)

def fetch_cell(west, south, east, north):
    """Return all flood zone features in this bbox (paginated)."""
    features = []
    offset   = 0
    while True:
        url = (
            f"{EA_ITEMS}?bbox={west:.4f},{south:.4f},{east:.4f},{north:.4f}"
            f"&limit={PAGE_SIZE}&offset={offset}&f=application/geo%2Bjson"
        )
        data  = fetch_json_resilient(url)
        batch = data.get("features", [])
        if not batch:
            break
        for feat in batch:
            raw = feat.get("properties", {}).get("flood_zone", "FZ2")
            feat["properties"]["flood_zone"] = 3 if "3" in str(raw) else 2
            feat["_bbox"] = _precompute_bbox(feat)
        features.extend(batch)
        offset += len(batch)
        if len(batch) < PAGE_SIZE:
            break
    return features


# ── Checkpoint helpers ─────────────────────────────────────────────

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            ck = json.load(f)
        # Convert list to set for O(1) lookup
        ck["done_set"] = set(ck.get("done_cells", []))
        return ck
    return {"done_cells": [], "done_set": set(), "zone_counts": {"1": 0, "2": 0, "3": 0}}

def save_checkpoint(done_cells, zone_counts):
    tmp = CHECKPOINT_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"done_cells": done_cells, "zone_counts": zone_counts}, f)
    os.replace(tmp, CHECKPOINT_FILE)

def save_parcels(geojson):
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)


# ── Main ───────────────────────────────────────────────────────────

def main():
    print("DC Site Finder — EA Flood Zone Enrichment (v2 — resumable)")
    print("=" * 60)
    t0 = time.time()

    with open(PARCELS_FILE) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"Parcels loaded: {len(features):,}")

    # ── Load checkpoint ────────────────────────────────────────────
    ck = load_checkpoint()
    done_set    = ck["done_set"]
    done_cells  = list(done_set)
    zone_counts = {int(k): v for k, v in ck["zone_counts"].items()}
    zone_counts.setdefault(1, 0)
    zone_counts.setdefault(2, 0)
    zone_counts.setdefault(3, 0)

    if done_set:
        print(f"Resuming — {len(done_set)} cells already processed")
    else:
        # First run: initialise all parcels to Zone 1
        for feat in features:
            feat["properties"]["flood_zone"]   = 1
            feat["properties"]["hard_excluded"] = False

    # ── Group parcel centroids by grid cell ────────────────────────
    cells = {}
    for i, feat in enumerate(features):
        coords = feat["geometry"]["coordinates"][0]
        plat, plng = centroid(coords)
        cx = int(plng / CELL_DEG)
        cy = int(plat / CELL_DEG)
        cells.setdefault((cx, cy), []).append((i, plng, plat))

    total_cells  = len(cells)
    remaining    = [(k, v) for k, v in sorted(cells.items()) if f"{k[0]},{k[1]}" not in done_set]
    print(f"Grid cells: {total_cells} total, {len(remaining)} remaining")
    print(f"Estimated time at {REQ_DELAY}s/request: see progress below")
    print()

    api_calls    = 0
    cells_done   = len(done_set)
    last_save    = cells_done
    t_batch      = time.time()

    for (cx, cy), parcel_list in remaining:
        cell_key = f"{cx},{cy}"
        west  = cx  * CELL_DEG
        east  = (cx + 1) * CELL_DEG
        south = cy  * CELL_DEG
        north = (cy + 1) * CELL_DEG

        # Skip API call for cells outside England (EA data only covers England)
        cell_lat = (south + north) / 2
        cell_lng = (west + east) / 2
        if not is_england(cell_lat, cell_lng):
            cell_feats = []   # Zone 1 default — no API call needed
        else:
            cell_feats = fetch_cell(west, south, east, north)
            n_pages    = max(1, math.ceil(len(cell_feats) / PAGE_SIZE)) if cell_feats else 1
            api_calls += n_pages

        for parcel_idx, plng, plat in parcel_list:
            zone = determine_zone(plng, plat, cell_feats) if cell_feats else 1
            p = features[parcel_idx]["properties"]
            p["flood_zone"]   = zone
            p["hard_excluded"] = (zone == 3)
            zone_counts[zone] = zone_counts.get(zone, 0) + 1

        cells_done += 1
        done_cells.append(cell_key)
        save_checkpoint(done_cells, {str(k): v for k, v in zone_counts.items()})

        # Save parcels every SAVE_INTERVAL cells
        if cells_done - last_save >= SAVE_INTERVAL:
            save_parcels(geojson)
            last_save = cells_done

        # Progress every 25 cells
        if cells_done % 25 == 0 or cells_done == total_cells:
            elapsed  = time.time() - t_batch
            rate     = 25 / elapsed if elapsed > 0 else 1
            remain   = (total_cells - cells_done) / rate if rate > 0 else 0
            z_str    = f"Z1:{zone_counts[1]:,} Z2:{zone_counts[2]:,} Z3:{zone_counts[3]:,}"
            eta_h    = remain / 3600
            print(f"  Cell {cells_done:>4}/{total_cells}  api:{api_calls:>5}  {z_str}  "
                  f"ETA:{eta_h:.1f}h")
            t_batch = time.time()

    # ── Final save ─────────────────────────────────────────────────
    save_parcels(geojson)

    elapsed_total = time.time() - t0
    size_mb = os.path.getsize(OUTPUT_FILE) / 1e6
    print(f"\nDone in {elapsed_total/60:.1f}min — {OUTPUT_FILE} ({size_mb:.1f} MB)")
    print(f"Total API calls: {api_calls}")
    print()

    total = len(features)
    print("Flood zone distribution:")
    for z in (1, 2, 3):
        n     = zone_counts.get(z, 0)
        label = {1: "Zone 1 (low risk)", 2: "Zone 2 (medium)", 3: "Zone 3 (high/excl)"}[z]
        bar   = "█" * (n * 30 // total) if total else ""
        print(f"  {label:<25}  {bar:<30} {n:>6,}  ({100*n/total:.1f}%)")

    # Clean up checkpoint on success
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("\nCheckpoint file removed (run complete).")

    print("\nRun  python3 scripts/enrich_composite_scores.py  to update composite scores.")


if __name__ == "__main__":
    main()
