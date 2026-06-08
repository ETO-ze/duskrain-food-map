const API_BASE = "/food-map/api";
const CACHE_PREFIX = "duskrain-food-map:";
const PLACES_CACHE_TTL = 60 * 1000;
const PLACE_CACHE_TTL = 5 * 60 * 1000;
const CATEGORY_CACHE_TTL = 30 * 60 * 1000;

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : detail?.message || "请求失败";
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  return data;
}

function readCache(key, ttl) {
  try {
    const cached = JSON.parse(localStorage.getItem(`${CACHE_PREFIX}${key}`) || "null");
    if (!cached || Date.now() - cached.time > ttl) return null;
    return cached.data;
  } catch {
    return null;
  }
}

function writeCache(key, data) {
  try {
    localStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify({ time: Date.now(), data }));
  } catch {
    // Cache is opportunistic; quota or privacy errors should not block the app.
  }
}

function clearCachePrefix(prefix) {
  try {
    Object.keys(localStorage)
      .filter((key) => key.startsWith(`${CACHE_PREFIX}${prefix}`))
      .forEach((key) => localStorage.removeItem(key));
  } catch {
    // Ignore storage cleanup failures.
  }
}

async function cachedJson(url, key, ttl) {
  const cached = readCache(key, ttl);
  if (cached) {
    fetch(url)
      .then(readJson)
      .then((data) => writeCache(key, data))
      .catch(() => {});
    return cached;
  }
  const data = await readJson(await fetch(url));
  writeCache(key, data);
  return data;
}

function clearPublicPlaceCaches() {
  clearCachePrefix("places:");
  clearCachePrefix("place:");
  clearCachePrefix("categories");
}

export async function getConfig() {
  return readJson(await fetch(`${API_BASE}/config`));
}

export async function getPublicPlaces(filters = {}) {
  const params = new URLSearchParams();
  if (filters.category) params.set("category", filters.category);
  if (filters.recommend) params.set("recommend", filters.recommend);
  const query = params.toString();
  return cachedJson(`${API_BASE}/places?${query}`, `places:${query}`, PLACES_CACHE_TTL);
}

export async function getPublicPlace(id) {
  const encodedId = encodeURIComponent(id);
  return cachedJson(`${API_BASE}/places/${encodedId}`, `place:${encodedId}`, PLACE_CACHE_TTL);
}

export async function getCategories() {
  return cachedJson(`${API_BASE}/categories`, "categories", CATEGORY_CACHE_TTL);
}

export async function searchPoi(q, city) {
  const params = new URLSearchParams({ q, city: city || "" });
  return readJson(await fetch(`${API_BASE}/search?${params.toString()}`));
}

export async function getPoiDetail(id) {
  const params = new URLSearchParams({ id });
  return readJson(await fetch(`${API_BASE}/poi-detail?${params.toString()}`));
}

export async function reverseGeocode(lng, lat) {
  const params = new URLSearchParams({ lng: String(lng), lat: String(lat) });
  return readJson(await fetch(`${API_BASE}/regeo?${params.toString()}`));
}

export async function getAdminPlaces() {
  return readJson(await fetch(`${API_BASE}/admin/places`));
}

export async function saveAdminPlace(payload, id) {
  const data = await readJson(await fetch(id ? `${API_BASE}/admin/places/${id}` : `${API_BASE}/admin/places`, {
    method: id ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
  clearPublicPlaceCaches();
  return data;
}

export async function deleteAdminPlace(id) {
  const data = await readJson(await fetch(`${API_BASE}/admin/places/${id}`, { method: "DELETE" }));
  clearPublicPlaceCaches();
  return data;
}
