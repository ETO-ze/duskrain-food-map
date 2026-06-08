<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { List, Map as MapIcon, Moon, Sun } from "@lucide/vue";
import { getCategories, getPublicPlaces } from "../utils/api";
import { gcj02ToWgs84, googleMarkerContent, loadGoogleMaps } from "../utils/google-map";
import { formatAddress, hydrateDeferredImages, imageList, infoHtml, schedulePlaceImagePreload } from "../utils/map";

const mapsRef = shallowRef(null);
const map = shallowRef(null);
const infoWindow = shallowRef(null);
const markers = shallowRef([]);
const places = ref([]);
const recommendLevels = ref([]);
const filters = ref({ mapCategory: "", recommend: "", city: "", author: "" });
const sidebarCollapsed = ref(false);
const showDomesticPlaces = ref(false);
const mapTheme = ref("day");
const error = ref("");

const globalPlaces = computed(() => places.value.filter((place) => place.map_provider === "google"));
const domesticPlaces = computed(() => places.value.filter((place) => (place.map_provider || "amap") === "amap"));
const availablePlaces = computed(() => [
  ...globalPlaces.value,
  ...(showDomesticPlaces.value ? domesticPlaces.value : []),
]);
const visiblePlaces = computed(() => availablePlaces.value
  .filter((place) => {
    if (filters.value.mapCategory && placeCategory(place) !== filters.value.mapCategory) return false;
    if (filters.value.city && place.city !== filters.value.city) return false;
    if (filters.value.author && place.rating_author !== filters.value.author) return false;
    return true;
  })
  .sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0)));
const mapCategoryOptions = computed(() => [...new Set(availablePlaces.value
  .map(placeCategory)
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

function placeCategory(place) {
  return place.my_category || place.provider_category || "";
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

async function loadPlaces() {
  places.value = await getPublicPlaces({ recommend: filters.value.recommend });
  await nextTick();
  await renderMarkers();
  schedulePlaceImagePreload(globalPlaces.value);
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
    marker.addListener("click", openCard);
    marker.addEventListener?.("gmp-click", openCard);
    content.addEventListener("click", openCard);
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
  infoWindow.value.open(anchor
    ? { map: map.value, anchor, shouldFocus: false }
    : { map: map.value, position, shouldFocus: false });
  hydrateDeferredImages();
}

async function syncDomesticPlaces() {
  const categories = new Set(mapCategoryOptions.value);
  const cities = new Set(cityOptions.value);
  const authors = new Set(authorOptions.value);
  if (filters.value.mapCategory && !categories.has(filters.value.mapCategory)) filters.value.mapCategory = "";
  if (filters.value.city && !cities.has(filters.value.city)) filters.value.city = "";
  if (filters.value.author && !authors.has(filters.value.author)) filters.value.author = "";
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
    <div class="map-actions">
      <button
        class="map-action-btn"
        type="button"
        :title="mapTheme === 'day' ? '切换夜间地图' : '切换日间地图'"
        :aria-label="mapTheme === 'day' ? '切换夜间地图' : '切换日间地图'"
        @click="toggleMapTheme"
      >
        <Sun v-if="mapTheme === 'day'" :size="20" :stroke-width="1.7" />
        <Moon v-else :size="20" :stroke-width="1.7" />
      </button>
      <div class="mobile-view-switch">
        <button class="map-action-btn" :class="{ 'is-active': !sidebarCollapsed }" type="button" title="详细列表" @click="sidebarCollapsed = false">
          <List :size="20" :stroke-width="1.8" />
        </button>
        <button class="map-action-btn" :class="{ 'is-active': sidebarCollapsed }" type="button" title="地图" @click="sidebarCollapsed = true">
          <MapIcon :size="20" :stroke-width="1.8" />
        </button>
      </div>
    </div>
    <aside v-show="!sidebarCollapsed" class="side-panel">
      <header>
        <p class="eyebrow">DUSKRAIN GLOBAL TASTE MAP</p>
        <h1>海外美食地图</h1>
        <p class="subtle">国外店家使用 Google Maps 与 WGS84 坐标，个人评分和评论仍由本站保存。</p>
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
      <div class="button-row">
        <button class="btn secondary" type="button" @click="fitAll">显示全部</button>
        <a class="btn secondary" href="/food-map/admin/">管理</a>
      </div>
      <section class="list">
        <article v-if="error" class="place-item"><p class="subtle">{{ error }}</p></article>
        <article v-else-if="!visiblePlaces.length" class="place-item">
          <strong>还没有国外店家</strong>
          <p class="subtle">进入管理页，在“搜索导入”中切换 Google 后添加。</p>
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
            <span v-if="place.my_category" class="pill">{{ place.my_category }}</span>
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
