# Interactive Map

Displays every discussed Hokkien Mee stall as a marker on a map of Singapore. Nearby markers group together at lower zoom levels and spread apart as you zoom in.

## Why it exists

A list of stalls is hard to reason about geographically. The map makes it immediately obvious where stalls are clustered, which neighbourhoods are well-represented, and how far a stall is from where you are.

## User stories

- As a **food hunter**, I want to see all stalls plotted on a map so I can spot which areas have the most options.
- As a **local**, I want markers to cluster at low zoom so the map isn't overwhelming when viewing all of Singapore.
- As a **visitor**, I want to zoom into my neighbourhood and see individual stall markers so I can find something nearby.
- As a **map visitor**, I want each marker to show the stall address and post count on hover so I can decide whether to click.

## How it works

Each stall gets a bowl-icon marker. At low zoom, nearby markers merge into a numbered cluster — click to zoom in and reveal individual stalls. At zoom ≥ 17, clustering is disabled and every stall shows separately. Clicking a marker opens the stall popup.

On load, the map fits all locations into view. Deep links (`?id=<stall-id>`) zoom directly to a specific stall and open its popup.

## Reference

**Library:** Leaflet.js + Leaflet.markercluster

**Tile source:** OneMap Singapore (`https://www.onemap.gov.sg/maps/tiles/Original/{z}/{x}/{y}.png`), max zoom 19

**Initial view:**
- Centre: `[1.3521, 103.8198]`
- Zoom: `14`
- `fitBounds()` padding: desktop `[60, 60]`, mobile `[10, 10]`
- Max zoom when fitting: `15`; mobile safeguard: minimum `13`

**Cluster config:**
- `maxClusterRadius: 40`
- `disableClusteringAtZoom: 17`
- `spiderfyOnMaxZoom: true`
- `zoomToBoundsOnClick: true`

**Markers:** `L.divIcon()` with `HKM_MARKER_SVG`, size `[36, 36]`, anchor `[18, 18]`. Tooltip: address + post count, `direction: 'top'`, offset `[0, -12]`.

**Deep link handling:** 500 ms delay on load, then `cluster.zoomToShowLayer(marker, callback)` → open popup → set active card → scroll into view.
