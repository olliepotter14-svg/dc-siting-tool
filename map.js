/* ─── DC Site Finder — Map ────────────────────────────────────────
   Feature 1: Base map + UK land parcels (all DC-relevant site types)
   Feature 2: Power scoring layer (substations, TEC queue, private wire)
   ─────────────────────────────────────────────────────────────── */

// ── Site type config ──────────────────────────────────────────────
const SITE_TYPES = {
  industrial: { label: "Industrial", color: "#00E5FF" },
  brownfield: { label: "Brownfield", color: "#FF6B35" },
  power:      { label: "Power",      color: "#FFB800" },
  aviation:   { label: "Aviation",   color: "#A855F7" },
  military:   { label: "Military",   color: "#FF4560" },
  transport:  { label: "Transport",  color: "#60A5FA" },
  extraction: { label: "Quarry",     color: "#A3E635" },
  farmland:   { label: "Farmland",   color: "#4ADE80" },
  commercial: { label: "Commercial", color: "#F472B6" },
};

// Power score colour stops (red → amber → green)
const SCORE_COLORS = [
  [0,   "#FF1744"],
  [30,  "#FF6D00"],
  [50,  "#FFB300"],
  [70,  "#69F0AE"],
  [90,  "#00E676"],
];

// Queue pressure colour for substations
function queueColor(pct) {
  if (pct <= 50)  return "#00E676";
  if (pct <= 150) return "#FFB300";
  if (pct <= 300) return "#FF6D00";
  return "#FF1744";
}

function scoreColor(score) {
  for (let i = SCORE_COLORS.length - 1; i >= 0; i--) {
    if (score >= SCORE_COLORS[i][0]) return SCORE_COLORS[i][1];
  }
  return SCORE_COLORS[0][1];
}

// ── State ─────────────────────────────────────────────────────────
const state = {
  allFeatures:      [],
  filteredFeatures: [],
  substations:      [],
  activeId:         null,
  colorMode:        "composite", // "type" | "power" | "composite"
  mwValue:          50,       // numeric MW — any value
  showSubstations:  true,
  showPowerlines:   true,
  showFibreRoutes:  false,
  areaSearch:       false,    // list filtered to current viewport
  filters: {
    region:           "all",
    minAcres:         0,
    minComposite:     0,
    excludeFloodZone3: true,   // hard exclude Zone 3 sites by default
  },
};

// ── Power score helpers ───────────────────────────────────────────
function lerp(a, b, t) { return a + (b - a) * t; }

/** Interpolate power score for any MW value from the three pre-computed anchors. */
function getPowerScore(props, mw) {
  mw = mw || state.mwValue;
  const s20  = props.power_score_20  ?? 0;
  const s50  = props.power_score_50  ?? 0;
  const s100 = props.power_score_100 ?? 0;
  if (mw <= 20)  return s20;
  if (mw >= 100) return s100;
  if (mw <= 50)  return lerp(s20, s50, (mw - 20) / 30);
  return lerp(s50, s100, (mw - 50) / 50);
}

/** Interpolate composite score. Falls back to power score if composite not yet enriched. */
function getCompositeScore(props, mw) {
  mw = mw || state.mwValue;
  const s20  = props.composite_score_20  ?? null;
  const s50  = props.composite_score_50  ?? null;
  const s100 = props.composite_score_100 ?? null;
  if (s20 === null) return getPowerScore(props, mw);  // pre-enrichment fallback
  if (mw <= 20)  return s20;
  if (mw >= 100) return s100;
  if (mw <= 50)  return lerp(s20, s50, (mw - 20) / 30);
  return lerp(s50, s100, (mw - 50) / 50);
}

/** Return the active sort score based on colorMode. */
function getActiveScore(props, mw) {
  return state.colorMode === "power"
    ? getPowerScore(props, mw)
    : getCompositeScore(props, mw);
}

/** Convert raw values to 0-100 component scores for the scorecard. */
function distScore(km) {
  if (km == null) return 0;
  if (km <= 1)  return 100;
  if (km <= 3)  return 95;
  if (km <= 5)  return 88;
  if (km <= 10) return 75;
  if (km <= 20) return 55;
  if (km <= 35) return 30;
  return 10;
}
function headroomScore(mva) {
  if (mva == null) return 0;
  if (mva >= 500) return 100;
  if (mva >= 300) return 90;
  if (mva >= 200) return 80;
  if (mva >= 100) return 65;
  if (mva >= 50)  return 45;
  if (mva >= 20)  return 25;
  return 10;
}
function queueScore(pct) {
  if (pct == null) return 0;
  if (pct <= 10)  return 100;
  if (pct <= 50)  return 90;
  if (pct <= 100) return 70;
  if (pct <= 200) return 45;
  if (pct <= 400) return 20;
  return 5;
}
function privateWireScore(km) {
  if (km == null || km >= 9999) return 0;
  if (km <= 5)  return 100;
  if (km <= 15) return 60;
  if (km <= 30) return 30;
  return 0;
}

/** Translate queue pressure % to NESO-based connection timeline string. */
function getTimeline(pct) {
  if (pct == null) return { label: "Unknown", years: "—", color: "#8B92A5" };
  if (pct <= 50)  return { label: "Short wait",   years: "~2–3 years",  color: "#00E676" };
  if (pct <= 150) return { label: "Moderate wait", years: "~3–5 years", color: "#FFB300" };
  if (pct <= 300) return { label: "Long wait",     years: "~5–8 years", color: "#FF6D00" };
  return            { label: "Very long wait", years: "~8–12+ years",   color: "#FF1744" };
}

// ── Map init ──────────────────────────────────────────────────────
mapboxgl.accessToken = window.MAPBOX_TOKEN;

const map = new mapboxgl.Map({
  container:  "map",
  style:      "mapbox://styles/mapbox/dark-v11",
  center:     [-1.8, 53.5],
  zoom:       5.8,
  minZoom:    4,
  maxBounds:  [[-12, 49], [3, 62]],
  projection: "mercator",
});

map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");

let popup = new mapboxgl.Popup({
  closeButton:  true,
  closeOnClick: false,
  offset:       8,
  maxWidth:     "300px",
});

// When popup X is clicked, clear full selection state
popup.on("close", () => {
  state.activeId = null;
  updateActiveFeatureState();
  document.getElementById("detail-panel").classList.add("hidden");
  document.querySelectorAll(".parcel-card.active").forEach(c => c.classList.remove("active"));
});

// ── Loading progress bar ──────────────────────────────────────────
function fetchWithProgress(url, onProgress) {
  return fetch(url).then(resp => {
    const total = parseInt(resp.headers.get("content-length") || "0", 10);
    const reader = resp.body.getReader();
    const chunks = [];
    let loaded = 0;
    function pump() {
      return reader.read().then(({ done, value }) => {
        if (done) {
          const blob = new Blob(chunks);
          return blob.text().then(text => JSON.parse(text));
        }
        chunks.push(value);
        loaded += value.length;
        if (onProgress) onProgress(loaded, total);
        return pump();
      });
    }
    return pump();
  });
}

function setLoadingMsg(html) {
  const el = document.getElementById("parcel-list");
  if (el) el.innerHTML = `<div class="list-loading">${html}</div>`;
}

// ── Load data ─────────────────────────────────────────────────────
map.on("load", () => {
  const parcelPromise = fetchWithProgress(
    "data/uk_industrial_parcels.geojson?v=7",
    (loaded, total) => {
      const mb = (loaded / 1_048_576).toFixed(1);
      const pct = total ? Math.round(loaded / total * 100) : null;
      const bar = pct
        ? `<div style="margin-top:8px;background:#1e2535;border-radius:4px;height:4px;overflow:hidden">
             <div style="width:${pct}%;height:100%;background:#3b82f6;transition:width 0.2s"></div>
           </div>`
        : "";
      setLoadingMsg(`Downloading parcel data… ${mb} MB${pct ? ` (${pct}%)` : ""}${bar}`);
    }
  );

  Promise.all([
    parcelPromise,
    fetch("data/uk_substations.json?v=7").then(r => r.json()),
    fetch("data/uk_powerlines.geojson?v=7").then(r => r.json()),
    fetch("data/uk_fibre_routes.geojson?v=7").then(r => r.json()),
  ])
  .then(([geojson, subsRaw, powerlines, fibreRoutes]) => {
    setLoadingMsg("Processing 63,478 parcels…");
    state.allFeatures = geojson.features;
    state.substations = Array.isArray(subsRaw) ? subsRaw
      : subsRaw.substations ?? subsRaw.features ?? subsRaw;
    initUI();
    applyFilters();
    addMapLayers();
    refreshParcelColors();  // apply correct opacity for initial colorMode
    addPowerlineLayer(powerlines);
    addFibreRouteLayer(fibreRoutes);
  })
  .catch((err) => {
    console.error("Failed to load data:", err);
    document.getElementById("parcel-list").innerHTML =
      `<div class="list-loading" style="color:#ff4d4d">
        Error: ${err.message || err}<br/>
        <small style="opacity:0.6">${err.stack ? err.stack.split('\n')[1] : 'Check console for details'}</small>
      </div>`;
  });
});

// ── Map layers ────────────────────────────────────────────────────
function addMapLayers() {
  // ── Parcel source & layers ─────────────────────────────────────
  map.addSource("parcels", {
    type: "geojson", data: buildFilteredGeoJSON(), generateId: true,
  });

  map.addLayer({
    id: "parcels-fill", type: "fill", source: "parcels",
    paint: {
      "fill-color":   buildColorExpression(),
      "fill-opacity": ["case",
        ["boolean", ["feature-state", "active"], false], 0.55,
        ["boolean", ["feature-state", "hover"],  false], 0.35,
        0.20,
      ],
    },
  });

  map.addLayer({
    id: "parcels-outline", type: "line", source: "parcels",
    paint: {
      "line-color": buildColorExpression(),
      "line-width": ["case",
        ["boolean", ["feature-state", "active"], false], 2,
        ["boolean", ["feature-state", "hover"],  false], 1.5,
        0.7,
      ],
      "line-opacity": ["case",
        ["boolean", ["feature-state", "active"], false], 1,
        ["boolean", ["feature-state", "hover"],  false], 0.85,
        0.45,
      ],
    },
  });

  // ── Substation source & layers ─────────────────────────────────
  const subGeoJSON = {
    type: "FeatureCollection",
    features: state.substations.map(s => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.lng, s.lat] },
      properties: {
        name:          s.name,
        voltage_kv:    s.voltage_kv,
        capacity_mva:  s.capacity_mva,
        headroom_mva:  s.estimated_headroom_mva,
        queue_pct:     s.real_queue_pressure_pct,
        queue_mw:      s.tec_queue_mw,
        region:        s.region,
        score_20:      s.scores_real?.["20"]?.total_score ?? 0,
        score_50:      s.scores_real?.["50"]?.total_score ?? 0,
        score_100:     s.scores_real?.["100"]?.total_score ?? 0,
      }
    }))
  };

  map.addSource("substations", { type: "geojson", data: subGeoJSON });

  const _QUEUE_COLOR = [
    "case",
    ["<=", ["get", "queue_pct"], 50],  "#00E676",
    ["<=", ["get", "queue_pct"], 150], "#FFB300",
    ["<=", ["get", "queue_pct"], 300], "#FF6D00",
    "#FF1744",
  ];

  // Outer pulse ring — opacity animated by RAF loop
  map.addLayer({
    id: "sub-pulse", type: "circle", source: "substations",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        5,  ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 11, 3000, 24],
        10, ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 22, 3000, 46],
      ],
      "circle-color":   _QUEUE_COLOR,
      "circle-opacity": 0,
      "circle-blur":    0.9,
    },
    minzoom: 5,
  });

  // Soft glow ring
  map.addLayer({
    id: "sub-glow", type: "circle", source: "substations",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        5,  ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 7, 3000, 16],
        10, ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 14, 3000, 32],
      ],
      "circle-color":   _QUEUE_COLOR,
      "circle-opacity": 0.22,
      "circle-blur":    0.65,
    },
    minzoom: 5,
  });

  // Mid ring halo — slightly larger than dot, creates a two-ring bullseye
  map.addLayer({
    id: "sub-ring", type: "circle", source: "substations",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        5,  ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 4.5, 3000, 10],
        10, ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 9, 3000, 18],
      ],
      "circle-color":          _QUEUE_COLOR,
      "circle-opacity":        0.30,
      "circle-blur":           0,
      "circle-stroke-color":   _QUEUE_COLOR,
      "circle-stroke-width":   1,
      "circle-stroke-opacity": 0.65,
    },
    minzoom: 5,
  });

  // Main solid dot
  map.addLayer({
    id: "sub-dot", type: "circle", source: "substations",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        5,  ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 3, 3000, 7],
        10, ["interpolate", ["linear"], ["get", "capacity_mva"], 500, 6, 3000, 14],
      ],
      "circle-color":        _QUEUE_COLOR,
      "circle-stroke-color": "rgba(255,255,255,0.22)",
      "circle-stroke-width": 1.5,
      "circle-opacity":      0.95,
    },
    minzoom: 5,
  });

  // Bright white core — "hot centre" highlight
  map.addLayer({
    id: "sub-core", type: "circle", source: "substations",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        5, 1.5,
        10, 3,
      ],
      "circle-color":   "#ffffff",
      "circle-opacity": 0.80,
    },
    minzoom: 6,
  });

  // Label (shows at higher zoom)
  map.addLayer({
    id: "sub-label", type: "symbol", source: "substations",
    layout: {
      "text-field":    ["get", "name"],
      "text-font":     ["DIN Pro Medium", "Arial Unicode MS Regular"],
      "text-size":     10,
      "text-offset":   [0, 1.2],
      "text-anchor":   "top",
      "text-optional": true,
    },
    paint: {
      "text-color":      "#C8D0E0",
      "text-halo-color": "rgba(10,13,18,0.8)",
      "text-halo-width": 1.5,
    },
    minzoom: 8,
  });

  // Pulse animation — cycles sub-pulse opacity 0.30→0 over 2.5s
  const _SUB = { rafId: null, PERIOD_MS: 2500 };
  function _animateSubPulse(ts) {
    const phase = (ts % _SUB.PERIOD_MS) / _SUB.PERIOD_MS;
    const opacity = 0.30 * Math.pow(1 - phase, 1.5);
    if (map.getLayer("sub-pulse"))
      map.setPaintProperty("sub-pulse", "circle-opacity", opacity);
    _SUB.rafId = requestAnimationFrame(_animateSubPulse);
  }
  _SUB.rafId = requestAnimationFrame(_animateSubPulse);

  // ── Substation hover popup ─────────────────────────────────────
  let subPopup = new mapboxgl.Popup({ closeButton: false, offset: 8, maxWidth: "260px" });

  map.on("mouseenter", "sub-dot", (e) => {
    map.getCanvas().style.cursor = "pointer";
    const p = e.features[0].properties;
    // Interpolate score for current mwValue from the three anchors
    const mw = state.mwValue;
    let score;
    if (mw <= 20)       score = p.score_20;
    else if (mw >= 100) score = p.score_100;
    else if (mw <= 50)  score = p.score_20 + (p.score_50 - p.score_20) * (mw - 20) / 30;
    else                score = p.score_50 + (p.score_100 - p.score_50) * (mw - 50) / 50;
    const qColor = queueColor(p.queue_pct);
    subPopup.setLngLat(e.features[0].geometry.coordinates)
      .setHTML(`
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
                    color:${qColor};margin-bottom:6px">${p.voltage_kv}kV Substation</div>
        <div style="font-size:13px;font-weight:700;color:#F0F4FF;margin-bottom:10px">${p.name}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div style="background:#161B25;border:1px solid rgba(255,255,255,.07);border-radius:6px;padding:8px">
            <div style="font-size:16px;font-weight:700;color:${qColor}">${Math.round(p.queue_pct)}%</div>
            <div style="font-size:10px;color:#4A5068;text-transform:uppercase;margin-top:2px">Queue pressure</div>
          </div>
          <div style="background:#161B25;border:1px solid rgba(255,255,255,.07);border-radius:6px;padding:8px">
            <div style="font-size:16px;font-weight:700;color:#00E5FF">${p.headroom_mva != null ? Math.round(p.headroom_mva) : "—"}</div>
            <div style="font-size:10px;color:#4A5068;text-transform:uppercase;margin-top:2px">MVA headroom</div>
          </div>
          <div style="background:#161B25;border:1px solid rgba(255,255,255,.07);border-radius:6px;padding:8px">
            <div style="font-size:16px;font-weight:700;color:#F0F4FF">${p.queue_mw != null ? Math.round(p.queue_mw) : "—"}</div>
            <div style="font-size:10px;color:#4A5068;text-transform:uppercase;margin-top:2px">Queue MW</div>
          </div>
          <div style="background:#161B25;border:1px solid rgba(255,255,255,.07);border-radius:6px;padding:8px">
            <div style="font-size:16px;font-weight:700;color:${scoreColor(score)}">${Math.round(score)}</div>
            <div style="font-size:10px;color:#4A5068;text-transform:uppercase;margin-top:2px">Score ${state.mwValue}MW</div>
          </div>
        </div>
      `)
      .addTo(map);
  });

  map.on("mouseleave", "sub-dot", () => {
    map.getCanvas().style.cursor = "";
    subPopup.remove();
  });

  // ── Parcel interactions ────────────────────────────────────────
  let hoveredId = null;

  map.on("mousemove", "parcels-fill", (e) => {
    map.getCanvas().style.cursor = "pointer";
    const id = e.features[0].id;
    if (hoveredId !== null && hoveredId !== id)
      map.setFeatureState({ source: "parcels", id: hoveredId }, { hover: false });
    hoveredId = id;
    map.setFeatureState({ source: "parcels", id }, { hover: true });
  });

  map.on("mouseleave", "parcels-fill", () => {
    map.getCanvas().style.cursor = "";
    if (hoveredId !== null)
      map.setFeatureState({ source: "parcels", id: hoveredId }, { hover: false });
    hoveredId = null;
  });

  map.on("click", "parcels-fill", (e) => {
    const feat = e.features[0];
    selectParcel(feat.properties.osm_id, feat.geometry, feat.properties);
  });

  map.on("click", (e) => {
    const hits = map.queryRenderedFeatures(e.point, { layers: ["parcels-fill"] });
    if (!hits.length) clearSelection();
  });
}

// ── Colour expressions ────────────────────────────────────────────
function _scoreColorExpression(prefix) {
  // Builds an interpolated colour expression for power_score_* or composite_score_*
  const mw = state.mwValue;
  let scoreExpr;
  if (mw <= 20) {
    scoreExpr = ["coalesce", ["get", `${prefix}_20`], 0];
  } else if (mw >= 100) {
    scoreExpr = ["coalesce", ["get", `${prefix}_100`], 0];
  } else if (mw <= 50) {
    const t = (mw - 20) / 30;
    scoreExpr = ["+",
      ["*", ["coalesce", ["get", `${prefix}_20`], 0], 1 - t],
      ["*", ["coalesce", ["get", `${prefix}_50`], 0], t],
    ];
  } else {
    const t = (mw - 50) / 50;
    scoreExpr = ["+",
      ["*", ["coalesce", ["get", `${prefix}_50`], 0], 1 - t],
      ["*", ["coalesce", ["get", `${prefix}_100`], 0], t],
    ];
  }
  return ["interpolate", ["linear"], scoreExpr,
    0, "#FF1744", 30, "#FF6D00", 50, "#FFB300", 70, "#69F0AE", 90, "#00E676",
  ];
}

function buildColorExpression() {
  if (state.colorMode === "power")     return _scoreColorExpression("power_score");
  if (state.colorMode === "composite") return _scoreColorExpression("composite_score");

  const expr = ["match", ["get", "site_type"]];
  Object.entries(SITE_TYPES).forEach(([t, cfg]) => expr.push(t, cfg.color));
  expr.push("#8B92A5");
  return expr;
}

function buildFillOpacityExpression(base) {
  return ["case",
    ["boolean", ["feature-state", "active"], false], 0.60,
    ["boolean", ["feature-state", "hover"],  false], 0.40,
    base,
  ];
}

function buildLineOpacityExpression(base) {
  return ["case",
    ["boolean", ["feature-state", "active"], false], 1,
    ["boolean", ["feature-state", "hover"],  false], 0.90,
    base,
  ];
}

function refreshParcelColors() {
  const expr = buildColorExpression();
  // In power mode use higher opacity — at 0.20 opacity, dark-red low-score parcels
  // composite to near-black on the dark basemap and are invisible.
  const scoreMode = state.colorMode === "power" || state.colorMode === "composite";
  const fillBase = scoreMode ? 0.35 : 0.20;
  const lineBase = scoreMode ? 0.70 : 0.45;
  const lineW    = scoreMode ? 1.2  : 0.7;

  map.setPaintProperty("parcels-fill",    "fill-color",    expr);
  map.setPaintProperty("parcels-fill",    "fill-opacity",  buildFillOpacityExpression(fillBase));
  map.setPaintProperty("parcels-outline", "line-color",    expr);
  map.setPaintProperty("parcels-outline", "line-opacity",  buildLineOpacityExpression(lineBase));
  map.setPaintProperty("parcels-outline", "line-width", ["case",
    ["boolean", ["feature-state", "active"], false], 2,
    ["boolean", ["feature-state", "hover"],  false], 1.5,
    lineW,
  ]);
}

// ── Selection ─────────────────────────────────────────────────────
function selectParcel(osmId, geometry, props) {
  state.activeId = String(osmId);
  updateActiveFeatureState();
  showPopup(getCentroid(geometry.coordinates[0]), props);
  showDetailPanel(props);
  highlightListCard(osmId);
}

function clearSelection() {
  state.activeId = null;
  updateActiveFeatureState();
  popup.remove();
  document.getElementById("detail-panel").classList.add("hidden");
  document.querySelectorAll(".parcel-card.active").forEach(c => c.classList.remove("active"));
}

function updateActiveFeatureState() {
  map.removeFeatureState({ source: "parcels" });
  if (state.activeId !== null) {
    map.querySourceFeatures("parcels").forEach(f => {
      if (String(f.properties.osm_id) === state.activeId)
        map.setFeatureState({ source: "parcels", id: f.id }, { active: true });
    });
  }
}

// ── Popup ─────────────────────────────────────────────────────────
function showPopup(lngLat, props) {
  const cfg       = SITE_TYPES[props.site_type] || { color: "#8B92A5", label: props.site_type };
  const composite = getCompositeScore(props);
  const cColor    = scoreColor(composite);
  const tl        = getTimeline(props.sub_queue_pressure_pct);
  const floodZone = props.flood_zone ?? null;
  const floodCfg  = { 1: null, 2: { label: "Zone 2 flood risk", color: "#FFB300" },
                       3: { label: "⚠ Zone 3 — excluded",       color: "#FF1744" } }[floodZone];

  popup.setLngLat(lngLat).setHTML(`
    <div class="popup-land-use" style="color:${cfg.color}">${cfg.label}</div>
    <div class="popup-name">${displayName(props)}</div>
    ${floodCfg ? `<div class="popup-flood" style="color:${floodCfg.color}">${floodCfg.label}</div>` : ""}
    <div class="popup-metrics">
      <div class="popup-metric">
        <span class="popup-metric-value">${fmtAcres(props.area_acres)}</span>
        <span class="popup-metric-label">Acres</span>
      </div>
      <div class="popup-metric">
        <span class="popup-metric-value" style="color:${cColor}">${Math.round(composite)}</span>
        <span class="popup-metric-label">${props.composite_score_50 != null ? "Composite" : "Power"}</span>
      </div>
      <div class="popup-metric">
        <span class="popup-metric-value" style="color:${tl.color}">${tl.years}</span>
        <span class="popup-metric-label">Est. connection</span>
      </div>
    </div>
    <a class="popup-detail-link" data-osm-id="${props.osm_id}">View details →</a>
  `).addTo(map);

  const link = popup.getElement().querySelector(".popup-detail-link");
  if (link) link.addEventListener("click", () => {
    const feat = state.allFeatures.find(f => f.properties.osm_id === props.osm_id);
    if (feat) showDetailPanel(feat.properties);
  });
}

// ── Detail panel ──────────────────────────────────────────────────
function scorecardBar(label, rawValue, score, unit) {
  const color = scoreColor(score);
  return `
    <div class="sc-row">
      <div class="sc-header">
        <span class="sc-label">${label}</span>
        <span class="sc-raw">${rawValue}</span>
      </div>
      <div class="sc-track">
        <div class="sc-fill" style="width:${score}%;background:${color}"></div>
      </div>
      <span class="sc-score" style="color:${color}">${Math.round(score)}</span>
    </div>`;
}

function floodZoneLabel(zone) {
  return { 1: "Zone 1 — Low risk", 2: "Zone 2 — Medium risk", 3: "Zone 3 — High risk" }[zone] ?? "Unknown";
}

/** Return a short permissioning bucket label for the detail panel. */
function permissioningBucket(props) {
  const score = props.permissioning_score ?? props.planning_score ?? 0;
  const gb    = props.green_belt;
  const grey  = props.grey_belt;
  const gz    = props.growth_zone;

  let bucket;
  if (score >= 75)      bucket = "A — Permitted";
  else if (score >= 50) bucket = "B — Achievable";
  else                  bucket = "C — Complex";

  const tags = [];
  if (gz)   tags.push("AI Growth Zone ✦");
  if (grey) tags.push("Grey Belt");
  else if (gb) tags.push("Green Belt");

  return bucket + (tags.length ? " · " + tags.join(" · ") : "");
}

function hardExclusionBanner(props) {
  if (!props.hard_excluded) return "";
  const reasons = [];
  if (props.flood_zone === 3) reasons.push("Flood Zone 3 (≥1% annual flood probability — NPPF prohibits critical infrastructure)");
  const desigs = (props.protected_designations || []).filter(d => d);
  desigs.forEach(d => reasons.push(d));
  const reasonHTML = reasons.map(r => `<li>${r}</li>`).join("");
  return `
    <div class="hard-exclusion-banner">
      <div class="hex-title">⛔ Hard-excluded — not viable for DC development</div>
      <div class="hex-subtitle">This site has been automatically excluded from scoring due to planning or environmental constraints that cannot be overcome:</div>
      <ul class="hex-reasons">${reasonHTML}</ul>
      <div class="hex-note">Green Belt sites are <em>not</em> excluded — they carry a planning score penalty only.</div>
    </div>`;
}

function showDetailPanel(props) {
  const panel     = document.getElementById("detail-panel");
  const content   = document.getElementById("detail-content");
  const cfg       = SITE_TYPES[props.site_type] || { color: "#8B92A5", label: props.site_type };
  const powerS    = getPowerScore(props);
  const compS     = getCompositeScore(props);
  const cColor    = scoreColor(compS);
  const qPct      = props.sub_queue_pressure_pct ?? 0;
  const tl        = getTimeline(qPct);
  const renKm     = props.nearest_renewable_km;
  const pwBonus   = props.private_wire_bonus ?? 0;
  const floodZone = props.flood_zone ?? 1;
  const hasComposite = props.composite_score_50 != null;

  // Power sub-scores
  const dScore  = distScore(props.nearest_sub_dist_km);
  const hScore  = headroomScore(props.nearest_sub_headroom_mva);
  const qScore  = queueScore(qPct);
  const pwScore = privateWireScore(renKm);

  // Flood zone styling
  const floodColors = { 1: "#00E676", 2: "#FFB300", 3: "#FF1744" };
  const floodColor  = floodColors[floodZone] ?? "#8B92A5";

  // Flood zone warning banner
  const floodWarning = floodZone === 3 ? `
    <div class="flood-warning">
      <strong>⚠ Flood Zone 3 — Site non-viable</strong><br>
      High probability of flooding (≥1% annually). Planning policy prohibits critical infrastructure here. Automatic exclusion applies.
    </div>` : floodZone === 2 ? `
    <div class="flood-caution">
      <strong>Flood Zone 2 — Moderate risk</strong><br>
      0.1–1% annual flood probability. A Flood Risk Assessment will be required at planning stage.
    </div>` : "";

  content.innerHTML = `
    <div class="detail-tag" style="color:${cfg.color};background:${cfg.color}18;border-color:${cfg.color}44">
      ${cfg.label}
    </div>
    <div class="detail-title">${displayName(props)}</div>
    <div class="detail-region">${props.region ?? ""}${props.addr_city ? " · " + props.addr_city : ""}</div>

    <div class="detail-grid">
      <div class="detail-metric">
        <div class="detail-metric-value" style="color:${cfg.color}">${fmtAcres(props.area_acres)}</div>
        <div class="detail-metric-label">Acres</div>
      </div>
      <div class="detail-metric">
        <div class="detail-metric-value" style="color:${cColor}">${props.hard_excluded ? "—" : Math.round(compS)}</div>
        <div class="detail-metric-label">${props.hard_excluded ? "Excluded" : (hasComposite ? "Composite" : "Power") + " (" + state.mwValue + "MW)"}</div>
      </div>
      <div class="detail-metric">
        <div class="detail-metric-value" style="color:${floodColor};font-size:12px">${floodZoneLabel(floodZone)}</div>
        <div class="detail-metric-label">Flood zone</div>
      </div>
    </div>

    ${hardExclusionBanner(props)}

    ${props.hard_excluded ? "" : floodWarning}

    ${props.hard_excluded ? "" : (() => {
      const desigs = (props.protected_designations || []).filter(d => d);
      const greenBelt = props.green_belt;
      const greyBelt  = props.grey_belt;
      if (!desigs.length && !greenBelt) return '';
      const badges = desigs.map(d => `<span class="desig-badge">${d}</span>`).join('');
      const beltBadge = greyBelt
        ? '<span class="desig-belt">Grey Belt</span>'
        : greenBelt ? '<span class="desig-belt">Green Belt</span>' : '';
      return `
        <div class="detail-section-title">Protected Designations</div>
        <div class="detail-designations">${badges}${beltBadge}</div>`;
    })()}

    ${!props.hard_excluded && hasComposite ? `
    <div class="detail-section-title">◉ Composite score breakdown</div>
    <div class="scorecard">
      ${scorecardBar("Power — grid access (40%)", Math.round(powerS) + " / 100", powerS)}
      ${scorecardBar("Permissioning (30%)", permissioningBucket(props), props.permissioning_score ?? 0)}
      ${scorecardBar("Fibre — connectivity (20%)", (() => {
        const route = props.fibre_route_km;
        const ix    = props.dist_to_ix_km;
        if (route != null && ix != null) {
          const best = Math.min(route, ix);
          return best.toFixed(1) + " km " + (route <= ix ? "(backbone)" : "(colo)");
        }
        return ix != null ? ix.toFixed(1) + " km" : "—";
      })(), props.fibre_score ?? 0)}
      ${scorecardBar("Buildability (10%)", fmtAcres(props.area_acres) + " ac", props.buildability_score ?? 0)}
    </div>` : ""}

    <div class="detail-section-title">⚡ Power detail</div>
    <div class="scorecard">
      ${scorecardBar("Distance to substation", props.nearest_sub_dist_km != null ? props.nearest_sub_dist_km.toFixed(1) + " km" : "—", dScore)}
      ${scorecardBar("Grid headroom", props.nearest_sub_headroom_mva != null ? Math.round(props.nearest_sub_headroom_mva) + " MVA" : "—", hScore)}
      ${scorecardBar("TEC queue pressure", qPct.toFixed(0) + "%", qScore)}
      ${scorecardBar("Private wire proximity", renKm && renKm < 9999 ? renKm.toFixed(1) + " km" : "None nearby", pwScore)}
    </div>

    <div class="detail-section-title">🕐 Connection timeline</div>
    <div class="timeline-box" style="border-color:${tl.color}33;background:${tl.color}0D">
      <div class="timeline-years" style="color:${tl.color}">${tl.years}</div>
      <div class="timeline-label" style="color:${tl.color}">${tl.label}</div>
      <div class="timeline-detail">
        Queue: <strong>${Math.round(qPct)}%</strong> ·
        Headroom: <strong>${props.nearest_sub_headroom_mva != null ? Math.round(props.nearest_sub_headroom_mva) + " MVA" : "—"}</strong> ·
        Substation: <strong>${props.nearest_sub_name ?? "—"}</strong> (${props.nearest_sub_voltage_kv ?? "—"}kV)
      </div>
    </div>

    ${pwBonus > 0 ? `
    <div class="detail-private-wire">
      <span class="pw-icon">☀️</span>
      <div>
        <div class="pw-title">Private wire opportunity</div>
        <div class="pw-sub">Renewable generation ${renKm != null ? renKm.toFixed(1) + " km" : ""} away — direct offtake agreement could bypass grid queue entirely</div>
      </div>
      <span class="pw-bonus">+${pwBonus}</span>
    </div>` : ""}

    ${renderCostEstimate(props, state.mwValue)}

    <div class="detail-section-title" style="margin-top:14px">📐 Site</div>
    <div class="detail-row">
      <span class="detail-row-label">Area</span>
      <span class="detail-row-value">${fmtAcres(props.area_acres)} ac / ${fmtHa(props.area_ha)} ha</span>
    </div>
    <div class="detail-row">
      <span class="detail-row-label">OSM tag</span>
      <span class="detail-row-value" style="font-family:monospace;font-size:11px">${props.osm_tag ?? ""}</span>
    </div>
    ${props.operator ? `<div class="detail-row">
      <span class="detail-row-label">Operator</span>
      <span class="detail-row-value">${props.operator}</span>
    </div>` : ""}
  `;

  panel.classList.remove("hidden");
}

document.getElementById("detail-close").addEventListener("click", clearSelection);

document.getElementById("parcel-list").addEventListener("click", (e) => {
  const card = e.target.closest(".parcel-card");
  if (!card) return;
  const osmId = card.dataset.id;
  const feat  = state.allFeatures.find(f => String(f.properties.osm_id) === osmId);
  if (!feat) return;
  selectParcel(osmId, feat.geometry, feat.properties);
  flyToParcel(feat.geometry);
});

// ── UI init ───────────────────────────────────────────────────────
function initUI() {
  // Region dropdown
  const regions = [...new Set(state.allFeatures.map(f => f.properties.region))].sort();
  const sel = document.getElementById("filter-region");
  regions.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r; opt.textContent = r;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", e => { state.filters.region = e.target.value; applyFilters(); });

  // Size filter
  document.getElementById("filter-size").addEventListener("change", e => {
    state.filters.minAcres = parseFloat(e.target.value);
    applyFilters();
  });

  // Min composite score filter
  const compSel = document.getElementById("filter-composite-score");
  if (compSel) {
    compSel.addEventListener("change", e => {
      state.filters.minComposite = parseInt(e.target.value, 10);
      applyFilters();
    });
  }

  // Flood zone 3 exclusion toggle
  const floodToggle = document.getElementById("toggle-flood-exclude");
  if (floodToggle) {
    floodToggle.addEventListener("change", () => {
      state.filters.excludeFloodZone3 = floodToggle.checked;
      applyFilters();
    });
  }

  // MW size selector (presets + custom input)
  function setMwValue(mw) {
    mw = Math.max(1, Math.min(500, Math.round(mw)));
    state.mwValue = mw;
    // Sync preset buttons — highlight if matches a preset
    document.querySelectorAll(".mw-btn").forEach(b => {
      b.classList.toggle("active", parseInt(b.dataset.mw, 10) === mw);
    });
    refreshParcelColors();
    applyFilters();
    if (state.activeId !== null) {
      const feat = state.allFeatures.find(f => f.properties.osm_id === state.activeId);
      if (feat) showDetailPanel(feat.properties);
    }
  }

  document.querySelectorAll(".mw-btn").forEach(btn => {
    btn.addEventListener("click", () => setMwValue(parseInt(btn.dataset.mw, 10)));
  });

  // Overlay chip toggles (substations / powerlines / fibre)
  document.querySelectorAll(".overlay-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
      const on = chip.classList.contains("active");
      const layer = chip.dataset.layer;
      if (layer === "substations") {
        state.showSubstations = on;
        ["sub-pulse", "sub-glow", "sub-ring", "sub-dot", "sub-core", "sub-label"].forEach(id => {
          if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
        });
      } else if (layer === "powerlines") {
        setPowerlineVisibility(on);
      } else if (layer === "fibre") {
        state.showFibreRoutes = on;
        if (map.getLayer("fibre-routes")) map.setLayoutProperty("fibre-routes", "visibility", on ? "visible" : "none");
      }
    });
  });

  // Colour mode toggle
  document.querySelectorAll(".color-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".color-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.colorMode = btn.dataset.mode;
      refreshParcelColors();
      updateLegend();
      applyFilters();  // re-sort list
    });
  });

  // Reset filters button
  const resetBtn = document.getElementById("reset-filters-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      state.filters.region           = "all";
      state.filters.minAcres         = 0;
      state.filters.minComposite     = 0;
      state.filters.excludeFloodZone3 = true;
      document.getElementById("filter-region").value           = "all";
      document.getElementById("filter-size").value             = "0";
      document.getElementById("filter-composite-score").value  = "0";
      document.getElementById("toggle-flood-exclude").checked  = true;
      applyFilters();
    });
  }

  // Search this area button
  const searchAreaBtn = document.getElementById("search-area-btn");
  if (searchAreaBtn) {
    searchAreaBtn.addEventListener("click", () => {
      setAreaSearch(!state.areaSearch);
    });
  }

  updateLegend();
}

function updateLegend() {
  const legend = document.getElementById("legend-items");
  legend.innerHTML = "";

  if (state.colorMode === "power" || state.colorMode === "composite") {
    const label = state.colorMode === "composite" ? "Composite" : "Power";
    const sec1 = document.createElement("div"); sec1.className = "legend-section-label"; sec1.textContent = label + " score"; legend.appendChild(sec1);
    SCORE_COLORS.slice().reverse().forEach(([score, color]) => {
      const item = document.createElement("div");
      item.className = "legend-item";
      item.innerHTML = `<span class="legend-dot" style="background:${color};box-shadow:0 0 5px ${color}"></span> ${score}+`;
      legend.appendChild(item);
    });
  } else {
    const sec1 = document.createElement("div"); sec1.className = "legend-section-label"; sec1.textContent = "Site type"; legend.appendChild(sec1);
    Object.entries(SITE_TYPES).forEach(([, cfg]) => {
      const item = document.createElement("div");
      item.className = "legend-item";
      item.innerHTML = `<span class="legend-dot" style="background:${cfg.color};box-shadow:0 0 5px ${cfg.color}"></span> ${cfg.label}`;
      legend.appendChild(item);
    });
  }

  const sep = document.createElement("div"); sep.className = "legend-sep"; legend.appendChild(sep);
  const sec2 = document.createElement("div"); sec2.className = "legend-section-label"; sec2.textContent = "Substation queue"; legend.appendChild(sec2);
  [["Low (<50%)", "#00E676"], ["Moderate (50–150%)", "#FFB300"],
   ["High (150–300%)", "#FF6D00"], ["Severe (>300%)", "#FF1744"]].forEach(([lbl, color]) => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-circle" style="background:${color};box-shadow:0 0 5px ${color}"></span> ${lbl}`;
    legend.appendChild(item);
  });
}

// ── Filters ───────────────────────────────────────────────────────
function applyFilters() {
  const { region, minAcres, minComposite, excludeFloodZone3 } = state.filters;

  state.filteredFeatures = state.allFeatures.filter(f => {
    const p = f.properties;
    if (region !== "all" && p.region !== region)                                  return false;
    if (p.area_acres != null && p.area_acres < minAcres)                           return false;
    if (excludeFloodZone3 && (p.hard_excluded === true || p.flood_zone === 3))     return false;
    if (minComposite > 0 && getCompositeScore(p) < minComposite)                   return false;
    return true;
  });

  updateStats();
  updateMapData();
  updateList();
}

function updateStats() {
  const total = state.allFeatures.length;
  const score90 = state.allFeatures.filter(f => getCompositeScore(f.properties) >= 90).length;

  document.getElementById("stat-count").textContent  = total.toLocaleString();
  document.getElementById("stat-type1").textContent  = score90.toLocaleString();

  // list-count is managed by updateList() when area search is active
  if (!state.areaSearch)
    document.getElementById("list-count").textContent = state.filteredFeatures.length.toLocaleString();
}

function buildFilteredGeoJSON() {
  return { type: "FeatureCollection", features: state.filteredFeatures };
}

function updateMapData() {
  const source = map.getSource("parcels");
  if (source) {
    source.setData(buildFilteredGeoJSON());
    // Re-apply feature state — setData reassigns Mapbox internal IDs
    map.once("sourcedata", () => updateActiveFeatureState());
  }
}

// ── Area search ───────────────────────────────────────────────────
function setAreaSearch(active) {
  state.areaSearch = active;
  const btn = document.getElementById("search-area-btn");
  if (!btn) return;
  if (active) {
    btn.textContent = "✕ Clear area filter";
    btn.classList.add("active");
  } else {
    btn.textContent = "Search this area";
    btn.classList.remove("active");
  }
  updateList();
}

map.on("moveend", () => { if (state.areaSearch) updateList(); });

// ── Sidebar list ──────────────────────────────────────────────────
const LIST_PAGE_SIZE = 100;

function updateList() {
  const list = document.getElementById("parcel-list");

  let features = state.filteredFeatures;

  // When area search is active, restrict list to current viewport
  if (state.areaSearch) {
    const bounds = map.getBounds();
    features = features.filter(f => {
      const [lng, lat] = getCentroid(f.geometry.coordinates[0]);
      return bounds.contains([lng, lat]);
    });
  }

  if (!features.length) {
    list.innerHTML = `<div class="list-loading">${
      state.areaSearch ? "No parcels in this area. Pan or zoom out." : "No parcels match the current filters."
    }</div>`;
    document.getElementById("list-count").textContent = "0";
    return;
  }

  // Sort by composite score (falls back to power score if not yet enriched)
  const sorted = [...features].sort((a, b) =>
    getCompositeScore(b.properties) - getCompositeScore(a.properties)
  );

  document.getElementById("list-count").textContent = sorted.length.toLocaleString();
  list.innerHTML = sorted.slice(0, LIST_PAGE_SIZE).map(f => buildCardHTML(f.properties)).join("");

  if (sorted.length > LIST_PAGE_SIZE) {
    list.innerHTML += `<div class="list-loading" style="padding:12px 0;font-size:11px">
      Showing top ${LIST_PAGE_SIZE} of ${sorted.length.toLocaleString()}. Filter to narrow results.
    </div>`;
  }
}

function buildCardHTML(props) {
  const cfg        = SITE_TYPES[props.site_type] || { color: "#8B92A5", label: props.site_type };
  const composite  = getCompositeScore(props);
  const cColor     = scoreColor(composite);
  const floodZone  = props.flood_zone ?? null;
  const floodIcon  = floodZone === 3
    ? ` <span style="color:#FF1744;font-size:9px;font-weight:700">⚠ FZ3</span>`
    : floodZone === 2
    ? ` <span style="color:#FFB300;font-size:9px;font-weight:700">FZ2</span>`
    : "";
  const hasComposite = props.composite_score_50 != null;

  return `
    <div class="parcel-card${String(props.osm_id) === state.activeId ? " active" : ""}"
         data-id="${props.osm_id}" style="--card-color:${cfg.color}">
      <div class="parcel-card-header">
        <span class="parcel-name">${displayName(props)}${floodIcon}</span>
        <span class="parcel-badge" style="color:${cfg.color};background:${cfg.color}18;border-color:${cfg.color}33">
          ${cfg.label}
        </span>
      </div>
      <div class="parcel-meta">
        <span class="parcel-meta-item"><strong>${fmtAcres(props.area_acres)}</strong> ac</span>
        <span class="parcel-meta-item" style="color:${cColor}" title="${hasComposite ? "Composite" : "Power"} score">
          ${hasComposite ? "◉" : "⚡"} ${Math.round(composite)}
        </span>
        ${hasComposite ? `<span class="parcel-meta-item" title="Power score">⚡ ${Math.round(getPowerScore(props))}</span>` : ""}
        <span class="parcel-meta-item">${props.region}</span>
      </div>
    </div>`;
}

function highlightListCard(osmId) {
  document.querySelectorAll(".parcel-card").forEach(c =>
    c.classList.toggle("active", c.dataset.id === String(osmId)));
}

// ── Helpers ───────────────────────────────────────────────────────
function getCentroid(coords) {
  if (!coords || !coords.length) return [0, 0];
  let x = 0, y = 0;
  coords.forEach(([lng, lat]) => { x += lng; y += lat; });
  return [x / coords.length, y / coords.length];
}

function flyToParcel(geometry) {
  const coords = geometry.coordinates[0];
  const lngs = coords.map(c => c[0]);
  const lats = coords.map(c => c[1]);
  map.fitBounds(
    [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
    { padding: { top: 80, bottom: 80, left: 360, right: 380 }, maxZoom: 15, duration: 700 }
  );
}

function fmtAcres(a) { return (a == null || isNaN(a)) ? "—" : a >= 100 ? Math.round(a).toLocaleString() : Number(a).toFixed(1); }
function fmtHa(h)    { return (h == null || isNaN(h)) ? "—" : h >= 100 ? Math.round(h).toLocaleString() : Number(h).toFixed(1); }
function fmtM(v)     { return v < 1 ? `£${(v * 1000).toFixed(0)}k` : v >= 100 ? `£${Math.round(v)}M` : `£${v.toFixed(1)}M`; }

// ── Connection cost estimate ───────────────────────────────────────
function computeConnectionCosts(props, mw) {
  const distKm   = props.nearest_sub_dist_km ?? 10;
  const queuePct = props.sub_queue_pressure_pct ?? 200;
  const fibreKm  = props.best_fibre_km ?? props.dist_to_ix_km ?? 20;
  const subName  = props.nearest_sub_name ?? "nearest substation";
  const subKv    = props.nearest_sub_voltage_kv ? `${props.nearest_sub_voltage_kv}kV` : "132kV";

  // ── Grid cable (132kV underground, NESO/Ofgem benchmarks) ──────
  const effectiveDist = Math.max(0, distKm - 0.3);   // first 300m assumed within site boundary
  const cableLow  = effectiveDist * 2.0;
  const cableHigh = effectiveDist * 4.0;

  // ── Substation reinforcement (queue pressure as congestion proxy) ─
  let rLow, rHigh, reinforceBand, reinforceRationale;
  if (queuePct <= 50) {
    [rLow, rHigh, reinforceBand, reinforceRationale] = [0.5, 1.5,
      "Minor works",
      "Low queue — sub has headroom, minimal reinforcement expected"];
  } else if (queuePct <= 150) {
    [rLow, rHigh, reinforceBand, reinforceRationale] = [2.0, 7.0,
      "Moderate reinforcement",
      "Moderate queue — some bay or protection upgrades likely required"];
  } else if (queuePct <= 300) {
    [rLow, rHigh, reinforceBand, reinforceRationale] = [5.0, 18.0,
      "Significant reinforcement",
      "High queue — transformer or switchgear reinforcement likely needed"];
  } else {
    [rLow, rHigh, reinforceBand, reinforceRationale] = [15.0, 45.0,
      "Major works",
      "Severe congestion — major substation reinforcement or alternative connection point required"];
  }

  // ── Onsite HV infrastructure (£200–400/kW) ─────────────────────
  const onsiteLow  = mw * 0.20;
  const onsiteHigh = mw * 0.40;

  // ── Fibre connection (dark fibre build or IRU) ──────────────────
  // Per-km rate bands reflect Ofcom/INCA dark fibre pricing data
  let fLow, fHigh, fibreRateLow, fibreRateHigh, fibreContext;
  if (fibreKm <= 1) {
    [fLow, fHigh, fibreRateLow, fibreRateHigh, fibreContext] =
      [0.05, 0.2, 50, 200, "On/adjacent to backbone — short duct connection only"];
  } else if (fibreKm <= 5) {
    [fLow, fHigh, fibreRateLow, fibreRateHigh, fibreContext] =
      [0.2, 1.5, 40, 300, "Metro range — carrier IRU deal likely available"];
  } else if (fibreKm <= 20) {
    [fLow, fHigh, fibreRateLow, fibreRateHigh, fibreContext] =
      [1.5, 6.0, 75, 300, "Mid-range — dark fibre build or wholesale IRU"];
  } else if (fibreKm <= 50) {
    [fLow, fHigh, fibreRateLow, fibreRateHigh, fibreContext] =
      [6.0, 20.0, 120, 400, "Long route — dedicated fibre build likely required"];
  } else {
    [fLow, fHigh, fibreRateLow, fibreRateHigh, fibreContext] =
      [20.0, 60.0, 300, 600, "Very remote — carrier wholesale deal likely required; cost highly variable"];
  }
  const fibreType = (props.fibre_route_km != null && props.dist_to_ix_km != null
    && props.fibre_route_km <= props.dist_to_ix_km)
    ? "ITU backbone route" : "carrier-neutral colo";

  const totalLow  = cableLow  + rLow  + onsiteLow  + fLow;
  const totalHigh = cableHigh + rHigh + onsiteHigh + fHigh;

  return {
    total: { low: totalLow, high: totalHigh, mid: (totalLow + totalHigh) / 2 },
    components: [
      {
        label:   "Grid cable to substation",
        input:   `${effectiveDist.toFixed(1)} km to ${subName} (${subKv})`,
        formula: `${effectiveDist.toFixed(1)} km × £2–4M/km`,
        source:  "NESO connection offer benchmarks for 132kV HV underground cable",
        low: cableLow, high: cableHigh,
      },
      {
        label:   "Substation reinforcement",
        input:   `${Math.round(queuePct)}% TEC queue pressure → ${reinforceBand}`,
        formula: `Lookup by queue band: ${fmtM(rLow)}–${fmtM(rHigh)}`,
        source:  reinforceRationale,
        low: rLow, high: rHigh,
      },
      {
        label:   "Onsite HV infrastructure",
        input:   `${mw} MW demand`,
        formula: `${mw} MW × £200–400/kW (= £${(mw*200).toLocaleString()}k–£${(mw*400).toLocaleString()}k)`,
        source:  "Turner & Townsend DC benchmark — switchgear, transformers, protection",
        low: onsiteLow, high: onsiteHigh,
      },
      {
        label:   "Fibre connection",
        input:   `${fibreKm.toFixed(1)} km to nearest ${fibreType}`,
        formula: `${fibreKm.toFixed(1)} km × £${fibreRateLow}–${fibreRateHigh}k/km`,
        source:  fibreContext + " · Ofcom/INCA dark fibre pricing data",
        low: fLow, high: fHigh,
      },
    ],
  };
}

function renderCostEstimate(props, mw) {
  const c = computeConnectionCosts(props, mw);
  const rows = c.components.map(comp => `
    <div class="cost-row">
      <div class="cost-row-top">
        <span class="cost-row-label">${comp.label}</span>
        <span class="cost-row-range">${fmtM(comp.low)} — ${fmtM(comp.high)}</span>
      </div>
      <div class="cost-row-input">${comp.input}</div>
      <div class="cost-row-formula">${comp.formula}</div>
      <div class="cost-row-source">${comp.source}</div>
    </div>`).join("");

  const pct = Math.min(100, Math.max(0, (c.total.mid / (c.total.high * 1.1)) * 100));

  return `
    <div class="detail-section-title" style="margin-top:14px">💰 Connection cost estimate</div>
    <div class="cost-total-block">
      <div class="cost-total-label">Total indicative capex</div>
      <div class="cost-total-range">
        <span class="cost-range-low">${fmtM(c.total.low)}</span>
        <div class="cost-range-track">
          <div class="cost-range-fill" style="width:${pct}%"></div>
          <div class="cost-range-mid" style="left:${pct}%" title="Mid estimate: ${fmtM(c.total.mid)}"></div>
        </div>
        <span class="cost-range-high">${fmtM(c.total.high)}</span>
      </div>
      <div class="cost-total-mid">Mid estimate ${fmtM(c.total.mid)}</div>
    </div>
    <div class="cost-breakdown">${rows}</div>
    <div class="cost-disclaimer">Indicative capital costs only. Based on NESO/Ofgem grid benchmarks and Turner &amp; Townsend data. Excludes planning, civil works, and building costs. Subject to detailed feasibility.</div>`;
}

function displayName(props) {
  if (props.name && !props.name.startsWith("Unnamed")) return props.name;
  const parts = [];
  if (props.addr_city) parts.push(props.addr_city);
  if (props.region)    parts.push(props.region);
  const cfg = SITE_TYPES[props.site_type];
  parts.push(cfg ? cfg.label + " site" : "site");
  return parts.join(" · ");
}

// ── Powerline layer ────────────────────────────────────────────────
const _PL = {                // module-level animation state
  frames:   [],
  frameIdx: 0,
  lastTs:   0,
  rafId:    null,
  FRAME_MS: 55,              // ms per frame → full period ≈ 1.1 s
};

function _computeDashFrames(dotSize, gapSize, numFrames) {
  const period = dotSize + gapSize;
  const frames = [];
  for (let i = 0; i < numFrames; i++) {
    const t = (i / numFrames) * period;
    if (t < dotSize) {
      frames.push([dotSize - t, gapSize, t]);
    } else {
      const g = t - dotSize;
      frames.push([0, gapSize - g, dotSize, g]);
    }
  }
  return frames;
}

function _animatePowerlineDots(ts) {
  if (!state.showPowerlines) {
    _PL.rafId = null;
    return;
  }
  if (ts - _PL.lastTs >= _PL.FRAME_MS) {
    if (map.getLayer("powerlines-dots")) {
      map.setPaintProperty("powerlines-dots", "line-dasharray", _PL.frames[_PL.frameIdx]);
    }
    _PL.frameIdx = (_PL.frameIdx + 1) % _PL.frames.length;
    _PL.lastTs   = ts;
  }
  _PL.rafId = requestAnimationFrame(_animatePowerlineDots);
}

function addPowerlineLayer(geojson) {
  _PL.frames = _computeDashFrames(2, 18, 20);   // dot=2, gap=18, 20 frames

  const voltageColor = ["match", ["get", "voltage"],
    400000, "#FFF176",   // bright lemon-white — 400 kV supergrid
    275000, "#FF6200",   // deep burnt orange  — 275 kV
    "#FFF176",
  ];

  map.addSource("powerlines", { type: "geojson", data: geojson });

  // Base line — subtle skeleton, sits BELOW parcel polygons
  map.addLayer({
    id:     "powerlines-base",
    type:   "line",
    source: "powerlines",
    layout: { "line-cap": "round", "line-join": "round",
              "visibility": state.showPowerlines ? "visible" : "none" },
    paint:  {
      "line-color":   voltageColor,
      "line-opacity": 0.28,
      "line-width":   ["match", ["get", "voltage"], 400000, 1.5, 1.0],
    },
  }, "parcels-fill");

  // Animated dots — sits ABOVE parcels, below substation circles
  map.addLayer({
    id:     "powerlines-dots",
    type:   "line",
    source: "powerlines",
    layout: { "line-cap": "round", "line-join": "round",
              "visibility": state.showPowerlines ? "visible" : "none" },
    paint:  {
      "line-color":     voltageColor,
      "line-opacity":   0.90,
      "line-width":     ["match", ["get", "voltage"], 400000, 2.2, 1.6],
      "line-dasharray": _PL.frames[0],
    },
  }, "sub-glow");

  if (state.showPowerlines) {
    _PL.rafId = requestAnimationFrame(_animatePowerlineDots);
  }
}

function setPowerlineVisibility(visible) {
  state.showPowerlines = visible;
  const vis = visible ? "visible" : "none";
  ["powerlines-base", "powerlines-dots"].forEach(id => {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
  });
  if (visible && !_PL.rafId) {
    _PL.rafId = requestAnimationFrame(_animatePowerlineDots);
  }
}

function addFibreRouteLayer(geojson) {
  map.addSource("fibre-routes", { type: "geojson", data: geojson });

  map.addLayer({
    id:     "fibre-routes",
    type:   "line",
    source: "fibre-routes",
    layout: {
      "line-cap":  "round",
      "line-join": "round",
      "visibility": state.showFibreRoutes ? "visible" : "none",
    },
    paint: {
      "line-color":   "#00E5FF",
      "line-opacity": 0.55,
      "line-width": ["interpolate", ["linear"], ["zoom"],
        5, 1.0,
        8, 1.8,
        11, 2.5,
      ],
    },
  }, "sub-glow");  // above parcels, below substation circles
}
