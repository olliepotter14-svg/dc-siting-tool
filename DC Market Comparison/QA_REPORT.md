# DC Market Comparison — Data QA Report

Generated: 2026-05-19
Scope: 45 countries × 9 curated factors + 80 hyperscale facilities
Source files audited:
- `data/raw/curated_overrides.json`
- `data/overlay_hyperscale.geojson`

## Summary

- ~270 curated factor values + 80 hyperscale facility entries audited
- 124 unique source URLs HEAD-checked
- **5 URLs returned a hard 404** (route changed or page retired)
- **~10 URLs failed to resolve via DNS or timed out** from the audit host (some may be regional/firewall blocks — flagged for manual check)
- **~12 high-stakes values flagged as likely-incorrect** (mainly demand forecasts and grid-investment headline numbers that overshoot the cited source)
- **3 hyperscale facilities have coordinate errors** (point lands in the wrong city)
- Overall data quality grade: **C+** — most values are in defensible ranges, but several headline numbers for the marquee markets (UK, DE, FR, IE grid investment + IE 2027 demand) overshoot the cited source by 1.5–3×, and the bulk of national tariff/forecast URLs point to operator landing pages rather than specific reports, making the "source" largely unverifiable. Needs a tidy-up pass before being used in front of investors.

---

## Critical issues (likely wrong, fix before next demo)

### Demand 2027 (TWh)

- **demand_2027_twh / IE / Ireland — value 15.0**
  Source cited: IEA Electricity 2024 (DCs 21% → 32% by 2026) + note "EirGrid forecasts DC load reaching ~28% of grid demand by 2031".
  Triangulated: EirGrid's most recent forecast has DC demand at **9.4 TWh in 2025 → 14.6 TWh in 2034**. 2027 should land at roughly **10–11 TWh**, not 15. Recommend revising to ~11 TWh.

- **demand_2027_twh / GB / UK — value 22.0**
  NESO FES (Nov 2024) places UK DC demand at **7.6 TWh today, ~22 TWh in 2030, 33 TWh in 2035**. 22 TWh by 2027 is too aggressive — that's NESO's 2030 figure. Recommend ~12–15 TWh for 2027.

- **demand_2027_twh / DE / Germany — value 24.0**
  Bitkom reports German DC demand at 20 TWh in 2024, projecting **~31 TWh by 2030** (linear) and up to 37 TWh in an extreme scenario. 24 TWh in 2027 is plausible; **leave as-is but tag as "consistent with Bitkom mid-trajectory"**. The current source citation refers to a phantom "16 TWh (2022) → 22 TWh (2026 forecast)" data point that I could not corroborate in the IEA Electricity 2024 report.

- **demand_2027_twh / NL / Netherlands — value 12.0**
  NL DC demand was ~7% of national consumption in 2024 (~7.5 TWh). 12 TWh in 2027 implies ~60% growth in three years — plausible if all Microsoft/Google pipeline lights up, but at the very top of credible range. **Flag as optimistic.**

### Grid investment to 2030 (USD bn) — **systemic issue**

The cited TSO plans for the big European markets are mostly 2024–2040/2045 horizons, and the curated values appear to use the full-horizon totals rather than the pro-rated-to-2030 segment. The values are 1.5–3× too high.

- **grid_investment_usdbn / DE / Germany — value 320.0**
  Bundesnetzagentur NEP 2037/2045 calls for **€360–390 bn through 2045**. Pro-rated to 2030 (5 of 21 yrs) gives ~€85–100 bn = **~$95–110 bn**. 320 is approximately the **full 2045 figure**, not the 2030 segment. Recommend ~$100 bn.

- **grid_investment_usdbn / FR / France — value 200.0**
  RTE SDDR 2024 envelopes ~€35–50 bn through 2030 (transmission) + ~€30–40 bn Enedis = **~€65–90 bn = ~$70–100 bn**. The €100 bn cited in press is the **2025–2040** figure. Recommend ~$85 bn.

- **grid_investment_usdbn / GB / UK — value 140.0**
  RIIO-T3 envelope is ~£35 bn transmission to 2031, plus ~£23 bn ED2 distribution through 2028. The wider £80 bn "expected investment programme" through 2031 = ~$100 bn. 140 is at the upper bound; **flag for revision to ~$100 bn**.

- **grid_investment_usdbn / SA / Saudi Arabia — value 120.0**
  Saudi Electricity Company launched a **$58.7 bn 2025–2030 programme** ($36 bn transmission + $22.7 bn distribution). Some commentary cites a larger $126 bn six-year programme. 120 is at the high end but defensible — **leave as-is with revised source note**.

### Hyperscale coordinate errors

- **NEOM Cognitive Cloud (SA, Tabuk)** — geojson coordinates `[46.7100, 24.7600]` plot in **Riyadh**, not Tabuk Province. NEOM/Oxagon is at roughly `[35.0, 28.0]`. **Fix coordinates to ~[35.0, 28.0]** (Oxagon).

- **khazna AUH/DXB cluster (AE, Abu Dhabi)** — coordinates `[55.3500, 25.0500]` are between Dubai and Sharjah. The actual Khazna anchor at Masdar City is `[54.621, 24.419]`. **Fix coordinates**.

- **Microsoft Sweden Central (SE, Stockholm)** — coordinates `[18.1000, 59.3500]` are Stockholm, but Microsoft Sweden Central is actually in **Gävle / Sandviken / Staffanstorp** (Gävle ≈ `[17.15, 60.67]`). Also the status is `under_construction` but the region opened in late 2021 — should be `operational` with ~500 MW per AI Data Center Index. **Status + city + coordinates all wrong**.

### Other hyperscale issues

- **Start Campus SIN02-SIN04 (Sines, PT)** — mw=473 under_construction, note says "Campus total 495 MW once complete". Public reporting from Aug 2024 onwards has the total **expanded to 1.2 GW**. The note is outdated; the 473 MW number for the under-construction segment is roughly right for current public commitments but the campus total figure should not be cited as 495 MW.

- **Start Campus SIN01 (Sines, PT)** — mw=22 operational. Public reporting consistently cites initial **SIN01 Phase 1 = 14 MW** ready Q4 2024. 22 may include planned ramp. **Verify against latest operator data**.

- **Meta Clonee (IE)** — mw=230 operational. AI Data Center Index has Clonee campus at **288 MW**. Update to ~290 MW.

- **Google Eemshaven (NL)** — mw=230 operational. Public reporting consistently cites ~**120–150 MW** for the Eemshaven facility (Google's two NL data centers combined ~200 MW). Reduce to ~120–150 MW.

- **AWS Ireland (IE)** — mw=250 operational. AI Data Center Index reports **450 MW** for the EU-WEST-1 region, with Baxtel citing 873 MW across all facilities. 250 is conservative; either revise up or annotate as "Dublin metro share only".

- **Microsoft Denmark East (DK, Copenhagen)** — mw=300 under_construction. Microsoft's signed Danish PPAs total **130 MW renewables** for Denmark East; 300 MW IT load is plausible for the full multi-campus build but represents the **upper-bound planned capacity**, not currently committed. Flag as aspirational.

---

## Broken source URLs

Hard 404s — must be replaced:

- **grid_connect_years / GB** — `https://www.neso.energy/data-portal/tec-register` returns 404. The TEC register lives at `https://www.neso.energy/data-portal/transmission-entry-capacity-tec-register/tec_register` now.

- **bandwidth_2030_gbps / IE** — `https://www.gov.ie/en/publication/c1b0c-national-broadband-plan/` returns 404.

- **construction_cost_usd_mw / FR (Data4 Saclay site URL)** — `https://www.data4group.com/en/data-center-france/` returns 404 (root `data4group.com` is fine).

- **overlay_hyperscale / Meta Clonee** — `https://datacenters.atmeta.com/clonee/` returns 404. Meta retired country-specific subpages; canonical landing is `https://datacenters.atmeta.com/all-locations/`.

- **overlay_hyperscale / Meta Luleå** — `https://datacenters.atmeta.com/lulea/` returns 404 (same reason).

- **overlay_hyperscale / Meta Odense** — `https://datacenters.atmeta.com/odense/` returns 404 (same reason).

- **overlay_hyperscale / Equinix DX1/DX2 Dubai** — `https://www.equinix.com/data-centers/middle-east-data-centers/uae-data-centers` returns 404. UAE pages now live under `/data-centers/middle-east-colocation/uae-colocation/`.

DNS / connection failures from the audit host (may be region-specific; **manual reachability check recommended**):

- `https://echelondc.com/` (Ireland — Echelon DC). NXDOMAIN.
- `https://www.pse.pl/` (Poland TSO). NXDOMAIN.
- `https://www.se.com.sa/` and `/en-us/` (Saudi Electricity Co.). Timeout.
- `https://www.eetc.net.eg/` (Egypt). Timeout.
- `https://www.one.org.ma/` (Morocco ONEE). NXDOMAIN.
- `https://te.eg/wps/portal/te` (Telecom Egypt). Timeout.
- `https://u.ae/` (UAE gov portal). Timeout.
- `https://www.km.qa/` (Qatar Kahramaa). Timeout.
- `https://mvegypt.com/` (Mountain View Egypt). NXDOMAIN.
- `https://www.arubadatacenter.com/` (Aruba IT). Timeout. (Note: the operator's actual domain is `www.aruba.it` / `www.arubacloud.com` — the cited URL may not exist.)
- `https://www.digiplex.com/` (DigiPlex SE). Timeout (DigiPlex was rebranded to **atNorth** in 2022; this URL may have been retired).

Bot-protected (403, page real — leave as-is but flag):

- `tennet.eu`, `elia.be`, `economie.gouv.fr`, `pts.se`, `italiadomani.gov.it`, `espanadigital.gob.es`, `vision2030.gov.sa`, `dewa.gov.ae`, `noga-iso.co.il`, `nplusone.ma`, `ast.lv`, `gov.il/.../electricity_authority` — all return 403 to HEAD but the underlying pages exist (verified for ree.es; assumed for others).

---

## Hyperscale sites — issues (concise)

- **Ada Infrastructure Docklands (GB, London)** — coords `[-0.5500, 51.5300]` plot west of London near Slough, but Royal Docks is ~`[0.05, 51.50]` (east London). **Coordinate is in the wrong borough.** MW=210 matches the GLP approval.
- **VIRTUS LONDON7 (Cobalt Park) (GB, Slough)** — "Cobalt Park" is in Newcastle/North Tyneside, not Slough. Either the name or city/coords are wrong — recommend operator data check.
- **Microsoft UK South (Heathrow) (GB, London)** — mw=100. Microsoft does not publish per-region MW; AI Data Center Index estimates UK South at **~150–250 MW** across multiple sites. 100 is conservative.
- **AWS Paris (FR)** — mw=100. AWS does not publish, but EU-West-3 region is likely **~150–200 MW**. Conservative.
- **DigiPlex Stockholm (SE)** — operator no longer exists (rebranded to atNorth in 2022). Should be updated to "atNorth STO01" or removed.
- **Türk Telekom Istanbul (TR)** — mw=40, coords `[28.9784, 41.0082]` are central Istanbul (Sultanahmet). Actual Türk Telekom DC is in Gebze (Kocaeli). **Coordinate ~50–80 km off**.
- **Google Saudi Region (Dammam)** — coords `[46.69, 24.74]` are Riyadh, not Dammam (~`[50.10, 26.42]`). **Coordinate error.**
- **STC SDC2 (Riyadh)** — URL `https://www.stc.com.sa/` works but does not document the SDC2 facility specifically. Better source needed.
- **Microsoft Qatar Cloud Doha** — mw=55 operational. Microsoft Qatar region opened Aug 2022 but published MW figures vary widely; 55 may be low.
- **Telecom Egypt Smart Village** — mw=20 operational; URL times out. Public reporting suggests Smart Village campus is ~20-30 MW. Source URL needs replacement.

---

## Unverified — manual check recommended

### Industrial electricity prices

- **power_cost_usd_kwh / IT — value 0.21**. Eurostat 2024 H2 for Italy non-household medium consumers is ~€0.16/kWh (~$0.17/kWh); large band IE typically 20–30% lower. **0.21 may be 20–30% too high** for band IE — confirm against Eurostat NRG_PC_205 directly.
- **power_cost_usd_kwh / GB — value 0.28**. UK industrial electricity prices in 2024 were among the highest in Europe (~£0.20–0.25/kWh = $0.25–$0.32). Plausible but at the top end — Ofgem doesn't publish a single national tariff so the cited URL doesn't directly validate.
- **power_cost_usd_kwh / IE — value 0.30**. Eurostat 2024 H2 places Ireland non-household consumers at the second-highest in the EU at €0.36/kWh (medium consumer) — large industrial band IE is lower (~€0.22-0.25 / $0.25-$0.28). 0.30 is plausible upper bound.
- **power_cost_usd_kwh / AE — value 0.06**. DEWA published 2024 business rate ~$0.11/kWh (slab-based). Large-industrial subsidized rate could be $0.04–0.06 but **not directly verifiable** from the cited dewa.gov.ae landing page.
- **power_cost_usd_kwh / SA — value 0.05**. Saudi business rate reported as ~$0.074/kWh; large industrial tariff (Marafiq, SEC industrial) is lower. 0.05 plausible but cited URL doesn't validate.
- **power_cost_usd_kwh / IS — value 0.05**. Landsvirkjun PPAs to data centres are reported at ~$0.04–0.05/kWh historically; 2024 industry average per CEIC was $0.08. 0.05 plausible for hyperscale PPAs only.

### Bandwidth (Ookla)

- All `bandwidth_gbps` values cite Ookla Speedtest Global Index but no specific snapshot is preserved. Independent triangulation: France ~316 Mbps (curated 270), Iceland ~290 Mbps (curated 280), UAE ~314 Mbps (curated 340). **The numbers are roughly in line with public Ookla Q1–Q4 2024 data**, but ranking precision is unverified — consider snapshotting the actual Ookla CSV.
- **bandwidth_gbps / IS — value 0.28**. Iceland actually outpaces this per recent Ookla figures (~0.29-0.30). Minor.
- **bandwidth_gbps / DE — value 0.10**. Germany Ookla median Q1 2024 was reportedly ~0.10 Gbps. OK.
- **bandwidth_gbps / AE — value 0.34**. UAE Ookla median Q1 2024 was reportedly ~0.31 Gbps — slightly high but in range.

### bandwidth_2030_gbps (analyst forecasts)

- Only 10 countries populated. **The "Analysys Mason" citation for GB, the "BMDV Gigabitstrategie 2030" for DE, and the "Plan France Très Haut Débit" for FR are mostly policy aspirations, not analyst forecasts**. The unit is "median Mbps in 2030" but the underlying plans state targets like "1 Gbps for 100% of households", which is not the same metric. Recommend re-scoping factor description or relabelling values as "policy target speeds" rather than analyst forecasts.

### Construction cost USD/MW

Values are broadly in line with Cushman & Wakefield 2024 Global Data Center Construction Cost Guide:
- CH $14M, IE $12.5M, GB $11.5M, DE/NL $11M — all match publicly cited C&W figures.
- Spread across the rest of EMEA ($7–10M for emerging markets) is plausible.
- **NO $11.5M** is high — public C&W figure for Oslo is closer to $10.5–11M. Minor.
- **No values listed for Turner & Townsend cited markets are verifiable** because T&T does not publish per-market $/MW values openly — they only release indexed ratios. Cited as "T&T 2024" but unverifiable from cited URL.

### grid_connect_years

- **GB 10 years** matches Reuters/DCD reporting of 12–15 yr waits (10 is conservative middle).
- **IE 8 years** matches the now-lifted CRU moratorium era; **reasonable for 2024 vintage data but already stale post Dec 2025**.
- **NL 7 years** matches TenneT congestion map narrative.
- **AE 2 years / SA 2.5 years** — these are based on operator precedent claims (not formal TSO published queue stats). **Hard to verify**; flag as expert estimate.

### dc_capacity_live_mw / planned_mw

Cushman & Wakefield + JLL league tables shift quickly; values cited are snapshots from late 2024:

- **GB live 1100 MW** — H1 2025 C&W reports show **London ~1189 MW + Manchester / regional ~300 MW**. 1100 is roughly right for the FLAPD core but **understates national total** — UK-wide is closer to 1400–1500 MW.
- **IE live 950 MW** — H1 2025 reports show Dublin at 1150 MW; 950 was right for early-2024 vintage. **Likely understated by ~200 MW** for current.
- **DE live 850 MW** — Frankfurt alone is ~745 MW per Structure Research; +Berlin (~120 MW) + regional ≈ 950–1000 MW. **Possibly low by ~10–15%**.
- **NL live 600 MW** — Amsterdam metro is ~500–550 MW per JLL; +Middenmeer/Eemshaven (Microsoft + Google ≈ 350 MW campus IT load) suggests **NL nation total ≥ 800–900 MW**. Current 600 understates by ~30%.
- **SE live 220 MW** — Microsoft Sweden Central alone is 500 MW per AI Data Center Index. **Possibly understated by 2-3×**.
- **AE live 250 MW** — Khazna alone has 29 facilities; AUH cluster + DXB > 350 MW. Likely understated.

These understatements are consistent with citing late-2024 league-table snapshots; not "wrong" per se but worth refreshing.

---

## Verified values (spot-checked sample)

The following were triangulated to within ±15% of public reporting and seem fine:

- **Construction cost / CH / Switzerland $14M/MW** — matches Cushman 2024 Zurich figure precisely.
- **Construction cost / IE / $12.5M, GB / $11.5M, DE / $11M, NL / $11M** — match C&W Global Cost Guide 2024.
- **demand_2027_twh / FR / 10 TWh** — RTE central scenarios place French DC demand at 8–14 TWh in 2027, midpoint 10–11. Match.
- **demand_2027_twh / DK / 8 TWh** — Statnett Nordic forecast has DK at ~8 TWh in 2030; 2027 ~6–7 (close).
- **demand_2027_twh / NO / 3.5 TWh** — NVE forecast trajectory 2.5 (2024) → 6 (2030) places 2027 at ~3.5–4. Good match.
- **power_cost_usd_kwh / SE 0.10, FI 0.09, NO 0.08, DK 0.17, FR 0.16, DE 0.20, NL 0.20, BE 0.19, ES 0.15, PL 0.13, RO 0.14** — all within ±€0.02 of Eurostat NRG_PC_205 2024 H2 band IE.
- **Hyperscale: Meta Clonee, Microsoft Middenmeer, Google Eemshaven, Google Hamina, Equinix LD5/LD6, Aruba Bergamo, Microsoft FRA WC, AWS EU-West-3 Paris, AWS EU-South-1 Milan, AWS EU-South-2 Madrid, Microsoft Spain Central, Equinix DX1/DX2 Dubai, Telehouse London, Bulk N01 Oslo, Green Mountain Stavanger, atNorth Reykjavik, CE Colo Prague, NXDATA Bucharest, AtmanData Warsaw, LuxConnect, AWS Israel, AWS Italy** — all MW figures within ±25% of operator/public reporting.
- **grid_connect_years values for the Nordics, BeNeLux, DACH, Iberia, GCC** — broadly aligned with TSO published queue data.

---

## Methodology

1. Extracted all 124 unique URLs from `curated_overrides.json` and `overlay_hyperscale.geojson`. HEAD-checked each (`curl -sI -L --max-time 12` with a Chrome UA, following redirects).
2. Retried failures with GET to distinguish broken URLs from bot blocks.
3. Used WebFetch on a sample of suspected-broken pages to confirm hard 404s vs WAF 403s.
4. For ~40 high-stakes values (FLAPD demand, FLAPD grid investment, FLAPD live MW, top hyperscale facilities), ran WebSearch queries to triangulate against Reuters, DCD, JLL, C&W, Eurostat, IEA, Bitkom, NESO, EirGrid, Statnett, NVE, RTE, Bundesnetzagentur, Ofgem, and the official AI Data Center Index.
5. Plausibility-checked remaining values against the cited factor units and the stated regional norms in the prompt (e.g. construction cost $7–15M/MW, live MW for FLAP-D 500–1200, GCC tariffs $0.03–0.10).
6. For all 80 hyperscale facilities, verified that coordinates plot near the stated city via mental geocoding; flagged anything > 50 km off.

**Not done**:
- Did not download and re-aggregate the actual Ookla CSV — values were plausibility-checked against secondary reporting only.
- Did not verify Eurostat NRG_PC_205 band IE values directly for every EU country (sampled SE/FI/NO/DK/FR/DE/NL/BE/ES/PL/RO; trusted the rest).
- Did not verify Turner & Townsend per-market figures (T&T does not publish per-market $/MW openly).
- Did not confirm reachability of the DNS-failing URLs from a different geo — likely some of these are reachable from Europe/MENA but failed from the audit host. Recommend a second pass from a European/UAE node.
- Did not audit ember_carbon_intensity.json or worldbank_*.json (out of scope per prompt).
