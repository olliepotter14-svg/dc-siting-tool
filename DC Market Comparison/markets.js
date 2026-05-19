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
const MAP_STYLE   = 'mapbox://styles/mapbox/dark-v11';

const FACTOR_COUNT = 13;            // 11 numeric + live MW + planned MW

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
  weights:           {},          // factor_id → 0..10  (F24)
  weightsActive:     true,        // toggle composite scoring globally
  composite:         {},          // iso2 → { score, rank, contributing, missing }  (F24)
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

/* ──────────────────────────────────────────────────────────────────
   4. Countries — load, render markers, render sidebar list (F2)
   ────────────────────────────────────────────────────────────────── */

const REGION_ORDER = [
  'Western Europe',
  'Northern Europe',
  'Southern Europe',
  'Central & Eastern Europe',
  'Middle East',
  'Africa',
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
  grid: {
    file: 'data/overlay_grid.geojson',
    sourceId: 'overlay-grid-src',
    interactive: false,
    layers: [{
      id: 'overlay-grid',
      type: 'line',
      paint: {
        'line-color':   '#FFB300',
        'line-width':   1.0,
        'line-opacity': 0.55,
      },
    }],
  },
  dcs: {
    file: 'data/overlay_dc_sites.geojson',
    sourceId: 'overlay-dcs-src',
    interactive: true,
    popup: (props) => {
      return ''
        + '<div class="popup-tag tag-dc">Data centre · ' + escapeHtml(props.status || 'operational') + '</div>'
        + '<div class="popup-name">' + escapeHtml(props.name || 'Unnamed facility') + '</div>'
        + '<div class="popup-region">' + escapeHtml(props.city || '') + (props.country ? ' · ' + escapeHtml(props.country) : '') + '</div>'
        + (props.url ? '<a class="popup-link" href="' + escapeHtml(props.url) + '" target="_blank" rel="noopener">View on PeeringDB ↗</a>' : '');
    },
    layers: [{
      id: 'overlay-dcs',
      type: 'circle',
      paint: {
        'circle-radius':       ['interpolate', ['linear'], ['zoom'], 2, 1.5, 6, 3, 8, 5],
        'circle-color':        '#9C27B0',
        'circle-stroke-color': '#10141C',
        'circle-stroke-width': 0.4,
        'circle-opacity':      0.85,
      },
    }],
  },
};

let _overlayPopup = null;

function wireOverlayLayerInteractions(o) {
  if (!o.interactive) return;
  for (const layer of o.layers) {
    state.map.on('click', layer.id, (e) => {
      if (!e.features || !e.features[0]) return;
      const props = e.features[0].properties || {};
      const html = o.popup(props);
      if (_overlayPopup) _overlayPopup.remove();
      _overlayPopup = new mapboxgl.Popup({ closeButton: true, closeOnClick: true, offset: 10, maxWidth: '280px' })
        .setLngLat(e.features[0].geometry.coordinates.slice())
        .setHTML(html)
        .addTo(state.map);
      // Stop the country-marker click from also firing
      e.originalEvent.stopPropagation();
    });
    state.map.on('mouseenter', layer.id, () => {
      state.map.getCanvas().style.cursor = 'pointer';
    });
    state.map.on('mouseleave', layer.id, () => {
      state.map.getCanvas().style.cursor = '';
    });
  }
}

async function toggleOverlay(key, enabled) {
  const o = OVERLAYS[key];
  if (!o) return;
  if (enabled) {
    // Lazy-load the data the first time the overlay is enabled.
    if (!state.map.getSource(o.sourceId)) {
      try {
        const res = await fetch(o.file);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        state.map.addSource(o.sourceId, { type: 'geojson', data });
        for (const layer of o.layers) {
          state.map.addLayer({ ...layer, source: o.sourceId }, 'country-markers');
        }
        wireOverlayLayerInteractions(o);
        console.log('[overlay]', key, 'loaded',
          (data.features && data.features.length) || 0, 'features');
      } catch (err) {
        console.warn('[overlay] failed to load', key, '—', err.message);
        flashCompareBar('Overlay data missing — run scripts/fetch_overlays.py');
        const btn = document.querySelector('.overlay-chip[data-layer="' + key + '"]');
        if (btn) btn.classList.remove('active');
        return;
      }
    } else {
      for (const layer of o.layers) {
        if (state.map.getLayer(layer.id)) {
          state.map.setLayoutProperty(layer.id, 'visibility', 'visible');
        }
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
  if (fid === 'demand_2027_twh')      return value.toFixed(1);
  if (fid === 'grid_connect_years')   return value.toFixed(1);
  if (fid === 'power_per_capita_kwh') return value >= 1000 ? Math.round(value / 1000) + 'k' : String(Math.round(value));
  if (fid === 'grid_investment_usdbn')return Math.round(value).toString();
  if (fid === 'bandwidth_gbps')       return value.toFixed(2);
  if (fid === 'bandwidth_2030_gbps')  return value.toFixed(1);
  if (fid === 'construction_cost_usd_mw') return (value / 1e6).toFixed(1);
  if (fid === 'power_cost_usd_kwh')   return value.toFixed(2);
  if (fid === 'rd_techs_per_million') return value >= 1000 ? Math.round(value / 1000) + 'k' : String(Math.round(value));
  if (fid === 'tertiary_grad_pct')    return Math.round(value).toString();
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
        ['boolean', ['feature-state', 'active'], false], '#FFFFFF',
        '#00E5FF',
      ],
      'circle-stroke-width': 2,
      'circle-stroke-color': [
        'case',
        ['boolean', ['feature-state', 'active'], false], '#00E5FF',
        'rgba(10, 13, 18, 0.85)',
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

  html += '</tbody></table>';
  body.innerHTML = html;
}

/* ── Map interactions ─────────────────────────────────────────── */

function wireMarkerInteractions() {
  const hover = (e) => {
    state.map.getCanvas().style.cursor = e.features && e.features.length ? 'pointer' : '';
  };

  state.map.on('mouseenter', 'country-markers-hit', () => {
    state.map.getCanvas().style.cursor = 'pointer';
  });
  state.map.on('mouseleave', 'country-markers-hit', () => {
    state.map.getCanvas().style.cursor = '';
  });

  state.map.on('click', 'country-markers-hit', (e) => {
    if (!e.features || !e.features[0]) return;
    const iso2 = e.features[0].properties.iso2;
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
  { id: 'bandwidth_2030_gbps',       label: 'Bandwidth 2030',       dir: 'asc'  },
  { id: 'construction_cost_usd_mw',  label: 'Construction cost',    dir: 'desc' },
  { id: 'power_cost_usd_kwh',        label: 'Power cost',           dir: 'desc' },
  { id: 'rd_techs_per_million',      label: 'R&D techs / million',  dir: 'asc'  },
  { id: 'tertiary_grad_pct',         label: 'Tertiary graduate %',  dir: 'asc'  },
  { id: 'carbon_intensity_gco2_kwh', label: 'Grid carbon intensity',dir: 'desc' },
];

const WEIGHT_PRESETS = {
  reset:   Object.fromEntries(SCORING_FACTORS.map(f => [f.id, 5])),
  power:   {
    // Power access — heavy on grid headroom, connection speed, and cheap
    // electricity. Today the #1 siting blocker for hyperscale DCs.
    grid_connect_years: 10, power_per_capita_kwh: 9, grid_investment_usdbn: 8,
    bandwidth_gbps: 2, bandwidth_2030_gbps: 1,
    construction_cost_usd_mw: 3, power_cost_usd_kwh: 8,
    rd_techs_per_million: 1, tertiary_grad_pct: 1, carbon_intensity_gco2_kwh: 3,
  },
  cost:    {
    grid_connect_years: 5, power_per_capita_kwh: 3, grid_investment_usdbn: 2,
    bandwidth_gbps: 2, bandwidth_2030_gbps: 1,
    construction_cost_usd_mw: 10, power_cost_usd_kwh: 10,
    rd_techs_per_million: 2, tertiary_grad_pct: 2, carbon_intensity_gco2_kwh: 2,
  },
  sustain: {
    grid_connect_years: 5, power_per_capita_kwh: 7, grid_investment_usdbn: 5,
    bandwidth_gbps: 2, bandwidth_2030_gbps: 2,
    construction_cost_usd_mw: 2, power_cost_usd_kwh: 4,
    rd_techs_per_million: 2, tertiary_grad_pct: 2, carbon_intensity_gco2_kwh: 10,
  },
  latency: {
    grid_connect_years: 4, power_per_capita_kwh: 3, grid_investment_usdbn: 3,
    bandwidth_gbps: 10, bandwidth_2030_gbps: 8,
    construction_cost_usd_mw: 2, power_cost_usd_kwh: 3,
    rd_techs_per_million: 4, tertiary_grad_pct: 3, carbon_intensity_gco2_kwh: 2,
  },
  off:     Object.fromEntries(SCORING_FACTORS.map(f => [f.id, 0])),
};

// Per-factor [min, max] across countries that have data — cached at load.
const FACTOR_RANGES = {};

function computeFactorRanges() {
  for (const f of SCORING_FACTORS) {
    const vals = state.markets
      .map(c => c.factors && c.factors[f.id] && c.factors[f.id].value)
      .filter(v => typeof v === 'number');
    if (vals.length > 0) {
      FACTOR_RANGES[f.id] = { min: Math.min(...vals), max: Math.max(...vals) };
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

  // 1. Score each country. Missing data is excluded and weights renormalise.
  const rows = [];
  for (const c of state.markets) {
    let weighted = 0;
    let weightSum = 0;
    const contrib = {};
    const missing = [];
    for (const f of SCORING_FACTORS) {
      const w = weights[f.id] || 0;
      if (w === 0) continue;
      const entry = c.factors && c.factors[f.id];
      if (!entry || typeof entry.value !== 'number') {
        missing.push(f.id);
        continue;
      }
      const norm = normalise(f.id, entry.value, f.dir);
      weighted   += w * norm;
      weightSum  += w;
      contrib[f.id] = { norm, weight: w, weightedContribution: w * norm };
    }
    if (weightSum === 0) {
      state.composite[c.iso2] = { score: null, contrib, missing };
      continue;
    }
    const score = weighted / weightSum;
    rows.push({ iso2: c.iso2, score });
    state.composite[c.iso2] = { score, contrib, missing };
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
  { id: 'demand_2027_twh',           label: 'Compute demand 2027',  fmt: v => v.toFixed(1) + ' TWh',                   dir: 'neutral' },
  { id: 'grid_connect_years',        label: 'Grid connection wait', fmt: v => v.toFixed(1) + ' yrs',                   dir: 'desc' },
  { id: 'power_per_capita_kwh',      label: 'Power / capita',       fmt: v => Math.round(v).toLocaleString() + ' kWh', dir: 'asc' },
  { id: 'grid_investment_usdbn',     label: 'Grid investment',      fmt: v => '$' + Math.round(v) + ' bn',             dir: 'asc' },
  { id: 'bandwidth_gbps',            label: 'Bandwidth',            fmt: v => v.toFixed(2) + ' Gbps',                  dir: 'asc' },
  { id: 'bandwidth_2030_gbps',       label: 'Bandwidth 2030',       fmt: v => v.toFixed(1) + ' Gbps',                  dir: 'asc' },
  { id: 'construction_cost_usd_mw',  label: 'Construction cost',    fmt: v => '$' + (v / 1e6).toFixed(1) + 'M / MW',   dir: 'desc' },
  { id: 'power_cost_usd_kwh',        label: 'Power cost',           fmt: v => '$' + v.toFixed(3) + '/kWh',             dir: 'desc' },
  { id: 'rd_techs_per_million',      label: 'R&D techs / million',  fmt: v => Math.round(v).toLocaleString(),          dir: 'asc' },
  { id: 'tertiary_grad_pct',         label: 'Tertiary graduate %',  fmt: v => v.toFixed(1) + ' %',                     dir: 'asc' },
  { id: 'carbon_intensity_gco2_kwh', label: 'Grid carbon intensity',fmt: v => Math.round(v) + ' gCO₂/kWh',             dir: 'desc' },
  { id: 'dc_capacity_live_mw',       label: 'Live DC capacity',     fmt: v => Math.round(v) + ' MW',                   dir: 'neutral' },
  { id: 'dc_capacity_planned_mw',    label: 'Planned DC capacity',  fmt: v => Math.round(v) + ' MW',                   dir: 'neutral' },
];

// Traffic-light red → amber → green ramp (5 stops).
// Worst → red, best → green. Reverses when a factor is direction='desc'.
const COLOUR_RAMP = [
  '#D32F2F',   // 0    — red (worst)
  '#F57C00',   // 0.25 — deep orange
  '#FBC02D',   // 0.50 — amber
  '#9CCC65',   // 0.75 — lime
  '#2E7D32',   // 1    — green (best)
];
const COLOUR_HIGH   = COLOUR_RAMP[COLOUR_RAMP.length - 1];
const COLOUR_NODATA = '#3B4257'; // grey

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
}

function applyColourMode() {
  const fid = state.colourBy;
  if (!fid) {
    // Default: solid cyan with active-state override + smaller markers
    state.map.setPaintProperty('country-markers', 'circle-color', [
      'case',
      ['boolean', ['feature-state', 'active'], false], '#FFFFFF',
      '#00E5FF',
    ]);
    state.map.setPaintProperty('country-markers', 'circle-radius', [
      'interpolate', ['linear'], ['zoom'],
      2, 5,  4, 7,  6, 10,
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
    ['boolean', ['feature-state', 'active'], false], '#FFFFFF',
    ['has', propKey],
    ['interpolate', ['linear'], ['get', propKey], ...stops],
    COLOUR_NODATA,
  ];
  state.map.setPaintProperty('country-markers', 'circle-color', colourExpr);

  // Bigger markers when colouring so the colour reads at a glance.
  state.map.setPaintProperty('country-markers', 'circle-radius', [
    'interpolate', ['linear'], ['zoom'],
    2, 7,  4, 11,  6, 16,
  ]);

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
    let sub = '';
    if (r.year) sub = '<span class="rank-value-sub">' + r.year + '</span>';
    else if (isComposite && state.composite[r.c.iso2] && state.composite[r.c.iso2].total) {
      sub = '<span class="rank-value-sub">of ' + state.composite[r.c.iso2].total + '</span>';
    }
    valCell = '<div><div class="rank-value"' + colourStyle + '>' + opt.fmt(r.value) + '</div>' + sub + '</div>';
  }

  // Country name with optional subtitle for composite (showing data coverage)
  let nameSub = '';
  if (isComposite) {
    const comp = state.composite[r.c.iso2];
    if (comp && comp.missing && comp.missing.length > 0) {
      nameSub = '<span class="rank-name-sub">' + comp.missing.length + ' factors missing</span>';
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
  ['Demand dynamics',     'Total compute demand 2027',  'demand_2027_twh',           v => v.toFixed(1) + ' TWh',                       'neutral'],

  ['Supply — Grid',       'Connection timeline',         'grid_connect_years',        v => v.toFixed(1) + ' yrs',                       'desc'],
  ['Supply — Grid',       'Power production / capita',   'power_per_capita_kwh',      v => Math.round(v).toLocaleString() + ' kWh/yr',  'asc'],
  ['Supply — Grid',       'Forecast grid investment',    'grid_investment_usdbn',     v => '$' + v.toFixed(0) + ' bn',                  'asc'],

  ['Supply — Fibre',      'Bandwidth (median)',          'bandwidth_gbps',            v => v.toFixed(2) + ' Gbps',                      'asc'],
  ['Supply — Fibre',      '2030 broadband forecast',     'bandwidth_2030_gbps',       v => v.toFixed(1) + ' Gbps',                      'asc'],

  ['Differentiators',     'DC construction cost',        'construction_cost_usd_mw',  v => '$' + (v / 1e6).toFixed(1) + 'M / MW',       'desc'],
  ['Differentiators',     'Power cost',                  'power_cost_usd_kwh',        v => '$' + v.toFixed(3) + ' / kWh',               'desc'],
  ['Differentiators',     'R&D techs / million',         'rd_techs_per_million',      v => Math.round(v).toLocaleString(),              'asc'],
  ['Differentiators',     'Tertiary graduate %',         'tertiary_grad_pct',         v => v.toFixed(1) + ' %',                         'asc'],
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
  return ''
    + '<div class="detail-row">'
    +   '<div class="detail-row-label">' + escapeHtml(label)
    +     '<div class="detail-row-source">' + srcLink + note + '</div>'
    +   '</div>'
    +   '<div class="detail-row-value-block">'
    +     '<span class="detail-row-value">' + valStr + year + '</span>'
    +     chip
    +   '</div>'
    + '</div>';
}

function renderScoreBreakdown(comp) {
  // Per-factor contribution bars. Sorted by weighted contribution descending.
  const rows = Object.entries(comp.contrib || {})
    .map(([fid, c]) => ({ fid, ...c, factor: SCORING_FACTORS.find(f => f.id === fid) }))
    .filter(r => r.factor)
    .sort((a, b) => b.weightedContribution - a.weightedContribution);
  if (rows.length === 0) return '';
  const maxWeighted = Math.max(...rows.map(r => r.weightedContribution));
  let html = '<div class="detail-section-title">Score breakdown</div>'
           + '<div class="score-breakdown">';
  for (const r of rows) {
    const widthPct = maxWeighted > 0 ? (r.weightedContribution / maxWeighted) * 100 : 0;
    html += '<div class="sb-row">'
         +    '<span class="sb-label">' + escapeHtml(r.factor.label) + '</span>'
         +    '<div class="sb-bar-wrap">'
         +      '<div class="sb-bar" style="width:' + widthPct.toFixed(0) + '%"></div>'
         +    '</div>'
         +    '<span class="sb-numbers">'
         +      '<span class="sb-norm">' + Math.round(r.norm) + '</span>'
         +      '<span class="sb-weight">×' + r.weight + '</span>'
         +    '</span>'
         +  '</div>';
  }
  html += '</div>';
  if (comp.missing && comp.missing.length > 0) {
    html += '<div class="sb-missing">Excluded (no data): '
         + comp.missing.map(fid => {
             const f = SCORING_FACTORS.find(x => x.id === fid);
             return f ? f.label : fid;
           }).join(', ')
         + '</div>';
  }
  return html;
}

function openDetailPanel(country) {
  const panel   = document.getElementById('detail-panel');
  const content = document.getElementById('detail-content');
  if (!panel || !content) return;

  const a = currentAnchorFor(country);
  const factors = country.factors || {};

  let html =
    '<div class="detail-title">' + country.flag + ' ' + escapeHtml(country.name) + '</div>' +
    '<div class="detail-region">' + escapeHtml(country.region) + ' · anchor: ' +
      escapeHtml(a.name) + ' (' + a.lat.toFixed(2) + ', ' + a.lon.toFixed(2) + ')</div>';

  // Composite score block — only if any weight is non-zero.
  if (state.weightsActive) {
    const comp = state.composite[country.iso2];
    if (comp && comp.score != null) {
      const missingStr = comp.missing.length > 0
        ? '<div class="detail-composite-meta">Missing data for ' + comp.missing.length + ' weighted factors — score normalised across the rest.</div>'
        : '';
      html +=
        '<div class="detail-composite">'
        + '<div>'
        +   '<div class="detail-composite-label">Composite score</div>'
        +   '<div class="detail-composite-value">' + Math.round(comp.score) + '</div>'
        + '</div>'
        + '<div class="detail-composite-rank">Rank<br><strong>#' + comp.rank + '</strong> of ' + comp.total + '</div>'
        + '</div>'
        + missingStr
        + renderScoreBreakdown(comp);
    } else {
      html += '<div class="detail-composite"><div><div class="detail-composite-label">Composite score</div>'
            + '<div class="detail-composite-value" style="color:var(--text-low)">—</div></div>'
            + '<div class="detail-composite-rank">No data for any weighted factor</div></div>';
    }
  }

  let currentSection = null;
  for (const [section, label, factorId, fmt, dir] of PANEL_ROWS) {
    if (section !== currentSection) {
      html += '<div class="detail-section-title">' + escapeHtml(section) + '</div>';
      currentSection = section;
    }
    html += renderDetailRow(label, factors[factorId], fmt, factorId, country.iso2, dir);
  }

  content.innerHTML = html;
  panel.classList.remove('hidden');
}

/* ──────────────────────────────────────────────────────────────────
   5. UI wiring (Feature 1 minimum)
   ────────────────────────────────────────────────────────────────── */

function wireDetailPanelClose() {
  const closeBtn = document.getElementById('detail-close');
  const panel    = document.getElementById('detail-panel');
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
  wireMobileTabs();
  initMap();
});

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
