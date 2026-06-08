<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { List, Map as MapIcon, Moon, Sun } from "@lucide/vue";
import { getCategories, getPublicPlaces } from "../utils/api";
import { applyMapLabels, applyMovingMapFeatures, cityClusterHtml, clusterCountHtml, formatAddress, hydrateDeferredImages, imageList, infoHtml, loadAmap, loadAmapPlugin, mapOptions, scheduleCityMapPrewarm, schedulePlaceImagePreload, storeMarkerHtml } from "../utils/map";

const AMapRef = shallowRef(null);
const map = shallowRef(null);
const infoWindow = shallowRef(null);
const places = ref([]);
const markerClusters = shallowRef([]);
const categories = ref([]);
const recommendLevels = ref([]);
const filters = ref({ category: "", recommend: "", city: "", author: "" });
const nearbyMode = ref(false);
const userLocation = ref(null);
const actionMessage = ref("");
const mapTheme = ref("day");
const sidebarCollapsed = ref(false);
const initialPlaceFocused = ref(false);
const error = ref("");
const CITY_OVERVIEW_MAX_ZOOM = 7.5;
let baseLabelTimer = 0;
let baseLabelFollowupTimer = 0;
let focusToken = 0;
let movingTimer = 0;
let isMapMoving = false;
let pointerStart = null;
let pointerDragging = false;
let mapElement = null;
let scaleControl = null;
const pendingTimers = new Set();
const singleMarkerHandlers = new WeakMap();

const domesticPlaces = computed(() => places.value.filter((place) => (place.map_provider || "amap") === "amap"));

const cityOptions = computed(() => {
  return [...new Set(domesticPlaces.value.map((place) => place.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
});

const authorOptions = computed(() => {
  return [...new Set(domesticPlaces.value.map((place) => place.rating_author).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
});

const visiblePlaces = computed(() => {
  const filtered = domesticPlaces.value.filter((place) => {
    if (filters.value.city && place.city !== filters.value.city) return false;
    if (filters.value.author && place.rating_author !== filters.value.author) return false;
    return true;
  });
  if (nearbyMode.value && userLocation.value) {
    const withDistance = filtered
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
  return [...filtered].sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0));
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
  places.value = await getPublicPlaces(filters.value);
  await nextTick();
  renderMarkers();
  focusInitialPlace();
  scheduleCityMapPrewarm(AMapRef.value, domesticPlaces.value);
  schedulePlaceImagePreload(domesticPlaces.value);
}

function renderMarkers() {
  if (!map.value || !AMapRef.value) return;
  clearMarkerClusters();
  markerClusters.value = groupPlacesByCity(visiblePlaces.value).map(({ city, places: cityPlaces }) => (
    new AMapRef.value.MarkerCluster(
      map.value,
      cityPlaces.map((place) => ({
        lnglat: [Number(place.lng), Number(place.lat)],
        place,
      })),
      {
        gridSize: isMobile() ? 44 : 52,
        averageCenter: true,
        clusterByZoomChange: false,
        renderClusterMarker: (context) => renderCityClusterMarker(context, city),
        renderMarker: (context) => renderSingleMarker(context, city, cityPlaces.length),
      },
    )
  ));
  fitAll();
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
  markerClusters.value.forEach((cluster) => {
    cluster.clearMarkers?.();
    cluster.setMap?.(null);
  });
  markerClusters.value = [];
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
  refreshBaseLabelsSoon(260);
}

function endMapMove() {
  window.clearTimeout(movingTimer);
  movingTimer = window.setTimeout(finishMapMove, 180);
}

function handlePointerDown(event) {
  const point = event.touches?.[0] || event;
  pointerStart = { x: point.clientX, y: point.clientY };
  pointerDragging = false;
}

function handlePointerMove(event) {
  if (!pointerStart || pointerDragging) return;
  const point = event.touches?.[0] || event;
  const dx = Math.abs(point.clientX - pointerStart.x);
  const dy = Math.abs(point.clientY - pointerStart.y);
  if (dx < 6 && dy < 6) return;
  pointerDragging = true;
  beginMapMove();
}

function handlePointerEnd() {
  if (pointerDragging) endMapMove();
  pointerStart = null;
  pointerDragging = false;
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

function renderCityClusterMarker(context, city) {
  removeSingleMarkerHandler(context.marker);
  const showCity = map.value.getZoom() <= CITY_OVERVIEW_MAX_ZOOM;
  context.marker.setContent(showCity ? cityClusterHtml(city, context.count) : clusterCountHtml(context.count));
  context.marker.setOffset(new AMapRef.value.Pixel(-15, -15));
  context.marker.setExtData({ city, count: context.count });
}

function contextPlace(context) {
  const sources = [context.data, context.clusterData, context.marker?.getExtData?.()];
  for (const source of sources) {
    const entry = Array.isArray(source) ? source[0] : source;
    if (entry?.place) return entry.place;
  }
  return null;
}

function renderSingleMarker(context, city, cityTotal) {
  const place = contextPlace(context);
  if (!place) return;
  const showCityOverview = cityTotal === 1 && map.value.getZoom() <= CITY_OVERVIEW_MAX_ZOOM;
  context.marker.setContent(showCityOverview ? cityClusterHtml(city, 1) : storeMarkerHtml(place));
  context.marker.setOffset(new AMapRef.value.Pixel(showCityOverview ? -15 : -14, showCityOverview ? -15 : -14));
  context.marker.setExtData({ place, placeId: place.id, city });
  removeSingleMarkerHandler(context.marker);
  const clickHandler = () => focusPlace(place);
  singleMarkerHandlers.set(context.marker, clickHandler);
  context.marker.on("click", clickHandler);
}

function handleMapComplete() {
  refreshBaseLabelsSoon(80, true);
}

function handleZoomEnd() {
  refreshBaseLabelsSoon(220);
}

onMounted(async () => {
  try {
    document.body.classList.add("map-day");
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
    map.value.on("zoomend", handleZoomEnd);
    mapElement = document.getElementById("publicMap");
    mapElement?.addEventListener("pointerdown", handlePointerDown, { passive: true });
    mapElement?.addEventListener("pointermove", handlePointerMove, { passive: true });
    mapElement?.addEventListener("mousedown", handlePointerDown, { passive: true });
    mapElement?.addEventListener("mousemove", handlePointerMove, { passive: true });
    mapElement?.addEventListener("touchstart", handlePointerDown, { passive: true });
    mapElement?.addEventListener("touchmove", handlePointerMove, { passive: true });
    window.addEventListener("pointerup", handlePointerEnd, { passive: true });
    window.addEventListener("pointercancel", handlePointerEnd, { passive: true });
    window.addEventListener("mouseup", handlePointerEnd, { passive: true });
    window.addEventListener("touchend", handlePointerEnd, { passive: true });
    window.addEventListener("touchcancel", handlePointerEnd, { passive: true });
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
  pendingTimers.forEach((timer) => window.clearTimeout(timer));
  pendingTimers.clear();
  document.body.classList.remove("map-moving", "map-day");

  mapElement?.removeEventListener("pointerdown", handlePointerDown);
  mapElement?.removeEventListener("pointermove", handlePointerMove);
  mapElement?.removeEventListener("mousedown", handlePointerDown);
  mapElement?.removeEventListener("mousemove", handlePointerMove);
  mapElement?.removeEventListener("touchstart", handlePointerDown);
  mapElement?.removeEventListener("touchmove", handlePointerMove);
  window.removeEventListener("pointerup", handlePointerEnd);
  window.removeEventListener("pointercancel", handlePointerEnd);
  window.removeEventListener("mouseup", handlePointerEnd);
  window.removeEventListener("touchend", handlePointerEnd);
  window.removeEventListener("touchcancel", handlePointerEnd);

  if (map.value) {
    map.value.off("complete", handleMapComplete);
    map.value.off("movestart", beginMapMove);
    map.value.off("dragstart", beginMapMove);
    map.value.off("moveend", endMapMove);
    map.value.off("dragend", endMapMove);
    map.value.off("zoomend", handleZoomEnd);
  }
  infoWindow.value?.close();
  clearMarkerClusters();
  if (scaleControl && map.value) map.value.removeControl?.(scaleControl);
  map.value?.destroy?.();

  infoWindow.value = null;
  markerClusters.value = [];
  map.value = null;
  AMapRef.value = null;
  mapElement = null;
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
    <aside id="foodSidebar" v-show="!sidebarCollapsed" class="side-panel">
      <header>
        <p class="eyebrow">DUSKRAIN TASTE MAP</p>
        <h1>吕其林美食指南</h1>
        <p class="subtle">把亲自吃过、想推荐、需要避雷的店铺标在地图上，按分类和推荐等级快速筛选。</p>
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

      <div class="button-row">
        <button class="btn secondary" type="button" @click="findNearby">{{ nearbyMode ? "取消附近" : "附近店家" }}</button>
        <button class="btn secondary" type="button" @click="randomPlace">随机探店</button>
      </div>
      <div v-if="actionMessage" class="status-line">{{ actionMessage }}</div>

      <section class="list" aria-live="polite">
        <article v-if="error" class="place-item">
          <p class="subtle">{{ error }}</p>
        </article>
        <article v-else-if="!visiblePlaces.length" class="place-item">
          <p class="subtle">还没有公开店铺。进入管理页添加第一家店。</p>
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
            <span v-if="place.my_category" class="pill">{{ place.my_category }}</span>
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
