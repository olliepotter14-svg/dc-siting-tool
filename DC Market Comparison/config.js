// DC Market Comparison — Configuration
//
// Mapbox public token. The token below is the same one used by the parent
// DC Site Finder tool. It is URL-restricted in the Mapbox dashboard.
//
// To run locally on http://localhost:* :
//   1. Open https://account.mapbox.com/access-tokens/
//   2. Click the token (pk.eyJ1Ijoib3BvdHRlcjEi…)
//   3. Under "URL restrictions" add: http://localhost:*
//      (and the future Netlify URL, e.g. https://dcsitingtool.netlify.app/markets/*)
//
// If running locally without unlocking the token, the map area will be blank
// and the red error banner will read "Mapbox token rejected".
// Token from the Forecourts at risk analysis project — confirmed working on localhost.
window.MAPBOX_TOKEN = "pk.eyJ1Ijoib3BvdHRlcjEiLCJhIjoiY21mandhZ3g2MHV5YTJxcXR4amNyamY4ZSJ9.m-JQyeqDqdIzq7yrTVrKZA";
