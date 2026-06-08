import { getConfig } from "./api";
import { markerClass } from "./map";

let googleMapsPromise;
const GOOGLE_PLACE_FIELDS = [
  "id",
  "displayName",
  "formattedAddress",
  "location",
  "primaryTypeDisplayName",
  "nationalPhoneNumber",
  "regularOpeningHours",
  "googleMapsURI",
  "addressComponents",
];

export async function loadGoogleMaps() {
  if (window.google?.maps?.importLibrary) return window.google.maps;
  if (googleMapsPromise) return googleMapsPromise;

  googleMapsPromise = getConfig().then((config) => new Promise((resolve, reject) => {
    if (!config.googleMapsApiKey) {
      reject(new Error("GOOGLE_MAPS_API_KEY is not configured"));
      return;
    }
    const callbackName = `__duskrainGoogleMapsReady${Date.now()}`;
    const script = document.createElement("script");
    window[callbackName] = () => {
      delete window[callbackName];
      resolve(window.google.maps);
    };
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(config.googleMapsApiKey)}&v=weekly&loading=async&libraries=maps,marker,places&language=zh-CN&callback=${callbackName}`;
    script.async = true;
    script.onerror = () => {
      delete window[callbackName];
      reject(new Error("Google Maps 脚本加载失败"));
    };
    document.head.appendChild(script);
  }));

  return googleMapsPromise;
}

function addressPart(components, types) {
  const component = (components || []).find((item) => (
    (item.types || []).some((type) => types.includes(type))
  ));
  return component?.longText || component?.shortText || "";
}

function countryCode(components) {
  const component = (components || []).find((item) => (
    (item.types || []).includes("country")
  ));
  return component?.shortText || "";
}

export function normalizeGooglePlace(place) {
  const location = place.location;
  const lng = typeof location?.lng === "function" ? location.lng() : Number(location?.lng);
  const lat = typeof location?.lat === "function" ? location.lat() : Number(location?.lat);
  const components = place.addressComponents || [];
  const city = addressPart(components, [
    "locality",
    "postal_town",
    "administrative_area_level_2",
    "administrative_area_level_1",
  ]);
  const district = addressPart(components, [
    "sublocality_level_1",
    "sublocality",
    "administrative_area_level_3",
  ]);

  return {
    map_provider: "google",
    country_code: countryCode(components),
    coordinate_system: "wgs84",
    provider_poi_id: place.id || "",
    name: place.displayName || "",
    address: place.formattedAddress || "",
    lng,
    lat,
    city,
    district,
    provider_category: place.primaryTypeDisplayName || "",
    phone: place.nationalPhoneNumber || "",
    business_hours: (place.regularOpeningHours?.weekdayDescriptions || []).join("；"),
    amap_detail_url: "",
    provider_detail_url: place.googleMapsURI || "",
    cover_image: "",
    image_urls: "",
  };
}

export async function searchGooglePlaces(textQuery) {
  const maps = await loadGoogleMaps();
  const { Place } = await maps.importLibrary("places");
  const response = await Place.searchByText({
    textQuery,
    fields: GOOGLE_PLACE_FIELDS,
    maxResultCount: 15,
    language: "zh-CN",
  });
  return (response.places || []).map(normalizeGooglePlace).filter((item) => (
    Number.isFinite(item.lng) && Number.isFinite(item.lat)
  ));
}

export async function fetchGooglePlace(placeId) {
  const maps = await loadGoogleMaps();
  const { Place } = await maps.importLibrary("places");
  const place = new Place({ id: placeId });
  await place.fetchFields({ fields: GOOGLE_PLACE_FIELDS });
  return normalizeGooglePlace(place);
}

function geocoderAddressPart(components, types) {
  const component = (components || []).find((item) => (
    (item.types || []).some((type) => types.includes(type))
  ));
  return component?.long_name || component?.short_name || "";
}

export async function reverseGeocodeGoogle(position) {
  const maps = await loadGoogleMaps();
  const { Geocoder } = await maps.importLibrary("geocoding");
  const response = await new Geocoder().geocode({ location: position });
  const result = response.results?.[0];
  const components = result?.address_components || [];
  const country = components.find((item) => item.types?.includes("country"));
  return {
    map_provider: "google",
    country_code: country?.short_name || "",
    coordinate_system: "wgs84",
    provider_poi_id: "",
    name: "",
    address: result?.formatted_address || "",
    lng: Number(position.lng),
    lat: Number(position.lat),
    city: geocoderAddressPart(components, [
      "locality",
      "postal_town",
      "administrative_area_level_2",
      "administrative_area_level_1",
    ]),
    district: geocoderAddressPart(components, [
      "sublocality_level_1",
      "sublocality",
      "administrative_area_level_3",
    ]),
    provider_category: "",
    phone: "",
    business_hours: "",
    amap_detail_url: "",
    provider_detail_url: `https://www.google.com/maps?q=${position.lat},${position.lng}`,
    cover_image: "",
    image_urls: "",
  };
}

function outOfChina(lng, lat) {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271;
}

function transformLat(x, y) {
  let value = -100 + (2 * x) + (3 * y) + (0.2 * y * y) + (0.1 * x * y) + (0.2 * Math.sqrt(Math.abs(x)));
  value += ((20 * Math.sin(6 * x * Math.PI)) + (20 * Math.sin(2 * x * Math.PI))) * 2 / 3;
  value += ((20 * Math.sin(y * Math.PI)) + (40 * Math.sin(y / 3 * Math.PI))) * 2 / 3;
  value += ((160 * Math.sin(y / 12 * Math.PI)) + (320 * Math.sin(y * Math.PI / 30))) * 2 / 3;
  return value;
}

function transformLng(x, y) {
  let value = 300 + x + (2 * y) + (0.1 * x * x) + (0.1 * x * y) + (0.1 * Math.sqrt(Math.abs(x)));
  value += ((20 * Math.sin(6 * x * Math.PI)) + (20 * Math.sin(2 * x * Math.PI))) * 2 / 3;
  value += ((20 * Math.sin(x * Math.PI)) + (40 * Math.sin(x / 3 * Math.PI))) * 2 / 3;
  value += ((150 * Math.sin(x / 12 * Math.PI)) + (300 * Math.sin(x / 30 * Math.PI))) * 2 / 3;
  return value;
}

export function gcj02ToWgs84(lngValue, latValue) {
  const lng = Number(lngValue);
  const lat = Number(latValue);
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || outOfChina(lng, lat)) {
    return { lng, lat };
  }
  const radius = 6378245;
  const eccentricity = 0.006693421622965943;
  let dLat = transformLat(lng - 105, lat - 35);
  let dLng = transformLng(lng - 105, lat - 35);
  const radLat = lat / 180 * Math.PI;
  let magic = Math.sin(radLat);
  magic = 1 - (eccentricity * magic * magic);
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180) / (((radius * (1 - eccentricity)) / (magic * sqrtMagic)) * Math.PI);
  dLng = (dLng * 180) / ((radius / sqrtMagic) * Math.cos(radLat) * Math.PI);
  const gcjLat = lat + dLat;
  const gcjLng = lng + dLng;
  return { lng: (lng * 2) - gcjLng, lat: (lat * 2) - gcjLat };
}

export function googleMarkerContent(place, options = {}) {
  const root = document.createElement("div");
  root.className = [
    "store-marker",
    "google-store-marker",
    options.compact ? "is-compact" : "",
    options.synced ? "is-amap-synced" : "",
  ].filter(Boolean).join(" ");
  const rating = place.rating == null ? "食" : String(Math.round(Number(place.rating)));
  root.innerHTML = `
    <div class="marker ${markerClass(place)}">${rating}</div>
    <span class="store-marker-name"></span>
  `;
  root.querySelector(".store-marker-name").textContent = place.name || "未命名店家";
  return root;
}
