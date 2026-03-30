"""
generate_waterfall.py

Generates a standalone HTML waterfall/funnel chart showing the site selection
process from all UK OSM parcels down to composite 90+ sites sized for a 100MW DC.

Usage:
    python3 scripts/generate_waterfall.py
    open dc_waterfall.html
"""

import json, os, datetime

PARCELS_FILE = "data/uk_industrial_parcels.geojson"
OUTPUT_FILE  = "dc_waterfall_auto.html"

# 100MW DC land requirement: ~200 acres minimum campus
MW100_ACRES = 200

# "Previously developed" types — viable for DC without change-of-use from greenfield
DEVELOPED_TYPES = {"industrial", "brownfield", "power", "extraction",
                   "transport", "aviation", "military", "commercial"}


def main():
    with open(PARCELS_FILE) as f:
        feats = json.load(f)["features"]

    total = len(feats)

    # ── Build funnel stages ───────────────────────────────────────
    # Each stage filters the previous remaining set
    remaining = feats[:]

    stages = []
    stages.append(("All UK land parcels (OSM)", total, "start",
                   "Brownfield, industrial, agricultural, military, aviation and other land types across all 13 UK regions"))

    # Stage 1: Flood Zone 3
    flood3 = [f for f in remaining if f["properties"].get("flood_zone", 1) == 3]
    remaining = [f for f in remaining if f["properties"].get("flood_zone", 1) != 3]
    stages.append(("Remove Flood Zone 3", len(flood3), "exclude",
                   f"High flood risk — uninhabitable for critical infrastructure. {len(flood3):,} parcels excluded."))

    # Stage 2: Statutory protected designations
    prot = [f for f in remaining if f["properties"].get("hard_excluded") and
            f["properties"].get("flood_zone", 1) != 3]
    remaining = [f for f in remaining if not f["properties"].get("hard_excluded")]
    stages.append(("Remove statutory designations", len(prot), "exclude",
                   f"National Parks, AONBs, SSSIs, SACs, SPAs, Ancient Woodland, Scheduled Monuments etc. {len(prot):,} parcels excluded."))

    after_excl = len(remaining)

    # Stage 3: Below 100MW size threshold
    too_small = [f for f in remaining if f["properties"].get("area_acres", 0) < MW100_ACRES]
    remaining = [f for f in remaining if f["properties"].get("area_acres", 0) >= MW100_ACRES]
    stages.append((f"Remove < {MW100_ACRES} acres", len(too_small), "size",
                   f"Minimum {MW100_ACRES} acres required for a 100MW campus. {len(too_small):,} parcels below threshold."))

    after_size = len(remaining)

    # Stage 4: Farmland (requires change of use, higher planning risk)
    farmland = [f for f in remaining if f["properties"].get("site_type") == "farmland"]
    remaining_dev = [f for f in remaining if f["properties"].get("site_type") != "farmland"]
    stages.append(("Set aside farmland", len(farmland), "deprioritise",
                   f"Agricultural land requires change of use — significantly higher planning risk and timeline. {len(farmland):,} parcels set aside (still scoreable)."))

    after_dev = len(remaining_dev)

    # Stage 5: Green Belt (undeveloped) — not excluded, but flagged
    gb_hard = [f for f in remaining_dev
               if f["properties"].get("green_belt") and not f["properties"].get("grey_belt")]
    gb_grey = [f for f in remaining_dev if f["properties"].get("grey_belt")]
    stages.append(("Green Belt context", 0, "info",
                   f"{len(gb_grey):,} Grey Belt (brownfield within Green Belt — CNI opportunity) · "
                   f"{len(gb_hard):,} undeveloped Green Belt (significant planning hurdle, not excluded)"))

    # Stage 6: Composite score ≥ 50
    score50 = [f for f in remaining_dev if f["properties"].get("composite_score_100", 0) >= 50]
    below50 = [f for f in remaining_dev if f["properties"].get("composite_score_100", 0) < 50]
    remaining_dev = score50
    stages.append(("Composite score ≥ 50", len(below50), "score",
                   f"Minimum viability threshold across power, fibre, flood, planning, buildability and market proximity. {len(below50):,} parcels below threshold."))

    # Stage 7: Composite score ≥ 70
    score70 = [f for f in remaining_dev if f["properties"].get("composite_score_100", 0) >= 70]
    below70 = [f for f in remaining_dev if f["properties"].get("composite_score_100", 0) < 70]
    remaining_dev = score70
    stages.append(("Composite score ≥ 70", len(below70), "score",
                   f"Strong candidates with good grid headroom, fibre connectivity and market proximity. {len(below70):,} parcels below threshold."))

    # Stage 8: Composite score ≥ 90
    score90 = [f for f in remaining_dev if f["properties"].get("composite_score_100", 0) >= 90]
    below90 = [f for f in remaining_dev if f["properties"].get("composite_score_100", 0) < 90]
    remaining_dev = score90
    stages.append(("Composite score ≥ 90", len(below90), "score",
                   f"Priority targets — top-tier on all six dimensions. {len(below90):,} parcels below threshold."))

    final = len(remaining_dev)
    stages.append((f"Priority 100MW sites", final, "end",
                   f"Composite 90+ sites ≥ {MW100_ACRES} acres on previously developed land — top-tier for 100MW DC investment analysis"))

    # ── Breakdown of final sites ──────────────────────────────────
    from collections import Counter
    type_breakdown = Counter(f["properties"].get("site_type") for f in remaining_dev)
    region_breakdown = Counter(f["properties"].get("region") for f in remaining_dev)

    # ── Build running totals for chart ────────────────────────────
    running = total
    chart_data = []
    for label, removed, kind, desc in stages:
        if kind == "start":
            chart_data.append({"label": label, "value": running, "removed": 0,
                                "kind": kind, "desc": desc})
        elif kind == "end":
            chart_data.append({"label": label, "value": running, "removed": 0,
                                "kind": kind, "desc": desc})
        elif kind == "info":
            chart_data.append({"label": label, "value": running, "removed": 0,
                                "kind": kind, "desc": desc})
        elif kind == "deprioritise":
            # Don't subtract from running total — farmland still exists, just set aside
            chart_data.append({"label": label, "value": running, "removed": removed,
                                "kind": kind, "desc": desc})
        else:
            running -= removed
            chart_data.append({"label": label, "value": running, "removed": removed,
                                "kind": kind, "desc": desc})

    # ── Render HTML ───────────────────────────────────────────────
    type_rows = "".join(
        f'<tr><td>{t.title()}</td><td>{n}</td></tr>'
        for t, n in type_breakdown.most_common()
    )
    region_rows = "".join(
        f'<tr><td>{r or "Unknown"}</td><td>{n}</td></tr>'
        for r, n in region_breakdown.most_common()
    )

    generated = datetime.datetime.now().strftime("%d %b %Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DC Site Selection Waterfall — 100MW</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 40px 24px; }}
  h1 {{ font-size: 22px; font-weight: 600; color: #f8fafc; margin-bottom: 4px; }}
  .subtitle {{ font-size: 13px; color: #64748b; margin-bottom: 36px; }}
  .waterfall {{ width: 100%; max-width: 960px; margin: 0 auto; }}
  .stage {{ display: flex; align-items: stretch; margin-bottom: 3px; cursor: default;
            border-radius: 6px; overflow: hidden; transition: filter 0.15s; }}
  .stage:hover {{ filter: brightness(1.1); }}
  .stage-label {{ width: 280px; flex-shrink: 0; padding: 10px 14px;
                  font-size: 13px; font-weight: 500; display: flex;
                  align-items: center; background: #1e2535; }}
  .bar-wrap {{ flex: 1; display: flex; align-items: center;
               background: #161b27; padding: 6px 10px; gap: 10px; }}
  .bar-outer {{ flex: 1; height: 28px; background: #1e2535; border-radius: 4px; overflow: hidden; }}
  .bar-inner {{ height: 100%; border-radius: 4px; transition: width 0.3s ease; }}
  .bar-value {{ font-size: 13px; font-weight: 600; white-space: nowrap; min-width: 70px; text-align: right; }}
  .bar-removed {{ font-size: 12px; color: #ef4444; white-space: nowrap; min-width: 80px; }}
  .tooltip {{ font-size: 11px; color: #94a3b8; padding: 4px 10px 8px 280px; margin-top: -3px;
              margin-bottom: 8px; max-width: 960px; line-height: 1.5; }}

  /* colour palette by kind */
  .kind-start  .stage-label {{ color: #60a5fa; }}
  .kind-start  .bar-inner   {{ background: #2563eb; }}
  .kind-start  .bar-value   {{ color: #60a5fa; }}

  .kind-exclude .stage-label {{ color: #f87171; }}
  .kind-exclude .bar-inner   {{ background: #dc2626; }}
  .kind-exclude .bar-value   {{ color: #f87171; }}

  .kind-size  .stage-label {{ color: #fb923c; }}
  .kind-size  .bar-inner   {{ background: #ea580c; }}
  .kind-size  .bar-value   {{ color: #fb923c; }}

  .kind-deprioritise .stage-label {{ color: #facc15; }}
  .kind-deprioritise .bar-inner   {{ background: #ca8a04; }}
  .kind-deprioritise .bar-value   {{ color: #facc15; }}

  .kind-info  .stage-label {{ color: #a78bfa; }}
  .kind-info  .bar-inner   {{ background: #7c3aed; }}
  .kind-info  .bar-value   {{ color: #a78bfa; }}

  .kind-score .stage-label {{ color: #34d399; }}
  .kind-score .bar-inner   {{ background: #059669; }}
  .kind-score .bar-value   {{ color: #34d399; }}

  .kind-end   .stage-label {{ color: #fbbf24; font-weight: 700; }}
  .kind-end   .bar-inner   {{ background: linear-gradient(90deg, #d97706, #fbbf24); }}
  .kind-end   .bar-value   {{ color: #fbbf24; font-weight: 700; font-size: 15px; }}

  .tables {{ max-width: 960px; margin: 40px auto 0; display: grid;
             grid-template-columns: 1fr 1fr; gap: 20px; }}
  .tbl {{ background: #1e2535; border-radius: 8px; padding: 16px; }}
  .tbl h3 {{ font-size: 13px; color: #94a3b8; font-weight: 500; margin-bottom: 10px;
             text-transform: uppercase; letter-spacing: 0.05em; }}
  .tbl table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .tbl td {{ padding: 5px 8px; border-bottom: 1px solid #2d3a4f; }}
  .tbl td:last-child {{ text-align: right; font-weight: 600; color: #fbbf24; }}
  .meta {{ max-width: 960px; margin: 12px auto 0; font-size: 11px; color: #475569; }}
</style>
</head>
<body>
<div class="waterfall">
  <h1>UK Data Centre Site Selection — 100MW Funnel</h1>
  <p class="subtitle">From {total:,} UK land parcels to composite 90+ sites of ≥{MW100_ACRES} acres · Generated {generated}</p>
"""

    max_val = total
    for d in chart_data:
        pct = d["value"] / max_val * 100
        kind = d["kind"]
        removed_str = f'−{d["removed"]:,}' if d["removed"] > 0 else ""
        value_str = f'{d["value"]:,}' if kind != "info" else ""

        html += f"""
  <div class="stage kind-{kind}">
    <div class="stage-label">{d["label"]}</div>
    <div class="bar-wrap">
      <div class="bar-outer">
        <div class="bar-inner" style="width:{pct:.1f}%"></div>
      </div>
      <div class="bar-value">{value_str}</div>
      <div class="bar-removed">{removed_str}</div>
    </div>
  </div>
  <div class="tooltip">{d["desc"]}</div>
"""

    html += f"""
</div>
<div class="tables">
  <div class="tbl">
    <h3>Priority sites by type</h3>
    <table>{type_rows}</table>
  </div>
  <div class="tbl">
    <h3>Priority sites by region</h3>
    <table>{region_rows}</table>
  </div>
</div>
<p class="meta">Composite score = weighted average of power (35%), fibre (20%), flood risk (15%), planning (15%), buildability (10%), market proximity (5%) · Green Belt sites carry planning score penalty (55–80%) · Farmland set aside, not excluded · Data: OSM · EA Flood Map · planning.data.gov.uk</p>
</body>
</html>"""

    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    print(f"Waterfall saved: {OUTPUT_FILE}")
    print()
    print("Funnel summary:")
    print(f"  Total parcels:               {total:>6,}")
    print(f"  After flood exclusions:      {total - sum(d['removed'] for d in chart_data if d['kind'] == 'exclude' and 'Flood' in d['label']):>6,}")
    print(f"  After all hard exclusions:   {after_excl:>6,}")
    print(f"  ≥ {MW100_ACRES} acres:                  {after_size:>6,}")
    print(f"  Prev. developed only:        {after_dev:>6,}")
    print(f"  Score ≥ 90, priority sites:  {final:>6,}")


if __name__ == "__main__":
    main()
