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


def bullet(doc, bold_text, detail_text=""):
    """Bullet point: bold key takeaway + regular supporting sentence."""
    p = doc.add_paragraph(style="List Bullet")
    run_b = p.add_run(bold_text)
    run_b.font.bold = True
    run_b.font.size = Pt(10)
    run_b.font.color.rgb = BLACK
    if detail_text:
        run_d = p.add_run(" " + detail_text)
        run_d.font.bold = False
        run_d.font.size = Pt(10)
        run_d.font.color.rgb = BLACK
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
    # SLIDE 1: OUTCOMES — TWO LEVELS
    # ══════════════════════════════════════════════════════════════
    hd1(doc, "SLIDE 1: What the Tool Does")

    # ── ORGANISATIONAL OUTCOMES ──────────────────────────────────
    hd2(doc, "For the organisation — proprietary ability to secure high-power land faster")

    body(doc, (
        "In the race for UK data centre sites, power is the constraint and speed is the differentiator. "
        "The organisations that win are not the ones with the best analysts — they are the ones that identify, "
        "option, and apply for power connections on viable sites before anyone else knows those sites exist. "
        "That window is closing. The DC Site Finder is built to be the systematic advantage that keeps it open."
    ))

    org_tbl = doc.add_table(rows=1, cols=2)
    org_tbl.style = "Table Grid"
    table_header_row(org_tbl, ["Organisational outcome", "What it means in practice"], widths=[7, 11])
    org_data = [
        ("Proprietary site pipeline before competitors",
         "Systematic scan of 63,478 UK parcels identifies optionable sites weeks before they surface "
         "through agents or are flagged by hyperscalers. First to option is first to apply for power. "
         "First to apply for power controls the connection queue position."),
        ("Grid intelligence that brokers and agents don't have",
         "The tool ingests UKPN LTDS Table 3a committed demand forecasts — data that shows which "
         "substations are 85–92% loaded by 2030 but appear unconstrained in the TEC Register. "
         "Competitors using standard grid reports are making decisions on wrong data."),
        ("IC-ready deal origination, not broker-dependent sourcing",
         "Every shortlisted site comes with an auditable score traceable to named public datasets. "
         "No reliance on broker estimates or anecdotal grid feedback. Suitable as primary input "
         "to investment committee analysis from day one."),
        ("Competitive intelligence on where hyperscalers are moving",
         "Planning application monitoring (coming F9) flags Amazon, Microsoft, Google, and Stack "
         "applications in real time — by geography and application stage. Know which markets "
         "are being targeted before those deals are public."),
    ]
    for i, row in enumerate(org_data):
        add_table_row(org_tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    callout(doc, (
        "The organisations that secure the best grid connections in the next 24 months will define "
        "UK data centre geography for a decade. This is the tool for that window."
    ))

    section_divider(doc)

    # ── EMPLOYEE / ANALYST OUTCOMES ──────────────────────────────
    hd2(doc, "For the analyst — stop wasting days on sites that fail at the last hurdle")

    body(doc, (
        "The current process is broken at the individual level. A site finder or analyst spends 90% of "
        "their due diligence on a site — power portal checks, flood map overlays, planning searches, "
        "fibre proximity — and then discovers a dealbreaker that was in the data all along. "
        "Flood Zone 3. An SSSI designation. A substation that is 91% committed by 2030. "
        "Days wasted. Deal dead. Start again."
    ))

    emp_tbl = doc.add_table(rows=1, cols=2)
    emp_tbl.style = "Table Grid"
    table_header_row(emp_tbl, ["Employee outcome", "What it replaces"], widths=[7, 11])
    emp_data = [
        ("Dealbreakers surfaced in seconds, not at the end of a week",
         "Hard exclusions (Flood Zone 3, SSSIs, AONBs, Scheduled Monuments) are pre-applied to all "
         "63,478 parcels. A site that would have failed after a week of manual checks is eliminated "
         "before it is ever opened. The analyst only sees viable sites."),
        ("One tool instead of ten portals",
         "NESO TEC Register. UKPN LTDS. EA Flood Map. planning.data.gov.uk. ITU BBmaps. PeeringDB. "
         "All pre-ingested, pre-processed, pre-scored. No more bouncing between portals and "
         "building spreadsheets to manually reconcile data in different formats."),
        ("A ranked shortlist in the time it takes to set three filters",
         "Region. Minimum site size. Minimum composite score. The tool returns a ranked list of "
         "matching parcels with full score breakdowns — power, permissioning, fibre, buildability. "
         "A 100MW shortlist that took two weeks to build manually is produced before lunch."),
        ("Scores you can defend, not gut feel you have to justify",
         "Every sub-score traces back to its source dataset. Power score → LTDS Table 3a row. "
         "Flood exclusion → EA polygon. Fibre score → ITU route segment. When a senior decision-maker "
         "or IC asks how you arrived at a site, the answer is a named public dataset, not 'desk research'."),
    ]
    for i, row in enumerate(emp_data):
        add_table_row(emp_tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    callout(doc, (
        "The tool does not replace judgement. It eliminates the work that was never worth doing in the first place."
    ))

    section_divider(doc)

    # ── GRID INTELLIGENCE CALLOUT ────────────────────────────────
    hd2(doc, "The grid picture everyone else is using is wrong")

    body(doc, (
        "The NESO TEC Register — the most cited grid constraint measure in the UK — shows near-zero queue "
        "pressure at London substations. That is because the TEC Register counts generation connections only: "
        "wind farms, batteries, power stations. No generators connect in Mayfair. So London looks unconstrained."
    ))
    body(doc, (
        "London is not unconstrained. It is running at 85–92% committed utilisation by 2030 once you "
        "include demand connections — the hyperscalers, rail operators, and EV charging networks that have "
        "already contracted connections but not yet been built. That data lives in UKPN LTDS Table 3a. "
        "The DC Site Finder ingests it."
    ))

    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    table_header_row(tbl, ["Substation", "Firm Capacity", "Current Util.", "2030 Committed Util."],
                     widths=[4.5, 3.5, 3.5, 4.5])
    london_data = [
        ("Wimbledon", "108 MW", "~55%", "85.6% — CONSTRAINED"),
        ("Barking 132kV", "84 MW", "~65%", "91.7% — CONSTRAINED"),
        ("St Johns Wood", "464 MW", "~42%", "59.6% — AMBER"),
        ("City Road", "980 MW", "~24%", "41.8% — AVAILABLE"),
    ]
    for i, row in enumerate(london_data):
        add_table_row(tbl, row, alt=(i % 2 == 1), bold_first=True)

    doc.add_paragraph()
    callout(doc, (
        "Wimbledon: 85.6% committed by 2030. Barking: 91.7%. "
        "That is not in any broker report. It is in the LTDS. We read the LTDS."
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
    # TOP 10 SITES — DETAILED ANALYSIS
    # ══════════════════════════════════════════════════════════════
    hd1(doc, "Top 10 Sites — Detailed Analysis (100MW)")

    body(doc, (
        "The following sites represent the highest-scoring land parcels from the DC Site Finder at a 100MW "
        "campus requirement. Each has been independently researched against publicly available sources. "
        "Where material changes have occurred since scoring (ownership changes, planning decisions, "
        "competing use commitments), these are flagged explicitly. All composite scores are as computed "
        "by the tool's four-factor model (Power 40%, Permissioning 30%, Fibre 20%, Buildability 10%)."
    ), italic=True)

    doc.add_paragraph()

    # ── SITE 1 ────────────────────────────────────────────────────
    hd2(doc, "1.  Carrington Energy Zone, Trafford, Greater Manchester")

    # Summary bar
    meta_tbl = doc.add_table(rows=1, cols=5)
    meta_tbl.style = "Table Grid"
    table_header_row(meta_tbl,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl, ["89.7 / 100", "266 acres", "Industrial", "North West", "Carrington 400kV (1.6km)"])

    doc.add_paragraph()
    bullet(doc, "Already a committed hyperscale cluster in formation, not a latent opportunity.",
           "Eclipse Power Optimise and Carlton Power signed a Joint Development Agreement in 2025 for Future Point Manchester — an energy park specifically designed for hyperscale DC development, actively marketing to operators as of mid-2025.")
    bullet(doc, "A 1.4GW bilateral private grid connection has been secured for 2028 with no upstream reinforcement required.",
           "This bypasses the multi-year queue problem that constrains virtually every other large UK site — an exceptional position that cannot be replicated at most comparable locations.")
    bullet(doc, "The on-site power cluster is unmatched in the UK outside London.",
           "The National Grid 400kV Carrington substation serves an 884MW ESB CCGT (commissioned 2016), a 680MW Statera BESS (planning secured, energisation target 2026), a £300M Highview liquid air energy storage project, and 500MW+ of planned low-carbon generation within the Future Point energy park.")
    bullet(doc, "Peel Land & Property is the dominant landowner across the wider 2,800-acre Carrington allocation.",
           "Trafford Council is leading an active masterplan process targeting 350,000 sqm of employment space. A prerequisite £130M Carrington Relief Road is in planning (2026), designed by Amey/Balfour Beatty.")
    bullet(doc, "The tool independently identified this geography as #1 before the market formalised around it.",
           "The scoring model's power weighting correctly surfaced the Carrington 400kV cluster — a validation of the methodology's ability to find signal ahead of public announcements.")

    doc.add_paragraph()

    # ── SITE 2 ────────────────────────────────────────────────────
    hd2(doc, "2.  Port of Southampton — Eastern Docks Industrial Area")

    meta_tbl2 = doc.add_table(rows=1, cols=5)
    meta_tbl2.style = "Table Grid"
    table_header_row(meta_tbl2,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl2, ["89.2 / 100", "605 acres", "Industrial", "South East", "Nursling 400kV (4.7km)"])

    doc.add_paragraph()
    bullet(doc, "ABP's Port Master Plan 2016–2035 is focused on expanding port capacity, not enabling change of use — making DC development on the core port estate unlikely without ABP's active cooperation.",
           "Southampton City Council's planning policy is strongly protective of port and industrial land; no data centre announcements or applications have been made on the port estate as of March 2026.")
    bullet(doc, "The Nursling 400kV Grid Supply Point 4.7km away is the principal attraction, not the port land itself.",
           "National Grid refurbished the entire Mannington-to-Nursling 400kV overhead line (115 pylons, originally 1966). Pivot Power received Test Valley BC approval for a 50MW BESS directly adjacent to the substation; BW ESS has consent for a grid-scale BESS at ABP's Marchwood Industrial Park.")
    bullet(doc, "Active grid investment in the Nursling corridor confirms this as a high-priority connection point, not a legacy asset.",
           "Two separate BESS projects with 400kV direct connections approved within 5km of the substation signals continued DNO investment in this grid node.")
    bullet(doc, "No local IXP in Southampton limits this location for colocation or wholesale deployments where carrier diversity matters.",
           "The nearest major internet exchanges are in London, accessed via national dark fibre along the M3 corridor — adequate for enterprise but limiting for carrier-neutral hosting.")
    callout(doc, (
        "Constraint flag: The Nursling Industrial Estate (Site 8 below) is the more actionable opportunity "
        "in this geography — closer to the substation, institutional ownership, no port land use protection. "
        "Port of Southampton scores on size and grid proximity; the acquisition route is through adjacent "
        "industrial land, not the ABP-controlled port estate."
    ))

    doc.add_paragraph()

    # ── SITE 3 ────────────────────────────────────────────────────
    hd2(doc, "3.  Ratcliffe-on-Soar Power Station, Nottinghamshire")

    meta_tbl3 = doc.add_table(rows=1, cols=5)
    meta_tbl3.style = "Table Grid"
    table_header_row(meta_tbl3,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl3, ["87.7 / 100", "276 acres", "Brownfield", "East Midlands", "Ratcliffe-on-Soar 400kV (0.35km)"])

    doc.add_paragraph()
    bullet(doc, "The 400kV and 132kV substations remain on-site through decommissioning, separately owned by National Grid and not part of the Uniper demolition programme.",
           "Uniper's planning documentation confirms 'existing energy infrastructure in place' with grid connections, demineralised water, and cooling water systems as retained infrastructure assets. The substation is just 350 metres from the parcel centroid — near-minimal connection cost.")
    bullet(doc, "Rushcliffe Borough Council's November 2025 Cabinet report formally proposed amending the LDO to explicitly permit data centre uses on the southern portion of the site.",
           "The report cited 'the rapid evolution of AI technology and the critical importance that the UK Government is placing on provision of data centres.' A full LDO review is scheduled for summer 2026 with DC uses expected to be formally incorporated.")
    bullet(doc, "The existing LDO (adopted July 2023, developed with Arup) already permits 810,000 sqm across advanced manufacturing, logistics, and R&D without individual planning consents.",
           "This is the fastest consent route of any brownfield DC site in the UK — no application, no determination, no appeal risk. DC uses are one Cabinet decision away from being added.")
    bullet(doc, "East Midlands Freeport designation provides business rates relief, enhanced capital allowances, and streamlined customs procedures for eligible occupiers.",
           "Adjacent East Midlands Parkway station connects to HS2, providing future high-speed rail access. The £330M EMERGE energy-from-waste facility has planning approval, adding potential waste-heat and behind-the-meter energy supply to the site.")
    callout(doc, (
        "Best-in-class former power station opportunity. On-site 400kV grid, streamlined LDO consent "
        "pathway, Freeport tax incentives, HS2 adjacency, and active council engagement with data "
        "centre operators — all confirmed by primary sources. The November 2025 LDO amendment is "
        "the clearest public signal of intent of any UK former power station site."
    ))

    doc.add_paragraph()

    # ── SITE 4 ────────────────────────────────────────────────────
    hd2(doc, "4.  Sowton Industrial Estate, Exeter, Devon")

    meta_tbl4 = doc.add_table(rows=1, cols=5)
    meta_tbl4.style = "Table Grid"
    table_header_row(meta_tbl4,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl4, ["87.7 / 100", "228 acres", "Industrial", "South West", "Exeter 400kV (3.6km)"])

    doc.add_paragraph()
    bullet(doc, "Sowton already has a proven data centre precedent — SWComms (now Focus Group) has operated a 600+ cabinet facility at Moor Lane since 2001, with multi-carrier redundancy and chilled water cooling.",
           "A second former DC at 9 Apple Lane (19,645 sq ft, 2.5MVA) was marketed at £2.95M in 2023, confirming both planning precedent and commercial demand for DC use within the estate.")
    bullet(doc, "The Exeter 400kV substation upgrade began October 2025 — explicitly designed to 'increase voltage control capability in anticipation of future demand growth'.",
           "Envolve Infrastructure on behalf of National Grid is replacing two transformers (SCT and EAT), commissioning through winter 2025/26. This is a direct forward-looking grid investment signal for this location.")
    bullet(doc, "Co-ownership by Devon County Council and Exeter City Council provides a public sector engagement route for large occupiers seeking a long-term leasehold.",
           "Stoford's long-term agreement with the Church Commissioners to unlock ~500,000 sq ft at the adjacent Exeter Logistics Park confirms continued institutional investment appetite in the M5 corridor.")
    bullet(doc, "No local IXP in Exeter limits wholesale or carrier-neutral DC deployments — the nearest major exchange is LINX Bristol.",
           "Dark fibre routes to London and Bristol are available via national carriers, but the absence of an Exeter-specific internet exchange is the binding connectivity constraint for any multi-tenant colocation use case.")

    doc.add_paragraph()

    # ── SITE 5 ────────────────────────────────────────────────────
    hd2(doc, "5.  West Burton Industrial Area, Nottinghamshire")

    meta_tbl5 = doc.add_table(rows=1, cols=5)
    meta_tbl5.style = "Table Grid"
    table_header_row(meta_tbl5,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl5, ["87.7 / 100", "443 acres", "Industrial", "Yorkshire / E. Midlands", "West Burton 400kV (0.8km)"])

    doc.add_paragraph()
    bullet(doc, "West Burton 400kV substation is an active, high-capacity transmission node — a 480MW solar farm received a Development Consent Order in January 2025 with its grid connection routed here.",
           "Keadby-to-West-Burton overhead line reconductoring completed November 2024. West Burton B (1,332MW CCGT, TotalEnergies) remains operational with active capacity market contracts, and 500MW BESS planning permission has been secured.")
    bullet(doc, "West Burton A (159ac, Site 14 in the dataset) is committed to the UK's first prototype fusion power plant — the STEP programme received £2.5B government commitment and cannot be considered for data centre use.",
           "In March 2026, the ILIOS consortium (Kier Group, Nuvia, BAM Nuttall, AECOM, Turner & Townsend) was appointed to lead a £200M redevelopment of West Burton A. Public consultation ran January to March 2026; first fusion operations targeted early 2040s.")
    bullet(doc, "The 443ac industrial parcel scored here is adjacent to but legally distinct from the West Burton A site — availability and ownership require direct verification.",
           "Any DC proposal in this area would need to navigate the STEP programme's planning protections, security perimeter requirements, and designation as nationally significant infrastructure.")
    callout(doc, (
        "Intelligence flag: West Burton A (159ac, ranked #14) is committed to STEP fusion. "
        "The 443ac industrial parcel is a separate but adjacent site — ownership and availability "
        "to be verified. Score reflects genuine grid advantage; STEP commitment is a material "
        "complication for any proposal in this area."
    ))

    doc.add_paragraph()

    # ── SITE 6 ────────────────────────────────────────────────────
    hd2(doc, "6.  Swansea West Business Park / Swansea Vale, South Wales")

    meta_tbl6 = doc.add_table(rows=1, cols=5)
    meta_tbl6.style = "Table Grid"
    table_header_row(meta_tbl6,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl6, ["87.0 / 100", "210 acres", "Industrial", "Wales", "Swansea North 400kV (4.7km)"])

    doc.add_paragraph()
    bullet(doc, "South Wales AI Growth Zone (designated autumn 2025) targets £10B investment and 1GW+ of data centre capacity — with Welsh Government fast-track planning averaging 28 days for major infrastructure decisions.",
           "Vantage Data Centers has already purchased the former Ford Bridgend factory (158 acres) and received outline planning consent for a 10-building campus with 3 substations, construction beginning 2026. Microsoft has also confirmed South Wales involvement.")
    bullet(doc, "Swansea North 400kV GIS substation is a modern installation using Mitsubishi Electric equipment — more capable and compact than legacy open-air substations elsewhere.",
           "GIS technology was commissioned specifically to transfer demand from the legacy 275kV infrastructure in response to rising 132kV demand, indicating a forward-looking grid investment cycle.")
    bullet(doc, "Both parks are managed directly by Swansea Council — a public sector counterparty that provides a straightforward, single-point engagement route for a large occupier.",
           "DVLA, ERS Insurance, and Western Power Distribution are confirmed occupiers at Swansea Vale, demonstrating government-grade occupier tolerance and planning precedent for large institutional uses.")
    bullet(doc, "Swansea sits 25–40km west of current Bridgend/Newport activity — lower land competition and earlier-stage opportunity, at the cost of slightly less established developer attention.",
           "Welsh Government support and Growth Zone fast-track benefits apply across South Wales, but the immediate concentration of hyperscaler and developer activity is further east. For an operator seeking lower competition with the same regulatory advantages, Swansea is the credible position.")

    doc.add_paragraph()

    # ── SITE 7 ────────────────────────────────────────────────────
    hd2(doc, "7.  Littlebrook Manorway, Dartford, Kent")

    meta_tbl7 = doc.add_table(rows=1, cols=5)
    meta_tbl7.style = "Table Grid"
    table_header_row(meta_tbl7,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl7, ["86.1 / 100", "166 acres", "Industrial", "London & South East", "Littlebrook 400kV (1.7km)"])

    doc.add_paragraph()
    bullet(doc, "The new Littlebrook 400kV substation was commissioned in April 2024 — one of the most significant recent transmission investments in the South East — designed to transmit 2GW of low-carbon electricity.",
           "Built by Balfour Beatty and GE Vernova replacing a 1977-era installation, it uses next-generation SF₆-free switchgear. It draws from IFA2, ElecLink, North Sea Link, and Thames Estuary offshore wind into approximately 1.5 million homes.")
    bullet(doc, "Thames Estuary Growth Board commissioned Buro Happold to conduct a dedicated data centre study for the region, explicitly naming the Littlebrook 400kV substation as the defining grid asset for future DC development.",
           "Custodian Data Centres opened a 10MW facility at Crossways Business Park, Dartford in Q2 2022. NTT, VIRTUS, and Kao Data operate large facilities in the wider M25/London orbital, confirming Dartford's role as an active secondary DC corridor.")
    bullet(doc, "The 166-acre Manorway parcel itself is substantially committed — Amazon's 2.3M sqft 'Mega Box', an IKEA pre-let, and Aegis Energy's EV charging hub (planning 2026) occupy or option the available land.",
           "The DC opportunity is the new 2GW substation and adjacent industrial land with direct connection access — not the Manorway parcel as scored. Acquisition requires identifying available land within 2km of the substation.")
    callout(doc, (
        "The tool's score reflects the grid proximity accurately; a direct acquisition approach would "
        "require identifying adjacent industrial land with connection access to the new substation. "
        "Dartford at the M25/M2 intersection is an increasingly competitive alternative to the "
        "congested Slough/Hayes/M4 cluster — 15 miles from Central London."
    ))

    doc.add_paragraph()

    # ── SITE 8 ────────────────────────────────────────────────────
    hd2(doc, "8.  Nursling Industrial Estate, Southampton, Hampshire")

    meta_tbl8 = doc.add_table(rows=1, cols=5)
    meta_tbl8.style = "Table Grid"
    table_header_row(meta_tbl8,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl8, ["88.7 / 100", "85 acres", "Industrial", "South East", "Nursling 400kV (1.3km)"])

    doc.add_paragraph()
    bullet(doc, "Scores 88.7 at only 85 acres — above several much larger sites — because the Nursling 400kV Grid Supply Point is just 1.3km away, the closest substation proximity of any South of England site in the top 10.",
           "National Grid has refurbished the entire Mannington-to-Nursling 400kV overhead line (115 pylons, originally 1966). Pivot Power (EDF) received Test Valley BC approval for a 50MW BESS with direct 400kV transmission connection on National Grid land adjacent to the substation.")
    bullet(doc, "Indurent — Blackstone-backed, formed July 2024 from Industrials REIT and St. Modwen Logistics — is the dominant institutional owner of the estate.",
           "Blackstone's institutional ownership profile means a single counterparty for any large occupier discussion, with the capital backing to structure non-standard long-term leasehold arrangements. Indurent 135 (135,617 sq ft, BREEAM Outstanding, EPC A+) was recently completed.")
    bullet(doc, "No data centre announcements as of March 2026 — this site is ahead of the market, not already committed.",
           "Southampton's DC market is thin (one commercial facility on DatacenterMap). No competing DC applications in the planning system. First-mover advantage is available to an operator willing to engage now.")
    bullet(doc, "No local IXP is the binding connectivity constraint for carrier-neutral or multi-tenant colocation deployments.",
           "For wholesale or enterprise DC where grid proximity is the primary factor and London latency is acceptable, the 1.3km substation distance makes Nursling one of the most actionable sites in the South of England outside the M25.")

    doc.add_paragraph()

    # ── SITE 9 ────────────────────────────────────────────────────
    hd2(doc, "9.  Rugeley Power Station, Staffordshire")

    meta_tbl9 = doc.add_table(rows=1, cols=5)
    meta_tbl9.style = "Table Grid"
    table_header_row(meta_tbl9,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl9, ["87.3 / 100", "142 acres", "Brownfield", "East Midlands", "Rugeley 400kV (1.6km)"])

    doc.add_paragraph()
    bullet(doc, "SOLD: ENGIE sold Rugeley to Vistry Group in August 2025 for a 2,300-home residential scheme — confirmed unavailable for data centre development.",
           "Vistry's redevelopment includes 2,300 low-carbon homes, a 26-hectare Riverside Park gifted to Staffordshire Wildlife Trust, and an Academy school opened September 2025. Only 5 hectares of unspecified employment space are included.")
    bullet(doc, "The 400kV National Grid substation remains operational and is being upgraded — National Grid is replacing and relocating the 132kV infrastructure with Stage 1 commissioning Autumn 2026 to Spring 2028.",
           "The grid asset that drove this site's score remains relevant for any adjacent industrial land within connection range. The substation itself is not part of the Vistry residential scheme.")
    bullet(doc, "Cannock Chase SAC and AONB within 8km is a material constraint for any high-impact industrial use in this area, independent of the residential commitment.",
           "Any proposal within the zone of influence requires a Habitats Regulations Assessment screening. The site also straddles Cannock Chase and Lichfield District Council boundaries, adding planning coordination complexity.")
    callout(doc, (
        "This site should be removed from active shortlists. Rugeley power station is confirmed for "
        "residential use. The 400kV substation remains a relevant grid asset but the site itself "
        "is not available. Monitor for adjacent brownfield parcels within substation connection range."
    ))

    doc.add_paragraph()

    # ── SITE 10 ────────────────────────────────────────────────────
    hd2(doc, "10.  Calmore Industrial Estate, Totton, Hampshire")

    meta_tbl10 = doc.add_table(rows=1, cols=5)
    meta_tbl10.style = "Table Grid"
    table_header_row(meta_tbl10,
                     ["Composite score", "Area", "Site type", "Region", "Nearest substation"],
                     widths=[3.5, 2.5, 3, 3.5, 5.5])
    add_table_row(meta_tbl10, ["87.0 / 100", "82 acres", "Industrial", "South East", "Nursling 400kV (3.1km)"])

    doc.add_paragraph()
    bullet(doc, "Sits in the same Nursling 400kV grid catchment as Sites 2 and 8, but 3.1km from the substation versus Nursling Industrial Estate's 1.3km — the additional distance is the principal score differentiator.",
           "The same grid fundamentals apply: Nursling 400kV GSP recently refurbished, Pivot Power 50MW BESS approved adjacent, active SSEN investment in the Hampshire distribution network.")
    bullet(doc, "New Forest National Park boundary constrains westward expansion, but the existing estate sits outside the designated area and benefits from established industrial land use (Bucket A permissioning).",
           "The Park boundary is a hard western limit for any scale-up — any DC development here must be contained within the existing estate footprint rather than assembled by expanding outward.")
    bullet(doc, "Land ownership is more fragmented than Nursling — multiple industrial freeholders rather than a dominant institutional counterparty.",
           "Assembly complexity is higher than Nursling. The principal argument for Calmore is lower cost per acre given the additional substation distance and more mixed occupier profile, not superior grid access.")
    bullet(doc, "Best assessed as part of a coordinated Nursling substation connection strategy alongside Site 8, not as a standalone acquisition.",
           "A developer assembling land in the Southampton grid catchment should treat Calmore and Nursling Industrial Estate as a combined opportunity — maximising parcel optionality within connection distance of the same 400kV GSP.")

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
         "Turns site identification into actionable deal origination. Cost: ~£3/query via HMLR API."),
        ("F8 — Land value estimation",
         "Medium",
         "£/acre benchmarks by region × site type (industrial, brownfield, agricultural). "
         "VOA rateable values as capital value proxy for commercial/industrial parcels. "
         "Brownfield remediation cost range (£50k–£500k/acre depending on former use). "
         "Planning risk flag (Low / Medium / High). Output: indicative land cost range in context "
         "of total capex stack."),
        ("F9 — Planning application monitoring",
         "High",
         "Alerts when planning applications are submitted near scored parcels — filterable by applicant "
         "name and keywords ('data centre', 'data hall', 'hyperscale'). Application stage shown: "
         "outline / detailed / permitted / refused. Identifies competitor activity by geography. "
         "Replaces £24k/yr ProPSearch subscription. Data: planning.data.gov.uk API (free, daily updates)."),
        ("F10 — Behind-the-meter power scoring",
         "High",
         "Sites with existing HV infrastructure on-site (former power stations, on-site substations, "
         "EfW plants) are categorically faster and cheaper to connect than grid-dependent sites. "
         "Currently scored identically — a material gap. OSM power layer detection of existing "
         "transformers, plant, and private wire within parcel boundary. Scoring bonus of +10–20 points "
         "on the power dimension for qualifying sites."),
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
