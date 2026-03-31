# DC Site Finder — Slide Brief
*Draft content for two-slide deck, March 2026*

---

## SLIDE 1: What the tool does + how it scores

### Three key outcomes for DC operators

**1. Replace weeks of manual screening with an instant ranked shortlist**
DC developers currently spend 4–8 weeks manually pulling together fragmented data — NESO TEC queue registers, DNO headroom portals, EA flood maps, planning databases, OS land parcel records — to produce a first-pass site list. The DC Site Finder replaces that process with a single scored, filterable map interface covering 63,000+ UK land parcels, pre-enriched with grid, flood, fibre, planning and buildability data. A 100MW search that would take a team two weeks to manually screen produces a ranked shortlist in seconds.

**2. Expose the real grid picture — including committed demand pipeline, not just generation queue**
The NESO TEC Register, the most commonly cited measure of grid constraint, captures only *generation* connections (wind farms, batteries, power stations). It shows near-zero queue pressure at London substations, which are in reality heavily loaded. The tool ingests UKPN LTDS Table 3a firm capacity data and the committed 2029/30 demand forecasts — showing the real pipeline of demand connections already contracted but not yet built. This gives a materially different (and accurate) view of which substations have genuine headroom for a new large load. Nationally, 134 substations are scored using real headroom data from six DNOs: UKPN, NGED, NPG, SSEN, SPEN, and ENW.

**3. Anchor investment decisions in objective, reproducible data**
Every score is derived from named, publicly available datasets with documented methodology. There are no qualitative judgements, broker estimates or manually assigned ratings. A site's score can be audited back to its source — the exact LTDS Table 3a row, the EA flood zone polygon, the ITU fibre route segment — making the tool suitable as a first-stage input to investment committee analysis, not just an internal screening exercise.

---

### The scoring approach — step by step

#### Stage 1 — Ingest all relevant land parcels

**What we do:** Pull every land parcel in the UK that could plausibly host a data centre.

**Data source:** OpenStreetMap Overpass API

**How:** Query for all polygons tagged as industrial, brownfield, power-related, transport, commercial, military, aviation, and extraction land use across all 13 UK regions. Filter to >2 acres (smaller sites are not viable for any meaningful DC development). Output: **63,478 raw parcels**.

---

#### Stage 2 — Apply hard exclusions (non-negotiable disqualifiers)

**What we do:** Remove parcels that are permanently non-viable regardless of grid or planning circumstances.

**Data sources and criteria:**

| Exclusion | Data source |
|---|---|
| Flood Zone 3 (high probability of flooding) | Environment Agency OGC WFS Flood Map API — all 63,478 parcels individually queried; 5,409 parcels excluded (8.5%) |
| National Parks | planning.data.gov.uk designation dataset |
| Areas of Outstanding Natural Beauty (AONBs) | planning.data.gov.uk designation dataset |
| Sites of Special Scientific Interest (SSSIs) | Natural England SSSI polygon layer |
| Special Areas of Conservation (SACs) | planning.data.gov.uk |
| Special Protection Areas (SPAs) | planning.data.gov.uk |
| Ancient Woodland | Forestry Commission Ancient Woodland Inventory |
| Scheduled Monuments | Historic England |

After exclusions: **52,242 parcels** remain in the scoreable universe.

---

#### Stage 3 — Score every remaining parcel across four dimensions

Each parcel receives a composite score from 0–100, computed as a weighted average of four factors. Scores are pre-computed at three DC sizes (20 MW / 50 MW / 100 MW) and linearly interpolated at runtime. This means every parcel has a score that responds to the user's selected campus size without recalculation.

---

##### Factor 1 — Power & Grid Access (40% of composite)

*What question it answers: Can I actually connect here, and how fast?*

**Sub-components:**

- **Headroom score** — Does the substation have enough firm capacity remaining to serve a DC of the requested size? Headroom = firm capacity (N-1 security standard) minus existing peak demand. Scores 0–100 based on headroom relative to MW requirement.

- **Queue pressure score** — How much of that headroom is already spoken for by committed connections? Scores 0–100 (100 = unconstrained, 0 = fully committed). For UKPN substations, uses the 2029/30 LTDS demand forecast (which includes all committed but not-yet-built demand connections). For other DNOs, uses TEC queue plus current utilisation. This is the critical distinguishing factor: it shows that Wimbledon (85.6% committed by 2030) and Barking (91.7%) are materially more constrained than they appear from TEC queue data alone.

- **Voltage score** — Higher voltage connection points (400kV, 275kV) score higher; 132kV scores moderately; lower voltages penalised.

- **Distance factor** — Applied as a multiplier: substations within 5km score full power points; beyond 30km the score degrades. Each parcel is scored against its nearest viable substation, not the nearest substation regardless of capacity.

**Substation headroom data sources by DNO:**

| DNO | Source | Metric used |
|---|---|---|
| UKPN (London, South East, East) | LTDS Table 3a — `ltds-table-3a-load-data-observed`, ukpowernetworks.opendatasoft.com | Firm capacity (N-1), current demand, committed 2029/30 forecast demand |
| NGED (Midlands, South West, Wales) | NGED GSP Technical Limits CSV | Technical import limits by season |
| NPG (North East, Yorkshire) | NPG GSP Heatmap | Firm capacity, max demand |
| SSEN (Southern England, Scottish Hydro) | SSEN Headroom Dashboard | Max observed demand, technical limits |
| SPEN (North West England, Scotland) | SPEN SPM Technical Limits | Winter import limits |
| ENW (North West England) | ENW Primary Aggregated data | GSP-level firm demand |

TEC generation queue data for all substations: **NESO TEC Register** (api.neso.energy, updated twice weekly, 2,229 projects, 137 GW total queue).

Transmission powerlines for distance calculations: **OpenStreetMap 132kV+ lines** (uk_powerlines.geojson).

---

##### Factor 2 — Permissioning (30% of composite)

*What question it answers: How hard will it be to get planning consent?*

Sites are placed into one of three consent risk buckets based on land type, then adjusted for designations:

| Bucket | Score | Land types |
|---|---|---|
| A — Permitted / low risk | 85 | Industrial, brownfield, former power stations |
| B — Achievable / standard consent | 55 | Transport, commercial, military |
| C — Complex / change of use required | 20 | Extraction, aviation, farmland |

**Adjustments:**
- Green Belt: score × 0.55 (significant planning hurdle)
- Grey Belt (brownfield within Green Belt): score × 0.80 (NPPF Grey Belt policy applies, somewhat more achievable)
- AI Growth Zone: +15 points (government-designated fast-track zones)

**Data sources:** Site type from OpenStreetMap tags; Green Belt and Grey Belt boundaries from planning.data.gov.uk; AI Growth Zone locations from DSIT.

---

##### Factor 3 — Fibre Connectivity (20% of composite)

*What question it answers: Can I get carrier-grade diverse fibre routes?*

Scored on distance to the nearest of two infrastructure types:
1. **Backbone fibre route** — distance in km to the nearest operational UK backbone segment. Under 1km scores maximum; degrades on a step curve to 100km (minimum score).
2. **Carrier-neutral colocation** — distance to the nearest internet exchange or carrier-neutral facility, which anchors diverse route availability.

The final fibre score takes the better of the two distances.

**Data sources:**
- **ITU BBmaps WFS** — 1,187 operational UK backbone fibre route segments (geometries downloaded from ITU open data service)
- **PeeringDB API** — UK internet exchanges (IXPs) and carrier-neutral colocation facilities

---

##### Factor 4 — Buildability (10% of composite)

*What question it answers: Is the site physically practical to develop?*

Two inputs:
- **Site area** — scored relative to MW requirement; larger sites score higher (more phasing flexibility, easier infrastructure layout)
- **Type penalty** — certain land types carry additional buildability challenges (e.g. active extraction sites, aviation with live runway constraints)

**Data source:** Parcel geometry from OpenStreetMap (area in acres computed from polygon).

---

#### Composite score formula

```
Composite = 0.40 × Power + 0.30 × Permissioning + 0.20 × Fibre + 0.10 × Buildability
```

Hard-excluded parcels (Flood Zone 3, protected designations) receive composite = 0 regardless of other scores. Flood Zone 2 is shown as an informational tag only and does not reduce the composite score.

Score range: 0–100. Distribution across all 52,242 scoreable parcels at 50MW:
- 90–100: 5 parcels
- 70–89: 8,137 parcels
- 50–69: 23,632 parcels
- 30–49: 18,999 parcels
- <30: 12,762 parcels (mostly remote or poorly connected)

---

## SLIDE 2: 100MW Waterfall — From 63,478 parcels to priority sites

*Content for a waterfall/funnel chart*

### Headline numbers for chart

| Step | Label | Parcels remaining | Removed | Why |
|---|---|---|---|---|
| 1 | All UK land parcels | 63,478 | — | Brownfield, industrial, agricultural, military, aviation and other DC-relevant types across all 13 UK regions |
| 2 | Remove Flood Zone 3 | 58,069 | −5,409 | High flood risk — uninsurable for critical infrastructure under EA classification |
| 3 | Remove statutory designations | 52,242 | −5,827 | National Parks, AONBs, SSSIs, SACs, SPAs, Ancient Woodland, Scheduled Monuments |
| 4 | Remove sites < 200 acres | 4,669 | −47,573 | Minimum footprint for a 100MW campus (power hall, cooling, switchgear, security perimeter) |
| 5 | Set aside farmland | 715 | −3,954 | Agricultural land requires change of use — materially longer planning timeline; retained in dataset but deprioritised |
| 6 | Composite score ≥ 50 | ~675 | ~40 | Minimum viability threshold — poor grid access, remote location, or connectivity gap |
| 7 | Composite score ≥ 70 | ~140 | ~535 | Strong candidates — good grid headroom, established connectivity, acceptable permissioning |
| 8 | Composite score ≥ 80 | 29 | ~111 | High-quality sites — top-tier on power, fibre and permissioning dimensions |
| 9 | **Priority 100MW sites** | **Top 10** | — | Best-in-class sites for detailed technical and commercial due diligence |

### Top sites emerging from the 100MW funnel

| Rank | Site | Region | Size | Type | Composite (100MW) | Notable |
|---|---|---|---|---|---|---|
| 1 | Industrial site | North West | 266 ac | Industrial | 89.7 | Near major 400kV substation, fibre on-site |
| 2 | Port of Southampton | South East | 605 ac | Industrial | 89.2 | Deep water access, existing HV infrastructure |
| 3 | Industrial site | Yorkshire | 443 ac | Industrial | 87.7 | Former heavy industry, 400kV proximity |
| 4 | Ratcliffe Power Station | East Midlands | 276 ac | Brownfield | 87.7 | Former coal plant; permitted development potential, grid connection already on-site |
| 5 | Sowton Industrial Estate | South West | 228 ac | Industrial | 87.7 | M5 corridor, Exeter fibre hub |

### Chart annotation notes

- **The 200-acre cut** is the single largest filter — 47,573 parcels removed. Most UK industrial sites are under 50 acres; 100MW campus requirements are fundamentally a land scarcity problem in the UK.
- **Flood Zone 3 and statutory designations combined** remove 11,236 parcels (18% of total). These are genuinely non-negotiable — no planning authority will grant consent for critical national infrastructure in these zones.
- **Farmland set aside, not excluded** — 3,954 large agricultural sites remain in the tool's scoreable dataset with a lower permissioning score (Bucket C, score 20), reflecting the change-of-use challenge. They are available for analysis but deprioritised in the 100MW shortlist.
- **Ratcliffe Power Station** is a notable example: brownfield former power station with an existing 400kV grid connection on-site, placing it in Bucket A for permissioning and close to maximum power score for 100MW. This class of site — former coal/gas power stations — represents some of the strongest opportunities in the UK.

---

*Data current as of March 2026. Parcel data from OpenStreetMap. Grid data from NESO TEC Register + UKPN LTDS Table 3a. Flood data from Environment Agency. Fibre data from ITU BBmaps + PeeringDB.*
