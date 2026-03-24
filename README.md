# DC Site Finder — UK Data Centre Land Intelligence

    A map-driven tool for screening UK land parcels for data centre development
    potential. Scores 40,000+ industrial and brownfield sites across six dimensions —
    power, fibre, flood risk, planning, buildability, and market proximity — and lets you
     filter, rank, and inspect them in real time.

    **Live demo:** [dcsitingtool.netlify.app](https://dcsitingtool.netlify.app)

    ---

    ## What it does

    DC developers and real estate buyers currently spend weeks manually screening land
    parcels across 10+ fragmented data sources. This tool replaces that process with a
    single scored interface.

    - **40,000+ parcels** — OSM industrial, brownfield, power, transport, aviation,
    military, commercial, and farmland sites across the UK
    - **Composite 0–100 score** across six weighted dimensions
    - **Three DC size anchors** — 20 MW, 50 MW, 100 MW (with interpolation between them)
    - **Substation overlay** — 134 UK substations with real TEC Register queue data,
    colour-coded by queue pressure
    - **Powerline overlay** — animated 132kV+ transmission network
    - **ITU backbone fibre overlay** — 1,187 operational UK fibre routes
    - **Site detail panel** — full score breakdown per parcel with connection timeline
    estimate
    - **Filters** — region, minimum size, minimum composite score, DC size, site type,
    flood zone exclusion

    ---

    ## Scoring model

    | Dimension | Weight | Metric |
    |---|---|---|
    | Power | 35% | Distance to substation, grid headroom, TEC queue pressure |
    | Fibre | 20% | Distance to nearest backbone route or carrier-neutral colo |
    | Flood risk | 15% | EA flood zone (Zone 1=100, Zone 2=50, Zone 3=0) |
    | Planning | 15% | Land use classification |
    | Buildability | 10% | Site size + land use penalty |
    | Market proximity | 5% | Distance to nearest Tier 1 demand centre |

    ---

    ## Data sources

    | Dataset | Source |
    |---|---|
    | Land parcels | OpenStreetMap (Overpass API) |
    | Substations + TEC queue | NESO TEC Register |
    | Powerlines | OpenStreetMap |
    | Fibre routes | ITU BBmaps WFS |
    | Carrier/IX locations | PeeringDB |
    | Flood zones | EA Flood Map for Planning (OGC API) |

    ---

    ## Local development

    ```bash
    # Serve locally (no build step needed)
    python -m http.server 8080
    # Open http://localhost:8080

    Requires a Mapbox public token in config.js.

    Re-running the enrichment pipeline

    python3 scripts/fetch_osm_parcels.py         # fetch parcels from OSM
    python3 scripts/enrich_power_scores.py       # add power scores
    python3 scripts/fetch_itu_fibre.py           # fetch ITU fibre routes
    python3 scripts/enrich_fibre_routes.py       # add fibre distances
    python3 scripts/enrich_flood_zones.py        # add EA flood zones (~3–5 hrs)
    python3 scripts/enrich_composite_scores.py   # compute final scores

    ---
    Stack

    - Mapbox GL JS 3.x — map rendering
    - Vanilla JS — no framework
    - Python 3 — data enrichment pipeline
    - Netlify — hosting (auto-deploys on push to main)

    ---
    Status

    - Base map + parcel layer
    - Power scoring (substations, TEC queue, private wire)
    - Composite scoring (six dimensions)
    - Fibre route overlay + scoring
    - Filters, parcel list, detail panel
    - Flood zone overlay (data enrichment in progress — 27% complete)
    - CSV export
    - Site pipeline / flagging

    ---

    Copy that into a file called `README.md` in the root of the repo, then push to
    GitHub. It'll render automatically on the repo page.
