# Geolocation

Finds your current location and re-sorts all stalls by distance, so the closest options appear at the top of the sidebar.

## Why it exists

Asking "what's nearby?" is the most natural question when you're hungry. Without geolocation, you'd have to estimate distances from the map or know your area well enough to search by name.

## User stories

- As a **local**, I want stalls sorted by distance from my current location so I can find somewhere to eat without planning ahead.
- As a **visitor**, I want to see how far each stall is so I can decide if it's worth the trip.
- As a **food hunter**, I want my location used only on my device so I know it isn't being tracked or stored.

## How it works

Tap "Near me" and the browser asks for location permission. Once granted, stalls are re-sorted by straight-line distance and each card shows the distance. A blue dot appears on the map at your position.

Distances show in metres under 1 km, kilometres above. Tap "Near me" again to clear and restore the previous sort order.

Your location is used only in your browser to calculate distances. It is never sent to any server or stored anywhere.

## Reference

**API:** `navigator.geolocation.getCurrentPosition()` with `enableHighAccuracy: true`, `timeout: 10000`.

**Haversine formula:**
```javascript
function distanceKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
            Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) *
            Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}
```

**Distance display:** `< 1 km` → metres (e.g. "450 m"); `≥ 1 km` → one decimal (e.g. "2.3 km"). Injected as `.loc-distance` span in each card's meta row.

**Sort:** `sortByDistance()` reorders cards via `appendChild` (in-place DOM reorder). Takes precedence over all pill-based sort modes while `userLatLng` is set.

**User marker:** `L.divIcon()`, 18×18 px, anchor `[9, 9]`, stored in `userMarker`. Removed by `clearUserLocation()`, which also clears `userLatLng` and restores the previous sort.

**Button states:** "Near me" → "Near me ✓" when active.
