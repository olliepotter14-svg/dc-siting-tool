"""
generate_slide_brief.py

Generates DC_Site_Finder_Slide_Brief.docx — a two-slide briefing document
covering outcomes, scoring methodology, waterfall funnel, and feature status.

Usage:
    python3 scripts/generate_slide_brief.py
"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

OUT_FILE = "DC_Site_Finder_Slide_Brief.docx"

# Colour palette
BLUE_DARK   = RGBColor(0x1a, 0x3a, 0x5c)   # headings
BLUE_MID    = RGBColor(0x2c, 0x5f, 0x8a)   # sub-headings / table headers
BLUE_LIGHT  = RGBColor(0xd6, 0xe8, 0xf7)   # table header fill
AMBER       = RGBColor(0xd9, 0x73, 0x00)   # highlights
GREEN       = RGBColor(0x1a, 0x7a, 0x3c)   # completed features
GREY_ROW    = RGBColor(0xf5, 0xf7, 0xfa)   # alt row fill
WHITE       = RGBColor(0xff, 0xff, 0xff)
BLACK       = RGBColor(0x1a, 0x1a, 0x1a)


def set_cell_bg(cell, colour: RGBColor):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    hex_col = f"{colour[0]:02X}{colour[1]:02X}{colour[2]:02X}"
    shd.set(qn("w:fill"), hex_col)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def hd1(doc, text):
    p = doc.add_heading(text, level=1)
    p.runs[0].font.color.rgb = BLUE_DARK
    p.runs[0].font.size = Pt(18)
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    return p


def hd2(doc, text):
    p = doc.add_heading(text, level=2)
    p.runs[0].font.color.rgb = BLUE_MID
    p.runs[0].font.size = Pt(13)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    return p


def hd3(doc, text):
    p = doc.add_heading(text, level=3)
    p.runs[0].font.color.rgb = BLUE_DARK
    p.runs[0].font.size = Pt(11)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    return p


def body(doc, text, bold=False, italic=False, size=10):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = BLACK
    p.paragraph_format.space_after = Pt(4)
    return p


def callout(doc, text):
    """Amber-highlighted callout paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.size = Pt(10)
    run.font.bold = True
    run.font.color.rgb = AMBER
    return p


def table_header_row(table, cols, widths=None):
    row = table.rows[0]
    for i, (cell, col) in enumerate(zip(row.cells, cols)):
        set_cell_bg(cell, BLUE_DARK)
        p = cell.paragraphs[0]
        p.clear()
        run = p.add_run(col)
        run.font.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = WHITE
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    if widths:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)


def add_table_row(table, values, alt=False, bold_first=False):
    row = table.add_row()
    fill = GREY_ROW if alt else WHITE
    for i, (cell, val) in enumerate(zip(row.cells, values)):
        set_cell_bg(cell, fill)
        p = cell.paragraphs[0]
        p.clear()
        run = p.add_run(str(val))
        run.font.size = Pt(9)
        run.font.color.rgb = BLACK
        if bold_first and i == 0:
            run.font.bold = True
    return row


def section_divider(doc):
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "2C5F8A")
    pBdr.append(bottom)
    pPr.append(pBdr)
    p.paragraph_format.space_after = Pt(8)


def main():
    doc = Document()

    # ── Page margins ──────────────────────────────────────────────
    section = doc.sections[0]
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

    generated = datetime.datetime.now().strftime("%d %b %Y")

    # ══════════════════════════════════════════════════════════════
    # TITLE
    # ══════════════════════════════════════════════════════════════
    title = doc.add_heading("DC Site Finder — Briefing Document", level=0)
    title.runs[0].font.color.rgb = BLUE_DARK
    title.runs[0].font.size = Pt(22)

    sub = doc.add_paragraph(f"Draft content for two-slide deck · {generated}")
    sub.runs[0].font.color.rgb = RGBColor(0x6b, 0x7a, 0x8d)
    sub.runs[0].font.size = Pt(10)
    sub.runs[0].font.italic = True
    sub.paragraph_format.space_after = Pt(16)

    section_divider(doc)

    # ══════════════════════════════════════════════════════════════
    # SLIDE 1: THREE OUTCOMES — HORMOZI STYLE
    # ══════════════════════════════════════════════════════════════
    hd1(doc, "SLIDE 1: What the Tool Does")
    hd2(doc, "Three outcomes DC operators get from day one")

    # ── Outcome 1 ──
    hd3(doc, "1.  Your team spends six weeks building a shortlist. This builds the same one before lunch.")

    body(doc, (
        "Manual site screening for a 100MW data centre currently takes a team of two, four to eight weeks. "
        "They're pulling NESO TEC queue registers, DNO headroom portals, EA flood maps, planning databases, "
        "and OS land parcel records — from different sources, in different formats, at different update frequencies. "
        "They're building a patchwork. And at the end of it, they might have 20 sites worth looking at."
    ))
    body(doc, (
        "The DC Site Finder covers 63,478 UK land parcels, pre-enriched with grid, flood, fibre, planning, and "
        "buildability data. Every parcel scored. Every filter instant. A 100MW search that takes a team two weeks "
        "to screen manually runs in seconds and returns a ranked shortlist with full score breakdowns."
    ))
    callout(doc, "63,478 parcels. Four dimensions. Instant ranked output. The analysis that took weeks now takes a filter.")

    doc.add_paragraph()

    # ── Outcome 2 ──
    hd3(doc, "2.  Every grid report you have seen about London substations is wrong — here is why.")

    body(doc, (
        "The most cited grid constraint measure in the UK is the NESO TEC Register. It shows near-zero queue "
        "pressure at London substations. That is because the TEC Register counts generation connections only — "
        "wind farms, batteries, power stations. No generators connect in Mayfair. So London looks unconstrained."
    ))
    body(doc, (
        "London is not unconstrained. It is running at 85–92% committed utilisation by 2030, once you include "
        "the demand connections — the hyperscalers, rail operators, and EV charging networks that have already "
        "contracted connections but haven't been built yet. That data lives in UKPN LTDS Table 3a. "
        "We ingest it, and we show you what the committed pipeline actually looks like."
    ))

    # Mini table: key London substations
    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    table_header_row(tbl, ["Substation", "Firm Capacity", "Current Util.", "2030 Committed Util."],
                     widths=[4.5, 3.5, 3.5, 4.5])
    data = [
        ("Wimbledon", "108 MW", "~55%", "85.6% — CONSTRAINED"),
        ("Barking 132kV", "84 MW", "~65%", "91.7% — CONSTRAINED"),
        ("St Johns Wood", "464 MW", "~42%", "59.6% — AMBER"),
        ("City Road", "980 MW", "~24%", "41.8% — AVAILABLE"),
    ]
    for i, row in enumerate(data):
        add_table_row(tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    callout(doc, (
        "Wimbledon: 85.6% committed by 2030. Barking: 91.7%. That is not in any broker report. "
        "It is in the LTDS. We read the LTDS."
    ))
    doc.add_paragraph()

    # ── Outcome 3 ──
    hd3(doc, "3.  Every number traces to a named public dataset. Take it to investment committee.")

    body(doc, (
        "Most site shortlists are built on qualitative judgement — broker estimates, anecdotal grid feedback, "
        "manual planning checks. They cannot be audited. They cannot be reproduced. And they create risk when "
        "the IC asks how you arrived at a number."
    ))
    body(doc, (
        "Every score in the DC Site Finder derives from a named, publicly available dataset with documented "
        "methodology. A site's power score traces back to its LTDS Table 3a row. Its flood exclusion traces "
        "back to the EA flood map polygon. Its fibre score traces back to the ITU BBmaps route segment. "
        "134 substations scored. 6 DNOs covered. No qualitative adjustments. No black boxes."
    ))
    callout(doc, (
        "Suitable as the primary data input to investment committee analysis — not just an internal screening exercise."
    ))

    section_divider(doc)

    # ══════════════════════════════════════════════════════════════
    # SCORING METHODOLOGY
    # ══════════════════════════════════════════════════════════════
    hd2(doc, "The scoring approach — step by step")

    # Stage 1
    hd3(doc, "Stage 1 — Ingest all relevant land parcels")
    body(doc, "What we do: Pull every land parcel in the UK that could plausibly host a data centre.")
    body(doc, "Data source: OpenStreetMap Overpass API")
    body(doc, (
        "How: Query for all polygons tagged as industrial, brownfield, power-related, transport, commercial, "
        "military, aviation, and extraction land use across all 13 UK regions. Filter to >2 acres (smaller "
        "sites are not viable for any meaningful DC development). Output: 63,478 raw parcels."
    ))

    # Stage 2
    hd3(doc, "Stage 2 — Apply hard exclusions (non-negotiable disqualifiers)")
    body(doc, "What we do: Remove parcels that are permanently non-viable regardless of grid or planning circumstances.")

    excl_tbl = doc.add_table(rows=1, cols=2)
    excl_tbl.style = "Table Grid"
    table_header_row(excl_tbl, ["Exclusion", "Data source"], widths=[7, 10])
    excl_data = [
        ("Flood Zone 3 (high probability of flooding)",
         "Environment Agency OGC WFS Flood Map API — all 63,478 parcels individually queried; 5,409 parcels excluded (8.5%)"),
        ("National Parks", "planning.data.gov.uk designation dataset"),
        ("Areas of Outstanding Natural Beauty (AONBs)", "planning.data.gov.uk designation dataset"),
        ("Sites of Special Scientific Interest (SSSIs)", "Natural England SSSI polygon layer"),
        ("Special Areas of Conservation (SACs)", "planning.data.gov.uk"),
        ("Special Protection Areas (SPAs)", "planning.data.gov.uk"),
        ("Ancient Woodland", "Forestry Commission Ancient Woodland Inventory"),
        ("Scheduled Monuments", "Historic England"),
    ]
    for i, row in enumerate(excl_data):
        add_table_row(excl_tbl, row, alt=(i % 2 == 1))

    body(doc, "After exclusions: 52,242 parcels remain in the scoreable universe.")
    doc.add_paragraph()

    # Stage 3
    hd3(doc, "Stage 3 — Score every remaining parcel across four dimensions")
    body(doc, (
        "Each parcel receives a composite score from 0–100, computed as a weighted average of four factors. "
        "Scores are pre-computed at three DC sizes (20 MW / 50 MW / 100 MW) and linearly interpolated at "
        "runtime. Every parcel has a score that responds to the user's selected campus size without recalculation."
    ))

    body(doc, "Composite formula:", bold=True)
    body(doc, "Composite = 0.40 × Power + 0.30 × Permissioning + 0.20 × Fibre + 0.10 × Buildability",
         bold=True, italic=True)
    doc.add_paragraph()

    # Factor 1 — Power
    body(doc, "Factor 1 — Power & Grid Access (40%)", bold=True, size=11)
    body(doc, "What question it answers: Can I actually connect here, and how fast?")

    body(doc, "Sub-components:", bold=True)

    pw_tbl = doc.add_table(rows=1, cols=2)
    pw_tbl.style = "Table Grid"
    table_header_row(pw_tbl, ["Sub-component", "Logic"], widths=[5, 12])
    pw_data = [
        ("Headroom score",
         "Firm capacity (N-1 standard) minus existing peak demand, scored 0–100 relative to MW requirement"),
        ("Queue pressure score",
         "How much headroom is already spoken for by committed connections. "
         "For UKPN: uses 2029/30 LTDS demand forecast (all contracted but not-yet-built connections). "
         "For other DNOs: TEC queue plus current utilisation. 100 = unconstrained, 0 = fully committed."),
        ("Voltage score",
         "400kV/275kV score highest; 132kV moderate; lower voltages penalised"),
        ("Distance factor",
         "Multiplier: within 5km = full score; degrades to 30km minimum. "
         "Each parcel scored against its nearest viable substation, not nearest regardless of capacity."),
    ]
    for i, row in enumerate(pw_data):
        add_table_row(pw_tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    body(doc, "Substation data by DNO:", bold=True)

    dno_tbl = doc.add_table(rows=1, cols=3)
    dno_tbl.style = "Table Grid"
    table_header_row(dno_tbl, ["DNO", "Source", "Metric used"], widths=[4, 7, 6])
    dno_data = [
        ("UKPN (London, South East, East)",
         "LTDS Table 3a — ltds-table-3a-load-data-observed\nukpowernetworks.opendatasoft.com",
         "Firm capacity (N-1), current demand, committed 2029/30 forecast demand"),
        ("NGED (Midlands, South West, Wales)",
         "NGED GSP Technical Limits CSV", "Technical import limits by season"),
        ("NPG (North East, Yorkshire)",
         "NPG GSP Heatmap", "Firm capacity, max demand"),
        ("SSEN (Southern England, Scottish Hydro)",
         "SSEN Headroom Dashboard", "Max observed demand, technical limits"),
        ("SPEN (North West England, Scotland)",
         "SPEN SPM Technical Limits", "Winter import limits"),
        ("ENW (North West England)",
         "ENW Primary Aggregated data", "GSP-level firm demand"),
    ]
    for i, row in enumerate(dno_data):
        add_table_row(dno_tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    body(doc, (
        "TEC generation queue for all substations: NESO TEC Register (api.neso.energy, updated twice weekly, "
        "2,229 projects, 137 GW total queue). Transmission powerlines: OpenStreetMap 132kV+ lines."
    ))
    doc.add_paragraph()

    # Factor 2 — Permissioning
    body(doc, "Factor 2 — Permissioning (30%)", bold=True, size=11)
    body(doc, "What question it answers: How hard will it be to get planning consent?")
    body(doc, (
        "Sites are placed into one of three consent risk buckets based on land type, "
        "then adjusted for designations. Flood zone is incorporated here — flood risk is a permissioning "
        "and insurability factor, not a separate dimension."
    ))

    perm_tbl = doc.add_table(rows=1, cols=3)
    perm_tbl.style = "Table Grid"
    table_header_row(perm_tbl, ["Bucket", "Score", "Land types"], widths=[3, 2, 12])
    perm_data = [
        ("A — Permitted / low risk", "85", "Industrial, brownfield, former power stations"),
        ("B — Achievable / standard consent", "55", "Transport, commercial, military"),
        ("C — Complex / change of use required", "20", "Extraction, aviation, farmland"),
    ]
    for i, row in enumerate(perm_data):
        add_table_row(perm_tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    body(doc, "Flood overlay: Zone 1 = full score retained; Zone 2 = score × 0.5; Zone 3 = hard excluded (score = 0).", bold=True)
    body(doc, "Adjustments:")
    body(doc, "  • Green Belt: score × 0.55 (significant planning hurdle)")
    body(doc, "  • Grey Belt (brownfield within Green Belt): score × 0.80 (NPPF Grey Belt policy — somewhat more achievable)")
    body(doc, "  • AI Growth Zone: +15 points (government-designated fast-track zones)")
    body(doc, "Data sources: OSM site tags; Green Belt / Grey Belt from planning.data.gov.uk; AI Growth Zones from DSIT.")
    doc.add_paragraph()

    # Factor 3 — Fibre
    body(doc, "Factor 3 — Fibre Connectivity (20%)", bold=True, size=11)
    body(doc, "What question it answers: Can I get carrier-grade diverse fibre routes?")
    body(doc, (
        "Scored on distance to the nearest of two infrastructure types: (1) backbone fibre route — under 1km "
        "scores maximum, degrades on a step curve to 100km minimum; (2) carrier-neutral colocation — "
        "nearest internet exchange or carrier-neutral facility. Final score takes the better of the two distances."
    ))
    body(doc, (
        "Data sources: ITU BBmaps WFS — 1,187 operational UK backbone fibre route segments. "
        "PeeringDB API — UK internet exchanges (IXPs) and carrier-neutral colocation facilities."
    ))
    doc.add_paragraph()

    # Factor 4 — Buildability
    body(doc, "Factor 4 — Buildability (10%)", bold=True, size=11)
    body(doc, "What question it answers: Is the site physically practical to develop?")
    body(doc, (
        "Two inputs: site area (scored relative to MW requirement; larger sites score higher — more phasing "
        "flexibility) and type penalty (active extraction sites, aviation with live runway constraints carry "
        "a buildability deduction). Data source: OpenStreetMap polygon geometry."
    ))

    section_divider(doc)

    # ══════════════════════════════════════════════════════════════
    # SLIDE 2: WATERFALL
    # ══════════════════════════════════════════════════════════════
    hd1(doc, "SLIDE 2: 100MW Waterfall — From 63,478 Parcels to Priority Sites")

    wf_tbl = doc.add_table(rows=1, cols=5)
    wf_tbl.style = "Table Grid"
    table_header_row(wf_tbl,
                     ["Step", "Label", "Parcels remaining", "Removed", "Why"],
                     widths=[1.5, 5, 3.5, 2.5, 5.5])
    wf_data = [
        ("1", "All UK land parcels", "63,478", "—",
         "Brownfield, industrial, agricultural, military, aviation and other DC-relevant types across all 13 UK regions"),
        ("2", "Remove Flood Zone 3", "58,069", "−5,409",
         "High flood risk — uninsurable for critical infrastructure under EA classification"),
        ("3", "Remove statutory designations", "52,242", "−5,827",
         "National Parks, AONBs, SSSIs, SACs, SPAs, Ancient Woodland, Scheduled Monuments"),
        ("4", "Remove sites < 200 acres", "4,669", "−47,573",
         "Minimum footprint for a 100MW campus (power hall, cooling, switchgear, security perimeter)"),
        ("5", "Set aside farmland", "715", "−3,954",
         "Agricultural land requires change of use — materially longer planning timeline; retained but deprioritised"),
        ("6", "Composite score ≥ 50", "~675", "~40",
         "Minimum viability threshold — poor grid access, remote location, or connectivity gap"),
        ("7", "Composite score ≥ 70", "~140", "~535",
         "Strong candidates — good grid headroom, established connectivity, acceptable permissioning"),
        ("8", "Composite score ≥ 80", "29", "~111",
         "High-quality sites — top-tier on power, fibre and permissioning dimensions"),
        ("9", "Priority 100MW sites", "Top 10", "—",
         "Best-in-class sites for detailed technical and commercial due diligence"),
    ]
    for i, row in enumerate(wf_data):
        r = add_table_row(wf_tbl, row, alt=(i % 2 == 1), bold_first=False)
        if i == 8:  # final row — highlight
            for cell in r.cells:
                set_cell_bg(cell, RGBColor(0xff, 0xf3, 0xcd))
                for para in cell.paragraphs:
                    for run in para.runs:
                        run.font.bold = True

    doc.add_paragraph()

    # Top sites table
    hd3(doc, "Top sites emerging from the 100MW funnel")

    ts_tbl = doc.add_table(rows=1, cols=6)
    ts_tbl.style = "Table Grid"
    table_header_row(ts_tbl,
                     ["Rank", "Site", "Region", "Size", "Type", "Score (100MW)"],
                     widths=[1.5, 4, 3.5, 2.5, 3, 3.5])
    ts_data = [
        ("1", "Industrial site", "North West", "266 ac", "Industrial", "89.7"),
        ("2", "Port of Southampton", "South East", "605 ac", "Industrial", "89.2"),
        ("3", "Industrial site", "Yorkshire", "443 ac", "Industrial", "87.7"),
        ("4", "Ratcliffe Power Station", "East Midlands", "276 ac", "Brownfield", "87.7"),
        ("5", "Sowton Industrial Estate", "South West", "228 ac", "Industrial", "87.7"),
    ]
    for i, row in enumerate(ts_data):
        add_table_row(ts_tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()

    body(doc, "Chart annotation notes:", bold=True)
    body(doc, (
        "The 200-acre cut is the single largest filter — 47,573 parcels removed. Most UK industrial sites "
        "are under 50 acres. 100MW campus requirements are fundamentally a land scarcity problem in the UK."
    ))
    body(doc, (
        "Flood Zone 3 and statutory designations combined remove 11,236 parcels (18% of total). "
        "These are genuinely non-negotiable — no planning authority will grant consent for critical national "
        "infrastructure in these zones."
    ))
    body(doc, (
        "Farmland is set aside, not excluded. 3,954 large agricultural sites remain in the dataset with a "
        "lower permissioning score (Bucket C, score 20), reflecting the change-of-use challenge. "
        "Available for analysis but deprioritised in the 100MW shortlist."
    ))
    body(doc, (
        "Ratcliffe Power Station is a notable example: brownfield former coal station with an existing 400kV "
        "grid connection on-site, placing it in Bucket A for permissioning and close to maximum power score "
        "for 100MW. Former coal and gas power stations represent some of the strongest opportunities in the UK."
    ))

    section_divider(doc)

    # ══════════════════════════════════════════════════════════════
    # WHAT'S BUILT — F1-F5
    # ══════════════════════════════════════════════════════════════
    hd1(doc, "What's Built — Current Feature Set")

    feat_tbl = doc.add_table(rows=1, cols=3)
    feat_tbl.style = "Table Grid"
    table_header_row(feat_tbl,
                     ["Feature", "Status", "Capability"],
                     widths=[5, 2.5, 10.5])

    feats_done = [
        ("F1 — Interactive map",
         "Complete",
         "63,478 UK land parcels across 13 regions, colour-coded by site type, power score, or composite "
         "score. Cluster view at low zoom; individual parcels at high zoom. Satellite / OS basemap toggle."),
        ("F2 — Power & grid scoring",
         "Complete",
         "134 substations, 6 DNOs (UKPN, NGED, NPG, SSEN, SPEN, ENW). Real TEC generation queue from NESO "
         "Register (2,229 projects, 137 GW). UKPN substations further enriched with LTDS Table 3a firm "
         "capacity (N-1 standard) and committed 2029/30 demand forecast — the only tool that shows real "
         "demand-side queue pressure, not just the generation register."),
        ("F3 — 4-factor composite scoring",
         "Complete",
         "Power (40%) + Permissioning (30%) + Fibre (20%) + Buildability (10%). Pre-computed at 20 MW, "
         "50 MW, and 100 MW anchor points and linearly interpolated at runtime. Score updates instantly "
         "as user moves the size slider."),
        ("F4 — Filters & search",
         "Complete",
         "Filter by: UK region, minimum site size (acres), minimum composite score, flood zone exclusion "
         "toggle, site type toggles (industrial / brownfield / transport / etc.), viewport-constrained "
         "area search. Results panel shows ranked shortlist with headline metrics."),
        ("F5 — Site detail panel",
         "Complete",
         "Click any parcel to open full breakdown: composite score and sub-scores, nearest substation "
         "with headroom / queue data, connection timeline estimate, permissioning bucket, flood zone "
         "status, site area, fibre proximity. All values traceable to source dataset."),
    ]

    for i, (feat, status, cap) in enumerate(feats_done):
        row = feat_tbl.add_row()
        for j, val in enumerate([feat, status, cap]):
            set_cell_bg(row.cells[j], GREY_ROW if i % 2 == 1 else WHITE)
            p = row.cells[j].paragraphs[0]
            p.clear()
            run = p.add_run(val)
            run.font.size = Pt(9)
            if j == 0:
                run.font.bold = True
                run.font.color.rgb = BLUE_DARK
            elif j == 1:
                run.font.bold = True
                run.font.color.rgb = GREEN
            else:
                run.font.color.rgb = BLACK

    section_divider(doc)

    # ══════════════════════════════════════════════════════════════
    # WHAT'S NEXT — F6-F8 BACKLOG
    # ══════════════════════════════════════════════════════════════
    hd1(doc, "What's Next — Backlog")

    back_tbl = doc.add_table(rows=1, cols=3)
    back_tbl.style = "Table Grid"
    table_header_row(back_tbl,
                     ["Feature", "Priority", "Description"],
                     widths=[5, 2.5, 10.5])

    backlog = [
        ("F6 — Export",
         "High",
         "CSV export of any filtered parcel shortlist (all scored fields). Single-site PDF summary for "
         "investor decks — composite scorecard, substation data, flood zone map, fibre proximity, "
         "permissioning bucket, connection timeline estimate."),
        ("F7 — Landowner identification",
         "High",
         "HMLR INSPIRE title number lookup. Companies House integration for corporate ownership resolution. "
         "Owner classification: individual / company / REIT / public sector / overseas entity. "
         "Direct outreach routing — finds the right contact rather than just the registered owner name. "
         "Cost: ~£3/query via HMLR API; queries run on-demand per site."),
        ("F8 — Land value estimation",
         "Medium",
         "£/acre benchmarks by region × site type (industrial, brownfield, agricultural). "
         "VOA rateable values as capital value proxy for commercial/industrial parcels. "
         "Brownfield remediation cost range (£50k–£500k/acre depending on former use). "
         "Planning risk flag (Low / Medium / High) based on designation, local plan policy, "
         "and Green Belt status. Output: indicative land cost range and total site acquisition budget."),
    ]

    for i, (feat, pri, desc) in enumerate(backlog):
        row = back_tbl.add_row()
        for j, val in enumerate([feat, pri, desc]):
            set_cell_bg(row.cells[j], GREY_ROW if i % 2 == 1 else WHITE)
            p = row.cells[j].paragraphs[0]
            p.clear()
            run = p.add_run(val)
            run.font.size = Pt(9)
            if j == 0:
                run.font.bold = True
                run.font.color.rgb = BLUE_DARK
            elif j == 1:
                run.font.bold = True
                run.font.color.rgb = AMBER
            else:
                run.font.color.rgb = BLACK

    doc.add_paragraph()

    # ── Footer note ──
    footer = doc.add_paragraph(
        f"Data current as of {generated}. Parcel data: OpenStreetMap. Grid data: NESO TEC Register + "
        "UKPN LTDS Table 3a. Flood data: Environment Agency. Fibre data: ITU BBmaps + PeeringDB. "
        "Planning: planning.data.gov.uk."
    )
    footer.runs[0].font.size = Pt(8)
    footer.runs[0].font.color.rgb = RGBColor(0x6b, 0x7a, 0x8d)
    footer.runs[0].font.italic = True

    doc.save(OUT_FILE)
    print(f"Saved: {OUT_FILE}")


if __name__ == "__main__":
    main()
