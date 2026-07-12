<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { List, Map as MapIcon, MapPin, Moon, RotateCcw, ScanSearch, Shuffle, Sun } from "@lucide/vue";
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
const sidePanelElement = ref(null);
const listElement = ref(null);
const mobileHeaderCollapsing = ref(false);
const mobileHeaderCompact = ref(false);
const mobileFilterHorizontal = ref(false);
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
let mobileCollapseFrame = 0;
let pendingMobileScrollTop = 0;
let expandedMobileHeaderHeight = 0;
let expandedMobileProviderHeight = 0;
let expandedMobileToolbarHeight = 0;
let expandedMobileActionsHeight = 0;
let expandedMobileStatusHeight = 0;
const pendingTimers = new Set();
const singleMarkerHandlers = new WeakMap();
const MOBILE_COLLAPSE_END = 215;

const domesticPlaces = computed(() => places.value.filter((place) => (place.map_provider || "amap") === "amap"));

const cityOptions = computed(() => {
  return [...new Set(domesticPlaces.value.map((place) => place.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
});

const authorOptions = computed(() => {
  return [...new Set(domesticPlaces.value.map((place) => place.rating_author).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
});

const hasActiveFilters = computed(() => Object.values(filters.value).some(Boolean) || Boolean(viewportBounds.value));

const visiblePlaces = computed(() => {
  const filtered = domesticPlaces.value.filter((place) => {
    if (filters.value.city && place.city !== filters.value.city) return false;
    if (filters.value.author && place.rating_author !== filters.value.author) return false;
    return true;
  });
  const inViewport = viewportBounds.value
    ? filtered.filter((place) => (
      Number(place.lng) >= viewportBounds.value.minLng
      && Number(place.lng) <= viewportBounds.value.maxLng
      && Number(place.lat) >= viewportBounds.value.minLat
      && Number(place.lat) <= viewportBounds.value.maxLat
    ))
    : filtered;
  if (nearbyMode.value && userLocation.value) {
    const withDistance = inViewport
      .map((place) => ({
        ...place,
        distanceKm: distanceKm(
          userLocation.value.lng,
          userLocation.value.lat,
          Number(place.lng),
          Number(place.lat),
        ),
      }))
      .sort((a, b) => a.distanceKm - b.distanceKm);
    const inRange = withDistance.filter((place) => place.distanceKm <= 30);
    return inRange.length ? inRange : withDistance.slice(0, 10);
  }
  return [...inViewport].sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0));
});

function distanceKm(lng1, lat1, lng2, lat2) {
  const radians = (value) => value * Math.PI / 180;
  const dLat = radians(lat2 - lat1);
  const dLng = radians(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function isMobile() {
  return window.matchMedia("(max-width: 860px)").matches;
}

function stage(value, start, end) {
  return Math.max(0, Math.min(1, (value - start) / (end - start)));
}

function setMobileVariable(panel, name, value) {
  panel.style.setProperty(name, value);
}

function clearMobileCollapse() {
  const panel = sidePanelElement.value;
  mobileHeaderCollapsing.value = false;
  mobileHeaderCompact.value = false;
  mobileFilterHorizontal.value = false;
  expandedMobileHeaderHeight = 0;
  expandedMobileProviderHeight = 0;
  expandedMobileToolbarHeight = 0;
  expandedMobileActionsHeight = 0;
  expandedMobileStatusHeight = 0;
  if (!panel) return;
  [
    "--mobile-header-height",
    "--mobile-expanded-opacity",
    "--mobile-summary-opacity",
    "--mobile-provider-height",
    "--mobile-provider-opacity",
    "--mobile-toolbar-height",
    "--mobile-toolbar-opacity",
    "--mobile-actions-height",
    "--mobile-actions-opacity",
    "--mobile-status-height",
    "--mobile-status-opacity",
    "--mobile-header-gap",
    "--mobile-provider-gap",
    "--mobile-toolbar-gap",
    "--mobile-actions-gap",
    "--mobile-status-gap",
  ].forEach((name) => panel.style.removeProperty(name));
}

function applyMobileCollapse(scrollTop) {
  const panel = sidePanelElement.value;
  if (!panel || !isMobile() || scrollTop <= 0.5) {
    clearMobileCollapse();
    return;
  }

  const expandedHeader = panel.querySelector(".mobile-expanded-header");
  const provider = panel.querySelector(":scope > .provider-switch");
  const toolbar = panel.querySelector(":scope > .toolbar");
  const actions = panel.querySelector(":scope > .explore-toolbar");
  const status = panel.querySelector(":scope > .status-line");
  if (!expandedMobileHeaderHeight && expandedHeader) expandedMobileHeaderHeight = expandedHeader.scrollHeight;
  if (!expandedMobileProviderHeight && provider) expandedMobileProviderHeight = provider.scrollHeight;
  if (!expandedMobileToolbarHeight && toolbar) expandedMobileToolbarHeight = toolbar.scrollHeight;
  if (!expandedMobileActionsHeight && actions) expandedMobileActionsHeight = actions.scrollHeight;
  if (!expandedMobileStatusHeight && status) expandedMobileStatusHeight = status.scrollHeight;

  const progress = Math.min(1, scrollTop / MOBILE_COLLAPSE_END);
  const headerProgress = stage(scrollTop, 0, 95);
  const summaryProgress = stage(scrollTop, 45, 105);
  const providerProgress = stage(scrollTop, 55, 150);
  const toolbarProgress = stage(scrollTop, 145, MOBILE_COLLAPSE_END);
  const actionsProgress = stage(scrollTop, 115, MOBILE_COLLAPSE_END);
  const toolbarOpacity = scrollTop < 180
    ? 1 - stage(scrollTop, 145, 180)
    : stage(scrollTop, 180, MOBILE_COLLAPSE_END);
  const baseGap = 12 - progress * 4;
  const expandedHeaderHeight = expandedMobileHeaderHeight || 118;
  const providerHeight = expandedMobileProviderHeight;
  const actionsHeight = expandedMobileActionsHeight;
  const statusHeight = expandedMobileStatusHeight;

  setMobileVariable(panel, "--mobile-header-height", `${expandedHeaderHeight + (30 - expandedHeaderHeight) * headerProgress}px`);
  setMobileVariable(panel, "--mobile-expanded-opacity", String(1 - headerProgress));
  setMobileVariable(panel, "--mobile-summary-opacity", String(summaryProgress));
  setMobileVariable(panel, "--mobile-provider-height", `${providerHeight * (1 - providerProgress)}px`);
  setMobileVariable(panel, "--mobile-provider-opacity", String(1 - stage(scrollTop, 55, 105)));
  setMobileVariable(panel, "--mobile-toolbar-height", `${expandedMobileToolbarHeight + (40 - expandedMobileToolbarHeight) * toolbarProgress}px`);
  setMobileVariable(panel, "--mobile-toolbar-opacity", String(toolbarOpacity));
  setMobileVariable(panel, "--mobile-actions-height", `${actionsHeight * (1 - actionsProgress)}px`);
  setMobileVariable(panel, "--mobile-actions-opacity", String(1 - actionsProgress));
  setMobileVariable(panel, "--mobile-status-height", `${statusHeight * (1 - actionsProgress)}px`);
  setMobileVariable(panel, "--mobile-status-opacity", String(1 - actionsProgress));
  setMobileVariable(panel, "--mobile-header-gap", `${baseGap}px`);
  setMobileVariable(panel, "--mobile-provider-gap", `${baseGap * (1 - providerProgress)}px`);
  setMobileVariable(panel, "--mobile-toolbar-gap", `${baseGap}px`);
  setMobileVariable(panel, "--mobile-actions-gap", `${baseGap * (1 - actionsProgress)}px`);
  setMobileVariable(panel, "--mobile-status-gap", `${baseGap * (1 - actionsProgress)}px`);

  mobileHeaderCollapsing.value = true;
  mobileFilterHorizontal.value = scrollTop >= 180;
  mobileHeaderCompact.value = scrollTop >= MOBILE_COLLAPSE_END;
}

function handleListScroll(event) {
  pendingMobileScrollTop = event.currentTarget.scrollTop;
  if (mobileCollapseFrame) return;
  mobileCollapseFrame = window.requestAnimationFrame(() => {
    mobileCollapseFrame = 0;
    applyMobileCollapse(pendingMobileScrollTop);
  });
}

function handleViewportResize() {
  if (!isMobile()) clearMobileCollapse();
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
    const loadedPlaces = await getPublicPlaces(filters.value);
    if (requestId !== placesRequestId) return;
    places.value = loadedPlaces;
    if (filters.value.city && !cityOptions.value.includes(filters.value.city)) filters.value.city = "";
    if (filters.value.author && !authorOptions.value.includes(filters.value.author)) filters.value.author = "";
    error.value = "";
    await nextTick();
    renderMarkers();
    focusInitialPlace();
  } catch (err) {
    if (requestId !== placesRequestId) return;
    error.value = err.message;
  }
}

function renderMarkers(fit = true) {
  if (!map.value || !AMapRef.value) return;
  clearMarkerClusters();
  storeMarkerData = visiblePlaces.value.map((place) => ({
    lnglat: [Number(place.lng), Number(place.lat)],
    place,
  }));
  if (storeMarkerData.length) {
    cityMarkers.value = groupPlacesByCity(visiblePlaces.value).map(createCityMarker);
    syncMarkerMode(true);
  }
  if (fit) fitAll();
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
  map.value.setBounds(bounds, true, isMobile() ? [52, 32, 52, 32] : [60, 60, 60, 460]);
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
    if (infoWindow.value) infoWindow.value.close();
    if (map.value) applyMovingMapFeatures(map.value);
  }
  movingTimer = window.setTimeout(finishMapMove, 1200);
}

function finishMapMove() {
  isMapMoving = false;
  document.body.classList.remove("map-moving");
  if (map.value) applyMapLabels(map.value, AMapRef.value, mapTheme.value);
  syncCityLabelDensity();
  refreshBaseLabelsSoon(260);
}

function endMapMove() {
  window.clearTimeout(movingTimer);
  movingTimer = window.setTimeout(finishMapMove, 180);
}

function fitAll() {
  if (!visiblePlaces.value.length) return;
  const padding = isMobile() ? [52, 32, 52, 32] : [60, 60, 60, 460];
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
  renderMarkers();
}

function findNearby() {
  if (nearbyMode.value) {
    nearbyMode.value = false;
    actionMessage.value = "";
    refreshVisiblePlaces();
    return;
  }
  if (!navigator.geolocation) {
    actionMessage.value = "当前设备不支持定位。";
    return;
  }
  actionMessage.value = "正在获取位置...";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      userLocation.value = {
        lng: Number(position.coords.longitude),
        lat: Number(position.coords.latitude),
      };
      nearbyMode.value = true;
      actionMessage.value = "已按距离显示附近店家。";
      refreshVisiblePlaces();
      if (visiblePlaces.value[0]) schedule(() => focusPlace(visiblePlaces.value[0]), 120);
    },
    () => {
      actionMessage.value = "定位失败，请检查浏览器定位权限。";
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
  );
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
    renderMarkers();
    return;
  }
  const bounds = map.value?.getBounds?.();
  const southWest = bounds?.getSouthWest?.();
  const northEast = bounds?.getNorthEast?.();
  if (!southWest || !northEast) {
    actionMessage.value = "当前地图视野暂不可读取。";
    return;
  }
  viewportBounds.value = {
    minLng: Number(southWest.lng),
    minLat: Number(southWest.lat),
    maxLng: Number(northEast.lng),
    maxLat: Number(northEast.lat),
  };
  actionMessage.value = "已筛选当前地图视野。";
  renderMarkers(false);
}

async function resetFilters() {
  Object.assign(filters.value, { category: "", recommend: "", city: "", author: "" });
  viewportBounds.value = null;
  actionMessage.value = "";
  await loadPlaces();
}

function focusInitialPlace() {
  if (initialPlaceFocused.value) return;
  const placeId = new URLSearchParams(window.location.search).get("place");
  if (!placeId) return;
  const target = domesticPlaces.value.find((place) => String(place.id) === String(placeId));
  if (!target) return;
  initialPlaceFocused.value = true;
  schedule(() => focusPlace(target), 120);
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  resizeMapSoon();
}

function showList() {
  if (!sidebarCollapsed.value) return;
  sidebarCollapsed.value = false;
  resizeMapSoon();
}

function showMap() {
  if (sidebarCollapsed.value) return;
  sidebarCollapsed.value = true;
  resizeMapSoon();
}

function toggleMapTheme() {
  mapTheme.value = mapTheme.value === "night" ? "day" : "night";
  map.value.setMapStyle(mapTheme.value === "night" ? "amap://styles/dark" : "amap://styles/normal");
  refreshBaseLabelsSoon(220, true);
  document.body.classList.toggle("map-day", mapTheme.value === "day");
}

async function focusPlace(place) {
  const token = ++focusToken;
  const lng = Number(place.lng);
  const lat = Number(place.lat);
  const position = new AMapRef.value.LngLat(lng, lat);
  if (isMobile()) {
    sidebarCollapsed.value = true;
    await nextTick();
    map.value.resize();
    await waitFrame();
    await waitFrame();
    map.value.resize();
  }
  const targetZoom = isMobile() ? 16 : Math.max(map.value.getZoom(), 15);
  const moveDuration = isMobile() ? 180 : 220;
  map.value.setZoomAndCenter(targetZoom, position, false, moveDuration);
  refreshBaseLabelsSoon(1000);
  schedule(() => {
    if (token !== focusToken) return;
    infoWindow.value.setContent(infoHtml(place, { deferImages: true }));
    infoWindow.value.open(map.value, position);
    hydrateDeferredImages();
  }, Math.max(120, moveDuration - 40));
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
  syncCityLabelDensity();
  refreshBaseLabelsSoon(80, true);
}

function handleZoomEnd() {
  endMapMove();
  syncMarkerMode();
  schedule(syncCityLabelDensity, 80);
  refreshBaseLabelsSoon(220);
}

onMounted(async () => {
  try {
    document.body.classList.add("map-day");
    window.addEventListener("resize", handleViewportResize, { passive: true });
    AMapRef.value = await loadAmap();
    map.value = new AMapRef.value.Map("publicMap", {
      ...mapOptions(),
    });
    await loadAmapPlugin(AMapRef.value, ["AMap.MarkerCluster"]);
    applyMapLabels(map.value, AMapRef.value, mapTheme.value);
    map.value.on("complete", handleMapComplete);
    map.value.on("movestart", beginMapMove);
    map.value.on("dragstart", beginMapMove);
    map.value.on("moveend", endMapMove);
    map.value.on("dragend", endMapMove);
    map.value.on("zoomstart", beginMapMove);
    map.value.on("zoomend", handleZoomEnd);
    scaleControl = new AMapRef.value.Scale();
    map.value.addControl(scaleControl);
    infoWindow.value = new AMapRef.value.InfoWindow({
      autoMove: false,
      closeWhenClickMap: true,
      offset: new AMapRef.value.Pixel(0, -20),
      showShadow: false,
    });
    await loadFilters();
    await loadPlaces();
    resizeMapSoon();
  } catch (err) {
    error.value = err.message;
  }
});

onUnmounted(() => {
  focusToken += 1;
  window.clearTimeout(baseLabelTimer);
  window.clearTimeout(baseLabelFollowupTimer);
  window.clearTimeout(movingTimer);
  window.cancelAnimationFrame(mobileCollapseFrame);
  window.removeEventListener("resize", handleViewportResize);
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
  <main class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
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
      :class="{
        'mobile-header-collapsing': mobileHeaderCollapsing,
        'mobile-header-compact': mobileHeaderCompact,
        'mobile-filter-horizontal': mobileFilterHorizontal,
      }"
    >
      <header>
        <div class="mobile-expanded-header">
          <p class="eyebrow">DUSKRAIN TASTE MAP</p>
          <h1>吕其林美食指南</h1>
          <p class="subtle">把亲自吃过、想推荐、需要避雷的店铺标在地图上，按分类和推荐等级快速筛选。</p>
        </div>
        <div class="mobile-compact-summary">
          <strong>吕其林美食指南</strong>
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

      <section class="toolbar">
        <div class="field">
          <label for="categoryFilter">分类</label>
          <select id="categoryFilter" v-model="filters.category" @change="loadPlaces">
            <option value="">全部分类</option>
            <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
          </select>
        </div>
        <div class="field">
          <label for="recommendFilter">推荐</label>
          <select id="recommendFilter" v-model="filters.recommend" @change="loadPlaces">
            <option value="">全部推荐</option>
            <option v-for="level in recommendLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </div>
        <div class="field">
          <label for="cityFilter">城市</label>
          <select id="cityFilter" v-model="filters.city" @change="refreshVisiblePlaces">
            <option value="">全部城市</option>
            <option v-for="city in cityOptions" :key="city" :value="city">{{ city }}</option>
          </select>
        </div>
        <div class="field">
          <label for="authorFilter">作者</label>
          <select id="authorFilter" v-model="filters.author" @change="refreshVisiblePlaces">
            <option value="">全部作者</option>
            <option v-for="author in authorOptions" :key="author" :value="author">{{ author }}</option>
          </select>
        </div>
      </section>

      <div class="explore-toolbar">
        <div class="explore-actions">
          <button class="btn secondary action-command" :class="{ 'is-active': nearbyMode }" type="button" @click="findNearby">
            <MapPin :size="17" :stroke-width="1.8" aria-hidden="true" />
            <span>{{ nearbyMode ? "取消附近" : "附近店家" }}</span>
          </button>
          <button class="btn secondary action-command" type="button" @click="randomPlace">
            <Shuffle :size="17" :stroke-width="1.8" aria-hidden="true" />
            <span>随机探店</span>
          </button>
          <button class="btn secondary action-command viewport-command" :class="{ 'is-active': viewportBounds }" type="button" @click="toggleViewportFilter">
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

      <section ref="listElement" class="list" aria-live="polite" @scroll.passive="handleListScroll">
        <article v-if="error" class="place-item">
          <p class="subtle">{{ error }}</p>
        </article>
        <article v-else-if="!visiblePlaces.length" class="place-item">
          <p class="subtle">{{ hasActiveFilters ? "当前筛选条件下没有店家，请调整筛选项。" : "还没有公开店铺。" }}</p>
        </article>
        <article v-for="place in visiblePlaces" :key="place.id" class="place-item" @click="focusPlace(place)">
          <div class="item-title">
            <span>{{ place.name }}</span>
            <span class="rating">{{ place.rating ?? "-" }} / 10 · {{ place.rating_author || "吕俊泽" }}</span>
          </div>
          <div v-if="imageList(place).length && !place.hide_images" class="image-strip">
            <img v-for="url in imageList(place).slice(0, 1)" :key="url" :src="url" :alt="place.name" loading="lazy" decoding="async">
          </div>
          <div class="subtle">{{ formatAddress(place) }}</div>
          <div class="pill-row">
            <span v-if="place.distanceKm != null" class="pill">{{ place.distanceKm.toFixed(1) }} 公里</span>
            <span v-for="category in placeCategories(place)" :key="category" class="pill">{{ category }}</span>
            <span v-if="place.recommend_level" class="pill">{{ place.recommend_level }}</span>
            <span class="pill">美食评价</span>
            <span v-if="place.business_hours" class="pill">{{ place.business_hours }}</span>
          </div>
          <div v-if="place.phone" class="subtle">电话：{{ place.phone }}</div>
          <div v-if="place.note" class="subtle">{{ place.note }}</div>
        </article>
      </section>
    </aside>
    <section class="map-stage">
      <div id="publicMap" class="map-canvas"></div>
    </section>
  </main>
</template>
