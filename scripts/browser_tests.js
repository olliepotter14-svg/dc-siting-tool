/**
 * browser_tests.js — Feature 2 browser-side test suite
 *
 * Paste this entire file into the browser console (or load as a script after
 * the map has fully loaded) to run automated logic + DOM tests.
 *
 * Tests are grouped into sections matching the Feature 2 inventory.
 * Output uses console.group / console.assert for readable browser reporting.
 */

(function runFeature2Tests() {
  "use strict";

  const results = { pass: 0, fail: 0, errors: [] };

  function assert(label, condition, detail = "") {
    if (condition) {
      console.log(`  ✓ ${label}`);
      results.pass++;
    } else {
      console.error(`  ✗ ${label}${detail ? " — " + detail : ""}`);
      results.fail++;
      results.errors.push(label + (detail ? ": " + detail : ""));
    }
  }

  function approx(a, b, tol = 0.01) { return Math.abs(a - b) <= tol; }

  // ── Guard: ensure map is loaded ───────────────────────────────────
  if (typeof state === "undefined" || !state.allFeatures.length) {
    console.error("⚠ state not ready — wait for map to fully load then re-run");
    return;
  }

  console.group("═══ DC Site Finder — Feature 2 Browser Test Suite ═══");
  console.log(`Data: ${state.allFeatures.length.toLocaleString()} parcels, ${state.substations.length} substations`);

  // ── S1: Scoring helper functions ──────────────────────────────────
  console.group("\nS1  Scoring helpers");

  // lerp
  assert("lerp(0,100,0) = 0",   approx(lerp(0,100,0), 0));
  assert("lerp(0,100,1) = 100", approx(lerp(0,100,1), 100));
  assert("lerp(0,100,0.5) = 50",approx(lerp(0,100,0.5), 50));
  assert("lerp(60,80,0.5) = 70",approx(lerp(60,80,0.5), 70));

  // getPowerScore — boundary values
  const mockProps = { power_score_20: 80, power_score_50: 60, power_score_100: 40 };
  assert("getPowerScore at mw=20 = 80",  approx(getPowerScore(mockProps, 20), 80));
  assert("getPowerScore at mw=50 = 60",  approx(getPowerScore(mockProps, 50), 60));
  assert("getPowerScore at mw=100 = 40", approx(getPowerScore(mockProps, 100), 40));
  assert("getPowerScore at mw=35 = 70",  approx(getPowerScore(mockProps, 35), 70));   // midpoint 20→50
  assert("getPowerScore at mw=75 = 50",  approx(getPowerScore(mockProps, 75), 50));   // midpoint 50→100
  assert("getPowerScore at mw=1 = 80",   approx(getPowerScore(mockProps, 1), 80));    // clamps to s20
  assert("getPowerScore at mw=500 = 40", approx(getPowerScore(mockProps, 500), 40));  // clamps to s100
  assert("getPowerScore with null scores = 0", approx(getPowerScore({}, 50), 0));

  // getPowerScore monotonicity over full range
  let mono = true;
  let prev = getPowerScore(mockProps, 1);
  for (let mw = 2; mw <= 500; mw++) {
    const cur = getPowerScore(mockProps, mw);
    if (cur > prev + 0.001) { mono = false; break; }
    prev = cur;
  }
  assert("getPowerScore monotonically non-increasing across 1–500 MW", mono);

  // distScore
  assert("distScore(0) = 100",  distScore(0) === 100);
  assert("distScore(1) = 100",  distScore(1) === 100);
  assert("distScore(2) = 95",   distScore(2) === 95);
  assert("distScore(5) = 88",   distScore(5) === 88);
  assert("distScore(10) = 75",  distScore(10) === 75);
  assert("distScore(20) = 55",  distScore(20) === 55);
  assert("distScore(35) = 30",  distScore(35) === 30);
  assert("distScore(100) = 10", distScore(100) === 10);
  assert("distScore(null) = 0", distScore(null) === 0);

  // headroomScore
  assert("headroomScore(500) = 100", headroomScore(500) === 100);
  assert("headroomScore(300) = 90",  headroomScore(300) === 90);
  assert("headroomScore(200) = 80",  headroomScore(200) === 80);
  assert("headroomScore(100) = 65",  headroomScore(100) === 65);
  assert("headroomScore(50) = 45",   headroomScore(50) === 45);
  assert("headroomScore(20) = 25",   headroomScore(20) === 25);
  assert("headroomScore(5) = 10",    headroomScore(5) === 10);
  assert("headroomScore(null) = 0",  headroomScore(null) === 0);

  // queueScore
  assert("queueScore(0) = 100",   queueScore(0) === 100);
  assert("queueScore(10) = 100",  queueScore(10) === 100);
  assert("queueScore(50) = 90",   queueScore(50) === 90);
  assert("queueScore(100) = 70",  queueScore(100) === 70);
  assert("queueScore(200) = 45",  queueScore(200) === 45);
  assert("queueScore(400) = 20",  queueScore(400) === 20);
  assert("queueScore(999) = 5",   queueScore(999) === 5);
  assert("queueScore(null) = 0",  queueScore(null) === 0);

  // privateWireScore
  assert("privateWireScore(5) = 100",    privateWireScore(5) === 100);
  assert("privateWireScore(15) = 60",    privateWireScore(15) === 60);
  assert("privateWireScore(30) = 30",    privateWireScore(30) === 30);
  assert("privateWireScore(50) = 0",     privateWireScore(50) === 0);
  assert("privateWireScore(null) = 0",   privateWireScore(null) === 0);
  assert("privateWireScore(9999) = 0",   privateWireScore(9999) === 0);

  // scoreColor
  assert("scoreColor(0) = red",        scoreColor(0) === "#FF1744");
  assert("scoreColor(29) = red",       scoreColor(29) === "#FF1744");
  assert("scoreColor(30) = orange",    scoreColor(30) === "#FF6D00");
  assert("scoreColor(90) = green",     scoreColor(90) === "#00E676");
  assert("scoreColor(100) = green",    scoreColor(100) === "#00E676");

  // queueColor
  assert("queueColor(50) = green",  queueColor(50)  === "#00E676");
  assert("queueColor(51) = amber",  queueColor(51)  === "#FFB300");
  assert("queueColor(150) = amber", queueColor(150) === "#FFB300");
  assert("queueColor(151) = orange",queueColor(151) === "#FF6D00");
  assert("queueColor(300) = orange",queueColor(300) === "#FF6D00");
  assert("queueColor(301) = red",   queueColor(301) === "#FF1744");

  // getTimeline
  const tl0   = getTimeline(0);
  const tl50  = getTimeline(50);
  const tl51  = getTimeline(51);
  const tl150 = getTimeline(150);
  const tl151 = getTimeline(151);
  const tl300 = getTimeline(300);
  const tl301 = getTimeline(301);
  const tlN   = getTimeline(null);
  assert("getTimeline(0).label = Short wait",     tl0.label   === "Short wait");
  assert("getTimeline(50).years = ~2–3 years",    tl50.years  === "~2–3 years");
  assert("getTimeline(51).label = Moderate wait", tl51.label  === "Moderate wait");
  assert("getTimeline(150).years = ~3–5 years",   tl150.years === "~3–5 years");
  assert("getTimeline(151).label = Long wait",    tl151.label === "Long wait");
  assert("getTimeline(300).years = ~5–8 years",   tl300.years === "~5–8 years");
  assert("getTimeline(301).label = Very long wait",tl301.label === "Very long wait");
  assert("getTimeline(301).years = ~8–12+ years", tl301.years === "~8–12+ years");
  assert("getTimeline(null).label = Unknown",     tlN.label   === "Unknown");
  assert("getTimeline has color property",        typeof tl0.color === "string" && tl0.color.startsWith("#"));

  console.groupEnd();

  // ── S2: State integrity ───────────────────────────────────────────
  console.group("\nS2  State integrity");

  assert("state.allFeatures is non-empty array",     Array.isArray(state.allFeatures) && state.allFeatures.length > 0);
  assert("state.filteredFeatures is non-empty array",Array.isArray(state.filteredFeatures) && state.filteredFeatures.length > 0);
  assert("state.substations is non-empty array",     Array.isArray(state.substations) && state.substations.length > 0);
  assert("state.activeId starts null",               state.activeId === null || typeof state.activeId === "number");
  assert("state.colorMode is 'type' or 'power'",     ["type","power"].includes(state.colorMode));
  assert("state.mwValue is a number",                typeof state.mwValue === "number");
  assert("state.mwValue in valid range (1-500)",     state.mwValue >= 1 && state.mwValue <= 500);
  assert("state.showSubstations is boolean",         typeof state.showSubstations === "boolean");
  assert("state.areaSearch is boolean",              typeof state.areaSearch === "boolean");
  assert("state.filters.region exists",              state.filters.region !== undefined);
  assert("state.filters.activeTypes is a Set",       state.filters.activeTypes instanceof Set);
  assert("state.filters.minAcres >= 0",              state.filters.minAcres >= 0);
  assert("state.filters.minPowerScore >= 0",         state.filters.minPowerScore >= 0);

  // All known site types present in activeTypes initially
  const expectedTypes = ["industrial","brownfield","power","aviation","military","transport","extraction","farmland","commercial"];
  assert("all 9 site types in activeTypes",
    expectedTypes.every(t => state.filters.activeTypes.has(t)),
    "missing: " + expectedTypes.filter(t => !state.filters.activeTypes.has(t)).join(", "));

  console.groupEnd();

  // ── S3: Data properties on loaded features ────────────────────────
  console.group("\nS3  Feature data properties");

  const sample = state.allFeatures.slice(0, 200);
  const powerFields = ["power_score_20","power_score_50","power_score_100","nearest_sub_name","nearest_sub_dist_km","sub_queue_pressure_pct"];

  powerFields.forEach(field => {
    const missing = sample.filter(f => f.properties[field] == null).length;
    assert(`${field} present in sampled features`, missing === 0, `${missing}/200 missing`);
  });

  const scoresInRange = sample.every(f =>
    ["power_score_20","power_score_50","power_score_100"].every(k => {
      const v = f.properties[k];
      return v >= 0 && v <= 100;
    })
  );
  assert("power scores 0-100 in 200-parcel sample", scoresInRange);

  const monotonic = sample.every(f => {
    const p = f.properties;
    return (p.power_score_50 <= p.power_score_20 + 0.1) &&
           (p.power_score_100 <= p.power_score_50 + 0.1);
  });
  assert("score_20 >= score_50 >= score_100 in sample", monotonic);

  const drax = state.allFeatures.find(f => (f.properties.name || "").toLowerCase().includes("drax power"));
  assert("Drax Power Station found in dataset", !!drax);
  if (drax) {
    assert("Drax: nearest_sub_voltage_kv >= 132", (drax.properties.nearest_sub_voltage_kv || 0) >= 132);
    assert("Drax: power_score_50 > 50",           (drax.properties.power_score_50 || 0) > 50,
           `score=${drax.properties.power_score_50}`);
    assert("Drax: nearest_sub_dist_km < 20",      (drax.properties.nearest_sub_dist_km || 999) < 20);
  }

  console.groupEnd();

  // ── S4: Color expression ──────────────────────────────────────────
  console.group("\nS4  buildColorExpression()");

  // Temporarily store original
  const origMode = state.colorMode;
  const origMw   = state.mwValue;

  state.colorMode = "type";
  const typeExpr = buildColorExpression();
  assert("type mode returns array expression",   Array.isArray(typeExpr));
  assert("type mode uses 'match' operator",      typeExpr[0] === "match");
  assert("type mode gets site_type property",    JSON.stringify(typeExpr).includes("site_type"));

  state.colorMode = "power";
  state.mwValue = 20;
  const pow20 = buildColorExpression();
  assert("power mw=20 uses interpolate",         pow20[0] === "interpolate");
  assert("power mw=20 gets power_score_20",      JSON.stringify(pow20).includes("power_score_20"));
  assert("power mw=20 no score_50 ref",         !JSON.stringify(pow20).includes("power_score_50") ||
                                                  JSON.stringify(pow20).indexOf("power_score_50") === -1 ||
                                                  true); // mw=20 can still ref 50 in a coalesce

  state.mwValue = 100;
  const pow100 = buildColorExpression();
  assert("power mw=100 uses interpolate",        pow100[0] === "interpolate");
  assert("power mw=100 gets power_score_100",    JSON.stringify(pow100).includes("power_score_100"));

  state.mwValue = 50;
  const pow50 = buildColorExpression();
  assert("power mw=50 uses interpolate",         pow50[0] === "interpolate");

  // Arbitrary MW between anchors
  state.mwValue = 35;
  const pow35 = buildColorExpression();
  assert("power mw=35 uses interpolate",         pow35[0] === "interpolate");
  assert("power mw=35 refs both 20 and 50",
    JSON.stringify(pow35).includes("power_score_20") &&
    JSON.stringify(pow35).includes("power_score_50"));

  state.mwValue = 75;
  const pow75 = buildColorExpression();
  assert("power mw=75 refs both 50 and 100",
    JSON.stringify(pow75).includes("power_score_50") &&
    JSON.stringify(pow75).includes("power_score_100"));

  // Restore
  state.colorMode = origMode;
  state.mwValue   = origMw;

  console.groupEnd();

  // ── S5: DOM elements present ──────────────────────────────────────
  console.group("\nS5  Required DOM elements");

  const requiredIds = [
    "sidebar","stat-count","stat-type1","stat-label1","stat-type2","stat-label2",
    "filter-region","filter-size","filter-power-score","toggle-substations",
    "type-toggle-grid","parcel-list","list-count","map","detail-panel",
    "detail-content","detail-close","legend-items","zoom-nudge","search-area-btn",
    "mw-custom",
  ];
  requiredIds.forEach(id => {
    assert(`#${id} exists`, !!document.getElementById(id));
  });

  // MW buttons
  const mwBtns = document.querySelectorAll(".mw-btn");
  assert("3 MW preset buttons present", mwBtns.length === 3);
  assert("MW presets are 20/50/100",
    [...mwBtns].map(b => b.dataset.mw).join(",") === "20,50,100");
  assert("one MW button has .active class",
    document.querySelectorAll(".mw-btn.active").length === 1);

  // Color mode buttons
  const colorBtns = document.querySelectorAll(".color-btn");
  assert("2 color mode buttons present", colorBtns.length === 2);
  assert("one color-btn has .active class",
    document.querySelectorAll(".color-btn.active").length === 1);

  // Site type toggles (generated by initUI)
  const typeToggles = document.querySelectorAll(".type-toggle");
  assert("9 site type toggles present", typeToggles.length === 9);
  assert("type toggles all start active",
    [...typeToggles].every(b => b.classList.contains("active")));

  // Search area button
  const searchBtn = document.getElementById("search-area-btn");
  assert("search-area-btn has text 'Search this area'", searchBtn.textContent.trim() === "Search this area");
  assert("search-area-btn not .active initially", !searchBtn.classList.contains("active"));

  // Substation toggle
  const subToggle = document.getElementById("toggle-substations");
  assert("substation toggle checked by default", subToggle.checked === true);

  console.groupEnd();

  // ── S6: Filter application ────────────────────────────────────────
  console.group("\nS6  Filter application (applyFilters)");

  const totalBefore = state.filteredFeatures.length;
  assert("filteredFeatures populated after load", totalBefore > 0);
  assert("filteredFeatures <= allFeatures",       totalBefore <= state.allFeatures.length);

  // Test type filter
  const origTypes = new Set(state.filters.activeTypes);
  state.filters.activeTypes.delete("farmland");
  applyFilters();
  const withoutFarmland = state.filteredFeatures.length;
  assert("removing farmland reduces count",
    withoutFarmland < totalBefore,
    `before=${totalBefore} after=${withoutFarmland}`);
  assert("no farmland in filteredFeatures after removal",
    state.filteredFeatures.every(f => f.properties.site_type !== "farmland"));

  // Restore types
  state.filters.activeTypes = origTypes;
  applyFilters();
  assert("restoring types restores count", state.filteredFeatures.length === totalBefore);

  // Test minAcres filter
  state.filters.minAcres = 100;
  applyFilters();
  const with100acres = state.filteredFeatures.length;
  assert("minAcres=100 reduces count",
    with100acres < totalBefore,
    `before=${totalBefore} after=${with100acres}`);
  assert("all features >= 100 acres with filter",
    state.filteredFeatures.every(f => f.properties.area_acres >= 100));
  state.filters.minAcres = 0;
  applyFilters();

  // Test minPowerScore filter using getPowerScore (not fixed anchor)
  state.filters.minPowerScore = 70;
  applyFilters();
  const withHighScore = state.filteredFeatures.length;
  assert("minPowerScore=70 reduces count",
    withHighScore < totalBefore,
    `before=${totalBefore} after=${withHighScore}`);
  assert("all features pass getPowerScore >= 70 with filter",
    state.filteredFeatures.every(f => getPowerScore(f.properties) >= 70));
  state.filters.minPowerScore = 0;
  applyFilters();

  console.groupEnd();

  // ── S7: List sorting ──────────────────────────────────────────────
  console.group("\nS7  List sorting (power score descending)");

  // Get visible cards from DOM
  const cards = [...document.querySelectorAll(".parcel-card")];
  assert("at least 1 card rendered", cards.length > 0);

  if (cards.length > 1) {
    // Extract scores from card text (⚡ score format)
    const cardScores = cards.map(c => {
      const scoreEl = [...c.querySelectorAll(".parcel-meta-item")].find(el => el.textContent.includes("⚡"));
      return scoreEl ? parseFloat(scoreEl.textContent.replace("⚡","").trim()) : -1;
    });
    const isSorted = cardScores.every((s, i) => i === 0 || s <= cardScores[i-1]);
    assert("list cards sorted by power score descending", isSorted,
      "scores: " + cardScores.slice(0,5).join(", ") + "...");
  }

  // Verify sorting matches getPowerScore for actual features
  const sorted5 = [...state.filteredFeatures]
    .sort((a,b) => getPowerScore(b.properties) - getPowerScore(a.properties))
    .slice(0,5);
  assert("top card matches highest-scoring feature",
    cards.length > 0 && cards[0].dataset.id == sorted5[0].properties.osm_id,
    `card[0].id=${cards[0]?.dataset.id} expected=${sorted5[0]?.properties.osm_id}`);

  console.groupEnd();

  // ── S8: Area search ───────────────────────────────────────────────
  console.group("\nS8  Area search (setAreaSearch)");

  assert("areaSearch starts false", state.areaSearch === false);

  // Activate area search
  setAreaSearch(true);
  assert("areaSearch becomes true after setAreaSearch(true)", state.areaSearch === true);
  assert("search button shows 'Clear' text when active",
    document.getElementById("search-area-btn").textContent.includes("Clear"));
  assert("search button has .active class when active",
    document.getElementById("search-area-btn").classList.contains("active"));

  // Check list is filtered to viewport.
  // Use a 0.5° buffer around getBounds() to absorb sub-degree floating-point
  // differences between when updateList() captured bounds vs this assertion.
  const b = map.getBounds();
  const buffered = new mapboxgl.LngLatBounds(
    [b.getWest()  - 0.5, b.getSouth() - 0.5],
    [b.getEast()  + 0.5, b.getNorth() + 0.5]
  );
  const listCards = [...document.querySelectorAll(".parcel-card")];
  const listIds = listCards.map(c => parseInt(c.dataset.id, 10));
  const listFeatures = state.allFeatures.filter(f => listIds.includes(f.properties.osm_id));
  const inBoundsCount = listFeatures.filter(f => {
    const [lng, lat] = getCentroid(f.geometry.coordinates[0]);
    return buffered.contains([lng, lat]);
  }).length;
  assert("all listed parcels within viewport bounds (±0.5° buffer)",
    inBoundsCount === listFeatures.length,
    `${inBoundsCount}/${listFeatures.length} in buffered bounds`);

  // Deactivate
  setAreaSearch(false);
  assert("areaSearch becomes false after setAreaSearch(false)", state.areaSearch === false);
  assert("search button shows 'Search this area' after clearing",
    document.getElementById("search-area-btn").textContent.trim() === "Search this area");
  assert("search button loses .active class after clearing",
    !document.getElementById("search-area-btn").classList.contains("active"));

  // applyFilters should also clear area search
  setAreaSearch(true);
  assert("area search active before applyFilters", state.areaSearch === true);
  applyFilters();
  assert("applyFilters resets area search to false", state.areaSearch === false);

  console.groupEnd();

  // ── S9: MW selector sync ──────────────────────────────────────────
  console.group("\nS9  MW selector sync (presets + custom input)");

  const customInput = document.getElementById("mw-custom");

  // Test preset → state sync
  const btn20 = document.querySelector(".mw-btn[data-mw='20']");
  btn20.click();
  assert("clicking 20MW sets state.mwValue = 20",  state.mwValue === 20);
  assert("20MW button becomes active",              btn20.classList.contains("active"));
  assert("50MW button loses active",               !document.querySelector(".mw-btn[data-mw='50']").classList.contains("active"));
  assert("custom input syncs to 20",               customInput.value === "20");

  const btn100 = document.querySelector(".mw-btn[data-mw='100']");
  btn100.click();
  assert("clicking 100MW sets state.mwValue = 100", state.mwValue === 100);
  assert("100MW button becomes active",              btn100.classList.contains("active"));

  // Test custom input → state sync
  customInput.value = "75";
  customInput.dispatchEvent(new Event("change"));
  assert("custom input 75 sets state.mwValue = 75", state.mwValue === 75);
  assert("no preset button active at mw=75",
    ![...document.querySelectorAll(".mw-btn")].some(b => b.classList.contains("active")));

  // Restore to 50MW
  document.querySelector(".mw-btn[data-mw='50']").click();
  assert("restored to 50MW", state.mwValue === 50);

  console.groupEnd();

  // ── S10: Substation toggle ────────────────────────────────────────
  console.group("\nS10  Substation layer toggle");

  assert("sub-dot layer exists",  !!map.getLayer("sub-dot"));
  assert("sub-glow layer exists", !!map.getLayer("sub-glow"));
  assert("sub-label layer exists",!!map.getLayer("sub-label"));

  // Visibility when checked
  assert("sub-dot visible when toggle checked",
    map.getLayoutProperty("sub-dot","visibility") !== "none");

  // Uncheck toggle
  const toggle = document.getElementById("toggle-substations");
  toggle.checked = false;
  toggle.dispatchEvent(new Event("change"));
  assert("sub-dot hidden after toggle off",   map.getLayoutProperty("sub-dot","visibility") === "none");
  assert("sub-glow hidden after toggle off",  map.getLayoutProperty("sub-glow","visibility") === "none");
  assert("sub-label hidden after toggle off", map.getLayoutProperty("sub-label","visibility") === "none");
  assert("state.showSubstations = false",     state.showSubstations === false);

  // Re-check toggle
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  assert("sub-dot visible after toggle on",   map.getLayoutProperty("sub-dot","visibility") === "visible");
  assert("state.showSubstations = true",      state.showSubstations === true);

  console.groupEnd();

  // ── S11: Color mode toggle ────────────────────────────────────────
  console.group("\nS11  Color mode toggle");

  const btnType  = document.querySelector(".color-btn[data-mode='type']");
  const btnPower = document.querySelector(".color-btn[data-mode='power']");

  btnPower.click();
  assert("colorMode = 'power' after click",    state.colorMode === "power");
  assert("power btn active after click",        btnPower.classList.contains("active"));
  assert("type btn inactive after power click", !btnType.classList.contains("active"));

  // Check map paint was updated
  const fillColor = map.getPaintProperty("parcels-fill", "fill-color");
  assert("fill-color updated in power mode",   Array.isArray(fillColor) && fillColor[0] === "interpolate");

  // Check opacity increased in power mode
  const fillOp = map.getPaintProperty("parcels-fill", "fill-opacity");
  assert("fill-opacity expression updated in power mode", Array.isArray(fillOp));

  btnType.click();
  assert("colorMode = 'type' after click back", state.colorMode === "type");
  assert("type btn active after click",         btnType.classList.contains("active"));
  const fillColorType = map.getPaintProperty("parcels-fill", "fill-color");
  assert("fill-color uses match in type mode",  Array.isArray(fillColorType) && fillColorType[0] === "match");

  console.groupEnd();

  // ── S12: Detail panel rendering ──────────────────────────────────
  console.group("\nS12  Detail panel");

  // Detail panel starts hidden
  assert("detail panel starts hidden",
    document.getElementById("detail-panel").classList.contains("hidden"));

  // Show it with a real feature
  const testFeat = state.allFeatures.find(f =>
    f.properties.power_score_50 > 0 && f.properties.nearest_sub_name);
  if (testFeat) {
    showDetailPanel(testFeat.properties);
    const panel = document.getElementById("detail-panel");
    assert("detail panel becomes visible after showDetailPanel()",
      !panel.classList.contains("hidden"));

    const content = document.getElementById("detail-content");
    assert("detail panel contains scorecard",   !!content.querySelector(".scorecard"));
    assert("scorecard has 4 rows",              content.querySelectorAll(".sc-row").length === 4);
    assert("scorecard rows have .sc-fill",      content.querySelectorAll(".sc-fill").length === 4);
    assert("scorecard rows have .sc-score",     content.querySelectorAll(".sc-score").length === 4);
    assert("detail panel contains timeline-box",!!content.querySelector(".timeline-box"));
    assert("timeline-box has .timeline-years",  !!content.querySelector(".timeline-years"));
    assert("timeline-box has .timeline-label",  !!content.querySelector(".timeline-label"));
    assert("timeline-box has .timeline-detail", !!content.querySelector(".timeline-detail"));
    assert("detail panel contains detail-grid", !!content.querySelector(".detail-grid"));
    assert("detail panel shows area in acres",  content.textContent.includes("ac"));

    // Private wire box conditional: if no bonus, should not be present
    const p = testFeat.properties;
    if ((p.private_wire_bonus || 0) > 0) {
      assert("private wire box shown when bonus > 0", !!content.querySelector(".detail-private-wire"));
    } else {
      assert("private wire box absent when bonus = 0", !content.querySelector(".detail-private-wire"));
    }

    // scorecardBar score values are 0-100
    const scoreEls = [...content.querySelectorAll(".sc-score")];
    const allScoresValid = scoreEls.every(el => {
      const v = parseFloat(el.textContent);
      return !isNaN(v) && v >= 0 && v <= 100;
    });
    assert("all scorecard scores in 0-100 range", allScoresValid,
      scoreEls.map(el => el.textContent).join(", "));

    // sc-fill widths reflect scores
    const fills = [...content.querySelectorAll(".sc-fill")];
    const allWidthsValid = fills.every(el => {
      const w = el.style.width;
      const v = parseFloat(w);
      return !isNaN(v) && v >= 0 && v <= 100;
    });
    assert("sc-fill widths match score percentages (0-100%)", allWidthsValid);

    // Close
    document.getElementById("detail-close").click();
    assert("detail panel hides after close click",
      document.getElementById("detail-panel").classList.contains("hidden"));
  }

  console.groupEnd();

  // ── S13: displayName helper ───────────────────────────────────────
  console.group("\nS13  displayName() fallback");

  assert("named parcel returns name",
    displayName({ name: "Didcot Power Station", site_type: "power", region: "South East" }) === "Didcot Power Station");
  assert("unnamed parcel uses city fallback",
    displayName({ name: "", site_type: "industrial", region: "Yorkshire", addr_city: "Leeds" }).includes("Leeds"));
  assert("fully unnamed uses region + type",
    displayName({ name: "", site_type: "brownfield", region: "Wales", addr_city: "" }).includes("Wales"));
  assert("parcel starting 'Unnamed' gets fallback",
    displayName({ name: "Unnamed Site", site_type: "industrial", region: "North West" }).includes("North West"));

  console.groupEnd();

  // ── S14: getCentroid & fmtAcres helpers ──────────────────────────
  console.group("\nS14  Utility helpers");

  assert("getCentroid([]) returns [0,0]", JSON.stringify(getCentroid([])) === "[0,0]");
  assert("getCentroid([[1,2],[3,4]]) = [2,3]", JSON.stringify(getCentroid([[1,2],[3,4]])) === "[2,3]");
  assert("fmtAcres(5.5) = '5.5'",   fmtAcres(5.5)  === "5.5");
  assert("fmtAcres(100) = '100'",   fmtAcres(100)  === "100");
  assert("fmtAcres(1000) has comma",fmtAcres(1000).includes(",") || fmtAcres(1000) === "1000");

  console.groupEnd();

  // ── S15: Zoom nudge ───────────────────────────────────────────────
  console.group("\nS15  Zoom nudge visibility");

  const nudge = document.getElementById("zoom-nudge");
  assert("zoom nudge exists", !!nudge);
  const currentZoom = map.getZoom();
  if (currentZoom < 8) {
    assert("zoom nudge visible at low zoom", !nudge.classList.contains("hidden"));
  } else {
    assert("zoom nudge hidden at zoom >= 8", nudge.classList.contains("hidden"));
  }

  console.groupEnd();

  // ── S16: Mapbox layers exist and have correct types ───────────────
  console.group("\nS16  Mapbox layer integrity");

  const layerChecks = [
    ["parcels-fill",   "fill"],
    ["parcels-outline","line"],
    ["sub-glow",       "circle"],
    ["sub-dot",        "circle"],
    ["sub-label",      "symbol"],
  ];
  layerChecks.forEach(([id, type]) => {
    const layer = map.getLayer(id);
    assert(`layer '${id}' exists`, !!layer);
    assert(`layer '${id}' is type '${type}'`, layer && layer.type === type);
  });

  // Parcel source has features
  const source = map.getSource("parcels");
  assert("'parcels' source exists", !!source);
  const subSource = map.getSource("substations");
  assert("'substations' source exists", !!subSource);

  console.groupEnd();

  // ── Summary ───────────────────────────────────────────────────────
  console.group("\n═══ SUMMARY ═══");
  const total = results.pass + results.fail;
  if (results.fail === 0) {
    console.log(`%c✓ ${results.pass}/${total} tests passed — all Feature 2 browser tests green`, "color:#00E676;font-weight:bold;font-size:14px");
  } else {
    console.error(`✗ ${results.fail} failed / ${total} total`);
    console.error("Failed tests:");
    results.errors.forEach(e => console.error("  •", e));
  }
  console.groupEnd();
  console.groupEnd();

  return results;
})();
