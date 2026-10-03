<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import { ChevronLeft, ChevronRight, Search, List, Map as MapIcon, MapPin, Moon, RotateCcw, ScanSearch, Shuffle, Sun, X } from "@lucide/vue";
import MapLoading from "./MapLoading.vue";
import BrowsePlaceCard from "./BrowsePlaceCard.vue";
import { useBrowseMemory } from "../utils/browse-memory";
import { useBrowseResults } from "../utils/browse-panel";
import { useMapLoading } from "../utils/map-loading";
import { matchesSearch, containsPosition, nearbyPlaces, sameBounds } from "../utils/explore";
import { gcj02ToWgs84 } from "../utils/google-map";
import { getCategories, getPublicPlaces } from "../utils/api";
import { placeCategories } from "../utils/categories";
import { applyMapLabels, applyMovingMapFeatures, cityClusterHtml, clusterCountHtml, formatAddress, hydrateDeferredImages, imageList, infoHtml, loadAmap, loadAmapPlugin, mapOptions, storeMarkerHtml } from "../utils/map";

const AMapRef = shallowRef(null);
const map = shallowRef(null);
const infoWindow = shallowRef(null);
const places = ref([]);
const markerCluster = shallowRef(null);
const cityMarkers = shallowRef([]);
const categories = ref([]);
const recommendLevels = ref([]);
const filters = ref({ category: "", recommend: "", city: "", author: "" });
const nearbyMode = ref(false);
const userLocation = ref(null);
const viewportBounds = ref(null);
const actionMessage = ref("");
const mapTheme = ref("day");
const sidebarCollapsed = ref(false);
const guidePromoDismissed = ref(false);
const adSlotDismissed = ref(false);
const adSlotIndex = ref(0);
const sidePanelElement = ref(null);
const listElement = ref(null);
const query = ref("");
const loadingPlaces = ref(true);
const locating = ref(false);
const nearbyRadius = ref(30);
const selectedId = ref(null);
const viewportDirty = ref(false);
const { phase: mapPhase, message: mapMessage, screenPhase: loadingPhase, screenVisible: loadingScreen, dismiss: dismissLoading, reveal: revealLoading, begin: beginLoading, current: currentLoading, rendering: mapRendering, ready: mapReady, fail: mapFailed } = useMapLoading(computed(() => loadingPlaces.value && !places.value.length));
let disposed = false;
let locationRequest = 0;
let initialFitDone = false;
let pendingPlace = null;
let searchTimer;
let markerSignature = "";
const cityMarkerCache = new Map();
const { restoreScroll } = useBrowseMemory("duskrain-browse-amap", { filters, query, mapTheme }, sidePanelElement);
useBrowseResults(sidePanelElement, listElement, [filters, query, nearbyMode, viewportBounds]);
const initialPlaceFocused = ref(false);
const error = ref("");
const CITY_OVERVIEW_MAX_ZOOM = 7.5;
let baseLabelTimer = 0;
let baseLabelFollowupTimer = 0;
let focusToken = 0;
let placesRequestId = 0;
let movingTimer = 0;
let isMapMoving = false;
let activeMarkerMode = "";
let storeMarkerData = [];
let scaleControl = null;
const pendingTimers = new Set();
const singleMarkerHandlers = new WeakMap();
const AD_SLOT_SESSION_KEY = "duskrainPublicMapAdDismissed";
const ADS_ENABLED = false;
const adSlots = ["广告位 1", "广告位 2", "广告位 3"];

const domesticPlaces = computed(() => places.value.filter((place) => (place.map_provider || "amap") === "amap"));

const cityOptions = computed(() => {
  return [...new Set(domesticPlaces.value.map((place) => place.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
});

const authorOptions = computed(() => {
  return [...new Set(domesticPlaces.value.map((place) => place.rating_author).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
});

const hasActiveFilters = computed(() => Object.values(filters.value).some(Boolean) || Boolean(viewportBounds.value) || nearbyMode.value || Boolean(query.value.trim()));

const visiblePlaces = computed(() => {
  const filtered = domesticPlaces.value.filter((place) => {
    if (filters.value.category && !placeCategories(place).includes(filters.value.category)) return false;
    if (filters.value.recommend && place.recommend_level !== filters.value.recommend) return false;
    if (filters.value.city && place.city !== filters.value.city) return false;
    if (filters.value.author && place.rating_author !== filters.value.author) return false;
    return matchesSearch(place, query.value) && containsPosition(viewportBounds.value, { lng: Number(place.lng), lat: Number(place.lat) });
  });
  if (nearbyMode.value && userLocation.value) {
    return nearbyPlaces(filtered, userLocation.value, nearbyRadius.value, (place) => gcj02ToWgs84(place.lng, place.lat));
  }
  return filtered.sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0));
});

watch(query, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refreshVisiblePlaces, 150);
});

function isMobile() {
  return window.matchMedia("(max-width: 860px)").matches;
}

function dismissAdSlot() {
  adSlotDismissed.value = true;
  try {
    window.sessionStorage.setItem(AD_SLOT_SESSION_KEY, "true");
  } catch {
    // The close action still works when browser storage is unavailable.
  }
}

function dismissGuidePromo() {
  guidePromoDismissed.value = true;
}

function switchAdSlot(direction) {
  adSlotIndex.value = (adSlotIndex.value + direction + adSlots.length) % adSlots.length;
}

function waitFrame() {
  return new Promise((resolve) => window.requestAnimationFrame(resolve));
}

function schedule(callback, delay) {
  const timer = window.setTimeout(() => {
    pendingTimers.delete(timer);
    callback();
  }, delay);
  pendingTimers.add(timer);
  return timer;
}

function resizeMapSoon() {
  schedule(() => {
    if (map.value && typeof map.value.resize === "function") map.value.resize();
  }, 260);
}

async function loadFilters() {
  const data = await getCategories();
  categories.value = data.categories || [];
  recommendLevels.value = data.recommendLevels || [];
}

async function loadPlaces() {
  const requestId = ++placesRequestId;
  try {
    loadingPlaces.value = true;
    const loadedPlaces = await getPublicPlaces();
    if (disposed || requestId !== placesRequestId) return;
    places.value = loadedPlaces;
    if (filters.value.city && !cityOptions.value.includes(filters.value.city)) filters.value.city = "";
    if (filters.value.author && !authorOptions.value.includes(filters.value.author)) filters.value.author = "";
    error.value = "";
    await nextTick();
    restoreScroll();
    renderMarkers(!initialFitDone);
    focusInitialPlace();
  } catch (err) {
    if (requestId !== placesRequestId) return;
    error.value = err.message;
  } finally {
    if (!disposed && requestId === placesRequestId) loadingPlaces.value = false;
  }
}

function renderMarkers(fit = false) {
  if (!map.value || !AMapRef.value || !infoWindow.value) return;
  if (selectedId.value && !visiblePlaces.value.some((place) => place.id === selectedId.value)) {
    selectedId.value = null;
    pendingPlace = null;
    focusToken++;
    infoWindow.value.close();
  }
  const signature = visiblePlaces.value.map((place) => [place.id, place.lng, place.lat, place.rating, place.name, place.recommend_level, place.updated_at].join(":")).join("|");
  if (signature !== markerSignature) {
    markerSignature = signature;
    storeMarkerData = visiblePlaces.value.map((place) => ({ lnglat: [Number(place.lng), Number(place.lat)], place }));
    const groups = groupPlacesByCity(visiblePlaces.value);
    const keys = new Set(groups.map((group) => group.city));
    cityMarkerCache.forEach((entry, key) => {
      if (!keys.has(key)) { entry.marker.setMap(null); cityMarkerCache.delete(key); }
    });
    groups.forEach((group) => {
      const key = group.places.map((place) => [place.id, place.lng, place.lat, place.updated_at].join(":")).join(",");
      let entry = cityMarkerCache.get(group.city);
      if (entry?.key === key) return;
      entry?.marker.setMap(null);
      entry = { key, marker: createCityMarker(group) };
      cityMarkerCache.set(group.city, entry);
    });
    cityMarkers.value = [...cityMarkerCache.values()].map((entry) => entry.marker);
    markerCluster.value?.setData(storeMarkerData);
    if (!storeMarkerData.length) {
      infoWindow.value.close();
      selectedId.value = null;
    } else { syncMarkerMode(true); }
  }
  if (fit && visiblePlaces.value.length) { fitAll(); initialFitDone = true; }
}

function groupPlacesByCity(source) {
  const groups = new Map();
  source.forEach((place) => {
    const city = place.city || "其他地区";
    if (!groups.has(city)) groups.set(city, []);
    groups.get(city).push(place);
  });
  return [...groups.entries()].map(([city, cityPlaces]) => ({ city, places: cityPlaces }));
}

function clearMarkerClusters() {
  destroyStoreCluster();
  if (cityMarkers.value.length) map.value?.remove?.(cityMarkers.value);
  cityMarkers.value.forEach((marker) => marker.setMap?.(null));
  cityMarkers.value = [];
  cityMarkerCache.clear();
  markerSignature = "";
  storeMarkerData = [];
  activeMarkerMode = "";
}

function destroyStoreCluster() {
  markerCluster.value?.clearMarkers?.();
  markerCluster.value?.setMap?.(null);
  markerCluster.value = null;
}

function createStoreCluster() {
  if (markerCluster.value || !storeMarkerData.length) return;
  markerCluster.value = new AMapRef.value.MarkerCluster(map.value, storeMarkerData, {
    gridSize: isMobile() ? 44 : 52,
    averageCenter: true,
    clusterByZoomChange: false,
    renderClusterMarker: renderStoreClusterMarker,
    renderMarker: renderSingleMarker,
  });
}

function cityCenter(cityPlaces) {
  const total = cityPlaces.reduce((result, place) => ({
    lng: result.lng + Number(place.lng),
    lat: result.lat + Number(place.lat),
  }), { lng: 0, lat: 0 });
  return [total.lng / cityPlaces.length, total.lat / cityPlaces.length];
}

function createCityMarker({ city, places: cityPlaces }) {
  const marker = new AMapRef.value.Marker({
    position: cityCenter(cityPlaces),
    content: cityClusterHtml(city, cityPlaces.length),
    offset: new AMapRef.value.Pixel(-15, -15),
    zIndex: 120,
    title: `${city} · ${cityPlaces.length}家`,
    extData: { city, count: cityPlaces.length, labelVisible: true },
  });
  marker.on("click", () => focusCity(cityPlaces));
  return marker;
}

function rectanglesOverlap(left, right, padding = 3) {
  return !(
    left.right + padding < right.left
    || left.left - padding > right.right
    || left.bottom + padding < right.top
    || left.top - padding > right.bottom
  );
}

function syncCityLabelDensity() {
  if (activeMarkerMode !== "cities" || !map.value?.lngLatToContainer) return;
  const entries = cityMarkers.value
    .map((marker) => {
      const point = map.value.lngLatToContainer(marker.getPosition());
      const data = marker.getExtData?.() || {};
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
      const labelWidth = Math.min(150, 28 + String(data.city || "").length * 13 + String(data.count || "").length * 7);
      return {
        marker,
        data,
        point,
        labelRect: {
          left: point.x + 10,
          right: point.x + 10 + labelWidth,
          top: point.y - 15,
          bottom: point.y + 15,
        },
        dotRect: {
          left: point.x - 17,
          right: point.x + 17,
          top: point.y - 17,
          bottom: point.y + 17,
        },
      };
    })
    .filter(Boolean)
    .sort((a, b) => Number(b.data.count || 0) - Number(a.data.count || 0));
  const visibleLabels = [];
  entries.forEach((entry) => {
    const coversAnotherDot = entries.some((other) => (
      other !== entry && rectanglesOverlap(entry.labelRect, other.dotRect, 1)
    ));
    const overlapsLabel = visibleLabels.some((rect) => rectanglesOverlap(entry.labelRect, rect));
    const showLabel = !coversAnotherDot && !overlapsLabel;
    if (showLabel) visibleLabels.push(entry.labelRect);
    if (entry.data.labelVisible === showLabel) return;
    entry.marker.setContent(cityClusterHtml(entry.data.city, entry.data.count, { showLabel }));
    entry.marker.setExtData({ ...entry.data, labelVisible: showLabel });
  });
}

function focusCity(cityPlaces) {
  if (cityPlaces.length === 1) {
    focusPlace(cityPlaces[0]);
    return;
  }
  const lngs = cityPlaces.map((place) => Number(place.lng));
  const lats = cityPlaces.map((place) => Number(place.lat));
  const bounds = new AMapRef.value.Bounds(
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  );
  map.value.setBounds(bounds, true, [52, 32, 52, 32]);
}

function syncMarkerMode(force = false) {
  if (!map.value || !storeMarkerData.length) return;
  const showCities = map.value.getZoom() <= CITY_OVERVIEW_MAX_ZOOM;
  const nextMode = showCities ? "cities" : "stores";
  if (!force && activeMarkerMode === nextMode) return;
  activeMarkerMode = nextMode;
  if (showCities) {
    destroyStoreCluster();
    if (cityMarkers.value.length) map.value.add?.(cityMarkers.value);
    schedule(syncCityLabelDensity, 60);
  } else {
    if (cityMarkers.value.length) map.value.remove?.(cityMarkers.value);
    createStoreCluster();
  }
}

function refreshBaseLabelsSoon(delay = 80, followup = false) {
  window.clearTimeout(baseLabelTimer);
  window.clearTimeout(baseLabelFollowupTimer);
  baseLabelTimer = window.setTimeout(() => {
    if (map.value) applyMapLabels(map.value, AMapRef.value, mapTheme.value);
    if (!followup) return;
    baseLabelFollowupTimer = window.setTimeout(() => {
      if (map.value) applyMapLabels(map.value, AMapRef.value, mapTheme.value);
    }, 320);
  }, delay);
}

function beginMapMove() {
  window.clearTimeout(movingTimer);
  if (!isMapMoving) {
    isMapMoving = true;
    document.body.classList.add("map-moving");
    if (map.value) applyMovingMapFeatures(map.value);
  }
  movingTimer = window.setTimeout(finishMapMove, 1200);
}

function finishMapMove() {
  isMapMoving = false;
  document.body.classList.remove("map-moving");
  if (map.value) applyMapLabels(map.value, AMapRef.value, mapTheme.value);
  syncCityLabelDensity();
  updateViewportState();
}

function endMapMove() {
  window.clearTimeout(movingTimer);
  movingTimer = window.setTimeout(finishMapMove, 180);
}

function fitAll() {
  if (!map.value || !visiblePlaces.value.length) return;
  const padding = [52, 32, 52, 32];
  const lngs = visiblePlaces.value.map((place) => Number(place.lng));
  const lats = visiblePlaces.value.map((place) => Number(place.lat));
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  if (minLng === maxLng && minLat === maxLat) {
    map.value.setZoomAndCenter(16, [minLng, minLat], true);
  } else {
    const bounds = new AMapRef.value.Bounds([minLng, minLat], [maxLng, maxLat]);
    map.value.setBounds(bounds, true, padding);
  }
  refreshBaseLabelsSoon(220, true);
}

function refreshVisiblePlaces() {
  if (selectedId.value && !visiblePlaces.value.some((place) => place.id === selectedId.value)) {
    selectedId.value = null;
    pendingPlace = null;
    focusToken++;
    infoWindow.value?.close();
  }
  renderMarkers(false);
}

function findNearby() {
  if (locating.value) return;
  if (nearbyMode.value) {
    nearbyMode.value = false;
    userLocation.value = null;
    actionMessage.value = "";
    refreshVisiblePlaces();
    return;
  }
  if (!navigator.geolocation) { actionMessage.value = "当前设备不支持定位。"; return; }
  const request = ++locationRequest;
  locating.value = true;
  actionMessage.value = "正在获取位置...";
  navigator.geolocation.getCurrentPosition((position) => {
    if (disposed || request !== locationRequest) return;
    locating.value = false;
    userLocation.value = { lng: position.coords.longitude, lat: position.coords.latitude };
    nearbyMode.value = true;
    nearbyRadius.value = 30;
    viewportBounds.value = null;
    actionMessage.value = "附近 30 公里，按距离排序";
    renderMarkers(true);
  }, () => {
    if (disposed || request !== locationRequest) return;
    locating.value = false;
    actionMessage.value = "定位失败，请检查浏览器定位权限。";
  }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
}

function expandNearby() {
  nearbyRadius.value = 100;
  actionMessage.value = "附近 100 公里，按距离排序";
  renderMarkers(true);
}

function currentBounds() {
  const bounds = map.value?.getBounds?.();
  const sw = bounds?.getSouthWest?.(), ne = bounds?.getNorthEast?.();
  return sw && ne ? { minLng: Number(sw.lng), minLat: Number(sw.lat), maxLng: Number(ne.lng), maxLat: Number(ne.lat) } : null;
}
function updateViewportState() {
  viewportDirty.value = !sameBounds(viewportBounds.value, currentBounds());
}
function searchViewport() {
  const bounds = currentBounds();
  if (!bounds) return;
  viewportBounds.value = bounds;
  viewportDirty.value = false;
  actionMessage.value = "已更新此区域的店家";
  refreshVisiblePlaces();
}

function randomPlace() {
  if (!visiblePlaces.value.length) {
    actionMessage.value = "当前筛选条件下没有可选店家。";
    return;
  }
  const target = visiblePlaces.value[Math.floor(Math.random() * visiblePlaces.value.length)];
  actionMessage.value = `随机选中：${target.name}`;
  focusPlace(target);
}

function toggleViewportFilter() {
  if (viewportBounds.value) {
    viewportBounds.value = null;
    actionMessage.value = "";
    refreshVisiblePlaces();
  } else { searchViewport(); }
}

function resetFilters() {
  Object.assign(filters.value, { category: "", recommend: "", city: "", author: "" });
  query.value = "";
  viewportBounds.value = null;
  nearbyMode.value = false;
  userLocation.value = null;
  nearbyRadius.value = 30;
  locationRequest++;
  locating.value = false;
  actionMessage.value = "";
  refreshVisiblePlaces();
}

function focusInitialPlace() {
  if (initialPlaceFocused.value || !infoWindow.value) return;
  const placeId = new URLSearchParams(window.location.search).get("place");
  if (!placeId) return;
  const target = domesticPlaces.value.find((place) => String(place.id) === String(placeId));
  if (!target) return;
  initialPlaceFocused.value = true;
  schedule(() => focusPlace(target), 120);
}

function toggleSidebar() {
  if (sidebarCollapsed.value) showList();
  else showMap();
}

function showList() {
  dismissLoading();
  if (!sidebarCollapsed.value) return;
  sidebarCollapsed.value = false;
  resizeMapSoon();
}

function showMap() {
  revealLoading();
  if (sidebarCollapsed.value) return;
  sidebarCollapsed.value = true;
  resizeMapSoon();
}

function toggleMapTheme() {
  mapTheme.value = mapTheme.value === "night" ? "day" : "night";
  map.value?.setMapStyle(mapTheme.value === "night" ? "amap://styles/dark" : "amap://styles/normal");
  refreshBaseLabelsSoon(220, true);
  document.body.classList.toggle("map-day", mapTheme.value === "day");
}

async function focusPlace(place) {
  selectedId.value = place.id;
  if (!infoWindow.value || mapPhase.value !== "ready") {
    pendingPlace = place;
    showMap();
    return;
  }
  pendingPlace = null;
  const token = ++focusToken;
  const lng = Number(place.lng);
  const lat = Number(place.lat);
  const position = new AMapRef.value.LngLat(lng, lat);
  if (isMobile()) {
    sidebarCollapsed.value = true;
    await nextTick();
    if (disposed || token !== focusToken || !map.value) return;
    map.value.resize();
    await waitFrame();
    await waitFrame();
    if (disposed || token !== focusToken || !map.value) return;
    map.value.resize();
  }
  const targetZoom = Math.max(map.value.getZoom(), isMobile() ? 16 : 15);
  const moveDuration = isMobile() ? 180 : 220;
  map.value.setZoomAndCenter(targetZoom, position, false, moveDuration);
  refreshBaseLabelsSoon(1000);
  schedule(() => {
    if (token !== focusToken) return;
    infoWindow.value.setContent(infoHtml(place, { deferImages: true }));
    infoWindow.value.open(map.value, position);
    hydrateDeferredImages();
  }, moveDuration + 80);
}

function removeSingleMarkerHandler(marker) {
  const previousHandler = singleMarkerHandlers.get(marker);
  if (!previousHandler) return;
  marker.off("click", previousHandler);
  singleMarkerHandlers.delete(marker);
}

function renderStoreClusterMarker(context) {
  removeSingleMarkerHandler(context.marker);
  context.marker.setContent(clusterCountHtml(context.count));
  context.marker.setOffset(new AMapRef.value.Pixel(-15, -15));
  context.marker.setExtData({ count: context.count });
}

function contextPlace(context) {
  const sources = [context.data, context.clusterData, context.marker?.getExtData?.()];
  for (const source of sources) {
    const entry = Array.isArray(source) ? source[0] : source;
    if (entry?.place) return entry.place;
  }
  return null;
}

function renderSingleMarker(context) {
  const place = contextPlace(context);
  if (!place) return;
  context.marker.setContent(storeMarkerHtml(place));
  context.marker.setOffset(new AMapRef.value.Pixel(-14, -14));
  context.marker.setExtData({ place, placeId: place.id, city: place.city || "" });
  removeSingleMarkerHandler(context.marker);
  const clickHandler = () => focusPlace(place);
  singleMarkerHandlers.set(context.marker, clickHandler);
  context.marker.on("click", clickHandler);
}

function handleMapComplete() {
  mapReady();
  if (pendingPlace) focusPlace(pendingPlace);
  syncCityLabelDensity();
  refreshBaseLabelsSoon(80, true);
}

function handleZoomEnd() {
  endMapMove();
  syncMarkerMode();
  schedule(syncCityLabelDensity, 80);
}

async function initializeMap() {
  const generation = beginLoading();
  if (map.value) {
    clearMarkerClusters();
    infoWindow.value?.close();
    infoWindow.value = null;
    map.value.destroy();
    map.value = null;
  }
  try {
    const api = await loadAmap();
    await loadAmapPlugin(api, ["AMap.MarkerCluster", "AMap.Scale"]);
    if (!currentLoading(generation)) return;
    AMapRef.value = api;
    mapRendering();
    map.value = new api.Map("publicMap", { ...mapOptions(), mapStyle: mapTheme.value === "day" ? "amap://styles/normal" : "amap://styles/dark" });
    map.value.on("complete", handleMapComplete);
    map.value.on("movestart", beginMapMove);
    map.value.on("dragstart", beginMapMove);
    map.value.on("moveend", endMapMove);
    map.value.on("dragend", endMapMove);
    map.value.on("zoomstart", beginMapMove);
    map.value.on("zoomend", handleZoomEnd);
    scaleControl = new api.Scale();
    map.value.addControl(scaleControl);
    infoWindow.value = new api.InfoWindow({ autoMove: false, closeWhenClickMap: true, offset: new api.Pixel(0, -20), showShadow: false });
    applyMapLabels(map.value, api, mapTheme.value);
    renderMarkers(!initialFitDone);
    focusInitialPlace();
    resizeMapSoon();
  } catch (err) {
    if (currentLoading(generation)) mapFailed(err.message);
  }
}

onMounted(() => {
  document.body.classList.toggle("map-day", mapTheme.value === "day");
  try { adSlotDismissed.value = window.sessionStorage.getItem(AD_SLOT_SESSION_KEY) === "true"; } catch { /* Optional preference. */ }
  loadFilters().catch(() => {});
  loadPlaces();
  initializeMap();
});

onUnmounted(() => {
  disposed = true;
  placesRequestId++;
  locationRequest++;
  clearTimeout(searchTimer);
  focusToken += 1;
  window.clearTimeout(baseLabelTimer);
  window.clearTimeout(baseLabelFollowupTimer);
  window.clearTimeout(movingTimer);
  pendingTimers.forEach((timer) => window.clearTimeout(timer));
  pendingTimers.clear();
  document.body.classList.remove("map-moving", "map-day");

  if (map.value) {
    map.value.off("complete", handleMapComplete);
    map.value.off("movestart", beginMapMove);
    map.value.off("dragstart", beginMapMove);
    map.value.off("moveend", endMapMove);
    map.value.off("dragend", endMapMove);
    map.value.off("zoomstart", beginMapMove);
    map.value.off("zoomend", handleZoomEnd);
  }
  infoWindow.value?.close();
  clearMarkerClusters();
  if (scaleControl && map.value) map.value.removeControl?.(scaleControl);
  map.value?.destroy?.();

  infoWindow.value = null;
  markerCluster.value = null;
  cityMarkers.value = [];
  storeMarkerData = [];
  map.value = null;
  AMapRef.value = null;
  scaleControl = null;
});
</script>

<template>
  <main class="app-shell browse-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed, 'is-booting': loadingScreen }" :inert="loadingScreen || null" :aria-busy="loadingScreen">
    <button class="sidebar-toggle desktop-sidebar-toggle" type="button" :aria-expanded="String(!sidebarCollapsed)" aria-controls="foodSidebar" @click="toggleSidebar">
      {{ sidebarCollapsed ? "展开列表" : "隐藏列表" }}
    </button>
    <div class="map-actions" aria-label="地图显示设置">
      <div class="mobile-view-switch" role="group" aria-label="页面视图">
        <button
          class="map-action-btn"
          :class="{ 'is-active': !sidebarCollapsed }"
          type="button"
          aria-label="详细列表"
          title="详细列表"
          @click="showList"
        >
          <List :size="20" :stroke-width="1.8" aria-hidden="true" />
        </button>
        <button
          class="map-action-btn"
          :class="{ 'is-active': sidebarCollapsed }"
          type="button"
          aria-label="地图"
          title="地图"
          @click="showMap"
        >
          <MapIcon :size="20" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </div>
      <button
        class="map-action-btn theme-action"
        type="button"
        :aria-label="mapTheme === 'night' ? '切换到日间地图' : '切换到夜间地图'"
        :title="mapTheme === 'night' ? '日间地图' : '夜间地图'"
        @click="toggleMapTheme"
      >
        <Sun v-if="mapTheme === 'night'" :size="21" :stroke-width="1.7" aria-hidden="true" />
        <Moon v-else :size="21" :stroke-width="1.7" aria-hidden="true" />
      </button>
    </div>
    <aside
      ref="sidePanelElement"
      id="foodSidebar"
      v-show="!sidebarCollapsed"
      class="side-panel"
    >
      <header>
        <div class="mobile-expanded-header">
          <p class="eyebrow">DUSKRAIN TASTE MAP</p>
          <h1>DuskRain美食地图</h1>
          <p class="subtle">每一份评分，都来自亲自到店的体验。</p>
          <div class="browse-overview"><span><strong>{{ domesticPlaces.length }}</strong> 家店</span><span><strong>{{ cityOptions.length }}</strong> 个地区</span><span><strong>{{ authorOptions.length }}</strong> 位作者</span></div>
          <div v-if="!ADS_ENABLED && !guidePromoDismissed" class="annual-guide-wrap">
            <a class="annual-guide-entry" href="/food-map/guide/2026/">
              <span>LÜ GUIDE · ÉDITION 2026</span>
              <strong>2026 吕其林指南，即将发布</strong>
              <small>Publication en janvier 2027 →</small>
            </a>
            <button
              class="annual-guide-dismiss"
              type="button"
              aria-label="关闭指南预告"
              title="关闭指南预告"
              @click="dismissGuidePromo"
            >
              <X :size="16" :stroke-width="1.8" aria-hidden="true" />
            </button>
          </div>
          <aside
            v-if="ADS_ENABLED && !adSlotDismissed"
            class="google-ad-reserve"
            aria-label="Google Ads 广告预留位"
          >
            <button
              class="google-ad-close"
              type="button"
              aria-label="关闭广告位"
              title="关闭广告位"
              @click="dismissAdSlot"
            >
              <X :size="16" :stroke-width="1.8" aria-hidden="true" />
            </button>
            <button
              class="google-ad-arrow google-ad-arrow-prev"
              type="button"
              aria-label="上一条广告"
              title="上一条广告"
              @click="switchAdSlot(-1)"
            >
              <ChevronLeft :size="18" :stroke-width="1.8" aria-hidden="true" />
            </button>
            <div class="google-ad-content" aria-live="polite">
              <span>ADVERTISEMENT</span>
              <strong>Google Ads</strong>
              <small>{{ adSlots[adSlotIndex] }}</small>
            </div>
            <button
              class="google-ad-arrow google-ad-arrow-next"
              type="button"
              aria-label="下一条广告"
              title="下一条广告"
              @click="switchAdSlot(1)"
            >
              <ChevronRight :size="18" :stroke-width="1.8" aria-hidden="true" />
            </button>
            <div class="google-ad-dots" aria-hidden="true">
              <span
                v-for="(_, index) in adSlots"
                :key="index"
                :class="{ 'is-active': index === adSlotIndex }"
              ></span>
            </div>
          </aside>
        </div>
        <div class="mobile-compact-summary">
          <strong>DuskRain美食地图</strong>
          <span>当前 {{ visiblePlaces.length }} 家</span>
          <button
            v-if="hasActiveFilters"
            class="mobile-compact-reset"
            type="button"
            aria-label="重置筛选"
            title="重置筛选"
            @click="resetFilters"
          >
            <RotateCcw :size="16" :stroke-width="1.8" aria-hidden="true" />
          </button>
        </div>
      </header>
      <div class="provider-switch">
        <span class="provider-switch-btn is-active">国内高德</span>
        <a class="provider-switch-btn" href="/food-map/global/">国外 Google</a>
      </div>

      <div class="browse-controls">
        <label class="browse-search"><Search :size="17" aria-hidden="true" /><input v-model="query" type="search" placeholder="搜索店名、城市或地址" aria-label="搜索店家" /></label>
      <section class="toolbar">
        <div class="field" :class="{ 'is-active': filters.category }">
          <label for="categoryFilter">分类</label>
          <select id="categoryFilter" v-model="filters.category" @change="refreshVisiblePlaces">
            <option value="">全部分类</option>
            <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
          </select>
        </div>
        <div class="field" :class="{ 'is-active': filters.recommend }">
          <label for="recommendFilter">推荐</label>
          <select id="recommendFilter" v-model="filters.recommend" @change="refreshVisiblePlaces">
            <option value="">全部推荐</option>
            <option v-for="level in recommendLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </div>
        <div class="field" :class="{ 'is-active': filters.city }">
          <label for="cityFilter">城市</label>
          <select id="cityFilter" v-model="filters.city" @change="renderMarkers(true)">
            <option value="">全部城市</option>
            <option v-for="city in cityOptions" :key="city" :value="city">{{ city }}</option>
          </select>
        </div>
        <div class="field" :class="{ 'is-active': filters.author }">
          <label for="authorFilter">作者</label>
          <select id="authorFilter" v-model="filters.author" @change="refreshVisiblePlaces">
            <option value="">全部作者</option>
            <option v-for="author in authorOptions" :key="author" :value="author">{{ author }}</option>
          </select>
        </div>
      </section>

      <div class="browse-result"><span>{{ hasActiveFilters ? '筛选结果' : '全部店家' }} <strong>{{ visiblePlaces.length }}</strong> 家</span><button v-if="hasActiveFilters" class="browse-reset" type="button" @click="resetFilters"><RotateCcw :size="13" />重置</button></div>
      </div>
      <div class="explore-toolbar">
        <div class="explore-actions">
          <button class="btn secondary action-command" :class="{ 'is-active': nearbyMode }" type="button" :disabled="locating" @click="findNearby">
            <MapPin :size="17" :stroke-width="1.8" aria-hidden="true" />
            <span>{{ locating ? "定位中" : nearbyMode ? "取消附近" : "附近店家" }}</span>
          </button>
          <button class="btn secondary action-command" type="button" :disabled="!visiblePlaces.length" @click="randomPlace">
            <Shuffle :size="17" :stroke-width="1.8" aria-hidden="true" />
            <span>随机探店</span>
          </button>
          <button class="btn secondary action-command viewport-command" :class="{ 'is-active': viewportBounds }" type="button" :disabled="mapPhase !== 'ready'" @click="toggleViewportFilter">
            <ScanSearch :size="17" :stroke-width="1.8" aria-hidden="true" />
            <span>{{ viewportBounds ? "取消视野" : "当前视野" }}</span>
          </button>
          <button v-if="hasActiveFilters" class="btn secondary action-command reset-command" type="button" @click="resetFilters">
            <RotateCcw :size="16" :stroke-width="1.8" aria-hidden="true" />
            <span>重置筛选</span>
          </button>
        </div>
        <span class="result-count" aria-live="polite">当前 {{ visiblePlaces.length }} 家</span>
      </div>
      <div v-if="actionMessage" class="status-line">{{ actionMessage }}</div>

      <section ref="listElement" class="list" aria-live="polite" :aria-busy="loadingPlaces">
        <div v-if="loadingPlaces && !places.length" class="list-skeleton" role="status" aria-label="店家加载中"><div v-for="n in 3" :key="n"><i /><i /><i /></div></div>
        <article v-else-if="error" class="place-item">
          <p class="subtle">{{ error }}</p><button class="btn secondary" type="button" @click="loadPlaces">重新加载店家</button>
        </article>
        <article v-else-if="!visiblePlaces.length" class="place-item">
          <p class="subtle">{{ nearbyMode ? `附近 ${nearbyRadius} 公里没有符合条件的店家。` : hasActiveFilters ? "当前筛选条件下没有店家，请调整筛选项。" : "还没有公开店铺。" }}</p>
        </article>
        <button v-if="nearbyMode && !visiblePlaces.length && nearbyRadius === 30" class="btn secondary" type="button" @click="expandNearby">扩大到 100 公里</button>
        <BrowsePlaceCard v-for="place in visiblePlaces" :key="place.id" :place="place" :selected="selectedId === place.id" :address="formatAddress(place)" :image="imageList(place)[0]" :categories="placeCategories(place)" :review-href="`/food-map/review/${place.id}`" @select="focusPlace" />
      </section>
    </aside>
    <section class="map-stage">
      <div id="publicMap" class="map-canvas"></div>
      <button v-if="mapPhase === 'ready' && viewportDirty" class="area-search btn action-command" type="button" @click="searchViewport"><ScanSearch :size="16" />搜索这片区域</button>
    </section>
    <MapLoading :visible="loadingScreen" :phase="loadingPhase" :message="mapMessage" :theme="mapTheme" provider="AMAP" @retry="initializeMap" @list="showList" @theme="toggleMapTheme" />
  </main>
</template>
