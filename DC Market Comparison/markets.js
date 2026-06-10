// DC Market Comparison — EMEA market intelligence tool
// v1: raw-data exploration across 13 factors. No scoring.
//
// Build order — one feature per session (see /Users/olliepotter/.claude/plans/i-want-to-create-shiny-cray.md):
//   F1  base map (this file scaffold)         ← shipped
//   F2  countries dataset + markers + anchor toggle
//   F3  detail panel scaffold
//   F4  total compute demand 2027 (TWh)
//   F5  latency reachability sphere
//   F6–F8 grid factors
//   F9–F10 fibre factors
//   F11–F14 differentiators
//   F15–F16 market maturity (live + planned MW)
//   F17 map colour modes
//   F18 multi-select compare drawer
//   F19 polish + deploy

/* ──────────────────────────────────────────────────────────────────
   1. Config
   ────────────────────────────────────────────────────────────────── */

const EMEA_CENTER = [10, 45];      // lon, lat — slightly west to leave the rankings panel some breathing room
const EMEA_ZOOM   = 3.0;            // shows from UK to Egypt with sidebar + rankings panel both visible
const MAP_STYLE   = 'mapbox://styles/mapbox/light-v11';

const FACTOR_COUNT = 13;            // 11 numeric + live MW + planned MW

// Booking CTA target — swap for your scheduling link (Calendly, etc.).
const BOOKING_URL = 'mailto:opotter@deloitte.co.uk?subject=EMEA%20data-centre%20market%20insights';

/* ──────────────────────────────────────────────────────────────────
   2. App state — single source of truth
   ────────────────────────────────────────────────────────────────── */

const state = {
  map:               null,
  markets:           [],          // populated in F2 from data/countries.geo.json (+ markets.json)
  anchorMode:        'dc_metro',  // locked to DC metro — capital/metro toggle removed per UX feedback
  rankBy:            'composite_score',  // factor key driving the right-side rankings panel (F26)
  selectedIso:       null,        // currently-open detail panel — F3
  compareSelected:   new Set(),   // ISO-2 codes — F18
  latencyAnchorIso:  null,        // F5 — auto-set from state.selectedIso when a country is clicked
  latencyMs:         10,          // F5 — default 10 ms so clicking a country immediately draws a sphere
  colourBy:          null,        // factor key — F17
  sizeBy:            'dc_capacity_total_mw',  // marker radius scales with live + planned DC capacity (MW)
  weights:           {},          // factor_id → 0..10  (F24)
  weightsActive:     true,        // toggle composite scoring globally
  composite:         {},          // iso2 → { score, rank, contributing, missing }  (F24)
  modelMw:           50,          // cost/emissions estimator — data-centre IT size (MW)
  modelPue:          1.3,         // cost/emissions estimator — power usage effectiveness
};

window.appState = state;          // expose for debugging

/* ──────────────────────────────────────────────────────────────────
   3. Map initialisation
   ────────────────────────────────────────────────────────────────── */

function setLoadStatus(label) {
  const el = document.getElementById('load-status');
  if (el) el.textContent = label;
}

function setLoadProgress(pct) {
  const el = document.getElementById('load-bar-fill');
  if (el) el.style.width = pct + '%';
}

function hideLoadOverlay() {
  const el = document.getElementById('load-overlay');
  if (!el) return;
  el.classList.add('hidden');
  setTimeout(() => { el.style.display = 'none'; }, 500);
}

function showFatalError(msg) {
  console.error('[markets]', msg);
  let el = document.getElementById('fatal-error');
  if (!el) {
    el = document.createElement('div');
    el.id = 'fatal-error';
    el.style.cssText = 'position:fixed;top:16px;left:calc(var(--sidebar-w) + 16px);z-index:10000;'
      + 'background:rgba(255,69,105,0.12);border:1px solid #FF4569;border-radius:8px;'
      + 'padding:10px 14px;color:#FF8AA1;font:600 12px Inter,sans-serif;max-width:520px;'
      + 'box-shadow:0 4px 20px rgba(0,0,0,0.5);';
    document.body.appendChild(el);
  }
  el.textContent = msg;
}

function initMap() {
  console.log('[markets] initMap() called. mapboxgl present?', typeof mapboxgl !== 'undefined');
  console.log('[markets] MAPBOX_TOKEN length:', (window.MAPBOX_TOKEN || '').length);

  if (typeof mapboxgl === 'undefined') {
    showFatalError('Mapbox GL JS failed to load (check network / CDN). Reloading the page usually fixes this.');
    hideLoadOverlay();
    return;
  }

  if (!window.MAPBOX_TOKEN) {
    showFatalError('Missing Mapbox token — check config.js.');
    hideLoadOverlay();
    return;
  }

  mapboxgl.accessToken = window.MAPBOX_TOKEN;

  setLoadStatus('Initialising map…');
  setLoadProgress(20);

  try {
    state.map = new mapboxgl.Map({
      container:          'map',
      style:              MAP_STYLE,
      center:             EMEA_CENTER,
      zoom:               EMEA_ZOOM,
      minZoom:            2,
      maxZoom:            7,
      attributionControl: true,
      projection:         'mercator',
    });
  } catch (err) {
    showFatalError('Mapbox failed to initialise: ' + err.message);
    hideLoadOverlay();
    return;
  }

  state.map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right');

  setLoadProgress(60);

  state.map.on('style.load', () => {
    console.log('[markets] basemap style loaded');
    styleBasemap();
    setLoadStatus('Ready');
    setLoadProgress(100);
    setTimeout(hideLoadOverlay, 200);
  });

  state.map.on('load', () => {
    console.log('[markets] map.load fired');

    // Restrict panning loosely to EMEA so the map doesn't drift to Pacific.
    state.map.setMaxBounds([
      [-30, -40],   // SW: Atlantic / south of Cape Town
      [ 70,  72],   // NE: Russian Arctic / Caspian
    ]);

    loadCountries();
  });

  state.map.on('error', (e) => {
    const msg = (e && e.error && e.error.message) || 'Unknown Mapbox error';
    console.error('[markets] map error:', msg, e);
    if (msg.toLowerCase().includes('access') || msg.toLowerCase().includes('token') || msg.toLowerCase().includes('401') || msg.toLowerCase().includes('403')) {
      showFatalError('Mapbox token rejected (' + msg + '). The token in config.js may be restricted to specific URLs.');
    }
  });

  // Safety: hide the loading overlay no matter what after 3s so it never
  // permanently masks the map.
  setTimeout(() => {
    const overlay = document.getElementById('load-overlay');
    if (overlay && !overlay.classList.contains('hidden')) {
      console.warn('[markets] hiding loading overlay via safety timeout');
      hideLoadOverlay();
    }
  }, 3000);
}

// Recolour the stock light-v11 vector layers into a bespoke warm-paper
// "atlas" that matches the editorial UI: cream land, soft water, ink hairline
// borders, muted labels, and no road/POI/building clutter at country zoom.
function styleBasemap() {
  const LAND  = '#E7E1D3';   // warm paper, a touch lighter than the page
  const WATER = '#CBD3D4';   // soft cool grey-blue
  const LABEL = '#46423A';
  const HALO  = '#EDE8DE';
  let layers;
  try { layers = state.map.getStyle().layers || []; } catch (e) { return; }
  for (const l of layers) {
    const id = l.id, t = l.type;
    try {
      if (t === 'background') {
        state.map.setPaintProperty(id, 'background-color', LAND);
      } else if (t === 'fill') {
        if (/water|ocean|sea|river|lake|bathym/i.test(id)) state.map.setPaintProperty(id, 'fill-color', WATER);
        else if (/building/i.test(id)) state.map.setPaintProperty(id, 'fill-opacity', 0);
        else state.map.setPaintProperty(id, 'fill-color', LAND);
      } else if (t === 'line') {
        if (/water|river|canal|stream/i.test(id)) {
          state.map.setPaintProperty(id, 'line-color', WATER);
        } else if (/admin|boundary|country|state/i.test(id)) {
          const major = /admin[-_]?0|country|dispute/i.test(id);
          state.map.setPaintProperty(id, 'line-color', major ? 'rgba(27,26,23,0.32)' : 'rgba(27,26,23,0.10)');
          if (!major) state.map.setPaintProperty(id, 'line-dasharray', [2, 2]);
        } else if (/road|bridge|tunnel|rail|ferry|path|transit|aeroway|pier/i.test(id)) {
          state.map.setLayoutProperty(id, 'visibility', 'none');
        }
      } else if (t === 'symbol') {
        if (/road|poi|transit|waterway|airport|natural-point|water-point|ferry|rail/i.test(id)) {
          state.map.setLayoutProperty(id, 'visibility', 'none');
        } else {
          state.map.setPaintProperty(id, 'text-color', LABEL);
          state.map.setPaintProperty(id, 'text-halo-color', HALO);
          state.map.setPaintProperty(id, 'text-halo-width', 1.1);
        }
      } else if (t === 'fill-extrusion') {
        state.map.setPaintProperty(id, 'fill-extrusion-opacity', 0);
      } else if (t === 'hillshade') {
        state.map.setLayoutProperty(id, 'visibility', 'none');
      }
    } catch (e) { /* property not applicable to this layer — skip */ }
  }
}

/* ──────────────────────────────────────────────────────────────────
   4. Countries — load, render markers, render sidebar list (F2)
   ────────────────────────────────────────────────────────────────── */

const REGION_ORDER = [
  'Western Europe',
  'Northern Europe',
  'Southern Europe',
  'Central & Eastern Europe',
  'Middle East',
  'North Africa',
];

async function loadCountries() {
  setLoadStatus('Loading markets…');
  setLoadProgress(75);
  try {
    // markets.json is rebuilt by scripts/build_markets_dataset.py from
    // countries.geo.json + every data/raw/* file. It already contains
    // anchors AND any factor values populated so far, keyed by ISO-2.
    const res = await fetch('data/markets.json');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const json = await res.json();
    state.markets = json.markets;
    console.log(
      '[markets] loaded', state.markets.length, 'markets;',
      'factor coverage:', json._meta && json._meta.factor_coverage,
    );
  } catch (err) {
    showFatalError('Failed to load markets dataset: ' + err.message);
    return;
  }

  document.getElementById('stat-countries').textContent = state.markets.length;

  computeFactorRanks();
  computeFactorRanges();
  computeRegionalMeans();
  state.weights = { ...WEIGHT_PRESETS.reset };  // default: all factors equally weighted
  computeCompositeScores();

  addCountriesSourceAndLayer();
  addLatencySphereSourceAndLayer();
  renderMarkerData();
  wireMarkerInteractions();
  wireLatencyControls();
  populateColourBySelect();
  wireColourBySelect();
  renderWeightSliders();
  wireWeightPresets();
  wireCompareControls();
  updateCompareBar();
  populateRankBySelect();
  wireRankBySelect();
  renderRankingPanel();

  // Default to colour-by composite — gives an immediate red-to-green
  // overview of which markets score best out of the box.
  state.colourBy = 'composite_score';
  const colourSel = document.getElementById('colour-by-select');
  if (colourSel) colourSel.value = 'composite_score';
  renderMarkerData();
  applyColourMode();

  wireOverlayChips();

  setLoadProgress(100);
}

/* ──────────────────────────────────────────────────────────────────
   Map overlays — IXPs · HV grid · DC sites (F20-F22)
   ────────────────────────────────────────────────────────────────── */

// Each entry describes one toggleable map overlay layer.
const OVERLAYS = {
  grid: {
    file: 'data/overlay_grid.geojson',
    sourceId: 'overlay-grid-src',
    interactive: false,
    layers: [{
      id: 'overlay-grid',
      type: 'line',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        // Colour by voltage band; thicker + bluer at higher voltage. DC = ochre.
        'line-color': ['match', ['get', 'band'],
          'dc',  '#B5832A',
          'shv', '#1B2F8A',
          'ehv', '#2A45C8',
          /* hv */ '#7C8AD6'],
        'line-width': ['interpolate', ['linear'], ['zoom'],
          2, ['match', ['get', 'band'], 'hv', 0.4, 0.7],
          6, ['match', ['get', 'band'], 'hv', 1.0, 1.8]],
        'line-opacity': 0.55,
      },
    }],
  },
  ixps: {
    file: 'data/overlay_ixps.geojson',
    sourceId: 'overlay-ixps-src',
    interactive: true,
    popup: (props) => {
      const member = props.members ? '<div class="popup-line"><span class="popup-key">Members</span> <strong>' + props.members + '</strong></div>' : '';
      return ''
        + '<div class="popup-tag tag-ixp">Internet exchange (IXP)</div>'
        + '<div class="popup-name">' + escapeHtml(props.name || 'Unnamed') + '</div>'
        + '<div class="popup-region">' + escapeHtml(props.city || '') + (props.country ? ' · ' + escapeHtml(props.country) : '') + '</div>'
        + member
        + (props.url ? '<a class="popup-link" href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">View on PeeringDB ↗</a>' : '');
    },
    layers: [{
      id: 'overlay-ixps',
      type: 'circle',
      paint: {
        'circle-radius':       ['interpolate', ['linear'], ['zoom'], 2, 2, 6, 4],
        'circle-color':        '#FF6B35',
        'circle-stroke-color': '#10141C',
        'circle-stroke-width': 0.5,
        'circle-opacity':      0.8,
      },
    }],
  },
  dcs: {
    // Two data sources behind the one toggle:
    // 1) Full PeeringDB facility list (~1,800 sites) — comprehensive
    //    coverage of carrier-neutral colos. No MW; small grey dots.
    // 2) Curated hyperscale + large colo dataset (~80 sites with MW + status).
    //    Rendered on top so MW labels and status colour pop above the base.
    sources: [
      { id: 'overlay-dcs-base-src',   file: 'data/overlay_dc_sites.geojson'  },
      { id: 'overlay-dcs-hyper-src',  file: 'data/overlay_hyperscale.geojson' },
    ],
    layers: [
      {
        id: 'overlay-dcs-base',
        sourceRef: 'overlay-dcs-base-src',
        type: 'circle',
        interactive: true,
        popupKind: 'peeringdb',
        paint: {
          'circle-radius':       ['interpolate', ['linear'], ['zoom'], 2, 1.5, 6, 3, 8, 4.5],
          'circle-color':        '#9C27B0',
          'circle-stroke-color': '#10141C',
          'circle-stroke-width': 0.4,
          'circle-opacity':      0.7,
        },
      },
      {
        id: 'overlay-dcs-hyper',
        sourceRef: 'overlay-dcs-hyper-src',
        type: 'circle',
        interactive: true,
        popupKind: 'hyperscale',
        // Same purple-dot style as the PeeringDB layer for a clean uniform
        // look. MW + status info still shows in the click popup.
        paint: {
          'circle-radius':       ['interpolate', ['linear'], ['zoom'], 2, 1.5, 6, 3, 8, 4.5],
          'circle-color':        '#9C27B0',
          'circle-stroke-color': '#10141C',
          'circle-stroke-width': 0.4,
          'circle-opacity':      0.7,
        },
      },
    ],
    popups: {
      peeringdb: (props) => ''
        + '<div class="popup-tag tag-dc">Carrier-neutral facility</div>'
        + '<div class="popup-name">' + escapeHtml(props.name || 'Unnamed facility') + '</div>'
        + '<div class="popup-region">' + escapeHtml(props.city || '') + (props.country ? ' · ' + escapeHtml(props.country) : '') + '</div>'
        + (props.url ? '<a class="popup-link" href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">View on PeeringDB ↗</a>' : ''),
      hyperscale: (props) => {
        const statusLabel = (props.status || 'operational').replace(/_/g, ' ');
        const note = props.note ? '<div class="popup-line" style="color:var(--text-low);font-size:10px;font-style:italic">' + escapeHtml(props.note) + '</div>' : '';
        return ''
          + '<div class="popup-tag tag-dc tag-status-' + escapeHtml(props.status || 'operational') + '">' + escapeHtml(statusLabel) + '</div>'
          + '<div class="popup-name">' + escapeHtml(props.name || 'Unnamed facility') + '</div>'
          + '<div class="popup-region">' + escapeHtml(props.operator || '') + (props.city ? ' · ' + escapeHtml(props.city) : '') + (props.country ? ', ' + escapeHtml(props.country) : '') + '</div>'
          + '<div class="popup-line"><span class="popup-key">Capacity</span> <strong>' + (props.mw != null ? props.mw + ' MW' : 'n/a') + '</strong></div>'
          + note
          + (props.url ? '<a class="popup-link" href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">Operator page ↗</a>' : '');
      },
    },
  },
};

let _overlayPopup = null;

function wireOverlayLayerInteractions(o) {
  // New schema (sources + layers w/ popupKind): wire each interactive layer
  // to its specific popup builder. Legacy schema falls back to o.popup.
  const layersToWire = (o.layers || []).filter(L => L.interactive !== false);
  for (const layer of layersToWire) {
    const id = layer.id;
    if (layer._wired) continue;
    layer._wired = true;
    state.map.on('click', id, (e) => {
      if (!e.features || !e.features[0]) return;
      const props = e.features[0].properties || {};
      let html;
      if (layer.popupKind && o.popups) {
        const builder = o.popups[layer.popupKind];
        html = builder ? builder(props) : '';
      } else if (typeof o.popup === 'function') {
        html = o.popup(props);
      } else {
        return;
      }
      if (!html) return;
      if (_overlayPopup) _overlayPopup.remove();
      _overlayPopup = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, offset: 10, maxWidth: '300px' })
        .setLngLat(e.features[0].geometry.coordinates.slice())
        .setHTML(html)
        .addTo(state.map);
      e.originalEvent.stopPropagation();
    });
    state.map.on('mouseenter', id, () => { state.map.getCanvas().style.cursor = 'pointer'; });
    state.map.on('mouseleave', id, () => { state.map.getCanvas().style.cursor = ''; });
  }
}

async function toggleOverlay(key, enabled) {
  const o = OVERLAYS[key];
  if (!o) return;

  // Normalise the schema: legacy entries use `sourceId` + `file`; new ones use
  // a `sources` array. Build a unified list of sources to manage.
  const sources = o.sources
    ? o.sources
    : [{ id: o.sourceId, file: o.file }];

  if (enabled) {
    // Lazy-load each source the first time the overlay is enabled.
    let loadedSomething = false;
    for (const src of sources) {
      if (state.map.getSource(src.id)) continue;
      try {
        const res = await fetch(src.file);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        state.map.addSource(src.id, { type: 'geojson', data });
        loadedSomething = true;
        console.log('[overlay]', key, '/', src.id, 'loaded',
          (data.features && data.features.length) || 0, 'features');
      } catch (err) {
        console.warn('[overlay] failed to load', src.file, '—', err.message);
      }
    }

    // Add each layer if it's not yet on the map.
    if (loadedSomething || sources.every(s => state.map.getSource(s.id))) {
      for (const layer of o.layers) {
        if (state.map.getLayer(layer.id)) continue;
        const sourceId = layer.sourceRef || o.sourceId;
        if (!state.map.getSource(sourceId)) continue;
        const layerCopy = { ...layer };
        delete layerCopy.sourceRef;
        delete layerCopy.interactive;
        delete layerCopy.popupKind;
        state.map.addLayer({ ...layerCopy, source: sourceId }, 'country-markers');
      }
      wireOverlayLayerInteractions(o);
    } else {
      flashCompareBar('Overlay data missing — run scripts/fetch_overlays.py');
      const btn = document.querySelector('.overlay-chip[data-layer="' + key + '"]');
      if (btn) btn.classList.remove('active');
      return;
    }

    // Show any layers that were previously hidden.
    for (const layer of o.layers) {
      if (state.map.getLayer(layer.id)) {
        state.map.setLayoutProperty(layer.id, 'visibility', 'visible');
      }
    }
  } else {
    for (const layer of o.layers) {
      if (state.map.getLayer(layer.id)) {
        state.map.setLayoutProperty(layer.id, 'visibility', 'none');
      }
    }
  }
}

function wireOverlayChips() {
  const group = document.getElementById('overlay-chips');
  if (!group) return;
  group.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-layer]');
    if (!btn) return;
    const key = btn.dataset.layer;
    const wasActive = btn.classList.contains('active');
    btn.classList.toggle('active', !wasActive);
    toggleOverlay(key, !wasActive);
  });
}

function currentAnchorFor(country) {
  return country.anchors[state.anchorMode];
}

function countriesFeatureCollection() {
  return {
    type: 'FeatureCollection',
    features: state.markets.map(c => {
      const a = currentAnchorFor(c);
      // Flatten factor values into properties so Mapbox data-driven paint
      // expressions can read them with `['get', 'f_<factor_id>']`. Only the
      // numeric value lands here; metadata stays in `country.factors[..]`.
      const factorProps = {};
      for (const [fid, entry] of Object.entries(c.factors || {})) {
        if (entry && typeof entry.value === 'number') {
          factorProps['f_' + fid] = entry.value;
        }
      }
      // Composite score from F24 — included so colour-by 'composite' works.
      const comp = state.composite[c.iso2];
      if (comp && comp.score != null) {
        factorProps['f_composite_score'] = comp.score;
      }
      // Synthetic factor: total DC capacity (live + planned). Used by the
      // size-by control so country orbs scale with market scale (F29).
      const live    = factorProps['f_dc_capacity_live_mw']    || 0;
      const planned = factorProps['f_dc_capacity_planned_mw'] || 0;
      if (live + planned > 0) {
        factorProps['f_dc_capacity_total_mw'] = live + planned;
      }
      // Label that the symbol layer renders on top of the circle when
      // colour-by is active. Short string of the active factor's value.
      const label = computeMarkerLabel(c);
      return {
        type: 'Feature',
        id: c.iso2,                       // stable string id for feature-state
        geometry: { type: 'Point', coordinates: [a.lon, a.lat] },
        properties: {
          iso2:        c.iso2,
          name:        c.name,
          flag:        c.flag,
          region:      c.region,
          anchor_name: a.name,
          label,
          ...factorProps,
        },
      };
    }),
  };
}

// Short text label drawn on top of each marker when colour-by is active.
// Reads from state.colourBy + the live composite/factor lookup.
function computeMarkerLabel(c) {
  const fid = state.colourBy;
  if (!fid) return '';
  let value;
  if (fid === 'composite_score') {
    const comp = state.composite[c.iso2];
    value = comp && comp.score;
  } else {
    const e = c.factors && c.factors[fid];
    value = e && e.value;
  }
  if (typeof value !== 'number') return '';
  // Compact format — only the magnitude. Keep labels under ~5 chars so they
  // fit inside the circle at typical zoom.
  if (fid === 'composite_score')      return String(Math.round(value));
  if (fid === 'demand_2027_twh')      return value >= 1000 ? (value / 1000).toFixed(1) + 'k' : String(Math.round(value));
  if (fid === 'grid_connect_years')   return value.toFixed(1);
  if (fid === 'power_per_capita_kwh') return value >= 1000 ? Math.round(value / 1000) + 'k' : String(Math.round(value));
  if (fid === 'grid_investment_usdbn')return value >= 1e9 ? (value / 1e9).toFixed(1) + 'b' : Math.round(value / 1e6) + 'm';
  if (fid === 'bandwidth_gbps')       return value.toFixed(2);
  if (fid === 'construction_cost_usd_mw') return '$' + value.toFixed(1);
  if (fid === 'power_cost_usd_kwh')   return value.toFixed(2);
  if (fid === 'rd_techs_per_million') return value >= 1000 ? Math.round(value / 1000) + 'k' : String(Math.round(value));
  if (fid === 'tertiary_grad_pct')    return Math.round(value * 100).toString();
  if (fid === 'carbon_intensity_gco2_kwh') return Math.round(value).toString();
  if (fid === 'dc_capacity_live_mw' || fid === 'dc_capacity_planned_mw') {
    return value >= 1000 ? (value / 1000).toFixed(1) + 'k' : String(Math.round(value));
  }
  return String(Math.round(value));
}

function addCountriesSourceAndLayer() {
  if (state.map.getSource('countries')) return;

  state.map.addSource('countries', {
    type: 'geojson',
    data: countriesFeatureCollection(),
    promoteId: 'iso2',
  });

  state.map.addLayer({
    id: 'country-markers',
    type: 'circle',
    source: 'countries',
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['zoom'],
        2, 4,
        4, 6,
        6, 9,
      ],
      'circle-color': [
        'case',
        ['boolean', ['feature-state', 'active'], false], '#1B1A17',
        '#2A45C8',
      ],
      'circle-stroke-width': 1.6,
      'circle-stroke-color': [
        'case',
        ['boolean', ['feature-state', 'active'], false], '#B5832A',
        'rgba(255, 255, 255, 0.9)',
      ],
      'circle-opacity': 0.95,
    },
  });

  state.map.addLayer({
    id: 'country-markers-hit',          // larger transparent hitbox for easier clicking
    type: 'circle',
    source: 'countries',
    paint: {
      'circle-radius': 14,
      'circle-color': '#000000',
      'circle-opacity': 0,
    },
  });

  // Score labels rendered on top of the coloured markers (F27).
  // The text reads ['get', 'label'] which is set in countriesFeatureCollection()
  // based on the current state.colourBy. Empty when colour-by is off.
  state.map.addLayer({
    id: 'country-markers-labels',
    type: 'symbol',
    source: 'countries',
    layout: {
      'text-field':            ['get', 'label'],
      'text-font':             ['Open Sans Bold', 'Arial Unicode MS Bold'],
      'text-size':             ['interpolate', ['linear'], ['zoom'], 2, 9, 4, 11, 6, 13],
      'text-allow-overlap':    true,
      'text-ignore-placement': true,
    },
    paint: {
      'text-color':       '#0A0D12',
      'text-halo-color':  'rgba(255,255,255,0.85)',
      'text-halo-width':  1.2,
    },
  });
}

function renderMarkerData() {
  const src = state.map.getSource('countries');
  if (src) src.setData(countriesFeatureCollection());
}

/* ── Sidebar list — removed; the right-side rankings panel is the
   primary list view. Compare checkboxes now live on rank rows. ── */

/* ──────────────────────────────────────────────────────────────────
   Multi-select compare drawer (F18)
   ────────────────────────────────────────────────────────────────── */

function updateCompareBar() {
  const label   = document.getElementById('compare-bar-label');
  const openBtn = document.getElementById('compare-open-btn');
  const clearBtn= document.getElementById('compare-clear-btn');
  if (!label || !openBtn) return;
  const n = state.compareSelected.size;
  label.textContent = n === 0 ? 'No markets selected'
                    : n === 1 ? '1 market selected (need 2+)'
                              : n + ' markets selected';
  openBtn.disabled = n < 2;
  openBtn.textContent = n >= 2 ? 'Compare (' + n + ')' : 'Compare';
  if (clearBtn) clearBtn.hidden = n === 0;
  // Live update the drawer if it's open
  if (!document.getElementById('compare-drawer').classList.contains('hidden')) {
    if (n < 2) closeCompareDrawer();
    else renderCompareDrawer();
  }
}

let _flashTimer = null;
function flashCompareBar(msg) {
  const label = document.getElementById('compare-bar-label');
  if (!label) return;
  const original = label.textContent;
  label.textContent = msg;
  label.style.color = 'var(--warn)';
  clearTimeout(_flashTimer);
  _flashTimer = setTimeout(() => {
    label.style.color = '';
    label.textContent = original;
  }, 1500);
}

function wireCompareControls() {
  const openBtn  = document.getElementById('compare-open-btn');
  const clearBtn = document.getElementById('compare-clear-btn');
  const closeBtn = document.getElementById('compare-drawer-close');
  if (openBtn) openBtn.addEventListener('click', openCompareDrawer);
  if (closeBtn) closeBtn.addEventListener('click', closeCompareDrawer);
  if (clearBtn) clearBtn.addEventListener('click', () => {
    state.compareSelected.clear();
    document.querySelectorAll('.market-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.market-card.compare-on').forEach(el => el.classList.remove('compare-on'));
    updateCompareBar();
    closeCompareDrawer();
  });
}

function openCompareDrawer() {
  if (state.compareSelected.size < 2) return;
  renderCompareDrawer();
  document.getElementById('compare-drawer').classList.remove('hidden');
}

function closeCompareDrawer() {
  document.getElementById('compare-drawer').classList.add('hidden');
}

function renderCompareDrawer() {
  const body = document.getElementById('compare-drawer-body');
  if (!body) return;

  // Stable order: by composite rank ascending (best first), then alpha.
  const selected = [...state.compareSelected]
    .map(iso => ({ iso, c: state.markets.find(x => x.iso2 === iso) }))
    .filter(x => x.c)
    .map(x => ({
      ...x,
      comp: state.composite[x.iso] || {},
    }))
    .sort((a, b) => {
      const ra = (a.comp && a.comp.rank) || 1e9;
      const rb = (b.comp && b.comp.rank) || 1e9;
      if (ra !== rb) return ra - rb;
      return a.c.name.localeCompare(b.c.name);
    });

  // Build header row
  let html = '<table class="compare-table">';
  html += '<thead><tr>'
        + '<th class="factor-col">Factor</th>';
  for (const { c, comp } of selected) {
    const compHtml = (state.weightsActive && comp && comp.score != null)
      ? '<div class="composite">'
        + '<span class="composite-val">' + Math.round(comp.score) + '</span>'
        + '<span class="composite-rank">#' + comp.rank + ' / ' + comp.total + '</span>'
        + '</div>'
      : '';
    html += '<th class="country-header">'
          + '<span class="flag">' + c.flag + '</span>'
          + '<span class="name">' + escapeHtml(c.name) + '</span>'
          + compHtml
          + '</th>';
  }
  html += '</tr></thead><tbody>';

  // For each row in PANEL_ROWS, render a value cell per selected country.
  // Highlight the "best" cell per row (respecting direction).
  let currentSection = null;
  for (const [section, label, fid, fmt, dir] of PANEL_ROWS) {
    if (section !== currentSection) {
      html += '<tr class="section-row"><td colspan="' + (selected.length + 1) + '">'
            + escapeHtml(section) + '</td></tr>';
      currentSection = section;
    }

    // Find which selected country has the "best" value for this factor.
    let bestIso = null;
    let bestVal = null;
    for (const { c } of selected) {
      const entry = c.factors && c.factors[fid];
      if (!entry || typeof entry.value !== 'number') continue;
      if (bestVal == null) { bestIso = c.iso2; bestVal = entry.value; continue; }
      const cmp = dir === 'desc' ? entry.value < bestVal : entry.value > bestVal;
      if (dir !== 'neutral' && cmp) { bestIso = c.iso2; bestVal = entry.value; }
    }

    // Surface a representative source URL on the factor row (first selected country with one).
    let sourceSnippet = '';
    for (const { c } of selected) {
      const e = c.factors && c.factors[fid];
      if (e && e.source) {
        sourceSnippet = '<span class="factor-source">' + escapeHtml(e.source) + '</span>';
        break;
      }
    }

    html += '<tr>'
          + '<td class="factor-name">' + escapeHtml(label) + sourceSnippet + '</td>';
    for (const { c } of selected) {
      const e = c.factors && c.factors[fid];
      if (!e || typeof e.value !== 'number') {
        html += '<td class="value-cell nodata">—</td>';
      } else {
        const cls = (c.iso2 === bestIso && dir !== 'neutral' && selected.length > 1) ? ' best' : '';
        html += '<td class="value-cell' + cls + '">'
              + fmt(e.value)
              + (e.url ? '<span class="src-link"><a href="' + escapeHtml(e.url) + '" target="_blank" rel="noopener">source</a></span>' : '')
              + '</td>';
      }
    }
    html += '</tr>';
  }

  // ── Economics section: build cost / annual power cost / annual CO₂ at the
  //    current Model-a-data-centre scenario (lower is better for all three). ──
  const mw = state.modelMw, pue = state.modelPue;
  const energyKwh = mw * pue * 8760 * 1000;
  const econ = [
    { label: 'Build cost', calc: c => { const v = (c.factors.construction_cost_usd_mw || {}).value; return v != null ? v * mw * 1e6 : null; }, fmt: fmtMoney },
    { label: 'Annual power cost', calc: c => { const v = (c.factors.power_cost_usd_kwh || {}).value; return v != null ? energyKwh * v : null; }, fmt: v => fmtMoney(v) + '/yr' },
    { label: 'Annual grid emissions', calc: c => { const v = (c.factors.carbon_intensity_gco2_kwh || {}).value; return v != null ? energyKwh * v / 1e6 : null; }, fmt: v => Math.round(v).toLocaleString() + ' tCO₂/yr' },
  ];
  html += '<tr class="section-row"><td colspan="' + (selected.length + 1) + '">'
        + 'Economics · ' + mw + ' MW · PUE ' + pue.toFixed(1) + '</td></tr>';
  for (const row of econ) {
    const vals = selected.map(({ c }) => ({ iso: c.iso2, v: row.calc(c) }));
    const present = vals.filter(x => typeof x.v === 'number');
    const bestIso = present.length > 1 ? present.reduce((a, b) => b.v < a.v ? b : a).iso : null;
    html += '<tr><td class="factor-name">' + row.label + '</td>';
    for (const { iso, v } of vals) {
      if (typeof v !== 'number') { html += '<td class="value-cell nodata">—</td>'; continue; }
      const cls = iso === bestIso ? ' best' : '';
      html += '<td class="value-cell' + cls + '">' + row.fmt(v) + '</td>';
    }
    html += '</tr>';
  }

  html += '</tbody></table>';
  body.innerHTML = html;
}

/* ── Map interactions ─────────────────────────────────────────── */

let _marketHoverPopup = null;

function wireMarkerInteractions() {
  _marketHoverPopup = new mapboxgl.Popup({
    closeButton: false, closeOnClick: false, offset: 12, className: 'market-hover-popup',
  });

  state.map.on('mouseenter', 'country-markers-hit', () => {
    state.map.getCanvas().style.cursor = 'pointer';
  });
  state.map.on('mousemove', 'country-markers-hit', (e) => {
    if (!e.features || !e.features[0]) return;
    const iso2 = e.features[0].properties.iso2;
    const country = state.markets.find(c => c.iso2 === iso2);
    if (!country) return;
    const a = currentAnchorFor(country);
    _marketHoverPopup.setLngLat([a.lon, a.lat]).setHTML(marketHoverHtml(country)).addTo(state.map);
  });
  state.map.on('mouseleave', 'country-markers-hit', () => {
    state.map.getCanvas().style.cursor = '';
    if (_marketHoverPopup) _marketHoverPopup.remove();
  });

  state.map.on('click', 'country-markers-hit', (e) => {
    if (!e.features || !e.features[0]) return;
    const iso2 = e.features[0].properties.iso2;
    if (_marketHoverPopup) _marketHoverPopup.remove();
    selectCountry(iso2, { fly: false, source: 'map' });
  });
}

function selectCountry(iso2, { fly = true, source = 'list' } = {}) {
  const country = state.markets.find(c => c.iso2 === iso2);
  if (!country) return;

  // Clear previous active state on the map source
  if (state.selectedIso) {
    state.map.setFeatureState(
      { source: 'countries', id: state.selectedIso },
      { active: false },
    );
  }
  state.selectedIso = iso2;
  state.map.setFeatureState(
    { source: 'countries', id: iso2 },
    { active: true },
  );

  // Sync rankings panel highlight
  document.querySelectorAll('.rank-row').forEach(el => {
    el.classList.toggle('active', el.dataset.iso2 === iso2);
    if (el.dataset.iso2 === iso2 && source === 'map') {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });

  // F5 follow-up: clicking a country auto-anchors the latency sphere there.
  if (state.latencyAnchorIso !== iso2) {
    state.latencyAnchorIso = iso2;
    updateLatencySphere();
  }

  // Fly the map to it when triggered from the list
  if (fly) {
    const a = currentAnchorFor(country);
    state.map.flyTo({ center: [a.lon, a.lat], zoom: Math.max(4.5, state.map.getZoom()), speed: 0.9 });
  }

  // F3 will open the detail panel here.
  openDetailPanel(country);
}

/* ──────────────────────────────────────────────────────────────────
   Composite scoring + weighting (F24)
   ────────────────────────────────────────────────────────────────── */

// Only factors with a defined direction ('asc' or 'desc') feed into the
// composite. Neutral factors (raw market size, capacity) are informational —
// they show in the panel and on the colour map but don't drive the ranking.
const SCORING_FACTORS = [
  { id: 'grid_connect_years',        label: 'Grid connection wait', dir: 'desc' },
  { id: 'power_per_capita_kwh',      label: 'Power / capita',       dir: 'asc'  },
  { id: 'grid_investment_usdbn',     label: 'Grid investment',      dir: 'asc'  },
  { id: 'bandwidth_gbps',            label: 'Bandwidth',            dir: 'asc'  },
  { id: 'construction_cost_usd_mw',  label: 'Construction cost',    dir: 'desc' },
  { id: 'power_cost_usd_kwh',        label: 'Power cost',           dir: 'desc' },
  { id: 'rd_techs_per_million',      label: 'R&D techs / million',  dir: 'asc'  },
  { id: 'tertiary_grad_pct',         label: 'STEM graduate share',  dir: 'asc'  },
  { id: 'carbon_intensity_gco2_kwh', label: 'Grid carbon intensity',dir: 'desc' },
];

const WEIGHT_PRESETS = {
  reset:   Object.fromEntries(SCORING_FACTORS.map(f => [f.id, 5])),
  power:   {
    // Power access — heavy on grid headroom, connection speed, and cheap
    // electricity. Today the #1 siting blocker for hyperscale DCs.
    grid_connect_years: 10, power_per_capita_kwh: 9, grid_investment_usdbn: 8,
    bandwidth_gbps: 2,
    construction_cost_usd_mw: 3, power_cost_usd_kwh: 8,
    rd_techs_per_million: 1, tertiary_grad_pct: 1, carbon_intensity_gco2_kwh: 3,
  },
  cost:    {
    grid_connect_years: 5, power_per_capita_kwh: 3, grid_investment_usdbn: 2,
    bandwidth_gbps: 2,
    construction_cost_usd_mw: 10, power_cost_usd_kwh: 10,
    rd_techs_per_million: 2, tertiary_grad_pct: 2, carbon_intensity_gco2_kwh: 2,
  },
  sustain: {
    grid_connect_years: 5, power_per_capita_kwh: 7, grid_investment_usdbn: 5,
    bandwidth_gbps: 2,
    construction_cost_usd_mw: 2, power_cost_usd_kwh: 4,
    rd_techs_per_million: 2, tertiary_grad_pct: 2, carbon_intensity_gco2_kwh: 10,
  },
  latency: {
    grid_connect_years: 4, power_per_capita_kwh: 3, grid_investment_usdbn: 3,
    bandwidth_gbps: 10,
    construction_cost_usd_mw: 2, power_cost_usd_kwh: 3,
    rd_techs_per_million: 4, tertiary_grad_pct: 3, carbon_intensity_gco2_kwh: 2,
  },
  off:     Object.fromEntries(SCORING_FACTORS.map(f => [f.id, 0])),
};

// Per-factor [min, max] across countries that have data — cached at load.
const FACTOR_RANGES = {};

// Per-region per-factor mean of raw values — used to impute scores for
// sparse-data countries (e.g. Bahrain) so they're judged against a regional
// baseline rather than over-weighted on the handful of factors they do have.
// Shape: REGIONAL_MEANS[region][factorId] = { mean, n }
const REGIONAL_MEANS = {};
// Global fallback when a country's region has no data for the factor either.
const GLOBAL_MEANS = {};

function computeFactorRanges() {
  for (const f of SCORING_FACTORS) {
    const vals = state.markets
      .map(c => c.factors && c.factors[f.id] && c.factors[f.id].value)
      .filter(v => typeof v === 'number');
    if (vals.length > 0) {
      FACTOR_RANGES[f.id] = { min: Math.min(...vals), max: Math.max(...vals) };
      GLOBAL_MEANS[f.id] = { mean: vals.reduce((a, b) => a + b, 0) / vals.length, n: vals.length };
    }
  }
}

function computeRegionalMeans() {
  for (const k of Object.keys(REGIONAL_MEANS)) delete REGIONAL_MEANS[k];
  const byRegion = {};
  for (const c of state.markets) {
    const region = c.region || 'Unknown';
    if (!byRegion[region]) byRegion[region] = [];
    byRegion[region].push(c);
  }
  for (const [region, members] of Object.entries(byRegion)) {
    REGIONAL_MEANS[region] = {};
    for (const f of SCORING_FACTORS) {
      const vals = members
        .map(c => c.factors && c.factors[f.id] && c.factors[f.id].value)
        .filter(v => typeof v === 'number');
      if (vals.length > 0) {
        REGIONAL_MEANS[region][f.id] = {
          mean: vals.reduce((a, b) => a + b, 0) / vals.length,
          n: vals.length,
        };
      }
    }
  }
}

// Normalise a raw value into 0-100. For 'desc' factors (lower=better) the
// scale is reversed so '#1' always means best.
function normalise(fid, value, dir) {
  const r = FACTOR_RANGES[fid];
  if (!r || r.max === r.min) return 50;
  const raw = (value - r.min) / (r.max - r.min);
  return dir === 'desc' ? (1 - raw) * 100 : raw * 100;
}

function computeCompositeScores() {
  const weights = state.weights;
  const totalWeightAvailable = Object.values(weights).reduce((a, b) => a + b, 0);
  state.composite = {};
  if (totalWeightAvailable === 0) {
    state.weightsActive = false;
    return;
  }
  state.weightsActive = true;

  // 1. Score each country. Missing factors are IMPUTED using the regional
  //    mean (falling back to the global mean if the region has no data
  //    either) so sparse-data markets like Bahrain are judged against a
  //    full factor set rather than over-weighted on the few values they
  //    happen to have. Imputed contributions are flagged so the UI can
  //    show users what's real vs modelled.
  const rows = [];
  for (const c of state.markets) {
    let weighted = 0;
    let weightSum = 0;
    const contrib = {};
    const missing = [];   // truly no data anywhere — could not impute
    const imputed = [];   // filled from region/global mean
    for (const f of SCORING_FACTORS) {
      const w = weights[f.id] || 0;
      if (w === 0) continue;
      const entry = c.factors && c.factors[f.id];
      let rawValue, source = null, sourceN = 0;
      if (entry && typeof entry.value === 'number') {
        rawValue = entry.value;
      } else {
        const regionStats = REGIONAL_MEANS[c.region] && REGIONAL_MEANS[c.region][f.id];
        if (regionStats) {
          rawValue = regionStats.mean;
          source = 'region';
          sourceN = regionStats.n;
        } else if (GLOBAL_MEANS[f.id]) {
          rawValue = GLOBAL_MEANS[f.id].mean;
          source = 'global';
          sourceN = GLOBAL_MEANS[f.id].n;
        } else {
          missing.push(f.id);
          continue;
        }
        imputed.push(f.id);
      }
      const norm = normalise(f.id, rawValue, f.dir);
      weighted   += w * norm;
      weightSum  += w;
      contrib[f.id] = {
        norm,
        weight: w,
        weightedContribution: w * norm,
        imputed: source,         // null | 'region' | 'global'
        imputedN: sourceN,
      };
    }
    if (weightSum === 0) {
      state.composite[c.iso2] = { score: null, contrib, missing, imputed };
      continue;
    }
    const score = weighted / weightSum;
    rows.push({ iso2: c.iso2, score });
    state.composite[c.iso2] = { score, contrib, missing, imputed };
  }

  // 2. Assign ranks. Higher score = better = rank 1.
  rows.sort((a, b) => b.score - a.score);
  let prevScore = null, prevRank = 0;
  rows.forEach((r, i) => {
    const rank = r.score === prevScore ? prevRank : (i + 1);
    state.composite[r.iso2].rank  = rank;
    state.composite[r.iso2].total = rows.length;
    prevScore = r.score;
    prevRank  = rank;
  });
}

function applyPreset(name) {
  const preset = WEIGHT_PRESETS[name];
  if (!preset) return;
  state.weights = { ...preset };
  syncWeightInputs();
  document.querySelectorAll('#weights-presets button').forEach(b => {
    b.classList.toggle('active', b.dataset.preset === name);
  });
  recomputeAndRefresh();
}

function syncWeightInputs() {
  for (const f of SCORING_FACTORS) {
    const input = document.getElementById('w-' + f.id);
    const valEl = document.getElementById('wv-' + f.id);
    if (input) input.value = state.weights[f.id] || 0;
    if (valEl) valEl.textContent = state.weights[f.id] || 0;
    const row = document.querySelector('.weight-row[data-fid="' + f.id + '"]');
    if (row) row.classList.toggle('zero', (state.weights[f.id] || 0) === 0);
  }
  const totalActive = SCORING_FACTORS.filter(f => (state.weights[f.id] || 0) > 0).length;
  const meta = document.getElementById('weights-meta');
  if (meta) meta.textContent = totalActive + ' / ' + SCORING_FACTORS.length + ' factors active';
}

function renderWeightSliders() {
  const container = document.getElementById('weights-sliders');
  if (!container) return;
  container.innerHTML = '';
  for (const f of SCORING_FACTORS) {
    const row = document.createElement('div');
    row.className = 'weight-row';
    row.dataset.fid = f.id;
    row.innerHTML =
      '<span class="weight-label" title="' + escapeHtml(f.label) + ' — ' + (f.dir === 'desc' ? 'lower is better' : 'higher is better') + '">'
      + escapeHtml(f.label) + '</span>'
      + '<input type="range" id="w-' + f.id + '" min="0" max="10" step="1" value="' + (state.weights[f.id] || 0) + '">'
      + '<span class="weight-value" id="wv-' + f.id + '">' + (state.weights[f.id] || 0) + '</span>';
    container.appendChild(row);
  }
  // Wire up each slider with live updates
  container.querySelectorAll('input[type="range"]').forEach(input => {
    input.addEventListener('input', () => {
      const fid = input.id.slice(2);
      const v = +input.value;
      state.weights[fid] = v;
      const valEl = document.getElementById('wv-' + fid);
      if (valEl) valEl.textContent = v;
      const row = input.closest('.weight-row');
      if (row) row.classList.toggle('zero', v === 0);
      // Manual change clears any active preset highlight
      document.querySelectorAll('#weights-presets button').forEach(b => b.classList.remove('active'));
      const meta = document.getElementById('weights-meta');
      if (meta) {
        const totalActive = SCORING_FACTORS.filter(f => (state.weights[f.id] || 0) > 0).length;
        meta.textContent = totalActive + ' / ' + SCORING_FACTORS.length + ' factors active';
      }
      recomputeAndRefresh();
    });
  });
}

function wireWeightPresets() {
  const presetGroup = document.getElementById('weights-presets');
  if (!presetGroup) return;
  presetGroup.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-preset]');
    if (!btn) return;
    applyPreset(btn.dataset.preset);
  });
}

function recomputeAndRefresh() {
  computeCompositeScores();
  renderMarkerData();
  if (state.colourBy === 'composite_score') applyColourMode();
  updateCompareBar();
  updateLatencySphere();
  renderRankingPanel();
  if (state.selectedIso) {
    const c = state.markets.find(x => x.iso2 === state.selectedIso);
    if (c) {
      openDetailPanel(c);
      document.querySelectorAll('.rank-row').forEach(el => {
        el.classList.toggle('active', el.dataset.iso2 === state.selectedIso);
      });
    }
  }
}

/* ──────────────────────────────────────────────────────────────────
   Colour markers by factor (F17)
   ────────────────────────────────────────────────────────────────── */

// Each entry: [factor_id, label, format, direction]
// direction: 'asc'  → higher values render brighter cyan (e.g. bandwidth, R&D)
//            'desc' → lower values render brighter cyan  (e.g. carbon, cost, wait)
//            'neutral' → just scale by magnitude (e.g. demand, capacity — informational)
const COLOUR_OPTIONS = [
  { id: 'composite_score',           label: '★ Composite score',    fmt: v => Math.round(v) + ' / 100',                dir: 'asc' },
  { id: 'demand_2027_twh',           label: 'Addressable demand 2030', fmt: v => Math.round(v).toLocaleString() + ' EB', dir: 'neutral' },
  { id: 'grid_connect_years',        label: 'Grid connection wait', fmt: v => v.toFixed(1) + ' yrs',                   dir: 'desc' },
  { id: 'power_per_capita_kwh',      label: 'Power / capita',       fmt: v => Math.round(v).toLocaleString() + ' kWh', dir: 'asc' },
  { id: 'grid_investment_usdbn',     label: 'Grid investment / yr', fmt: v => '€' + Math.round(v / 1e6).toLocaleString() + 'M/yr', dir: 'asc' },
  { id: 'bandwidth_gbps',            label: 'Bandwidth',            fmt: v => v.toFixed(2) + ' Gbps',                  dir: 'asc' },
  { id: 'construction_cost_usd_mw',  label: 'Construction cost',    fmt: v => '$' + v.toFixed(1) + '/W',               dir: 'desc' },
  { id: 'power_cost_usd_kwh',        label: 'Power cost',           fmt: v => '$' + v.toFixed(3) + '/kWh',             dir: 'desc' },
  { id: 'rd_techs_per_million',      label: 'R&D techs / million',  fmt: v => Math.round(v).toLocaleString(),          dir: 'asc' },
  { id: 'tertiary_grad_pct',         label: 'STEM graduate share',  fmt: v => Math.round(v * 100) + '%',               dir: 'asc' },
  { id: 'carbon_intensity_gco2_kwh', label: 'Grid carbon intensity',fmt: v => Math.round(v) + ' gCO₂/kWh',             dir: 'desc' },
  { id: 'dc_capacity_live_mw',       label: 'Live DC capacity',     fmt: v => Math.round(v) + ' MW',                   dir: 'neutral' },
  { id: 'dc_capacity_planned_mw',    label: 'Planned DC capacity',  fmt: v => Math.round(v) + ' MW',                   dir: 'neutral' },
];

// Traffic-light red → amber → green ramp (5 stops).
// Worst → red, best → green. Reverses when a factor is direction='desc'.
// Deepened for legibility on the light/paper basemap.
const COLOUR_RAMP = [
  '#B23A2E',   // 0    — deep red (worst)
  '#CC6B2C',   // 0.25 — burnt orange
  '#C99A2E',   // 0.50 — ochre
  '#6E8C3A',   // 0.75 — olive
  '#1F7A3D',   // 1    — deep green (best)
];
const COLOUR_HIGH   = COLOUR_RAMP[COLOUR_RAMP.length - 1];
const COLOUR_NODATA = '#C2BCAD'; // warm grey

function populateColourBySelect() {
  const sel = document.getElementById('colour-by-select');
  if (!sel) return;
  for (const opt of COLOUR_OPTIONS) {
    const o = document.createElement('option');
    o.value = opt.id;
    o.textContent = opt.label;
    sel.appendChild(o);
  }
}

function wireColourBySelect() {
  const sel = document.getElementById('colour-by-select');
  if (!sel) return;
  sel.addEventListener('change', () => {
    state.colourBy = sel.value || null;
    renderMarkerData();   // re-emits the `label` property on every feature
    applyColourMode();
  });
  const sizeSel = document.getElementById('size-by-select');
  if (sizeSel) {
    sizeSel.addEventListener('change', () => {
      state.sizeBy = sizeSel.value || null;
      applyMarkerRadius();
    });
  }
}

function applyMarkerRadius() {
  const sizeFid = state.sizeBy;
  if (!sizeFid) {
    // Uniform default radius — when colourBy is on, this gets overridden
    // further down by applyColourMode for legibility.
    state.map.setPaintProperty('country-markers', 'circle-radius', [
      'interpolate', ['linear'], ['zoom'],
      2, 5,  4, 7,  6, 10,
    ]);
    return;
  }
  // Build a per-factor min/max bracket so the smallest market still reads as
  // a marker, not a dot. Floor at 4 px, cap at 26 px.
  let max = 0;
  for (const c of state.markets) {
    if (sizeFid === 'dc_capacity_total_mw') {
      const live    = (c.factors.dc_capacity_live_mw    || {}).value || 0;
      const planned = (c.factors.dc_capacity_planned_mw || {}).value || 0;
      if (live + planned > max) max = live + planned;
    } else {
      const v = (c.factors[sizeFid] || {}).value;
      if (typeof v === 'number' && v > max) max = v;
    }
  }
  if (max === 0) max = 1;
  const propKey = 'f_' + sizeFid;
  const sqrtMax = Math.sqrt(max);
  // Area-proportional (sqrt) scaling so the skewed distribution spreads well
  // and small markets keep a visible floor (still clickable via the 14px hitbox).
  const sz = ['sqrt', ['coalesce', ['get', propKey], 0]];
  state.map.setPaintProperty('country-markers', 'circle-radius', [
    'interpolate', ['linear'], ['zoom'],
    2, ['interpolate', ['linear'], sz, 0, 3.5, sqrtMax, 13],
    4, ['interpolate', ['linear'], sz, 0, 4.5, sqrtMax, 18],
    6, ['interpolate', ['linear'], sz, 0, 6,   sqrtMax, 24],
  ]);
}

function applyColourMode() {
  applyMarkerRadius();  // size always re-applies; colour layered on top
  const fid = state.colourBy;
  if (!fid) {
    // Default: solid cyan with active-state override
    state.map.setPaintProperty('country-markers', 'circle-color', [
      'case',
      ['boolean', ['feature-state', 'active'], false], '#1B1A17',
      '#2A45C8',
    ]);
    renderColourLegend(null);
    return;
  }

  const opt = COLOUR_OPTIONS.find(o => o.id === fid);
  if (!opt) return;

  // For composite_score read from state.composite instead of country.factors.
  const valueLookup = (fid === 'composite_score')
    ? (c => state.composite[c.iso2] && state.composite[c.iso2].score)
    : (c => c.factors && c.factors[fid] && c.factors[fid].value);

  // Compute min/max across countries that actually have this factor.
  const values = state.markets
    .map(valueLookup)
    .filter(v => typeof v === 'number');
  if (values.length === 0) {
    renderColourLegend(opt, null, null, 0);
    return;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const propKey = 'f_' + fid;
  const range = max - min || 1;

  // 5-stop ramp. For 'desc' direction the ramp is reversed so the best
  // value (lowest) lands on COLOUR_RAMP[4] (yellow).
  const reverse = opt.dir === 'desc';
  const stops = [];
  for (let i = 0; i < COLOUR_RAMP.length; i++) {
    const t = i / (COLOUR_RAMP.length - 1);
    stops.push(min + t * range);
    stops.push(reverse ? COLOUR_RAMP[COLOUR_RAMP.length - 1 - i] : COLOUR_RAMP[i]);
  }

  const colourExpr = [
    'case',
    ['boolean', ['feature-state', 'active'], false], '#1B1A17',
    ['has', propKey],
    ['interpolate', ['linear'], ['get', propKey], ...stops],
    COLOUR_NODATA,
  ];
  state.map.setPaintProperty('country-markers', 'circle-color', colourExpr);

  // If no size-by is active, fall back to the bigger uniform radius for
  // legibility when colouring. Otherwise leave the size driven by sizeBy.
  if (!state.sizeBy) {
    state.map.setPaintProperty('country-markers', 'circle-radius', [
      'interpolate', ['linear'], ['zoom'],
      2, 7,  4, 11,  6, 16,
    ]);
  }

  renderColourLegend(opt, min, max, values.length);
}

function renderColourLegend(opt, min, max, count) {
  const legend = document.getElementById('map-legend');
  const items  = document.getElementById('legend-items');
  if (!legend || !items) return;

  if (!opt) {
    legend.classList.add('hidden');
    items.innerHTML = '';
    return;
  }

  legend.classList.remove('hidden');
  // Reverse the ramp when lower-is-better so colour interpretation stays
  // consistent: leftmost stop = worst, rightmost = best.
  const reverse = opt.dir === 'desc';
  const ramp = reverse ? [...COLOUR_RAMP].reverse() : COLOUR_RAMP;
  const directionNote = opt.dir === 'asc'
    ? 'Higher is better'
    : opt.dir === 'desc'
      ? 'Lower is better (cost / wait direction)'
      : 'By magnitude (no normative meaning)';

  // The legend orientation is fixed worst→best left→right, so we re-orient
  // the min/max labels accordingly.
  const leftLabel  = opt.fmt(reverse ? max : min);
  const rightLabel = opt.fmt(reverse ? min : max);

  items.innerHTML =
    '<div class="legend-title">' + escapeHtml(opt.label) + '</div>' +
    '<div class="legend-ramp">' +
      ramp.map(c => '<span class="legend-stop" style="background:' + c + '"></span>').join('') +
    '</div>' +
    '<div class="legend-range">' +
      '<span>worst · ' + escapeHtml(leftLabel) + '</span>' +
      '<span>' + escapeHtml(rightLabel) + ' · best</span>' +
    '</div>' +
    '<div class="legend-meta">' + escapeHtml(directionNote) +
      ' · ' + count + '/' + state.markets.length + ' countries with data</div>' +
    '<div class="legend-nodata">' +
      '<span class="legend-circle" style="background:' + COLOUR_NODATA + '"></span> no data' +
    '</div>';
}

/* ──────────────────────────────────────────────────────────────────
   Latency reachability sphere (F5)
   ────────────────────────────────────────────────────────────────── */

// Speed-of-light-in-fibre, one-way, theoretical max. Real-world production
// fibre adds 15-30% routing overhead; users should treat the sphere as a
// best-case envelope. Quoted in the UI tooltip beneath the controls.
const KM_PER_MS = 200;

const EARTH_RADIUS_KM = 6371;

// Generate a polygon approximating a great-circle disc of `radiusKm` around
// (lon,lat). 128 vertices gives a smooth render at any zoom while staying
// cheap to update. Handles antimeridian wrap by unwrapping longitudes so the
// resulting polygon is continuous (Mapbox renders it correctly when wrapped).
function generateCircleGeoJSON(lon, lat, radiusKm, segments = 128) {
  const lat1 = lat * Math.PI / 180;
  const lon1 = lon * Math.PI / 180;
  const delta = radiusKm / EARTH_RADIUS_KM;          // angular distance, rad
  const coords = [];
  let prevLonDeg = null;
  let lonOffset = 0;
  for (let i = 0; i <= segments; i++) {
    const bearing = (i / segments) * 2 * Math.PI;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(delta) +
      Math.cos(lat1) * Math.sin(delta) * Math.cos(bearing)
    );
    const lon2 = lon1 + Math.atan2(
      Math.sin(bearing) * Math.sin(delta) * Math.cos(lat1),
      Math.cos(delta) - Math.sin(lat1) * Math.sin(lat2)
    );
    let lonDeg = lon2 * 180 / Math.PI;
    const latDeg = lat2 * 180 / Math.PI;
    if (prevLonDeg !== null) {
      const diff = lonDeg - prevLonDeg;
      if (diff > 180)  lonOffset -= 360;
      if (diff < -180) lonOffset += 360;
    }
    prevLonDeg = lonDeg;
    coords.push([lonDeg + lonOffset, latDeg]);
  }
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [coords] },
    properties: {},
  };
}

function haversineKm(lon1, lat1, lon2, lat2) {
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
          + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

function addLatencySphereSourceAndLayer() {
  if (state.map.getSource('latency-sphere')) return;
  state.map.addSource('latency-sphere', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });
  // Fill drawn below markers so country dots stay legible inside the sphere.
  state.map.addLayer({
    id: 'latency-sphere-fill',
    type: 'fill',
    source: 'latency-sphere',
    paint: {
      'fill-color':   '#00E5FF',
      'fill-opacity': 0.08,
    },
  }, 'country-markers');
  state.map.addLayer({
    id: 'latency-sphere-stroke',
    type: 'line',
    source: 'latency-sphere',
    paint: {
      'line-color':       '#00E5FF',
      'line-width':       2,
      'line-opacity':     0.55,
      'line-dasharray':   [2, 2],
    },
  }, 'country-markers');
}

function updateLatencySphere() {
  const src = state.map.getSource('latency-sphere');
  if (!src) return;

  const anchorIso = state.latencyAnchorIso;
  const ms        = state.latencyMs;
  const meta      = document.getElementById('latency-meta');

  if (!anchorIso || !ms) {
    src.setData({ type: 'FeatureCollection', features: [] });
    refreshMarketListRangeBadges([], null);
    if (meta) {
      meta.classList.remove('has-data');
      meta.innerHTML = 'Pick an anchor + latency to draw a reach sphere. Radius assumes 200 km/ms (theoretical fibre limit; real paths add 15–30% routing overhead).';
    }
    return;
  }

  const anchor = state.markets.find(c => c.iso2 === anchorIso);
  if (!anchor) return;
  const a = currentAnchorFor(anchor);
  const radiusKm = ms * KM_PER_MS;

  src.setData({
    type: 'FeatureCollection',
    features: [generateCircleGeoJSON(a.lon, a.lat, radiusKm)],
  });

  // Compute which other countries fall inside the sphere (great-circle).
  const inRange = [];
  for (const c of state.markets) {
    if (c.iso2 === anchorIso) continue;
    const ca = currentAnchorFor(c);
    if (haversineKm(a.lon, a.lat, ca.lon, ca.lat) <= radiusKm) {
      inRange.push(c.iso2);
    }
  }
  refreshMarketListRangeBadges(inRange, anchorIso);

  if (meta) {
    meta.classList.add('has-data');
    meta.innerHTML =
      'From <strong>' + escapeHtml(anchor.name) + '</strong> · <strong>' + ms + ' ms</strong> · '
      + '<strong>' + radiusKm.toLocaleString() + ' km</strong> reach · '
      + '<strong>' + inRange.length + '</strong> markets in range.';
  }
}

function refreshMarketListRangeBadges(inRangeIsos, anchorIso) {
  const inRangeSet = new Set(inRangeIsos);
  document.querySelectorAll('.rank-row').forEach(row => {
    const iso = row.dataset.iso2;
    row.classList.toggle('is-anchor', iso === anchorIso);
    row.classList.toggle('in-range', inRangeSet.has(iso));
  });
}

function wireLatencyControls() {
  const sel    = document.getElementById('latency-anchor');
  const toggle = document.getElementById('latency-ms-toggle');
  if (sel) {
    sel.addEventListener('change', () => {
      state.latencyAnchorIso = sel.value || null;
      updateLatencySphere();
    });
  }
  if (toggle) {
    toggle.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-ms]');
      if (!btn) return;
      const ms = +btn.dataset.ms;
      state.latencyMs = ms;
      toggle.querySelectorAll('button').forEach(b => {
        b.classList.toggle('active', +b.dataset.ms === ms);
      });
      updateLatencySphere();
    });
  }
}

/* ──────────────────────────────────────────────────────────────────
   Right-side rankings panel (F26)
   ────────────────────────────────────────────────────────────────── */

function populateRankBySelect() {
  const sel = document.getElementById('rankby-select');
  if (!sel) return;
  // Composite is the most useful default — keep it at the top.
  for (const opt of COLOUR_OPTIONS) {
    const o = document.createElement('option');
    o.value = opt.id;
    o.textContent = opt.label;
    sel.appendChild(o);
  }
  sel.value = state.rankBy;
}

function wireRankBySelect() {
  const sel = document.getElementById('rankby-select');
  if (!sel) return;
  sel.addEventListener('change', () => {
    state.rankBy = sel.value;
    renderRankingPanel();
  });
}

function renderRankingPanel() {
  const body = document.getElementById('ranking-panel-body');
  const meta = document.getElementById('ranking-panel-meta');
  if (!body) return;

  const fid = state.rankBy;
  const opt = COLOUR_OPTIONS.find(o => o.id === fid);
  if (!opt) return;

  // Two value sources: composite_score uses state.composite; everything else
  // reads from country.factors directly.
  const isComposite = fid === 'composite_score';
  const rows = state.markets.map(c => {
    let value, year, source, url;
    if (isComposite) {
      const comp = state.composite[c.iso2];
      value = comp && comp.score;
      year  = null;
      source = state.weightsActive ? 'Weighted across ' + Object.keys(state.weights).filter(k => state.weights[k] > 0).length + ' factors' : null;
    } else {
      const entry = c.factors && c.factors[fid];
      if (entry) { value = entry.value; year = entry.year; source = entry.source; url = entry.url; }
    }
    return { c, value, year, source, url };
  });

  // Sort: countries with data first by direction, then no-data at the bottom.
  const withData = rows.filter(r => typeof r.value === 'number');
  const noData   = rows.filter(r => typeof r.value !== 'number');
  if (opt.dir === 'desc') withData.sort((a, b) => a.value - b.value);
  else                     withData.sort((a, b) => b.value - a.value);
  noData.sort((a, b) => a.c.name.localeCompare(b.c.name));

  // Dense ranking
  let prevVal = null, prevRank = 0;
  withData.forEach((r, i) => {
    r.rank = r.value === prevVal ? prevRank : (i + 1);
    prevVal = r.value;
    prevRank = r.rank;
  });

  if (meta) {
    const dirText = opt.dir === 'desc' ? 'Lower is better' : opt.dir === 'neutral' ? 'By magnitude' : 'Higher is better';
    const coverage = withData.length + ' / ' + state.markets.length + ' have data';
    meta.textContent = dirText + ' · ' + coverage;
  }

  body.innerHTML = '';
  const total = withData.length;
  for (const r of withData) {
    body.appendChild(rankRowEl(r, total, opt, isComposite));
  }
  if (noData.length > 0) {
    const hdr = document.createElement('div');
    hdr.style.cssText = 'font-size:10px;color:var(--text-low);text-transform:uppercase;letter-spacing:0.08em;padding:14px 10px 6px;';
    hdr.textContent = 'No data · ' + noData.length;
    body.appendChild(hdr);
    for (const r of noData) {
      body.appendChild(rankRowEl(r, total, opt, isComposite));
    }
  }
}

function rampColourForRank(rank, total) {
  if (typeof rank !== 'number' || !total || total < 2) return null;
  const pct = (rank - 1) / (total - 1);  // 0 = best, 1 = worst
  // Snap to one of the 5 ramp stops so the colour matches the marker layer.
  // Rank 1 → COLOUR_RAMP[4] (green), Rank N → COLOUR_RAMP[0] (red).
  const idx = Math.round((1 - pct) * (COLOUR_RAMP.length - 1));
  return COLOUR_RAMP[idx];
}

function rankRowEl(r, total, opt, isComposite) {
  const row = document.createElement('div');
  row.className = 'rank-row';
  row.dataset.iso2 = r.c.iso2;
  if (typeof r.value !== 'number') row.classList.add('nodata');
  if (state.selectedIso === r.c.iso2) row.classList.add('active');
  if (state.compareSelected.has(r.c.iso2)) row.classList.add('compare-on');

  const rampColor = rampColourForRank(r.rank, total);
  const colourStyle = rampColor ? ' style="color:' + rampColor + '"' : '';

  const numCell = (typeof r.value === 'number')
    ? '<div class="rank-num"' + colourStyle + '>#' + r.rank + '</div>'
    : '<div class="rank-num">—</div>';

  // Right-hand value cell
  let valCell;
  if (typeof r.value !== 'number') {
    valCell = '<div class="rank-value">— no data</div>';
  } else {
    const sub = r.year ? '<span class="rank-value-sub">' + r.year + '</span>' : '';
    valCell = '<div><div class="rank-value"' + colourStyle + '>' + opt.fmt(r.value) + '</div>' + sub + '</div>';
  }

  // Country name with optional subtitle for composite (showing data coverage)
  let nameSub = '';
  if (isComposite) {
    const comp = state.composite[r.c.iso2];
    const impN  = comp && comp.imputed ? comp.imputed.length : 0;
    const missN = comp && comp.missing ? comp.missing.length : 0;
    if (impN > 0 || missN > 0) {
      const parts = [];
      if (impN > 0)  parts.push(impN + ' imputed');
      if (missN > 0) parts.push(missN + ' missing');
      nameSub = '<span class="rank-name-sub">' + parts.join(' · ') + '</span>';
    }
  } else if (r.source) {
    nameSub = '<span class="rank-name-sub" title="' + escapeHtml(r.source) + '">' + escapeHtml(truncate(r.source, 36)) + '</span>';
  }

  const checked = state.compareSelected.has(r.c.iso2) ? ' checked' : '';
  row.innerHTML =
      '<input type="checkbox" class="rank-checkbox" data-iso2="' + r.c.iso2 + '"' + checked + ' title="Add to compare" />'
    + numCell
    + '<span class="rank-flag">' + r.c.flag + '</span>'
    + '<div><span class="rank-name">' + escapeHtml(r.c.name) + '</span>' + nameSub + '</div>'
    + valCell;

  // Body click selects; checkbox click toggles compare selection.
  row.addEventListener('click', (e) => {
    if (e.target.classList.contains('rank-checkbox')) return;
    selectCountry(r.c.iso2, { fly: true, source: 'rank' });
  });
  // Hover summary card
  row.addEventListener('mouseenter', (e) => showHoverCardFor(r.c, e.clientX, e.clientY));
  row.addEventListener('mousemove',  (e) => moveHoverCard(e.clientX, e.clientY));
  row.addEventListener('mouseleave', hideHoverCard);

  const cb = row.querySelector('.rank-checkbox');
  cb.addEventListener('click', (e) => e.stopPropagation());
  cb.addEventListener('change', () => {
    if (cb.checked) {
      if (state.compareSelected.size >= 4) {
        cb.checked = false;
        flashCompareBar('Max 4 markets at once');
        return;
      }
      state.compareSelected.add(r.c.iso2);
      row.classList.add('compare-on');
    } else {
      state.compareSelected.delete(r.c.iso2);
      row.classList.remove('compare-on');
    }
    updateCompareBar();
  });
  return row;
}

function truncate(s, n) { return s.length <= n ? s : s.slice(0, n - 1) + '…'; }

/* ── Detail panel ─────────────────────────────────────────────── */

// One row per factor in the detail panel.
// dir: 'asc'  → higher is better (rank 1 = highest value)
//      'desc' → lower is better  (rank 1 = lowest value)
//      'neutral' → rank by magnitude, but no normative meaning
const PANEL_ROWS = [
  ['Demand dynamics',     'Addressable demand 2030',     'demand_2027_twh',           v => Math.round(v).toLocaleString() + ' EB',      'neutral'],

  ['Supply — Grid',       'Connection timeline',         'grid_connect_years',        v => v.toFixed(1) + ' yrs',                       'desc'],
  ['Supply — Grid',       'Power production / capita',   'power_per_capita_kwh',      v => Math.round(v).toLocaleString() + ' kWh/yr',  'asc'],
  ['Supply — Grid',       'Grid investment (annual)',    'grid_investment_usdbn',     v => '€' + Math.round(v / 1e6).toLocaleString() + 'M / yr', 'asc'],

  ['Supply — Fibre',      'Bandwidth (median)',          'bandwidth_gbps',            v => v.toFixed(2) + ' Gbps',                      'asc'],

  ['Differentiators',     'DC construction cost',        'construction_cost_usd_mw',  v => '$' + v.toFixed(1) + ' /W',                  'desc'],
  ['Differentiators',     'Power cost',                  'power_cost_usd_kwh',        v => '$' + v.toFixed(3) + ' / kWh',               'desc'],
  ['Differentiators',     'R&D techs / million',         'rd_techs_per_million',      v => Math.round(v).toLocaleString(),              'asc'],
  ['Differentiators',     'STEM graduate share',         'tertiary_grad_pct',         v => Math.round(v * 100) + '%',                   'asc'],
  ['Differentiators',     'Grid carbon intensity',       'carbon_intensity_gco2_kwh', v => Math.round(v) + ' gCO₂/kWh',                 'desc'],

  ['Market maturity',     'Live DC capacity',            'dc_capacity_live_mw',       v => Math.round(v).toLocaleString() + ' MW',      'neutral'],
  ['Market maturity',     'Planned DC capacity',         'dc_capacity_planned_mw',    v => Math.round(v).toLocaleString() + ' MW',      'neutral'],
];

// Cache of per-factor ranking: { factor_id → { iso2 → {rank, total} } }
// Computed once at load time; cheap O(N log N) per factor.
let FACTOR_RANKS = null;

function computeFactorRanks() {
  const ranks = {};
  for (const [, , fid, , dir] of PANEL_ROWS) {
    const withValue = state.markets
      .map(c => ({ iso2: c.iso2, v: c.factors && c.factors[fid] && c.factors[fid].value }))
      .filter(x => typeof x.v === 'number');
    if (withValue.length === 0) {
      ranks[fid] = {};
      continue;
    }
    const reverse = dir === 'desc';
    withValue.sort((a, b) => reverse ? a.v - b.v : b.v - a.v);
    const total = withValue.length;
    const r = {};
    let prevVal = null, prevRank = 0;
    withValue.forEach((entry, i) => {
      const rank = entry.v === prevVal ? prevRank : (i + 1);
      r[entry.iso2] = { rank, total };
      prevVal = entry.v;
      prevRank = rank;
    });
    ranks[fid] = r;
  }
  FACTOR_RANKS = ranks;
}

function rankChipHtml(fid, iso2, dir) {
  const r = FACTOR_RANKS && FACTOR_RANKS[fid] && FACTOR_RANKS[fid][iso2];
  if (!r) return '';
  // colour by quartile within the factor
  const pct = r.rank / r.total;
  let cls = 'rank-chip-low';
  if (pct <= 0.25) cls = 'rank-chip-top';
  else if (pct <= 0.5) cls = 'rank-chip-mid';
  const dirHint = dir === 'desc' ? ' (lower=better)' : dir === 'asc' ? '' : ' (by size)';
  return '<span class="rank-chip ' + cls + '" title="Rank ' + r.rank + ' of ' + r.total + dirHint + '">'
       + '#' + r.rank + '<span class="rank-chip-total"> / ' + r.total + '</span></span>';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function confidenceBadge(entry) {
  // VERIFIED  : primary-published figure(s) from named source(s). Includes
  //             API-fetched (Ember, World Bank, Eurostat) and PDF-cited
  //             (T&T DCCI, JLL Research, Ember/BCG reports).
  // INFERRED  : sub-regional mean of VERIFIED neighbours. Used where no
  //             per-country primary figure is published.
  // ESTIMATE  : curated from a named source but specific figure not
  //             programmatically confirmable from the linked page.
  const c = (entry && entry.confidence) || 'estimate';
  if (c === 'verified') {
    const sourceCount = (entry.sources && entry.sources.length) || 1;
    const rangeTxt = (entry.value_low != null && entry.value_high != null && entry.value_low !== entry.value_high)
      ? ' (range ' + entry.value_low + '–' + entry.value_high + ' across ' + sourceCount + ' sources)'
      : (sourceCount > 1 ? ' (' + sourceCount + ' converging sources)' : '');
    return '<span class="conf-badge conf-verified" title="VERIFIED — primary-published figure'
      + escapeHtml(rangeTxt)
      + (entry.evidence_url ? '\nEvidence: ' + entry.evidence_url : '')
      + '">VERIFIED</span>';
  }
  if (c === 'regional-inferred') {
    return '<span class="conf-badge conf-inferred" title="INFERRED — sub-regional mean of VERIFIED neighbouring countries. No per-country primary figure published. See source field for which peers were averaged.">INFERRED</span>';
  }
  return '<span class="conf-badge conf-estimate" title="ESTIMATE — curated from the named source. Underlying report is real but the specific figure cannot be programmatically confirmed from the linked page.">ESTIMATE</span>';
}

function renderMultiSources(entry) {
  if (!entry || !entry.sources || entry.sources.length < 2) return '';
  const rows = entry.sources.map(s => {
    const valStr = s.value != null ? s.value : '—';
    const link = s.url
      ? '<a href="' + escapeHtml(s.url) + '" target="_blank" rel="noopener">' + escapeHtml(s.name) + '</a>'
      : escapeHtml(s.name);
    return '<li><strong>' + valStr + '</strong> — ' + link + '</li>';
  }).join('');
  return '<details class="multi-sources"><summary>' + entry.sources.length + ' sources · range ' +
    (entry.value_low != null ? entry.value_low : '—') + '–' +
    (entry.value_high != null ? entry.value_high : '—') +
    '</summary><ul>' + rows + '</ul></details>';
}

function renderDetailRow(label, entry, fmt, fid, iso2, dir) {
  if (!entry || entry.value == null) {
    return '<div class="detail-row"><span class="detail-row-label">' + escapeHtml(label) + '</span>'
         + '<span class="detail-row-value nodata">— no data</span></div>';
  }
  const valStr = fmt(entry.value);
  const year   = entry.year ? ' <span style="color:var(--text-low);font-weight:400">(' + entry.year + ')</span>' : '';
  const srcLink = entry.url
    ? '<a href="' + escapeHtml(entry.url) + '" target="_blank" rel="noopener">' + escapeHtml(entry.source || 'source') + '</a>'
    : escapeHtml(entry.source || '');
  const note = entry.note ? ' — ' + escapeHtml(entry.note) : '';
  const chip = rankChipHtml(fid, iso2, dir);
  const badge = confidenceBadge(entry);
  const multiSrc = renderMultiSources(entry);
  return ''
    + '<div class="detail-row">'
    +   '<div class="detail-row-label">' + escapeHtml(label) + ' ' + badge
    +     '<div class="detail-row-source">' + srcLink + note + '</div>'
    +     multiSrc
    +   '</div>'
    +   '<div class="detail-row-value-block">'
    +     '<span class="detail-row-value">' + valStr + year + '</span>'
    +     chip
    +   '</div>'
    + '</div>';
}

function renderCapacityBar(factors) {
  const live    = (factors.dc_capacity_live_mw    || {}).value;
  const planned = (factors.dc_capacity_planned_mw || {}).value;
  if (typeof live !== 'number' && typeof planned !== 'number') return '';

  // Reference against the largest EMEA market so different countries' bars
  // are comparable side-by-side.
  let emeaMax = 0;
  for (const c of state.markets) {
    const l = (c.factors.dc_capacity_live_mw    || {}).value || 0;
    const p = (c.factors.dc_capacity_planned_mw || {}).value || 0;
    if (l + p > emeaMax) emeaMax = l + p;
  }
  if (emeaMax === 0) emeaMax = 1;
  const liveVal    = typeof live    === 'number' ? live    : 0;
  const plannedVal = typeof planned === 'number' ? planned : 0;
  const livePct    = (liveVal    / emeaMax) * 100;
  const plannedPct = (plannedVal / emeaMax) * 100;

  const liveTxt    = typeof live    === 'number' ? liveVal.toLocaleString()    + ' MW' : '—';
  const plannedTxt = typeof planned === 'number' ? plannedVal.toLocaleString() + ' MW' : '—';
  return ''
    + '<div class="capacity-bar-wrap">'
    +   '<div class="capacity-bar-figs">'
    +     '<div class="cap-fig"><span class="cap-fig-val">' + liveTxt + '</span><span class="cap-fig-lab"><span class="cap-dot cap-dot-live"></span>Live (operational)</span></div>'
    +     '<div class="cap-fig"><span class="cap-fig-val">' + plannedTxt + '</span><span class="cap-fig-lab"><span class="cap-dot cap-dot-planned"></span>Planned + under construction</span></div>'
    +   '</div>'
    +   '<div class="capacity-bar-track">'
    +     '<div class="capacity-bar-live"    style="width:' + livePct.toFixed(1)    + '%" title="Live: ' + liveVal + ' MW"></div>'
    +     '<div class="capacity-bar-planned" style="width:' + plannedPct.toFixed(1) + '%" title="Planned + under construction: ' + plannedVal + ' MW"></div>'
    +   '</div>'
    +   '<div class="capacity-bar-scale">Bar scaled vs EMEA’s largest market (' + Math.round(emeaMax).toLocaleString() + ' MW total)</div>'
    + '</div>';
}

// The 9 scored factors grouped into 5 plain-language buckets — the same
// framing the intro overlay uses. Order matches the intro.
const SUPPLY_BUCKETS = [
  { key: 'power',   label: 'Power & grid',   factors: ['grid_connect_years', 'power_per_capita_kwh', 'grid_investment_usdbn'] },
  { key: 'connect', label: 'Connectivity',   factors: ['bandwidth_gbps'] },
  { key: 'cost',    label: 'Cost',           factors: ['construction_cost_usd_mw', 'power_cost_usd_kwh'] },
  { key: 'talent',  label: 'Talent',         factors: ['rd_techs_per_million', 'tertiary_grad_pct'] },
  { key: 'sustain', label: 'Sustainability', factors: ['carbon_intensity_gco2_kwh'] },
];

// fid -> { label, fmt, dir } from PANEL_ROWS, for raw-value formatting.
const FACTOR_META = {};
PANEL_ROWS.forEach(([section, label, fid, fmt, dir]) => { FACTOR_META[fid] = { label, fmt, dir, section }; });

// Plain-language "why this matters" for each factor — surfaced on hover so a
// newcomer understands what each data point means for siting a data centre.
const FACTOR_WHY = {
  grid_connect_years:        'Time to secure a grid connection — today the #1 schedule risk for a new data centre. Shorter is better.',
  power_per_capita_kwh:      'Electricity generated per person — a proxy for a mature power system with capacity to spare for large new loads.',
  grid_investment_usdbn:     'Money committed to expanding the grid — signals future headroom for energy-hungry data centres.',
  bandwidth_gbps:            'Available fibre bandwidth — data centres need dense, high-capacity connectivity to carry traffic.',
  construction_cost_usd_mw:  'All-in build cost per watt of IT capacity ($/W) — lower means cheaper capex to put megawatts on the floor.',
  power_cost_usd_kwh:        'Industrial electricity price — the single largest ongoing running cost for a data centre. Lower is better.',
  rd_techs_per_million:      'Depth of the technical workforce — skilled people available to build and operate facilities.',
  tertiary_grad_pct:         'Share of graduates in engineering, manufacturing & construction — the local talent pipeline for the sector.',
  carbon_intensity_gco2_kwh: 'Carbon emitted per kWh — lower makes it far easier to meet sustainability targets and sign green PPAs.',
  demand_2027_twh:           'Total addressable broadband demand (exabytes), 2025 and projected 2030 — a proxy for the size of the market opportunity. Shown for context, not part of the score.',
};
function whyIcon(fid) {
  const why = FACTOR_WHY[fid];
  if (!why) return '';
  return ' <span class="sc-why" tabindex="0" role="button" aria-label="Why it matters: ' + escapeHtml(why)
    + '" data-why="' + escapeHtml(why) + '">i</span>';
}

// Custom tooltip for the "why it matters" markers (native title is unreliable
// and slow). Delegated, so it works after the panel re-renders.
let _whyTip = null;
function wireWhyTips() {
  _whyTip = document.createElement('div');
  _whyTip.className = 'why-tip hidden';
  document.body.appendChild(_whyTip);
  const show = (el) => {
    const txt = el.getAttribute('data-why');
    if (!txt) return;
    _whyTip.textContent = txt;
    _whyTip.classList.remove('hidden');
    const r = el.getBoundingClientRect();
    const w = _whyTip.offsetWidth, h = _whyTip.offsetHeight;
    let left = r.left + r.width / 2 - w / 2;
    left = Math.max(10, Math.min(window.innerWidth - w - 10, left));
    let top = r.top - h - 9;                 // above by default
    if (top < 8) top = r.bottom + 9;         // flip below if no room
    _whyTip.style.left = left + 'px';
    _whyTip.style.top = top + 'px';
  };
  const hide = () => { if (_whyTip) _whyTip.classList.add('hidden'); };
  document.addEventListener('mouseover', (e) => {
    const el = e.target.closest && e.target.closest('.sc-why');
    if (el) show(el);
  });
  document.addEventListener('mouseout', (e) => {
    if (e.target.closest && e.target.closest('.sc-why')) hide();
  });
  document.addEventListener('focusin', (e) => {
    if (e.target.closest && e.target.closest('.sc-why')) show(e.target.closest('.sc-why'));
  });
  document.addEventListener('focusout', hide);
  // Hide on scroll inside the panel so it doesn't float detached.
  document.addEventListener('scroll', hide, true);
}

function normColour(norm) {
  // Map a 0-100 score onto the shared map ramp (clay → deep green) so the
  // panel bar colour matches the market's colour on the map.
  const idx = Math.max(0, Math.min(COLOUR_RAMP.length - 1, Math.round((norm / 100) * (COLOUR_RAMP.length - 1))));
  return COLOUR_RAMP[idx];
}

// Market-perception verdicts grounded in 2026 industry commentary (JLL/CBRE/
// C&W EMEA updates, DCD, Data Center Knowledge). One sharp line per notable
// market; the long tail falls back to a score-band line. A separate dynamic
// line ties it to the user's current weighting.
const MARKET_VERDICTS = {
  DE: 'The backbone of European interconnection — but with Frankfurt now power-bound, Germany’s 2030 strategy is pushing the build-out to Berlin and the regions.',
  GB: 'Europe’s largest market — yet Slough and West London are power-starved, steering the next wave toward the UK regions.',
  NL: 'A mature FLAP-D core capped by Amsterdam’s construction moratorium to ~2035; growth is leaking beyond the metro.',
  FR: 'A stable FLAP-D anchor running on cheap, low-carbon nuclear power — though grid-connection queues keep lengthening.',
  IE: 'A hyperscale heavyweight frozen by Ireland’s de-facto grid-connection moratorium; operators are already scouting alternatives.',
  ES: 'The breakout challenger — a subsea gateway to Africa and the Middle East with hyperscaler-friendly policy and Europe’s fastest growth.',
  IT: 'Southern Europe’s fastest riser, now ranked alongside the FLAP-D core; grid lead times are the main brake.',
  SE: 'The Nordic heavyweight — abundant near-zero-carbon power and a deep pipeline; distance from the demand core is the trade-off.',
  NO: '100% hydro power and land to spare — already landing AI-training clusters like OpenAI’s Stargate; remote from the core.',
  FI: 'The Nordics’ fastest-growing node — repeat hyperscale bets (Hamina, TikTok) on cheap green power and free cooling.',
  DK: 'Clean Nordic power and strong connectivity anchoring hyperscale cloud regions; grid headroom is the watch-point.',
  IS: 'Near-100% renewable geothermal and hydro with natural cooling — a pure sustainability play, isolated by subsea latency.',
  PL: 'CEE’s leader and the region’s sovereign-cloud hub, relieving Frankfurt — held back by a coal-heavy grid.',
  AT: 'A rising CEE alternative pulling hyperscalers toward Vienna as the German core fills up.',
  PT: 'An Atlantic subsea gateway (Sines) with green power — the emerging Iberian alternative to Madrid.',
  BE: 'A well-connected near-core market in Amsterdam’s and Paris’s shadow; grid access is the binding constraint.',
  CH: 'A premium, low-carbon, sovereignty-friendly market — and one of the most expensive places in Europe to build.',
  CZ: 'A stable CEE alternative winning hyperscale attention as the German core saturates.',
  RO: 'An emerging Black Sea connectivity hub — early-stage, but improving fast.',
  HU: 'A CEE contender drawing cloud investment, with grid readiness and carbon the watch-points.',
  GR: 'An emerging Eastern-Med crossroads where new subsea cables are landing — early in its build-out.',
  TR: 'A fast-growing bridge between Europe and Asia on low-cost power — with a longer grid and risk story.',
  AE: 'The Gulf’s AI magnet — gigawatt Stargate ambitions, cheap power and state backing — at the cost of a carbon-heavy grid.',
  SA: 'Vision 2030 firepower and the cheapest power in EMEA fuelling gigawatt AI plans; grid carbon is the catch.',
  QA: 'Cheap power and deep sovereign funding — a small but fast-moving Gulf market.',
  IL: 'A deep-tech talent hub with strong cloud demand, constrained by scale and grid headroom.',
  EG: 'A subsea-cable nexus linking Europe, Africa and Asia — strategic geography, nascent capacity.',
  MA: 'North Africa’s Atlantic subsea gateway, positioning as a regional hub from a low base.',
  LU: 'A connectivity- and sovereignty-rich micro-market; land and scale cap its ceiling.',
};
function narrativeVerdict(iso2, score) {
  if (MARKET_VERDICTS[iso2]) return MARKET_VERDICTS[iso2];
  if (score >= 68) return 'A top-tier market on the factors that decide a build.';
  if (score >= 50) return 'A credible mid-pack market for the right strategy.';
  return 'An emerging market — early in its build-out, with clear gaps to close.';
}
function dynamicVerdict(bucketScores) {
  const present = bucketScores.filter(b => b.score != null);
  if (present.length < 2) return '';
  const top = present.reduce((a, b) => b.score > a.score ? b : a);
  const bot = present.reduce((a, b) => b.score < a.score ? b : a);
  if (top.key === bot.key) return '';
  return 'At your weighting: strongest on <strong>' + top.label.toLowerCase()
       + '</strong>, held back by <strong>' + bot.label.toLowerCase() + '</strong>.';
}

// The score scorecard: raw value -> 0-100 score -> x weight -> contribution,
// grouped by the 5 plain buckets. This is the "how the score is built" view.
function renderScorecard(country, comp) {
  const contrib = comp.contrib || {};
  const factors = country.factors || {};
  // max weighted contribution across shown factors, for the contribution bars
  const allWeighted = Object.values(contrib).map(c => c.weightedContribution || 0);
  const maxWeighted = allWeighted.length ? Math.max(...allWeighted, 0.0001) : 1;

  const bucketScores = [];
  let bucketsHtml = '';

  for (const bucket of SUPPLY_BUCKETS) {
    const present = bucket.factors.filter(fid => contrib[fid]);
    if (!present.length) continue;
    const avg = present.reduce((s, fid) => s + contrib[fid].norm, 0) / present.length;
    bucketScores.push({ key: bucket.key, label: bucket.label, score: avg });

    let rowsHtml = '';
    for (const fid of bucket.factors) {
      const c = contrib[fid];
      const meta = FACTOR_META[fid] || { label: fid, fmt: v => String(v), dir: 'asc' };
      if (!c) {
        rowsHtml += '<div class="sc-row sc-row--nodata">'
          + '<div class="sc-row-head"><span class="sc-factor">' + escapeHtml(meta.label) + whyIcon(fid) + '</span></div>'
          + '<div class="sc-row-meter"><span class="sc-raw">— no data</span></div></div>';
        continue;
      }
      const rawEntry = factors[fid];
      const rawStr = (!c.imputed && rawEntry && rawEntry.value != null) ? escapeHtml(meta.fmt(rawEntry.value)) : '—';
      const norm = Math.round(c.norm);
      const off  = c.weight === 0 ? ' sc-row--off' : '';
      const chip = rankChipHtml(fid, country.iso2, meta.dir);
      rowsHtml += '<div class="sc-row' + off + '">'
        + '<div class="sc-row-head"><span class="sc-factor">' + escapeHtml(meta.label) + whyIcon(fid) + '</span>' + chip + '</div>'
        + '<div class="sc-row-meter">'
        +   '<span class="sc-raw" title="Raw value">' + rawStr + '</span>'
        +   '<span class="sc-bar" title="Score 0–100 vs EMEA"><i style="width:' + norm + '%;background:' + normColour(c.norm) + '"></i></span>'
        +   '<b class="sc-score">' + norm + '</b>'
        +   '<span class="sc-weight" title="Weight in the composite">×' + c.weight + '</span>'
        + '</div>'
        + '</div>';
    }

    bucketsHtml += '<div class="sc-bucket">'
      + '<div class="sc-bucket-head"><span class="sc-bucket-name">' + escapeHtml(bucket.label) + '</span>'
      + '<span class="sc-bucket-score" title="Average score for this group">' + Math.round(avg) + '</span></div>'
      + rowsHtml + '</div>';
  }

  // ── Readiness block: verdict + live read + headline gauge ──
  let readiness = '';
  readiness += '<p class="detail-verdict">' + narrativeVerdict(country.iso2, comp.score) + '</p>';
  const dyn = dynamicVerdict(bucketScores);
  if (dyn) readiness += '<p class="detail-verdict-dyn">' + dyn + '</p>';
  readiness += '<div class="readiness">'
    + '<div class="readiness-top"><span class="readiness-label">Supply-side readiness</span>'
    + '<span class="readiness-score">' + Math.round(comp.score) + '<small>/100</small></span></div>'
    + '<div class="readiness-bar"><div class="readiness-fill" style="width:' + Math.round(comp.score) + '%"></div></div>'
    + '<div class="readiness-sub">Rank ' + comp.rank + ' of ' + comp.total + ' EMEA markets</div>'
    + '</div>';

  // ── Build-up: how the score is built ──
  let build = '<div class="scorecard">'
    + '<div class="scorecard-head">How this score is built</div>'
    + '<div class="scorecard-legend">Each factor’s <b>raw value</b> is scored <b>0–100</b> — where <b>100</b> = the best of all 45 markets and <b>0</b> = the worst — then multiplied by <b>the weight you set in the left panel</b> to build the composite. The <b>#</b> chip is the market’s rank on that factor.</div>'
    + bucketsHtml
    + '<div class="sc-total">Weighted average of the bars above = <b>' + Math.round(comp.score) + ' / 100</b></div>';
  const missCount = (comp.missing || []).length;
  if (missCount) {
    build += '<div class="sc-foot-note">' + missCount + ' factor' + (missCount === 1 ? '' : 's') + ' excluded (no data)</div>';
  }
  build += '</div>';
  return { readiness, build };
}

// Data-centre facilities indexed by ISO-2 once loaded:
//   PROJECTS_BY_ISO   — flagship/hyperscale (operator + MW + status)
//   FACILITIES_BY_ISO — full PeeringDB carrier-neutral facility list (the count)
let PROJECTS_BY_ISO = null;
let FACILITIES_BY_ISO = null;
function indexByCountry(gj) {
  const out = {};
  (gj.features || []).forEach(f => {
    const p = f.properties || {};
    if (!p.country) return;
    (out[p.country] = out[p.country] || []).push(p);
  });
  return out;
}
function refreshOpenPanel() {
  const panel = document.getElementById('detail-panel');
  if (state.selectedIso && panel && !panel.classList.contains('hidden')) {
    const c = state.markets.find(x => x.iso2 === state.selectedIso);
    if (c) openDetailPanel(c);
  }
}
function loadProjects() {
  fetch('data/overlay_hyperscale.geojson').then(r => r.json())
    .then(gj => { PROJECTS_BY_ISO = indexByCountry(gj); refreshOpenPanel(); })
    .catch(() => {});
  fetch('data/overlay_dc_sites.geojson').then(r => r.json())
    .then(gj => { FACILITIES_BY_ISO = indexByCountry(gj); refreshOpenPanel(); })
    .catch(() => {});
}

function renderProjects(iso2) {
  const hs  = (PROJECTS_BY_ISO && PROJECTS_BY_ISO[iso2]) || [];
  const fac = (FACILITIES_BY_ISO && FACILITIES_BY_ISO[iso2]) || [];
  const total = fac.length || hs.length;
  if (!total) return '';

  const cap = 10;
  const seen = new Set();
  const rowFor = (name, sub, status, mw, url) => {
    const uc = status === 'under_construction';
    const mwHtml = mw != null ? '<span class="pj-mw">' + mw + ' MW</span>' : '';
    const link = url ? ' <a class="pj-link" href="' + escapeHtml(url) + '" target="_blank" rel="noopener" title="Facility page">↗</a>' : '';
    const subHtml = sub ? '<div class="pj-sub">' + escapeHtml(sub) + '</div>' : '';
    return '<div class="pj-row"><span class="pj-dot ' + (uc ? 'pj-uc' : 'pj-op') + '" title="' + (uc ? 'Under construction' : 'Operational') + '"></span>'
      + '<div class="pj-main"><div class="pj-name">' + escapeHtml(name) + link + '</div>' + subHtml + '</div>'
      + mwHtml + '</div>';
  };

  let rows = '';
  // Flagship / hyperscale first (they carry MW + operator), biggest first.
  hs.slice().sort((a, b) => (b.mw || 0) - (a.mw || 0)).forEach(p => {
    if (rows.split('pj-row').length - 1 >= cap) return;
    const name = p.operator || p.name || 'Data centre';
    seen.add((p.name || name).toLowerCase());
    const sub = [(p.operator && p.name) ? p.name : null, p.city].filter(Boolean).join(' · ');
    rows += rowFor(name, sub, p.status, p.mw, p.url);
  });
  // Then fill from the broader PeeringDB facility list.
  for (const p of fac) {
    if (rows.split('pj-row').length - 1 >= cap) break;
    if (p.name && seen.has(p.name.toLowerCase())) continue;
    rows += rowFor(p.name || 'Facility', p.city || '', p.status, null, p.url);
  }

  const hsN = hs.length;
  const tag = total.toLocaleString() + ' facilities' + (hsN ? ' · ' + hsN + ' flagship' : '');
  const shownCount = rows.split('pj-row').length - 1;
  const more = total > shownCount ? '<div class="pj-more">+ ' + (total - shownCount).toLocaleString() + ' more in this market</div>' : '';
  return '<div class="detail-projects">'
    + '<div class="detail-section-title">Data centres here <span class="section-tag section-tag--neutral">' + tag + '</span></div>'
    + '<div class="pj-list">' + rows + more + '</div>'
    + '<div class="pj-foot">Carrier-neutral facilities (PeeringDB) enriched with flagship/hyperscale campuses (operator &amp; MW). Indicative, not exhaustive.</div>'
    + '</div>';
}

// High-level cost & emissions estimate for the selected market at the chosen
// size + PUE. Power cost ($/kWh) and carbon (gCO2/kWh) are solid absolute
// figures; build cost is per-geography but its $/W basis is under review, so
// it's clearly flagged as provisional.
function fmtMoney(v) {
  if (v == null || isNaN(v)) return '—';
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'bn';
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M';
  return '$' + Math.round(v).toLocaleString();
}
function estRow(label, value, sub, cls) {
  return '<div class="est-row ' + (cls || '') + '">'
    + '<div class="est-label">' + label + '<div class="est-sub">' + escapeHtml(sub) + '</div></div>'
    + '<div class="est-val">' + value + '</div></div>';
}
function renderEstimate(country) {
  const f = country.factors || {};
  const pc = f.power_cost_usd_kwh ? f.power_cost_usd_kwh.value : null;          // $/kWh
  const ci = f.carbon_intensity_gco2_kwh ? f.carbon_intensity_gco2_kwh.value : null; // gCO2/kWh
  const cw = f.construction_cost_usd_mw ? f.construction_cost_usd_mw.value : null;    // $/W (provisional)
  const mw = state.modelMw, pue = state.modelPue;
  const energyKwh = mw * pue * 8760 * 1000;       // annual facility energy (kWh), nameplate

  const powerCost = pc != null ? energyKwh * pc : null;       // $/yr
  const emis      = ci != null ? energyKwh * ci / 1e6 : null;  // tCO2/yr
  const capex     = cw != null ? cw * mw * 1e6 : null;         // $/W × W (provisional)

  const rows =
      estRow('Build cost', fmtMoney(capex),
        cw != null ? '@ $' + cw.toFixed(1) + '/W (all-in, T&T 2025-26)' : 'no construction-cost data', '')
    + estRow('Annual power cost', powerCost != null ? fmtMoney(powerCost) + '/yr' : '—',
        pc != null ? '@ $' + pc.toFixed(3) + '/kWh' : 'no power-price data', '')
    + estRow('Annual grid emissions', emis != null ? Math.round(emis).toLocaleString() + ' tCO₂/yr' : '—',
        ci != null ? '@ ' + Math.round(ci) + ' gCO₂/kWh' : 'no carbon data', '');

  return '<div class="estimate">'
    + '<div class="detail-section-title">Cost &amp; emissions estimate'
    +   ' <span class="est-scenario">' + mw + ' MW · PUE ' + pue.toFixed(1) + '</span></div>'
    + '<div class="est-rows">' + rows + '</div>'
    + '<div class="est-foot">≈ ' + Math.round(energyKwh / 1e6).toLocaleString() + ' MWh/yr at ' + mw + ' MW × PUE ' + pue.toFixed(1) + ' (8,760 h, nameplate). Adjust size &amp; PUE in the sidebar. High-level indicative figures.</div>'
    + '</div>';
}

function openDetailPanel(country) {
  const panel   = document.getElementById('detail-panel');
  const content = document.getElementById('detail-content');
  if (!panel || !content) return;

  const a = currentAnchorFor(country);
  const factors = country.factors || {};
  const comp = state.weightsActive ? state.composite[country.iso2] : null;
  const hasScore = comp && comp.score != null;

  // ── Header: rank eyebrow + serif name + region ──
  let html = '<div class="detail-head">';
  if (hasScore) {
    html += '<div class="detail-rank-eyebrow">N°' + comp.rank
          + '<span class="detail-rank-of"> of ' + comp.total + '</span></div>';
  }
  html += '<h2 class="detail-title">' + country.flag + ' ' + escapeHtml(country.name) + '</h2>'
        + '<div class="detail-region">' + escapeHtml(country.region) + ' · ' + escapeHtml(a.name) + '</div>'
        + '</div>';

  // ── Verdict + readiness gauge, then cost & emissions front-and-centre,
  //    then the score build-up. ──
  let buildHtml = '';
  if (state.weightsActive) {
    if (hasScore) {
      const sc = renderScorecard(country, comp);
      html += sc.readiness;
      buildHtml = sc.build;
    } else {
      html += '<p class="detail-verdict">Scoring is turned off (all weights are zero), or this market has no data for any weighted factor.</p>';
    }
  }

  // ── High-level cost & emissions estimate (uses the sidebar size/PUE) ──
  html += renderEstimate(country);

  // ── How the score is built (after the headline + economics) ──
  html += buildHtml;

  // ── Demand-side context (explicitly not part of the score) ──
  html += '<div class="detail-context">'
        + '<div class="detail-section-title">Demand outlook' + whyIcon('demand_2027_twh') + ' <span class="section-tag">not scored</span></div>';
  html += demandBlockHtml(country, 'panel');
  html += renderCapacityBar(factors);
  html += '</div>';

  // ── Live & under-construction data centres in this market ──
  html += renderProjects(country.iso2);

  // ── Full data + sources, tucked away to keep the panel calm ──
  let rowsHtml = '';
  let currentSection = null;
  for (const [section, label, factorId, fmt, dir] of PANEL_ROWS) {
    if (factorId === 'demand_2027_twh') continue; // shown above as context
    if (section !== currentSection) {
      rowsHtml += '<div class="detail-section-title detail-section-title--sub">' + escapeHtml(section) + '</div>';
      currentSection = section;
    }
    rowsHtml += renderDetailRow(label, factors[factorId], fmt, factorId, country.iso2, dir);
  }
  html += '<details class="detail-sources"><summary>All data, sources &amp; confidence</summary>'
        + '<div class="detail-sources-body">' + rowsHtml + '</div></details>';

  // ── CTA — book an EMEA insights call (contextual to this market) ──
  html += '<a class="cta-block" href="' + BOOKING_URL + '" target="_blank" rel="noopener">'
        + '<div class="cta-text"><div class="cta-title">Go deeper on ' + escapeHtml(country.name) + '?</div>'
        + '<div class="cta-sub">Book a call for tailored EMEA market &amp; site insights.</div></div>'
        + '<span class="cta-arrow">→</span></a>';

  content.innerHTML = html;
  panel.classList.remove('hidden');
}

/* ──────────────────────────────────────────────────────────────────
   5. UI wiring (Feature 1 minimum)
   ────────────────────────────────────────────────────────────────── */

function wireDetailPanelClose() {
  const closeBtn = document.getElementById('detail-close');
  const panel    = document.getElementById('detail-panel');

  // Cost-estimator size/PUE toggles — delegated on the persistent content
  // container so they survive panel re-renders.
  const content = document.getElementById('detail-content');
  if (content) {
    content.addEventListener('click', (e) => {
      const mwBtn  = e.target.closest('[data-est-mw]');
      const pueBtn = e.target.closest('[data-est-pue]');
      if (mwBtn)       state.modelMw = +mwBtn.dataset.estMw;
      else if (pueBtn) state.modelPue = +pueBtn.dataset.estPue;
      else return;
      if (state.selectedIso) {
        const c = state.markets.find(x => x.iso2 === state.selectedIso);
        if (c) openDetailPanel(c);
      }
    });
  }

  if (closeBtn && panel) {
    closeBtn.addEventListener('click', () => {
      panel.classList.add('hidden');
      state.selectedIso = null;
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.classList.contains('hidden')) {
      panel.classList.add('hidden');
      state.selectedIso = null;
    }
  });
}

/* ──────────────────────────────────────────────────────────────────
   5. Boot
   ────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  wireDetailPanelClose();
  wireSourcesModal();
  wireIntroOverlay();
  wireTour();
  wireWhyTips();
  wireModelControls();
  wireMobileTabs();
  loadProjects();
  initMap();
});

// Sidebar "model a data centre" scenario controls — feed the cost/emissions
// estimate in the detail panel.
function wireModelControls() {
  ['model-size-toggle', 'model-pue-toggle'].forEach(id => {
    const g = document.getElementById(id);
    if (!g) return;
    g.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.estMw != null)       state.modelMw = +b.dataset.estMw;
      else if (b.dataset.estPue != null) state.modelPue = +b.dataset.estPue;
      else return;
      g.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
      if (state.selectedIso) {
        const c = state.markets.find(x => x.iso2 === state.selectedIso);
        if (c) openDetailPanel(c);
      }
      // Keep the compare drawer's economics rows in sync with the scenario.
      const drawer = document.getElementById('compare-drawer');
      if (drawer && !drawer.classList.contains('hidden')) renderCompareDrawer();
    });
  });
}

function wireIntroOverlay() {
  const overlay = document.getElementById('intro-overlay');
  if (!overlay) return;
  const SEEN_KEY = 'dcmc_intro_seen_v1';
  const dontShow = document.getElementById('intro-dontshow');
  const show = () => { overlay.classList.remove('hidden'); overlay.setAttribute('aria-hidden', 'false'); };
  const hide = () => {
    overlay.classList.add('hidden');
    overlay.setAttribute('aria-hidden', 'true');
    if (dontShow && dontShow.checked) {
      try { localStorage.setItem(SEEN_KEY, '1'); } catch (e) {}
    }
  };
  // First-run: show unless the user has dismissed it permanently.
  let seen = false;
  try { seen = localStorage.getItem(SEEN_KEY) === '1'; } catch (e) {}
  if (!seen) show();

  const closeEl = document.getElementById('intro-close');
  if (closeEl) closeEl.addEventListener('click', hide);
  const goEl = document.getElementById('intro-go');
  if (goEl) goEl.addEventListener('click', () => {
    hide();
    // First-time visitors get the guided tour right after the intro.
    let tourDone = false;
    try { tourDone = localStorage.getItem('dcmc_tour_done_v1') === '1'; } catch (e) {}
    if (!tourDone) setTimeout(startTour, 380);
  });
  const back = overlay.querySelector('.intro-backdrop');
  if (back) back.addEventListener('click', hide);
  const methodBtn = document.getElementById('method-btn');
  if (methodBtn) methodBtn.addEventListener('click', show);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !overlay.classList.contains('hidden')) hide();
  });
}

/* ── Market hover summary (rankings rows + map markers) ───────────── */

function bucketScoresFor(iso2) {
  const comp = state.composite[iso2];
  if (!comp || !comp.contrib) return [];
  const out = [];
  for (const b of SUPPLY_BUCKETS) {
    const present = b.factors.filter(f => comp.contrib[f]);
    if (!present.length) continue;
    const avg = present.reduce((s, f) => s + comp.contrib[f].norm, 0) / present.length;
    out.push({ key: b.key, label: b.label, score: avg });
  }
  return out;
}

// Market-demand block: a two-bar chart (2025 vs 2030 addressable broadband
// demand, in EB) with a growth callout. Real units, easy to read.
function demandBlockHtml(country, variant) {
  const e = country.factors && country.factors.demand_2027_twh;
  if (!e || e.value == null) return '';
  const now = e.value_2025, future = e.value;
  const cls = variant === 'panel' ? 'dm dm--panel' : 'dm';
  const peak = Math.max(future, now != null ? now : 0) || 1;
  const fmtEB = v => Math.round(v).toLocaleString() + ' EB';

  let callout = '';
  if (now != null && now > 0) {
    const pct = Math.round((future / now - 1) * 100);
    callout = '<span class="dm-growth">+' + pct.toLocaleString() + '% to 2030</span>';
  }
  let bars = '';
  if (now != null) {
    bars += '<div class="dm-bar-row"><span class="dm-bar-yr">2025</span>'
      + '<span class="dm-bar-track"><i class="dm-bar-fill dm-bar-now" style="width:' + (now / peak * 100).toFixed(1) + '%"></i></span>'
      + '<span class="dm-bar-val">' + fmtEB(now) + '</span></div>';
  }
  bars += '<div class="dm-bar-row"><span class="dm-bar-yr">2030</span>'
    + '<span class="dm-bar-track"><i class="dm-bar-fill dm-bar-future" style="width:' + (future / peak * 100).toFixed(1) + '%"></i></span>'
    + '<span class="dm-bar-val">' + fmtEB(future) + '</span></div>';

  return '<div class="' + cls + '">'
    + '<div class="dm-top"><span class="dm-label">Addressable demand <span class="dm-unit-tag">EB</span></span>' + callout + '</div>'
    + '<div class="dm-bars">' + bars + '</div>'
    + '</div>';
}

// Compact DC-capacity bars (Live vs Planned+UC, MW) for the hover card —
// same visual language as the demand chart.
function capacityBlockHtml(country) {
  const f = country.factors || {};
  const live    = (f.dc_capacity_live_mw    || {}).value;
  const planned = (f.dc_capacity_planned_mw || {}).value;
  if (typeof live !== 'number' && typeof planned !== 'number') return '';
  const liveVal = typeof live === 'number' ? live : 0;
  const planVal = typeof planned === 'number' ? planned : 0;
  const peak = Math.max(liveVal, planVal) || 1;
  const fmtMW = v => Math.round(v).toLocaleString() + ' MW';
  const total = liveVal + planVal;
  const row = (lab, val, fillCls) =>
    '<div class="dm-bar-row"><span class="dm-bar-yr dm-bar-yr--cap">' + lab + '</span>'
    + '<span class="dm-bar-track"><i class="dm-bar-fill ' + fillCls + '" style="width:' + (val / peak * 100).toFixed(1) + '%"></i></span>'
    + '<span class="dm-bar-val">' + fmtMW(val) + '</span></div>';
  return '<div class="dm dm--cap">'
    + '<div class="dm-top"><span class="dm-label">DC capacity <span class="dm-unit-tag dm-unit-tag--mw">MW</span></span>'
    +   '<span class="dm-growth dm-growth--neutral">' + fmtMW(total) + ' total</span></div>'
    + '<div class="dm-bars">'
    +   row('Live', liveVal, 'cap-fill-live')
    +   row('Plan', planVal, 'cap-fill-planned')
    + '</div></div>';
}

function marketHoverHtml(country) {
  const comp = state.composite[country.iso2];
  const name = escapeHtml(country.name);
  if (!comp || comp.score == null) {
    return '<div class="mh"><div class="mh-top"><span class="mh-flag">' + country.flag
      + '</span><span class="mh-name">' + name + '</span></div>'
      + '<div class="mh-sub">No composite score at the current weights</div></div>';
  }
  const score = Math.round(comp.score);
  const bs = bucketScoresFor(country.iso2);
  let tags = '';
  if (bs.length >= 2) {
    const top = bs.reduce((a, b) => b.score > a.score ? b : a);
    const bot = bs.reduce((a, b) => b.score < a.score ? b : a);
    tags = '<div class="mh-tags"><span class="mh-up">▲ ' + escapeHtml(top.label)
         + '</span><span class="mh-down">▼ ' + escapeHtml(bot.label) + '</span></div>';
  }
  return '<div class="mh">'
    + '<div class="mh-top"><span class="mh-flag">' + country.flag + '</span>'
    +   '<span class="mh-name">' + name + '</span>'
    +   '<span class="mh-rank">N°' + comp.rank + '</span></div>'
    + '<div class="mh-score"><b style="color:' + normColour(score) + '">' + score
    +   '</b><small>/100 readiness · rank ' + comp.rank + ' of ' + comp.total + '</small></div>'
    + '<div class="mh-bar"><i style="width:' + score + '%;background:' + normColour(score) + '"></i></div>'
    + demandBlockHtml(country, 'hover')
    + capacityBlockHtml(country)
    + tags
    + '<div class="mh-hint">Click for the full breakdown</div>'
    + '</div>';
}

let _hoverCard = null;
function ensureHoverCard() {
  if (!_hoverCard) {
    _hoverCard = document.createElement('div');
    _hoverCard.className = 'market-hovercard hidden';
    document.body.appendChild(_hoverCard);
  }
  return _hoverCard;
}
function showHoverCardFor(country, x, y) {
  const el = ensureHoverCard();
  el.innerHTML = marketHoverHtml(country);
  el.classList.remove('hidden');
  moveHoverCard(x, y);
}
function moveHoverCard(x, y) {
  if (!_hoverCard) return;
  const pad = 16;
  const w = _hoverCard.offsetWidth || 240;
  const h = _hoverCard.offsetHeight || 120;
  let nx = x - w - pad;                 // prefer left of cursor (rows are on the right edge)
  if (nx < 8) nx = x + pad;
  let ny = Math.max(8, Math.min(window.innerHeight - h - 8, y - h / 2));
  _hoverCard.style.left = nx + 'px';
  _hoverCard.style.top = ny + 'px';
}
function hideHoverCard() { if (_hoverCard) _hoverCard.classList.add('hidden'); }

/* ── Guided tour (first run + "Take a tour") ──────────────────────── */

const TOUR_STEPS = [
  { sel: '.value-prop',         title: 'What this tool does',      body: 'It ranks 45 EMEA markets by how ready they are to host data centres — today’s leaders and the next wave of build-out.', place: 'right' },
  { sel: '#ranking-panel',      title: 'The leaderboard',          body: 'Markets ranked best → worst by the composite score. Hover any row for a quick summary; click for the full breakdown.', place: 'left' },
  { sel: '.model-controls',     title: 'Model a data centre',      body: 'Set a facility size (MW) and efficiency (PUE). Every market’s detail panel then estimates its build cost, annual power cost and CO₂ at that scenario — so you can compare the economics like-for-like.', place: 'right' },
  { sel: '.weights-panel',      title: 'Tune it to your strategy', body: 'Drag the weights, or pick a preset (Power, Cost, Sustain…). The ranking and map re-sort instantly.', place: 'right' },
  { sel: '.map-colour-control', title: 'Recolour the map',         body: 'Colour the markets by the composite score or any single factor to see patterns geographically.', place: 'bottom' },
];
let _tourIdx = 0, _tourEls = null, _tourTarget = null;

function ensureTourEls() {
  if (_tourEls) return _tourEls;
  const backdrop = document.createElement('div');
  backdrop.className = 'tour-backdrop hidden';
  const pop = document.createElement('div');
  pop.className = 'tour-pop hidden';
  pop.innerHTML =
      '<div class="tour-step-num"></div>'
    + '<div class="tour-title"></div>'
    + '<div class="tour-body"></div>'
    + '<div class="tour-foot">'
    +   '<button class="tour-skip" type="button">Skip</button>'
    +   '<div class="tour-nav"><button class="tour-back" type="button">Back</button>'
    +   '<button class="tour-next" type="button">Next</button></div>'
    + '</div>';
  document.body.appendChild(backdrop);
  document.body.appendChild(pop);
  backdrop.addEventListener('click', () => endTour(true));
  pop.querySelector('.tour-skip').addEventListener('click', () => endTour(true));
  pop.querySelector('.tour-back').addEventListener('click', () => { if (_tourIdx > 0) { _tourIdx--; showTourStep(); } });
  pop.querySelector('.tour-next').addEventListener('click', () => {
    if (_tourIdx < TOUR_STEPS.length - 1) { _tourIdx++; showTourStep(); } else endTour(true);
  });
  _tourEls = { backdrop, pop };
  return _tourEls;
}
function clearTourHighlight() {
  if (_tourTarget) { _tourTarget.classList.remove('tour-highlight'); _tourTarget = null; }
}
function showTourStep() {
  const { backdrop, pop } = ensureTourEls();
  const step = TOUR_STEPS[_tourIdx];
  const target = document.querySelector(step.sel);
  clearTourHighlight();
  backdrop.classList.remove('hidden');
  pop.classList.remove('hidden');
  pop.querySelector('.tour-step-num').textContent = 'Step ' + (_tourIdx + 1) + ' of ' + TOUR_STEPS.length;
  pop.querySelector('.tour-title').textContent = step.title;
  pop.querySelector('.tour-body').textContent = step.body;
  pop.querySelector('.tour-back').style.visibility = _tourIdx === 0 ? 'hidden' : 'visible';
  pop.querySelector('.tour-next').textContent = _tourIdx === TOUR_STEPS.length - 1 ? 'Done' : 'Next';

  if (!target) return;
  _tourTarget = target;
  target.classList.add('tour-highlight');
  // Position the pop near the target, clamped to the viewport.
  const r = target.getBoundingClientRect();
  const pw = pop.offsetWidth || 280, ph = pop.offsetHeight || 140, gap = 14;
  let left, top;
  if (step.place === 'right')      { left = r.right + gap; top = r.top; }
  else if (step.place === 'left')  { left = r.left - pw - gap; top = r.top + 20; }
  else if (step.place === 'bottom'){ left = r.left; top = r.bottom + gap; }
  else                             { left = r.left; top = r.top - ph - gap; }
  left = Math.max(10, Math.min(window.innerWidth - pw - 10, left));
  top  = Math.max(10, Math.min(window.innerHeight - ph - 10, top));
  pop.style.left = left + 'px';
  pop.style.top = top + 'px';
}
function startTour() {
  _tourIdx = 0;
  ensureTourEls();
  showTourStep();
}
function endTour(markDone) {
  clearTourHighlight();
  if (_tourEls) { _tourEls.backdrop.classList.add('hidden'); _tourEls.pop.classList.add('hidden'); }
  if (markDone) { try { localStorage.setItem('dcmc_tour_done_v1', '1'); } catch (e) {} }
}
function wireTour() {
  const btn = document.getElementById('tour-btn');
  if (btn) btn.addEventListener('click', startTour);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _tourEls && !_tourEls.pop.classList.contains('hidden')) endTour(true);
  });
  window.addEventListener('resize', () => {
    if (_tourEls && !_tourEls.pop.classList.contains('hidden')) showTourStep();
  });
}

function wireMobileTabs() {
  const bar = document.getElementById('mobile-tabs');
  if (!bar) return;
  bar.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-mobile-tab]');
    if (!btn) return;
    const tab = btn.dataset.mobileTab;
    document.body.classList.remove('mobile-tab-map', 'mobile-tab-rank', 'mobile-tab-settings');
    document.body.classList.add('mobile-tab-' + tab);
    bar.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.mobileTab === tab));
    // Mapbox needs a resize call after its container size changes.
    if (state.map) setTimeout(() => state.map.resize(), 50);
  });
}

function wireSourcesModal() {
  const btn   = document.getElementById('sources-btn');
  const modal = document.getElementById('sources-modal');
  const close = document.getElementById('sources-close');
  const back  = modal && modal.querySelector('.sources-modal-backdrop');
  if (!btn || !modal) return;
  const open  = () => modal.classList.remove('hidden');
  const hide  = () => modal.classList.add('hidden');
  btn.addEventListener('click', open);
  if (close) close.addEventListener('click', hide);
  if (back) back.addEventListener('click', hide);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) hide();
  });
}
