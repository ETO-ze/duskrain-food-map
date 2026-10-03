export function matchesSearch(place, query) {
  const terms = String(query || "").trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const text = [place.name, place.address, place.city, place.district, place.rating_author].join(" ").toLocaleLowerCase();
  return terms.every((term) => text.includes(term));
}

export function containsPosition(bounds, position) {
  if (!bounds) return true;
  const { lng, lat } = position;
  const inLongitude = bounds.minLng <= bounds.maxLng
    ? lng >= bounds.minLng && lng <= bounds.maxLng
    : lng >= bounds.minLng || lng <= bounds.maxLng;
  return inLongitude && lat >= bounds.minLat && lat <= bounds.maxLat;
}

export function distanceKm(left, right) {
  const radians = (value) => Number(value) * Math.PI / 180;
  const lat1 = radians(left.lat);
  const lat2 = radians(right.lat);
  const a = Math.sin((lat2 - lat1) / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(radians(right.lng - left.lng) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.max(0, Math.min(1, a))));
}

export function nearbyPlaces(places, origin, radius, positionOf) {
  return places.map((place) => ({ ...place, distanceKm: distanceKm(origin, positionOf(place)) }))
    .filter((place) => Number.isFinite(place.distanceKm) && place.distanceKm <= radius)
    .sort((a, b) => a.distanceKm - b.distanceKm);
}

export function sameBounds(left, right) {
  return Boolean(left && right) && ["minLng", "maxLng", "minLat", "maxLat"]
    .every((key) => Math.abs(left[key] - right[key]) < 0.00001);
}
