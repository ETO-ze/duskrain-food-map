<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import { Search, List, Map as MapIcon, MapPin, Moon, RotateCcw, ScanSearch, Shuffle, Sun } from "@lucide/vue";
import MapLoading from "./MapLoading.vue";
import BrowsePlaceCard from "./BrowsePlaceCard.vue";
import { useBrowseMemory } from "../utils/browse-memory";
import { useBrowseResults } from "../utils/browse-panel";
import { useMapLoading } from "../utils/map-loading";
import { matchesSearch, containsPosition, nearbyPlaces, sameBounds } from "../utils/explore";
import { getCategories, getPublicPlaces } from "../utils/api";
import { placeCategories } from "../utils/categories";
import { gcj02ToWgs84, googleMarkerContent, loadGoogleMaps, GOOGLE_AUTH_MESSAGE } from "../utils/google-map";
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
let renderRequest = 0;
let providerDenied = false;
let initialPlaceFocused = false;
const markerCache = new Map();
const showDomesticPlaces = ref(false);
const mapTheme = ref("day");
const error = ref("");
const nearbyMode = ref(false);
const userLocation = ref(null);
const viewportBounds = ref(null);
const actionMessage = ref("");
const { restoreScroll } = useBrowseMemory("duskrain-browse-google", { filters, query, mapTheme, showDomesticPlaces }, sidePanelElement);
useBrowseResults(sidePanelElement, listElement, [filters, query, nearbyMode, viewportBounds, showDomesticPlaces]);
let placesRequestId = 0;
const hasActiveFilters = computed(() => Object.values(filters.value).some(Boolean) || Boolean(viewportBounds.value) || nearbyMode.value || Boolean(query.value.trim()));

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
    if (filters.value.recommend && place.recommend_level !== filters.value.recommend) return false;
    if (!matchesSearch(place, query.value) || !containsPosition(viewportBounds.value, placePosition(place))) return false;
    return true;
  })
  .sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0)));
const visiblePlaces = computed(() => {
  if (!nearbyMode.value || !userLocation.value) return filteredPlaces.value;
  return nearbyPlaces(filteredPlaces.value, userLocation.value, nearbyRadius.value, placePosition);
});
watch(query, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => renderMarkers(), 150);
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

function isMobile() {
  return window.matchMedia("(max-width: 860px)").matches;
}

function showList() { dismissLoading(); sidebarCollapsed.value = false; }
function showMap() { revealLoading(); sidebarCollapsed.value = true; }

async function loadPlaces() {
  const requestId = ++placesRequestId;
  try {
    loadingPlaces.value = true;
    const loadedPlaces = await getPublicPlaces();
    if (disposed || requestId !== placesRequestId) return;
    places.value = loadedPlaces;
    reconcileFilters();
    error.value = "";
    await nextTick();
    restoreScroll();
    await renderMarkers(!initialFitDone);
    focusInitialPlace();
  } catch (err) {
    if (requestId !== placesRequestId) return;
    error.value = err.message;
  } finally {
    if (!disposed && requestId === placesRequestId) loadingPlaces.value = false;
  }
}

function clearMarkers() {
  renderRequest++;
  infoWindow.value?.close();
  markerCache.forEach(({ marker, click }) => { marker.removeEventListener?.("gmp-click", click); marker.map = null; });
  markerCache.clear();
  markers.value = [];
}

async function renderMarkers(fit = false) {
  if (!map.value || !mapsRef.value || !infoWindow.value) return;
  const request = ++renderRequest;
  const instance = map.value;
  try {
    const { AdvancedMarkerElement } = await mapsRef.value.importLibrary("marker");
    if (disposed || request !== renderRequest || map.value !== instance) return;
    const ids = new Set(renderedPlaces.value.map(({ place }) => place.id));
    markerCache.forEach((entry, id) => {
      if (!ids.has(id)) {
        entry.marker.removeEventListener?.("gmp-click", entry.click);
        entry.marker.map = null;
        markerCache.delete(id);
      }
    });
    if (selectedId.value && !ids.has(selectedId.value)) {
      selectedId.value = null;
      pendingPlace = null;
      infoWindow.value.close();
    }
    renderedPlaces.value.forEach(({ place, position, synced }) => {
      const signature = JSON.stringify([place.name, place.rating, place.recommend_level, position]);
      const entry = markerCache.get(place.id);
      if (entry) {
        entry.place = place;
        if (entry.signature !== signature) {
          entry.marker.position = position;
          entry.marker.content = googleMarkerContent(place, { synced });
          entry.marker.title = place.name;
          entry.signature = signature;
        }
        return;
      }
      const marker = new AdvancedMarkerElement({ map: instance, position, content: googleMarkerContent(place, { synced }), title: place.name, gmpClickable: true });
      const next = { marker, place, signature, click: null };
      next.click = (event) => { event?.stopPropagation?.(); focusPlace(next.place, null, marker); };
      marker.addEventListener("gmp-click", next.click);
      markerCache.set(place.id, next);
    });
    markers.value = [...markerCache.values()].map((entry) => entry.marker);
    if (fit && renderedPlaces.value.length) { fitAll(); initialFitDone = true; }
  } catch (err) {
    if (!disposed && request === renderRequest) actionMessage.value = "店家标记暂未加载，请重试地图。";
  }
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
  selectedId.value = place.id;
  if (!infoWindow.value || mapPhase.value !== "ready") { pendingPlace = place; showMap(); return; }
  pendingPlace = null;
  if (isMobile()) {
    sidebarCollapsed.value = true;
    await nextTick();
  }
  const position = fixedPosition || placePosition(place);
  if (disposed || !map.value || !infoWindow.value) return;
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

function focusInitialPlace() {
  if (initialPlaceFocused || mapPhase.value !== "ready") return;
  const id = new URLSearchParams(window.location.search).get("place");
  const place = places.value.find((item) => String(item.id) === id);
  if (!place) return;
  initialPlaceFocused = true;
  if ((place.map_provider || "amap") === "amap") showDomesticPlaces.value = true;
  renderMarkers().then(() => { if (!disposed) focusPlace(place); });
}

function findNearby() {
  if (locating.value) return;
  if (nearbyMode.value) {
    nearbyMode.value = false;
    userLocation.value = null;
    actionMessage.value = "";
    renderMarkers();
    return;
  }
  if (!navigator.geolocation) { actionMessage.value = "当前浏览器不支持定位。"; return; }
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
  return sw && ne ? { minLng: sw.lng(), minLat: sw.lat(), maxLng: ne.lng(), maxLat: ne.lat() } : null;
}
function searchViewport() {
  const bounds = currentBounds();
  if (!bounds) return;
  viewportBounds.value = bounds;
  viewportDirty.value = false;
  actionMessage.value = "已更新此区域的店家";
  renderMarkers();
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

function toggleViewportFilter() {
  if (viewportBounds.value) {
    viewportBounds.value = null;
    actionMessage.value = "";
    renderMarkers();
  } else { searchViewport(); }
}

function resetFilters() {
  Object.assign(filters.value, { mapCategory: "", recommend: "", city: "", author: "" });
  query.value = "";
  viewportBounds.value = null;
  nearbyMode.value = false;
  userLocation.value = null;
  nearbyRadius.value = 30;
  locationRequest++;
  locating.value = false;
  actionMessage.value = "";
  renderMarkers();
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

async function createMap(view = null, generation) {
  const { Map, InfoWindow } = await mapsRef.value.importLibrary("maps");
  if (providerDenied || !currentLoading(generation)) return false;
  clearMarkers();
  infoWindow.value?.close();
  if (map.value && window.google?.maps?.event) {
    window.google.maps.event.clearInstanceListeners(map.value);
  }

  const mapElement = document.getElementById("globalMap");
  mapElement.replaceChildren();
  mapRendering();
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
  const instance = map.value;
  instance.addListener("tilesloaded", () => {
    if (providerDenied || !currentLoading(generation) || map.value !== instance) return;
    mapReady();
    if (pendingPlace) focusPlace(pendingPlace);
    else focusInitialPlace();
  });
  instance.addListener("idle", () => {
    if (currentLoading(generation)) viewportDirty.value = !sameBounds(viewportBounds.value, currentBounds());
  });
  return true;
}

async function initializeMap(view = null) {
  const generation = beginLoading();
  try {
    const maps = await loadGoogleMaps();
    if (providerDenied) throw new Error(GOOGLE_AUTH_MESSAGE);
    if (!currentLoading(generation)) return;
    mapsRef.value = maps;
    if (!await createMap(view, generation)) return;
    await renderMarkers(!initialFitDone);
  } catch (err) {
    if (currentLoading(generation)) mapFailed(err.message);
  }
}

function handleGoogleAuthFailure() {
  providerDenied = true;
  mapFailed(GOOGLE_AUTH_MESSAGE);
}

function toggleMapTheme() {
  const view = { center: map.value?.getCenter()?.toJSON(), zoom: map.value?.getZoom() };
  mapTheme.value = mapTheme.value === "night" ? "day" : "night";
  document.body.classList.toggle("map-day", mapTheme.value === "day");
  if (map.value) initializeMap(view);
}

onMounted(() => {
  window.addEventListener("duskrain-google-auth-error", handleGoogleAuthFailure);
  document.body.classList.toggle("map-day", mapTheme.value === "day");
  getCategories().then((data) => { if (!disposed) recommendLevels.value = data.recommendLevels || []; }).catch(() => {});
  loadPlaces();
  initializeMap();
});

onUnmounted(() => {
  window.removeEventListener("duskrain-google-auth-error", handleGoogleAuthFailure);
  disposed = true;
  placesRequestId++;
  locationRequest++;
  clearTimeout(searchTimer);
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
  <main class="app-shell browse-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed, 'is-booting': loadingScreen }" :inert="loadingScreen || null" :aria-busy="loadingScreen">
    <button class="sidebar-toggle desktop-sidebar-toggle" type="button" @click="sidebarCollapsed ? showList() : showMap()">
      {{ sidebarCollapsed ? "展开列表" : "隐藏列表" }}
    </button>
    <div class="map-actions" aria-label="地图显示设置">
      <div class="mobile-view-switch" role="group" aria-label="页面视图">
        <button class="map-action-btn" :class="{ 'is-active': !sidebarCollapsed }" type="button" aria-label="详细列表" title="详细列表" @click="showList">
          <List :size="20" :stroke-width="1.8" aria-hidden="true" />
        </button>
        <button class="map-action-btn" :class="{ 'is-active': sidebarCollapsed }" type="button" aria-label="地图" title="地图" @click="showMap">
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
    >
      <header>
        <div class="mobile-expanded-header">
          <p class="eyebrow">DUSKRAIN GLOBAL TASTE MAP</p>
          <h1>海外美食地图</h1>
          <p class="subtle">世界各地的好味道，来自亲自到店的体验。</p>
          <div class="browse-overview"><span><strong>{{ availablePlaces.length }}</strong> 家店</span><span><strong>{{ cityOptions.length }}</strong> 个地区</span><span><strong>{{ authorOptions.length }}</strong> 位作者</span></div>
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
      <div class="browse-controls">
        <label class="browse-search"><Search :size="17" aria-hidden="true" /><input v-model="query" type="search" placeholder="搜索店名、城市或地址" aria-label="搜索店家" /></label>
      <section class="toolbar">
        <div class="field" :class="{ 'is-active': filters.mapCategory }">
          <label for="globalCategory">菜系 / 地图分类</label>
          <select id="globalCategory" v-model="filters.mapCategory" @change="renderMarkers()">
            <option value="">全部菜系与分类</option>
            <option v-for="category in mapCategoryOptions" :key="category" :value="category">{{ category }}</option>
          </select>
        </div>
        <div class="field" :class="{ 'is-active': filters.recommend }">
          <label for="globalRecommend">推荐</label>
          <select id="globalRecommend" v-model="filters.recommend" @change="renderMarkers()">
            <option value="">全部推荐</option>
            <option v-for="level in recommendLevels" :key="level" :value="level">{{ level }}</option>
          </select>
        </div>
        <div class="field" :class="{ 'is-active': filters.city }">
          <label for="globalCity">城市</label>
          <select id="globalCity" v-model="filters.city" @change="renderMarkers(true)">
            <option value="">全部城市</option>
            <option v-for="city in cityOptions" :key="city" :value="city">{{ city }}</option>
          </select>
        </div>
        <div class="field" :class="{ 'is-active': filters.author }">
          <label for="globalAuthor">作者</label>
          <select id="globalAuthor" v-model="filters.author" @change="renderMarkers()">
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
      <section ref="listElement" class="list" :aria-busy="loadingPlaces">
        <div v-if="loadingPlaces && !places.length" class="list-skeleton" role="status" aria-label="店家加载中"><div v-for="n in 3" :key="n"><i /><i /><i /></div></div>
        <article v-else-if="error" class="place-item"><p class="subtle">{{ error }}</p><button class="btn secondary" type="button" @click="loadPlaces">重新加载店家</button></article>
        <article v-else-if="!visiblePlaces.length" class="place-item">
          <strong>{{ nearbyMode ? `附近 ${nearbyRadius} 公里没有符合条件的店家` : availablePlaces.length ? "当前筛选条件下没有店家" : "还没有国外店家" }}</strong>
          <p class="subtle">{{ availablePlaces.length ? "请调整菜系、推荐、城市或作者筛选。" : "进入管理页，在“搜索导入”中切换 Google 后添加。" }}</p>
        </article>
        <button v-if="nearbyMode && !visiblePlaces.length && nearbyRadius === 30" class="btn secondary" type="button" @click="expandNearby">扩大到 100 公里</button>
        <BrowsePlaceCard v-for="place in visiblePlaces" :key="place.id" :place="place" :selected="selectedId === place.id" :address="formatAddress(place)" :image="imageList(place)[0]" :categories="[...new Set([place.provider_category, ...placeCategories(place)].filter(Boolean))]" :review-href="`/food-map/review/${place.id}?from=global`" show-country @select="focusPlace" />
      </section>
    </aside>
    <section class="map-stage">
      <div id="globalMap" class="map-canvas"></div>
      <button v-if="mapPhase === 'ready' && viewportDirty" class="area-search btn action-command" type="button" @click="searchViewport"><ScanSearch :size="16" />搜索这片区域</button>
    </section>
    <MapLoading :visible="loadingScreen" :phase="loadingPhase" :message="mapMessage" :theme="mapTheme" provider="GOOGLE MAPS" @retry="initializeMap()" @list="showList" @theme="toggleMapTheme" />
  </main>
</template>
