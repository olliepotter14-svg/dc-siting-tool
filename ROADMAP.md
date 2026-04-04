# Plan: UK Data Centre Land Siting Tool

## Context

DC developers and real estate buyers currently spend weeks manually screening land parcels across 10+ fragmented data sources (NESO TEC Register, local planning portals, EA flood maps, fibre databases, OS data). There is no single tool that scores raw land parcels against the factors that actually kill sites — primarily power, then fibre access, flood risk, planning land use, buildability, and proximity to demand centres.

This tool replaces that manual process with a map-driven, scored interface for finding the highest-potential UK land parcels for new data centre development. It targets both technical DC developers (who understand MW and TEC queues) and non-technical real estate buyers/investors (who need plain scores and summaries). It will be demoed to clients, so design quality matters.

**Key decisions made:**
- Raw land parcels (undeveloped/brownfield), not existing commercial buildings
- OSM `landuse=industrial` + `landuse=brownfield` polygons as data source (free, real polygons, no licensing)
- Mapbox GL JS for mapping (user has API key)
- GitHub + Netlify for hosting (multi-file web app)
- One feature built and tested per session
- Client demo quality UX

---

## Scoring Model (informed by industry research)

Based on CBRE, Ramboll, RPS, Cushman & Wakefield, and NESO frameworks, the scoring dimensions are:

| Dimension | Weight | Key Metric |
|-----------|--------|-----------|
| Power (grid access) | 35% | Substation headroom (MW), TEC queue pressure, distance to 132kV+ substation |
| Fibre connectivity | 20% | Distance to nearest carrier-neutral PoP / IX |
| Flood risk | 15% | EA flood zone (Zone 1 = 10pts, Zone 2 = 5pts, Zone 3 = 0pts — hard filter option) |
| Planning / land use | 15% | Current OSM land use class (industrial > brownfield > mixed > greenfield) |
| Buildability | 10% | Slope/topography, contamination proxy (brownfield penalty), site size |
| Market proximity | 5% | Distance to nearest Tier 1 city / demand centre |

Hard filters (auto-excluded): Green Belt, SSSI, AONB, Flood Zone 3.

---

## Feature Roadmap (one per session)

### Feature 1 (this session): Base map + land parcels
**Goal**: Working Netlify-hosted page with a Mapbox GL JS map showing UK industrial/brownfield land parcels from OSM data. Click a parcel to see name, size, and land use type.

**Deliverables**:
1. GitHub repo set up (`dc-siting-tool`)
2. `index.html` + `map.js` + `style.css` (multi-file structure for maintainability)
3. `data/uk_industrial_parcels.geojson` — pre-fetched OSM data for UK industrial + brownfield land parcels, filtered to >2 acres
4. Mapbox GL JS map centred on UK, satellite + streets style
5. Parcel polygons rendered as a fill layer (colour by land use type)
6. Click popup: parcel name, land use type, approximate size (ha), OSM ID
7. Sidebar: title, tagline, parcel count, basic region filter (dropdown)
8. Netlify deployment via GitHub

**OSM data fetch strategy**: Use Overpass API query to extract `landuse=industrial` + `landuse=brownfield` polygons across the UK. Pre-process and save as static GeoJSON (not live API call — avoids latency and rate limits). Script to be run once to generate the file.

**Design direction**: Dark map basemap (Mapbox dark-v11), accent colour #00E5FF (electric cyan), clean sans-serif font, professional sidebar. Inspired by CBRE Athena aesthetic — not the existing green/amber/red tools.

---

### Feature 2 (next session): Power scoring layer
- Overlay substations from `uk_substations_real.json` with headroom colour coding
- For each parcel, calculate score based on distance to nearest substation + TEC queue pressure
- Show power score badge on parcel popup
- Add power filter: "minimum available MW" slider

### Feature 3: Composite scoring engine
- Add fibre, flood risk, planning, buildability, market dimensions
- Composite score (0–100) displayed on each parcel
- Score breakdown panel (radar chart or bar breakdown)
- "Sort by score" in sidebar list view

### Feature 4: Search & filters
- Region dropdown (UK regions)
- Min power requirement (MW): 10 / 20 / 50 / 100 / 200+
- Min site size (acres): 5 / 10 / 25 / 50+
- Max grid queue pressure (%)
- Hard filter toggles: exclude flood zone 3, exclude Green Belt

### Feature 5: Site detail card
- Full per-site deep-dive panel
- Score breakdown by dimension
- Nearest substations (top 3) with headroom + queue
- Indicative connection cost estimate
- Planning notes (LPA name, nearest planning decisions)
- "Flag for pipeline" button

### Feature 6: Export
- CSV export of filtered + ranked parcel list
- Single-site PDF summary card for investor decks

### Feature 7: Landowner identification & outreach
**Goal**: For any shortlisted parcel, surface the registered landowner and provide a clear outreach route — turning site identification into actionable deal origination.

**What to show in the detail panel:**
```
Registered title:   AGL12345
Owner:              Prologis UK Limited
Owner type:         Institutional REIT
Registered address: The Prologis Building, Guildford...
Approach route:     Known institutional — BD channel recommended

  [Search Land Registry ↗]   [View Companies House ↗]
```

**Owner type classification:**
- **Individual** → direct letter / solicitor introduction
- **UK company** → Companies House lookup → directors → LinkedIn / direct outreach
- **Institutional** (REIT, fund — SEGRO, Tritax, Prologis etc.) → known BD channels
- **Public sector** (council, MoD, Network Rail) → FOI / disposal process
- **Overseas entity** → Companies House overseas register (introduced 2023) + further diligence

**Data sources:**
1. **HMLR INSPIRE polygons** (free download) — title number boundaries for England & Wales; overlay against parcel centroid to find title number
2. **Land Registry title register** — £3/query per title via GOV.UK API; returns owner name + address for service
3. **Companies House API** (free) — company name → directors, registered address, filing history; traces SPV ownership chains
4. **Registers of Scotland** — equivalent for Scottish parcels

**Build approach:**
- Pre-enrich parcels with HMLR INSPIRE title numbers (spatial join, one-off script) — store as `title_number` property
- On parcel click: live £3 HMLR API call to fetch owner name/address (only when user views detail — avoids bulk cost)
- Classify owner type heuristically (contains "Ltd/PLC/REIT" → company; known institutional names → REIT flag)
- Companies House lookup runs client-side via free API using owner name
- Show deep-link buttons to Land Registry and Companies House records

**Cost consideration:** Live HMLR queries at £3/title — consider whether to gate behind a "Request owner data" button to avoid accidental cost at scale.

### Feature 9: Planning application monitoring
**Goal**: Alert users when planning applications are submitted near scored parcels — particularly from hyperscalers (Amazon, Microsoft, Google, Stack) or major DC developers. Replaces the need for a £2k/month ProPSearch subscription.

**What to show:**
- Recent planning applications within X km of a parcel, filterable by applicant name / keyword ("data centre", "data hall", "hyperscale")
- Application stage: outline / detailed / permitted / refused
- Applicant name — signals which operators are moving in a given area
- "Competitor activity" tag on parcels where a major player has submitted nearby

**Data source**: planning.data.gov.uk planning applications API (free, national coverage, updated daily). Filterable by description keyword, applicant, geometry, date range.

**Build approach:**
- Nightly or on-demand fetch of recent DC-related planning applications into `data/planning_applications.json`
- Spatial index: for each application, find parcels within 10km
- In detail panel: "Nearby planning activity" section listing relevant applications with links to LPA portal
- Optional: email alert when a new application matches a saved search area

**Why it matters**: Stage of application tells you how far along a competitor is — outline planning means they've decided on the site; detailed means they're close to building. Early-stage applications (pre-app, outline) are the most valuable intelligence.

---

### Feature 10: Behind-the-meter power scoring enhancement
**Goal**: Sites with existing HV infrastructure on-site (former power stations, substations, EfW plants, industrial sites with private wire) are categorically different from grid-dependent sites. Surface this in the scoring and detail panel.

**Current gap**: A site 500m from a 400kV substation with an existing 132kV transformer on-site scores the same as one with no on-site infrastructure. In reality the latter is a materially faster, cheaper connection.

**What to add:**
- OSM tag detection: `power=substation`, `power=plant`, `power=transformer` within or adjacent to parcel boundary → flag as "existing HV infrastructure"
- Former power station classification: `power=plant` + `plant:source=coal/gas/nuclear` → "former power station" badge, significant scoring bonus
- Private wire detection: existing generation assets (solar farm, wind, EfW, CHP) within 1km → flag as behind-the-meter generation potential
- Score bonus: sites with on-site HV infrastructure get +10–20 points on the power dimension

**Data source**: OSM power layer (already loaded as `uk_powerlines.geojson` — extend to include plant/substation polygons).

---

### Feature 8: Land value estimation
**Goal**: Show an indicative land acquisition cost range per parcel with full transparency on how the figure was derived — same approach as connection cost estimates.

**Three cost components to show:**
1. **Land acquisition** — £/acre range derived from data sources below × parcel area
2. **Remediation** — brownfield/landfill sites only; Arup/Arcadis benchmark £50k–£500k/acre depending on contamination proxy
3. **Planning risk flag** — qualitative indicator shown alongside cost (Low / Medium / High)

**Planning risk logic:**
- 🟢 Low — `industrial`, `commercial` (existing use class likely DC-compatible)
- 🟡 Medium — `brownfield`, `extraction`, `transport` (change-of-use required, 12–24 months typical)
- 🔴 High — `farmland`, `military` (full DC consent needed, 24–48+ months, viability uncertain)

**Data source strategy (tiered by quality):**

| Tier | Source | Coverage | Notes |
|------|--------|----------|-------|
| 1 | DEFRA agricultural land price surveys | Farmland, by region | Free, quarterly, download directly |
| 1 | SEGRO / Tritax / LondonMetric REIT annual reports | Industrial/logistics, by region | Audited portfolio valuations — manually extract once per year |
| 2 | VOA Rateable Values (data.gov.uk) | All commercial, England/Wales | £/sqft rental proxy → capital value via yield. Free API, high spatial resolution |
| 2 | LPA Local Plan benchmark land values | All types, by LPA area | Public documents in council evidence bases — labour intensive to collect but very accurate |
| 3 | Planning viability assessments | Site-specific, patchy | Public docs on council portals — gold standard when available; seed from DC/logistics applications |
| 3 | Rightmove Commercial asking prices | Industrial/commercial, live | Asking price proxy (10–20% above transaction) — scrapeable for directional data |

**Recommended build approach:**
1. Build a `data/land_benchmarks.json` lookup: `{ region × site_type → { low, mid, high, source, tier } }`
2. Seed with DEFRA (farmland) + REIT annual reports (industrial) + CBRE/Savills published indices (commercial)
3. VOA enrichment script: match rateable values to parcel centroids, convert to capital value, store per-parcel
4. Show confidence tier badge (High / Medium / Estimated) so user knows data quality
5. Render in detail panel alongside connection costs — same visual style

**Key insight to surface in UI**: For most DC sites, land cost is the *smallest* component vs connection + construction. But planning risk is the biggest programme killer. The tool should make this explicit — show land cost in context of total capex stack.

---

## Technical Architecture

```
dc-siting-tool/
├── index.html          # Main app shell
├── map.js              # Mapbox GL JS map logic
├── style.css           # UI styles
├── data/
│   ├── uk_industrial_parcels.geojson   # Pre-fetched OSM parcels
│   ├── uk_substations_real.json        # Existing substation data (copy from projects folder)
│   └── tec_queue_by_site.json          # Existing TEC data (copy from projects folder)
├── scripts/
│   └── fetch_osm_parcels.py            # One-time OSM data fetch script
└── netlify.toml                        # Netlify config
```

**Key files from existing project to reuse**:
- `/Users/olliepotter/Documents/1-Projects (Active)/Learning Claude Code/uk_substations_real.json` — 134 substations with real TEC data
- `/Users/olliepotter/Documents/1-Projects (Active)/Learning Claude Code/tec_queue_by_site.json` — queue aggregated by connection site
- `/Users/olliepotter/Documents/1-Projects (Active)/Learning Claude Code/site_selection_model_v2.json` — existing scoring weights to adapt

**Stack**: Vanilla JS + Mapbox GL JS 3.x + Turf.js (spatial calculations) + no framework (keep it simple and fast to load)

---

## Feature 1 Build Steps

1. Create `dc-siting-tool/` directory
2. Write `scripts/fetch_osm_parcels.py` — Overpass API query for UK `landuse=industrial` + `landuse=brownfield` polygons >2 acres, output to `data/uk_industrial_parcels.geojson`
3. Run the fetch script to generate the GeoJSON data file
4. Write `index.html` — app shell with sidebar + map container
5. Write `style.css` — dark theme, cyan accent, professional layout
6. Write `map.js` — Mapbox GL JS map, load GeoJSON layer, click handler, popup, region filter
7. Test locally with `python -m http.server`
8. Init git repo, push to GitHub
9. Connect to Netlify (user adds Mapbox token as environment variable)

---

## Verification

- Open hosted URL: map loads centred on UK
- Industrial/brownfield parcels visible as cyan/teal polygons
- Click a parcel: popup shows name, land use, size
- Region dropdown filters visible parcels
- Parcel count in sidebar updates on filter
- Works on mobile viewport (responsive)
- No console errors; Mapbox key not exposed in source
