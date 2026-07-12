<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { List, Map as MapIcon, MapPin, Moon, RotateCcw, ScanSearch, Shuffle, Sun } from "@lucide/vue";
import { getCategories, getPublicPlaces } from "../utils/api";
import { placeCategories } from "../utils/categories";
import { gcj02ToWgs84, googleMarkerContent, loadGoogleMaps } from "../utils/google-map";
import { formatAddress, hydrateDeferredImages, imageList, infoHtml } from "../utils/map";

const mapsRef = shallowRef(null);
const map = shallowRef(null);
const infoWindow = shallowRef(null);
const markers = shallowRef([]);
const places = ref([]);
const recommendLevels = ref([]);
const filters = ref({ mapCategory: "", recommend: "", city: "", author: "" });
const sidebarCollapsed = ref(false);
const sidePanelElement = ref(null);
const listElement = ref(null);
const mobileHeaderCollapsing = ref(false);
const mobileHeaderCompact = ref(false);
const mobileFilterHorizontal = ref(false);
const showDomesticPlaces = ref(false);
const mapTheme = ref("day");
const error = ref("");
const nearbyMode = ref(false);
const userLocation = ref(null);
const viewportBounds = ref(null);
const actionMessage = ref("");
let placesRequestId = 0;
let mobileCollapseFrame = 0;
let pendingMobileScrollTop = 0;
let expandedMobileHeaderHeight = 0;
let expandedMobileProviderHeight = 0;
let expandedMobileSyncHeight = 0;
let expandedMobileToolbarHeight = 0;
let expandedMobileActionsHeight = 0;
let expandedMobileStatusHeight = 0;
const MOBILE_COLLAPSE_END = 215;
const hasActiveFilters = computed(() => Object.values(filters.value).some(Boolean) || Boolean(viewportBounds.value));

const globalPlaces = computed(() => places.value.filter((place) => place.map_provider === "google"));
const domesticPlaces = computed(() => places.value.filter((place) => (place.map_provider || "amap") === "amap"));
const availablePlaces = computed(() => [
  ...globalPlaces.value,
  ...(showDomesticPlaces.value ? domesticPlaces.value : []),
]);
const filteredPlaces = computed(() => availablePlaces.value
  .filter((place) => {
    if (filters.value.mapCategory && !placeMapCategories(place).includes(filters.value.mapCategory)) return false;
    if (filters.value.city && place.city !== filters.value.city) return false;
    if (filters.value.author && place.rating_author !== filters.value.author) return false;
    if (viewportBounds.value) {
      const position = placePosition(place);
      if (
        position.lng < viewportBounds.value.minLng
        || position.lng > viewportBounds.value.maxLng
        || position.lat < viewportBounds.value.minLat
        || position.lat > viewportBounds.value.maxLat
      ) return false;
    }
    return true;
  })
  .sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0)));
const visiblePlaces = computed(() => {
  if (!nearbyMode.value || !userLocation.value) return filteredPlaces.value;
  const ranked = filteredPlaces.value
    .map((place) => ({ place, distance: distanceKm(userLocation.value, placePosition(place)) }))
    .sort((a, b) => a.distance - b.distance);
  const nearby = ranked.filter((item) => item.distance <= 30);
  return (nearby.length ? nearby : ranked.slice(0, 10)).map((item) => item.place);
});
const mapCategoryOptions = computed(() => [...new Set(availablePlaces.value
  .flatMap(placeMapCategories)
  .filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN")));
const cityOptions = computed(() => [...new Set(availablePlaces.value.map((place) => place.city).filter(Boolean))].sort());
const authorOptions = computed(() => [...new Set(availablePlaces.value.map((place) => place.rating_author).filter(Boolean))].sort());
const renderedPlaces = computed(() => visiblePlaces.value
  .map((place) => ({
    place,
    position: placePosition(place),
    synced: (place.map_provider || "amap") === "amap",
  }))
  .filter((item) => Number.isFinite(item.position.lat) && Number.isFinite(item.position.lng)));

function placeMapCategories(place) {
  const customCategories = placeCategories(place);
  if (place.map_provider === "google") {
    return place.provider_category ? [place.provider_category] : customCategories;
  }
  return customCategories.length
    ? customCategories
    : [place.provider_category].filter(Boolean);
}

function placePosition(place) {
  if ((place.map_provider || "amap") === "amap") {
    return gcj02ToWgs84(place.lng, place.lat);
  }
  return { lat: Number(place.lat), lng: Number(place.lng) };
}

function distanceKm(left, right) {
  const radius = 6371;
  const lat1 = Number(left.lat) * Math.PI / 180;
  const lat2 = Number(right.lat) * Math.PI / 180;
  const dLat = lat2 - lat1;
  const dLng = (Number(right.lng) - Number(left.lng)) * Math.PI / 180;
  const value = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return radius * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
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
  expandedMobileSyncHeight = 0;
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
    "--mobile-sync-height",
    "--mobile-sync-opacity",
    "--mobile-toolbar-height",
    "--mobile-toolbar-opacity",
    "--mobile-actions-height",
    "--mobile-actions-opacity",
    "--mobile-status-height",
    "--mobile-status-opacity",
    "--mobile-header-gap",
    "--mobile-provider-gap",
    "--mobile-sync-gap",
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
  const sync = panel.querySelector(":scope > .sync-toggle");
  const toolbar = panel.querySelector(":scope > .toolbar");
  const actions = panel.querySelector(":scope > .explore-toolbar");
  const status = panel.querySelector(":scope > .status-line");
  if (!expandedMobileHeaderHeight && expandedHeader) expandedMobileHeaderHeight = expandedHeader.scrollHeight;
  if (!expandedMobileProviderHeight && provider) expandedMobileProviderHeight = provider.scrollHeight;
  if (!expandedMobileSyncHeight && sync) expandedMobileSyncHeight = sync.scrollHeight;
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
  const syncHeight = expandedMobileSyncHeight;
  const actionsHeight = expandedMobileActionsHeight;
  const statusHeight = expandedMobileStatusHeight;

  setMobileVariable(panel, "--mobile-header-height", `${expandedHeaderHeight + (30 - expandedHeaderHeight) * headerProgress}px`);
  setMobileVariable(panel, "--mobile-expanded-opacity", String(1 - headerProgress));
  setMobileVariable(panel, "--mobile-summary-opacity", String(summaryProgress));
  setMobileVariable(panel, "--mobile-provider-height", `${providerHeight * (1 - providerProgress)}px`);
  setMobileVariable(panel, "--mobile-provider-opacity", String(1 - stage(scrollTop, 55, 105)));
  setMobileVariable(panel, "--mobile-sync-height", `${syncHeight * (1 - providerProgress)}px`);
  setMobileVariable(panel, "--mobile-sync-opacity", String(1 - stage(scrollTop, 55, 105)));
  setMobileVariable(panel, "--mobile-toolbar-height", `${expandedMobileToolbarHeight + (40 - expandedMobileToolbarHeight) * toolbarProgress}px`);
  setMobileVariable(panel, "--mobile-toolbar-opacity", String(toolbarOpacity));
  setMobileVariable(panel, "--mobile-actions-height", `${actionsHeight * (1 - actionsProgress)}px`);
  setMobileVariable(panel, "--mobile-actions-opacity", String(1 - actionsProgress));
  setMobileVariable(panel, "--mobile-status-height", `${statusHeight * (1 - actionsProgress)}px`);
  setMobileVariable(panel, "--mobile-status-opacity", String(1 - actionsProgress));
  setMobileVariable(panel, "--mobile-header-gap", `${baseGap}px`);
  setMobileVariable(panel, "--mobile-provider-gap", `${baseGap * (1 - providerProgress)}px`);
  setMobileVariable(panel, "--mobile-sync-gap", `${baseGap * (1 - providerProgress)}px`);
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

async function loadPlaces() {
  const requestId = ++placesRequestId;
  try {
    const loadedPlaces = await getPublicPlaces({ recommend: filters.value.recommend });
    if (requestId !== placesRequestId) return;
    places.value = loadedPlaces;
    reconcileFilters();
    error.value = "";
    await nextTick();
    await renderMarkers();
  } catch (err) {
    if (requestId !== placesRequestId) return;
    error.value = err.message;
  }
}

function clearMarkers() {
  infoWindow.value?.close();
  markers.value.forEach((marker) => {
    marker.map = null;
  });
  markers.value = [];
}

async function renderMarkers(fit = true) {
  if (!map.value || !mapsRef.value) return;
  clearMarkers();
  const { AdvancedMarkerElement } = await mapsRef.value.importLibrary("marker");
  markers.value = renderedPlaces.value.map(({ place, position, synced }) => {
    const content = googleMarkerContent(place, { synced });
    const marker = new AdvancedMarkerElement({
      map: map.value,
      position,
      content,
      title: place.name,
      gmpClickable: true,
    });
    let lastOpenAt = 0;
    const openCard = (event) => {
      event?.stop?.();
      event?.stopPropagation?.();
      const now = Date.now();
      if (now - lastOpenAt < 250) return;
      lastOpenAt = now;
      focusPlace(place, position, marker);
    };
    marker.addEventListener?.("gmp-click", openCard);
    return marker;
  });
  if (fit) fitAll();
}

function fitAll() {
  if (!map.value || !renderedPlaces.value.length) return;
  if (renderedPlaces.value.length === 1) {
    map.value.setCenter(renderedPlaces.value[0].position);
    map.value.setZoom(15);
    return;
  }
  const bounds = new window.google.maps.LatLngBounds();
  renderedPlaces.value.forEach(({ position }) => bounds.extend(position));
  map.value.fitBounds(bounds, isMobile() ? 52 : 80);
}

async function focusPlace(place, fixedPosition = null, anchor = null) {
  if (isMobile()) {
    sidebarCollapsed.value = true;
    await nextTick();
  }
  const position = fixedPosition || placePosition(place);
  map.value.panTo(position);
  map.value.setZoom(Math.max(map.value.getZoom() || 0, 15));
  infoWindow.value.setContent(infoHtml(place, { deferImages: true }));
  if (anchor) {
    infoWindow.value.open({ map: map.value, anchor, shouldFocus: false });
  } else {
    infoWindow.value.setPosition(position);
    infoWindow.value.open({ map: map.value, shouldFocus: false });
  }
  hydrateDeferredImages();
}

async function findNearby() {
  if (nearbyMode.value) {
    nearbyMode.value = false;
    userLocation.value = null;
    actionMessage.value = "";
    await renderMarkers();
    return;
  }
  if (!navigator.geolocation) {
    actionMessage.value = "当前浏览器不支持定位。";
    return;
  }
  actionMessage.value = "正在获取位置...";
  navigator.geolocation.getCurrentPosition(async (position) => {
    userLocation.value = {
      lng: Number(position.coords.longitude),
      lat: Number(position.coords.latitude),
    };
    nearbyMode.value = true;
    actionMessage.value = "已按距离显示附近店家。";
    await renderMarkers();
    if (visiblePlaces.value[0]) await focusPlace(visiblePlaces.value[0]);
  }, () => {
    actionMessage.value = "定位失败，请检查浏览器定位权限。";
  }, {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 300000,
  });
}

async function randomPlace() {
  if (!visiblePlaces.value.length) {
    actionMessage.value = "当前筛选条件下没有可选店家。";
    return;
  }
  const place = visiblePlaces.value[Math.floor(Math.random() * visiblePlaces.value.length)];
  actionMessage.value = `随机选择：${place.name}`;
  await focusPlace(place);
}

async function toggleViewportFilter() {
  if (viewportBounds.value) {
    viewportBounds.value = null;
    await renderMarkers();
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
    minLng: Number(southWest.lng()),
    minLat: Number(southWest.lat()),
    maxLng: Number(northEast.lng()),
    maxLat: Number(northEast.lat()),
  };
  actionMessage.value = "已筛选当前地图视野。";
  await renderMarkers(false);
}

async function resetFilters() {
  Object.assign(filters.value, { mapCategory: "", recommend: "", city: "", author: "" });
  viewportBounds.value = null;
  actionMessage.value = "";
  await loadPlaces();
}

function reconcileFilters() {
  const categories = new Set(mapCategoryOptions.value);
  const cities = new Set(cityOptions.value);
  const authors = new Set(authorOptions.value);
  if (filters.value.mapCategory && !categories.has(filters.value.mapCategory)) filters.value.mapCategory = "";
  if (filters.value.city && !cities.has(filters.value.city)) filters.value.city = "";
  if (filters.value.author && !authors.has(filters.value.author)) filters.value.author = "";
}

async function syncDomesticPlaces() {
  reconcileFilters();
  await renderMarkers();
}

async function createMap(view = null) {
  clearMarkers();
  infoWindow.value?.close();
  if (map.value && window.google?.maps?.event) {
    window.google.maps.event.clearInstanceListeners(map.value);
  }

  const mapElement = document.getElementById("globalMap");
  mapElement.replaceChildren();
  const { Map, InfoWindow } = await mapsRef.value.importLibrary("maps");
  map.value = new Map(mapElement, {
    center: view?.center || { lat: 20, lng: 0 },
    zoom: view?.zoom ?? 2,
    mapId: "DEMO_MAP_ID",
    colorScheme: mapTheme.value === "night" ? "DARK" : "LIGHT",
    streetViewControl: false,
    mapTypeControl: false,
    fullscreenControl: false,
    zoomControl: false,
    clickableIcons: false,
    gestureHandling: "greedy",
  });
  infoWindow.value = new InfoWindow();
}

async function toggleMapTheme() {
  const center = map.value?.getCenter?.();
  const view = {
    center: center?.toJSON?.() || { lat: 20, lng: 0 },
    zoom: map.value?.getZoom?.() ?? 2,
  };
  mapTheme.value = mapTheme.value === "day" ? "night" : "day";
  document.body.classList.toggle("map-day", mapTheme.value === "day");
  await createMap(view);
  await renderMarkers(false);
}

onMounted(async () => {
  try {
    document.body.classList.add("map-day");
    window.addEventListener("resize", handleViewportResize, { passive: true });
    mapsRef.value = await loadGoogleMaps();
    await createMap();
    const filterData = await getCategories();
    recommendLevels.value = filterData.recommendLevels || [];
    await loadPlaces();
  } catch (err) {
    error.value = err.message;
  }
});

onUnmounted(() => {
  window.cancelAnimationFrame(mobileCollapseFrame);
  window.removeEventListener("resize", handleViewportResize);
  clearMarkers();
  infoWindow.value?.close();
  if (map.value && window.google?.maps?.event) {
    window.google.maps.event.clearInstanceListeners(map.value);
  }
  infoWindow.value = null;
  map.value = null;
  mapsRef.value = null;
  document.body.classList.remove("map-day");
});
</script>

<template>
  <main class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <button class="sidebar-toggle desktop-sidebar-toggle" type="button" @click="sidebarCollapsed = !sidebarCollapsed">
      {{ sidebarCollapsed ? "展开列表" : "隐藏列表" }}
    </button>
    <div class="map-actions" aria-label="地图显示设置">
      <div class="mobile-view-switch" role="group" aria-label="页面视图">
        <button class="map-action-btn" :class="{ 'is-active': !sidebarCollapsed }" type="button" aria-label="详细列表" title="详细列表" @click="sidebarCollapsed = false">
          <List :size="20" :stroke-width="1.8" aria-hidden="true" />
        </button>
        <button class="map-action-btn" :class="{ 'is-active': sidebarCollapsed }" type="button" aria-label="地图" title="地图" @click="sidebarCollapsed = true">
          <MapIcon :size="20" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </div>
      <button
        class="map-action-btn theme-action"
        type="button"
        :title="mapTheme === 'day' ? '夜间地图' : '日间地图'"
        :aria-label="mapTheme === 'day' ? '切换到夜间地图' : '切换到日间地图'"
        @click="toggleMapTheme"
      >
        <Moon v-if="mapTheme === 'day'" :size="21" :stroke-width="1.7" aria-hidden="true" />
        <Sun v-else :size="21" :stroke-width="1.7" aria-hidden="true" />
      </button>
    </div>
    <aside
      ref="sidePanelElement"
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
          <p class="eyebrow">DUSKRAIN GLOBAL TASTE MAP</p>
          <h1>海外美食地图</h1>
          <p class="subtle">国外店家使用 Google Maps 与 WGS84 坐标，个人评分和评论仍由本站保存。</p>
        </div>
        <div class="mobile-compact-summary">
          <strong>海外美食地图</strong>
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
        <a class="provider-switch-btn" href="/food-map/">国内高德</a>
        <span class="provider-switch-btn is-active">国外 Google</span>
      </div>
      <label class="sync-toggle">
        <input v-model="showDomesticPlaces" type="checkbox" @change="syncDomesticPlaces">
        <span>
          <strong>同步国内店家 / China stores</strong>
          <small>高德坐标转换后显示，共 {{ domesticPlaces.length }} 家</small>
        </span>
      </label>
      <section class="toolbar">
        <div class="field">
          <label for="globalCategory">菜系 / 地图分类</label>
          <select id="globalCategory" v-model="filters.mapCategory" @change="renderMarkers">
            <option value="">全部菜系与分类</option>
            <option v-for="category in mapCategoryOptions" :key="category" :value="category">{{ category }}</option>
          </select>
        </div>
        <div class="field">
          <label for="globalRecommend">推荐</label>
          <select id="globalRecommend" v-model="filters.recommend" @change="loadPlaces">
            <option value="">全部推荐</option>
            <option v-for="level in recommendLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </div>
        <div class="field">
          <label for="globalCity">城市</label>
          <select id="globalCity" v-model="filters.city" @change="renderMarkers">
            <option value="">全部城市</option>
            <option v-for="city in cityOptions" :key="city" :value="city">{{ city }}</option>
          </select>
        </div>
        <div class="field">
          <label for="globalAuthor">作者</label>
          <select id="globalAuthor" v-model="filters.author" @change="renderMarkers">
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
      <section ref="listElement" class="list" @scroll.passive="handleListScroll">
        <article v-if="error" class="place-item"><p class="subtle">{{ error }}</p></article>
        <article v-else-if="!visiblePlaces.length" class="place-item">
          <strong>{{ availablePlaces.length ? "当前筛选条件下没有店家" : "还没有国外店家" }}</strong>
          <p class="subtle">{{ availablePlaces.length ? "请调整菜系、推荐、城市或作者筛选。" : "进入管理页，在“搜索导入”中切换 Google 后添加。" }}</p>
        </article>
        <article v-for="place in visiblePlaces" :key="place.id" class="place-item" @click="focusPlace(place)">
          <div class="item-title">
            <span>{{ place.name }}</span>
            <span class="rating">{{ place.rating ?? "-" }} / 10 · {{ place.rating_author || "吕俊泽" }}</span>
          </div>
          <div v-if="imageList(place).length && !place.hide_images" class="image-strip">
            <img :src="imageList(place)[0]" :alt="place.name" loading="lazy" decoding="async">
          </div>
          <div class="subtle">{{ formatAddress(place) }}</div>
          <div class="pill-row">
            <span v-if="place.country_code" class="pill">{{ place.country_code }}</span>
            <span v-if="place.provider_category" class="pill">{{ place.provider_category }}</span>
            <span v-for="category in placeCategories(place)" :key="category" class="pill">{{ category }}</span>
            <span v-if="place.recommend_level" class="pill">{{ place.recommend_level }}</span>
          </div>
        </article>
      </section>
    </aside>
    <section class="map-stage">
      <div id="globalMap" class="map-canvas"></div>
    </section>
  </main>
</template>
