<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef } from "vue";
import AdminAuthors from "./AdminAuthors.vue";
import AdminBulkImport from "./AdminBulkImport.vue";
import AdminMenu from "./AdminMenu.vue";
import AdminPlaceForm from "./AdminPlaceForm.vue";
import AdminPlaceList from "./AdminPlaceList.vue";
import AdminPoiSearch from "./AdminPoiSearch.vue";
import AdminSettings from "./AdminSettings.vue";
import { deleteAdminPlace, getAdminAuthors, getAdminPlaces, getPoiDetail, reverseGeocode, saveAdminPlace } from "../utils/api";
import { categoryPayload, placeCategories } from "../utils/categories";
import {
  fetchGooglePlace,
  googleMarkerContent,
  loadGoogleMaps,
  reverseGeocodeGoogle,
} from "../utils/google-map";
import { applyMapLabels, applyMovingMapFeatures, hydrateDeferredImages, infoHtml, loadAmap, mapOptions, placeLabelMarker, setLabelMarkerText } from "../utils/map";

const activeModule = ref("list");
const statusLine = ref("");
const places = ref([]);
const authors = ref([]);
const authorOptions = computed(() => authors.value.map((author) => author.author_name));
const categoryOptions = computed(() => [...new Set(places.value.flatMap(placeCategories))]
  .sort((a, b) => a.localeCompare(b, "zh-CN")));
const markers = shallowRef([]);
const labels = shallowRef([]);
const markerLayer = shallowRef(null);
const AMapRef = shallowRef(null);
const map = shallowRef(null);
const infoWindow = shallowRef(null);
const googleMapsRef = shallowRef(null);
const googleMap = shallowRef(null);
const googleInfoWindow = shallowRef(null);
const googlePreviewMarker = shallowRef(null);
const mapProvider = ref("amap");
const mapTheme = ref("day");
const activePlaceId = ref(null);
const LABEL_MIN_ZOOM = 12;
let baseLabelTimer = 0;
let baseLabelFollowupTimer = 0;
let labelTimer = 0;
let focusToken = 0;
let movingTimer = 0;
let renderTimer = 0;
let lastHotspotClickAt = 0;
let isMapMoving = false;
let renderedLabelSet = new Set();
let scaleControl = null;
let googleMapClickListener = null;
const pendingTimers = new Set();

const form = reactive(newForm());

function newForm() {
  return {
    id: "",
    map_provider: "amap",
    country_code: "CN",
    coordinate_system: "gcj02",
    provider_poi_id: "",
    name: "",
    address: "",
    lng: "",
    lat: "",
    city: "",
    district: "",
    provider_category: "",
    phone: "",
    business_hours: "",
    amap_detail_url: "",
    provider_detail_url: "",
    my_category: "",
    my_categories: [],
    rating: null,
    rating_author: "吕俊泽",
    recommend_level: "",
    review_url: "",
    review_text: "",
    tags: "",
    note: "",
    visited_at: "",
    cover_image: "",
    image_urls: "",
    hide_images: false,
    is_public: true,
  };
}

function setStatus(message) {
  statusLine.value = message;
}

function setActive(moduleName) {
  setStatus("");
  activeModule.value = moduleName;
}

function resetForm() {
  setStatus("");
  Object.assign(form, newForm());
  showMapProvider("amap");
  activeModule.value = "edit";
}

function fillFromPlace(place, includeId = true) {
  const categories = placeCategories(place);
  Object.assign(form, {
    ...newForm(),
    ...place,
    id: includeId ? place.id || "" : "",
    my_category: categories[0] || "",
    my_categories: [...categories],
    rating: place.rating ?? null,
    rating_author: place.rating_author || "吕俊泽",
    hide_images: Boolean(place.hide_images),
    is_public: place.is_public ?? true,
  });
}

function readPayload() {
  const categories = categoryPayload(form.my_categories, form.my_category);
  return {
    provider_poi_id: String(form.provider_poi_id || "").trim(),
    map_provider: form.map_provider === "google" ? "google" : "amap",
    country_code: String(form.country_code || "").trim().toUpperCase(),
    coordinate_system: form.map_provider === "google" ? "wgs84" : "gcj02",
    name: String(form.name || "").trim(),
    address: String(form.address || "").trim(),
    lng: Number(form.lng),
    lat: Number(form.lat),
    city: String(form.city || "").trim(),
    district: String(form.district || "").trim(),
    provider_category: String(form.provider_category || "").trim(),
    phone: String(form.phone || "").trim(),
    business_hours: String(form.business_hours || "").trim(),
    amap_detail_url: String(form.amap_detail_url || "").trim(),
    provider_detail_url: String(form.provider_detail_url || form.amap_detail_url || "").trim(),
    ...categories,
    rating: form.rating === "" || form.rating == null ? null : Number(form.rating),
    rating_author: String(form.rating_author || "").trim(),
    recommend_level: form.recommend_level || "",
    review_url: String(form.review_url || "").trim(),
    review_text: String(form.review_text || "").trim(),
    tags: String(form.tags || "").trim(),
    note: String(form.note || "").trim(),
    visited_at: form.visited_at || "",
    cover_image: String(form.cover_image || "").trim(),
    image_urls: String(form.image_urls || "").trim(),
    hide_images: Boolean(form.hide_images),
    is_public: Boolean(form.is_public),
  };
}

async function loadPlaces() {
  places.value = await getAdminPlaces();
  await nextTick();
}

async function loadAuthors() {
  authors.value = await getAdminAuthors();
}

async function refreshAuthors() {
  await Promise.all([loadAuthors(), loadPlaces()]);
}

async function handleBulkCompleted(createdPlaces) {
  await loadPlaces();
  if (createdPlaces?.length) fillFromPlace(createdPlaces[createdPlaces.length - 1]);
}

function renderMarkers() {
  markers.value = [];
  labels.value = [];
  renderedLabelSet = new Set();
}

function setLabelVisible(item, visible) {
  if (item.visible === visible) return;
  item.visible = visible;
  setLabelMarkerText(item.label, item.place, visible);
  if (String(item.place.id) === String(activePlaceId.value) && typeof item.label.setRank === "function") {
    item.label.setRank(visible ? 1000 : 100);
  }
}

function hidePlaceTexts() {
  labels.value.forEach((item) => setLabelVisible(item, false));
}

function readBounds() {
  const bounds = map.value?.getBounds?.();
  const southWest = bounds?.getSouthWest?.();
  const northEast = bounds?.getNorthEast?.();
  if (!southWest || !northEast) return null;
  const minLng = Number(southWest.lng);
  const minLat = Number(southWest.lat);
  const maxLng = Number(northEast.lng);
  const maxLat = Number(northEast.lat);
  const lngPad = Math.max((maxLng - minLng) * 0.18, 0.002);
  const latPad = Math.max((maxLat - minLat) * 0.18, 0.002);
  return {
    minLng: minLng - lngPad,
    maxLng: maxLng + lngPad,
    minLat: minLat - latPad,
    maxLat: maxLat + latPad,
  };
}

function isInBounds(place, bounds) {
  if (!bounds) return true;
  const lng = Number(place.lng);
  const lat = Number(place.lat);
  return lng >= bounds.minLng && lng <= bounds.maxLng && lat >= bounds.minLat && lat <= bounds.maxLat;
}

function syncRenderedMarkers(extraPlace = null) {
  markers.value = [];
  labels.value = [];
  renderedLabelSet = new Set();
}

function syncRenderedMarkersSoon(delay = 90) {
  window.clearTimeout(renderTimer);
  renderTimer = window.setTimeout(() => syncRenderedMarkers(), delay);
}

function shouldShowLabels() {
  return map.value && map.value.getZoom() >= LABEL_MIN_ZOOM;
}

function visibleLabelLimit(zoom) {
  if (zoom >= 16) return 28;
  if (zoom >= 14) return 16;
  return 10;
}

function syncLabelVisibility() {
  if (!shouldShowLabels()) {
    labels.value.forEach((item) => {
      const isActive = item.rendered && String(item.place.id) === String(activePlaceId.value);
      setLabelVisible(item, isActive);
      if (typeof item.label.setRank === "function") item.label.setRank(isActive ? 1000 : 100);
    });
    return;
  }
  const zoom = map.value.getZoom();
  const center = map.value.getCenter();
  const centerLng = Number(center.lng);
  const centerLat = Number(center.lat);
  const visibleLabels = labels.value
    .filter((item) => item.rendered)
    .map((item) => {
      const placeLng = Number(item.place.lng);
      const placeLat = Number(item.place.lat);
      const distance = ((placeLng - centerLng) ** 2) + ((placeLat - centerLat) ** 2);
      const activeBoost = String(item.place.id) === String(activePlaceId.value) ? -1 : 0;
      return { ...item, distance, activeBoost };
    })
    .sort((a, b) => a.activeBoost - b.activeBoost || a.distance - b.distance)
    .slice(0, visibleLabelLimit(zoom));
  const visibleSet = new Set(visibleLabels.map((item) => item.label));
  labels.value.forEach((item) => {
    const isActive = String(item.place.id) === String(activePlaceId.value);
    setLabelVisible(item, item.rendered && visibleSet.has(item.label));
    if (typeof item.label.setRank === "function") item.label.setRank(isActive ? 1000 : 100);
  });
}

function syncLabelVisibilitySoon(delay = 120) {
  window.clearTimeout(labelTimer);
  labelTimer = window.setTimeout(syncLabelVisibility, delay);
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
    hidePlaceTexts();
    if (infoWindow.value) infoWindow.value.close();
    if (map.value) applyMovingMapFeatures(map.value);
  }
  movingTimer = window.setTimeout(finishMapMove, 1200);
}

function finishMapMove() {
  isMapMoving = false;
  document.body.classList.remove("map-moving");
  syncRenderedMarkersSoon(80);
  if (map.value) applyMapLabels(map.value, AMapRef.value, mapTheme.value);
  refreshBaseLabelsSoon(260);
}

function endMapMove() {
  window.clearTimeout(movingTimer);
  movingTimer = window.setTimeout(finishMapMove, 180);
}

function schedule(callback, delay) {
  const timer = window.setTimeout(() => {
    pendingTimers.delete(timer);
    callback();
  }, delay);
  pendingTimers.add(timer);
  return timer;
}

async function initGoogleMap() {
  if (googleMap.value) return;
  googleMapsRef.value = await loadGoogleMaps();
  const { Map, InfoWindow } = await googleMapsRef.value.importLibrary("maps");
  googleMap.value = new Map(document.getElementById("adminGoogleMap"), {
    center: { lat: 35.6762, lng: 139.6503 },
    zoom: 11,
    mapId: "DEMO_MAP_ID",
    streetViewControl: false,
    mapTypeControl: false,
    fullscreenControl: false,
    clickableIcons: true,
    gestureHandling: "greedy",
  });
  googleInfoWindow.value = new InfoWindow();
  googleMapClickListener = googleMap.value.addListener("click", async (event) => {
    const lat = Number(event.latLng?.lat());
    const lng = Number(event.latLng?.lng());
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    try {
      if (event.placeId) {
        event.stop?.();
        setStatus("正在读取点击的 Google 商家详情...");
        const candidate = await fetchGooglePlace(event.placeId);
        const existing = findExistingPlace(candidate);
        if (existing) {
          await selectPlace(existing);
          setStatus(`已添加过：${existing.name}，已切换为编辑已有店铺。`);
          return;
        }
        await selectCandidate(candidate);
        setStatus(`已从 Google 地图选中：${candidate.name}。确认评分和分类后点保存。`);
        return;
      }

      setStatus("正在解析 Google 地图点击位置...");
      const candidate = await reverseGeocodeGoogle({ lat, lng });
      await selectCandidate(candidate);
      setStatus("地址、国家和城市已自动填入，请补充店名、评分和分类后保存。");
    } catch (error) {
      fillFromPlace({
        map_provider: "google",
        country_code: "",
        coordinate_system: "wgs84",
        provider_poi_id: "",
        name: "",
        address: "",
        lng,
        lat,
        city: "",
        district: "",
        provider_category: "",
        phone: "",
        business_hours: "",
        amap_detail_url: "",
        provider_detail_url: `https://www.google.com/maps?q=${lat},${lng}`,
      }, false);
      activeModule.value = "edit";
      setStatus(`已填入 Google 坐标，地址解析失败，可手动补充：${error.message}`);
    }
  });
}

async function showMapProvider(provider) {
  mapProvider.value = provider === "google" ? "google" : "amap";
  if (mapProvider.value === "google") {
    await nextTick();
    await initGoogleMap();
  }
}

async function previewGooglePlace(place) {
  await initGoogleMap();
  const position = { lat: Number(place.lat), lng: Number(place.lng) };
  if (!Number.isFinite(position.lat) || !Number.isFinite(position.lng)) return;
  const { AdvancedMarkerElement } = await googleMapsRef.value.importLibrary("marker");
  if (googlePreviewMarker.value) googlePreviewMarker.value.map = null;
  googlePreviewMarker.value = new AdvancedMarkerElement({
    map: googleMap.value,
    position,
    content: googleMarkerContent(place),
    title: place.name || "地图选点",
  });
  googleMap.value.panTo(position);
  googleMap.value.setZoom(15);
  googleInfoWindow.value.setContent(infoHtml(place, { deferImages: true }));
  googleInfoWindow.value.setPosition(position);
  googleInfoWindow.value.open({ map: googleMap.value, anchor: googlePreviewMarker.value });
  hydrateDeferredImages();
}

async function previewSelected(place) {
  const provider = place.map_provider === "google" ? "google" : "amap";
  await showMapProvider(provider);
  if (provider === "google") {
    await previewGooglePlace(place);
    return;
  }
  const token = ++focusToken;
  activePlaceId.value = place.id;
  const position = new AMapRef.value.LngLat(Number(place.lng), Number(place.lat));
  const moveDuration = 220;
  syncRenderedMarkers(place);
  map.value.setZoomAndCenter(Math.max(map.value.getZoom(), 15), position, false, moveDuration);
  schedule(() => syncRenderedMarkers(place), moveDuration + 160);
  refreshBaseLabelsSoon(1000);
  schedule(() => {
    if (token !== focusToken) return;
    infoWindow.value.setContent(infoHtml(place, { deferImages: true }));
    infoWindow.value.open(map.value, position);
    hydrateDeferredImages();
  }, moveDuration - 40);
}

async function selectPlace(place) {
  setStatus("");
  fillFromPlace(place);
  activeModule.value = "edit";
  try {
    await previewSelected(place);
  } catch (error) {
    setStatus(`资料已载入，地图预览暂不可用：${error.message}`);
  }
}

async function selectCandidate(candidate) {
  setStatus("");
  fillFromPlace(candidate, false);
  activeModule.value = "edit";
  try {
    await previewSelected(candidate);
  } catch (error) {
    setStatus(`商家资料已填入，地图预览暂不可用：${error.message}`);
  }
}

function findExistingPlace(candidate) {
  return places.value.find((place) => {
    if (
      candidate.provider_poi_id
      && place.provider_poi_id === candidate.provider_poi_id
      && (place.map_provider || "amap") === (candidate.map_provider || "amap")
    ) return true;
    const sameName = (place.name || "").trim().toLowerCase() === (candidate.name || "").trim().toLowerCase();
    const sameAddress = (place.address || "").trim().toLowerCase() === (candidate.address || "").trim().toLowerCase();
    const sameLng = Math.abs(Number(place.lng) - Number(candidate.lng)) < 0.000001;
    const sameLat = Math.abs(Number(place.lat) - Number(candidate.lat)) < 0.000001;
    return sameName && sameAddress && sameLng && sameLat;
  });
}

function distanceScore(candidate, lng, lat) {
  const dx = Number(candidate.lng) - Number(lng);
  const dy = Number(candidate.lat) - Number(lat);
  return ((dx * dx) + (dy * dy)) * 100000000;
}

function poiKindScore(candidate) {
  const text = `${candidate.provider_category || ""} ${candidate.name || ""}`;
  let score = 0;
  if (/[\u9910\u996e\u7f8e\u98df\u5c0f\u5403\u751c\u54c1\u5496\u5561\u8336\u9152\u5427\u70e7\u70e4\u706b\u9505\u6599\u7406\u9762\u5305]/.test(text)) score -= 80;
  if (/[\u8d2d\u7269\u5546\u573a\u5199\u5b57\u697c\u4f4f\u5b85\u505c\u8f66\u573a\u95e8\u51fa\u5165\u53e3]|Shopping|Mall|Building/i.test(text)) score += 90;
  return score;
}

function bestNearbyCandidate(items, lng, lat) {
  return [...(items || [])]
    .filter((item) => item?.lng && item?.lat)
    .sort((a, b) => {
      const scoreA = distanceScore(a, lng, lat) + poiKindScore(a);
      const scoreB = distanceScore(b, lng, lat) + poiKindScore(b);
      return scoreA - scoreB;
    })[0];
}

function candidateFromHotspot(event) {
  const lng = Number(event.lnglat?.lng);
  const lat = Number(event.lnglat?.lat);
  return {
    provider_poi_id: event.id || "",
    name: event.name || "",
    address: "",
    lng,
    lat,
    city: "",
    district: "",
    provider_category: "",
    phone: "",
    business_hours: "",
    amap_detail_url: event.id
      ? `https://ditu.amap.com/place/${encodeURIComponent(event.id)}`
      : `https://uri.amap.com/marker?position=${lng},${lat}&name=${encodeURIComponent(event.name || "地图选点")}&src=duskrain&coordinate=gaode&callnative=0`,
    my_category: "",
    rating: null,
    rating_author: "吕俊泽",
    recommend_level: "",
    is_public: true,
  };
}

function manualCandidateFromClick(event, data = {}) {
  const lng = Number(event.lnglat.lng);
  const lat = Number(event.lnglat.lat);
  return {
    provider_poi_id: "",
    name: "",
    address: data.address || "",
    lng,
    lat,
    city: data.city || "",
    district: data.district || "",
    provider_category: "",
    phone: "",
    business_hours: "",
    amap_detail_url: `https://uri.amap.com/marker?position=${lng},${lat}&name=地图选点&src=duskrain&coordinate=gaode&callnative=0`,
    my_category: "",
    rating: null,
    rating_author: "吕俊泽",
    recommend_level: "",
    is_public: true,
  };
}

async function addFromMapClick(event) {
  if (Date.now() - lastHotspotClickAt < 700) return;
  const lng = Number(event.lnglat.lng);
  const lat = Number(event.lnglat.lat);
  form.lng = lng.toFixed(6);
  form.lat = lat.toFixed(6);
  activeModule.value = "edit";
  setStatus("正在读取地图点击位置附近的高德商家...");
  try {
    const data = await reverseGeocode(lng.toFixed(6), lat.toFixed(6));
    const candidate = bestNearbyCandidate(data.items, lng, lat) || manualCandidateFromClick(event, data);
    const existing = findExistingPlace(candidate);
    if (existing) {
      fillFromPlace(existing);
      previewSelected(existing);
      setStatus(`已添加过：${existing.name}，已切换为编辑已有店铺。`);
      return;
    }
    fillFromPlace(candidate, false);
    if (!candidate.name) {
      form.name = "";
      setStatus("已用地图坐标创建空白店铺，请补店名、评分和分类后保存。");
    } else {
      setStatus(`已从地图附近选中：${candidate.name}。确认评分和分类后点保存。`);
    }
    previewSelected({ ...candidate, name: candidate.name || "地图选点" });
  } catch (error) {
    const candidate = manualCandidateFromClick(event);
    fillFromPlace(candidate, false);
    setStatus(`附近商家读取失败，已填入坐标，可手动补店名保存：${error.message}`);
  }
}

async function addFromHotspotClick(event) {
  lastHotspotClickAt = Date.now();
  const lng = Number(event.lnglat?.lng);
  const lat = Number(event.lnglat?.lat);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
  form.lng = lng.toFixed(6);
  form.lat = lat.toFixed(6);
  activeModule.value = "edit";
  setStatus("正在读取点中的高德店铺详情...");
  try {
    let candidate = null;
    if (event.id) {
      const detail = await getPoiDetail(event.id);
      candidate = detail.item;
    }
    candidate = candidate || candidateFromHotspot(event);
    const existing = findExistingPlace(candidate);
    if (existing) {
      fillFromPlace(existing);
      previewSelected(existing);
      setStatus(`已添加过：${existing.name}，已切换为编辑已有店铺。`);
      return;
    }
    fillFromPlace(candidate, false);
    previewSelected(candidate);
    setStatus(`已按地图点中的店铺选择：${candidate.name || event.name}。确认评分和分类后点保存。`);
  } catch (error) {
    const candidate = candidateFromHotspot(event);
    fillFromPlace(candidate, false);
    previewSelected(candidate);
    setStatus(`高德详情读取失败，已按地图热点填入基础信息：${error.message}`);
  }
}

async function savePlace() {
  try {
    const saved = await saveAdminPlace(readPayload(), form.id);
    fillFromPlace(saved);
    setStatus("已保存");
    await Promise.all([loadPlaces(), loadAuthors()]);
    activeModule.value = "edit";
  } catch (error) {
    if (error.status === 409 && error.detail?.existing) {
      await loadPlaces();
      fillFromPlace(error.detail.existing);
      previewSelected(error.detail.existing);
      setStatus(`已添加过：${error.detail.existing.name}，已切换为编辑已有店铺。`);
      activeModule.value = "edit";
      return;
    }
    setStatus(`保存失败：${error.message}`);
  }
}

async function removePlace(place = form) {
  if (!place?.id) return;
  if (!window.confirm("确认删除这家店？")) return;
  try {
    await deleteAdminPlace(place.id);
    resetForm();
    setStatus("已删除");
    await loadPlaces();
    activeModule.value = "list";
  } catch (error) {
    setStatus(`删除失败：${error.message}`);
  }
}

function toggleMapTheme() {
  mapTheme.value = mapTheme.value === "night" ? "day" : "night";
  map.value.setMapStyle(mapTheme.value === "night" ? "amap://styles/dark" : "amap://styles/normal");
  refreshBaseLabelsSoon(220, true);
  document.body.classList.toggle("map-day", mapTheme.value === "day");
}

function handleMapComplete() {
  refreshBaseLabelsSoon(80, true);
}

function handleZoomEnd() {
  syncRenderedMarkersSoon(120);
  refreshBaseLabelsSoon(220);
}

onMounted(async () => {
  try {
    document.body.classList.add("map-day");
    await Promise.all([loadPlaces(), loadAuthors()]);
    AMapRef.value = await loadAmap();
    map.value = new AMapRef.value.Map("adminMap", {
      ...mapOptions({
        animateEnable: false,
        isHotspot: true,
      }),
    });
    applyMapLabels(map.value, AMapRef.value, mapTheme.value);
    map.value.on("complete", handleMapComplete);
    map.value.on("movestart", beginMapMove);
    map.value.on("dragstart", beginMapMove);
    map.value.on("moveend", endMapMove);
    map.value.on("dragend", endMapMove);
    map.value.on("zoomend", handleZoomEnd);
    scaleControl = new AMapRef.value.Scale();
    map.value.addControl(scaleControl);
    infoWindow.value = new AMapRef.value.InfoWindow({
      autoMove: false,
      closeWhenClickMap: true,
      offset: new AMapRef.value.Pixel(0, -20),
      showShadow: false,
    });
    map.value.on("hotspotclick", addFromHotspotClick);
    map.value.on("click", addFromMapClick);
  } catch (error) {
    setStatus(error.message);
  }
});

onUnmounted(() => {
  focusToken += 1;
  window.clearTimeout(baseLabelTimer);
  window.clearTimeout(baseLabelFollowupTimer);
  window.clearTimeout(labelTimer);
  window.clearTimeout(movingTimer);
  window.clearTimeout(renderTimer);
  pendingTimers.forEach((timer) => window.clearTimeout(timer));
  pendingTimers.clear();
  document.body.classList.remove("map-moving", "map-day");

  if (map.value) {
    map.value.off("complete", handleMapComplete);
    map.value.off("movestart", beginMapMove);
    map.value.off("dragstart", beginMapMove);
    map.value.off("moveend", endMapMove);
    map.value.off("dragend", endMapMove);
    map.value.off("zoomend", handleZoomEnd);
    map.value.off("hotspotclick", addFromHotspotClick);
    map.value.off("click", addFromMapClick);
  }
  infoWindow.value?.close();
  googleInfoWindow.value?.close();
  if (googlePreviewMarker.value) googlePreviewMarker.value.map = null;
  if (googleMapClickListener && window.google?.maps?.event) {
    window.google.maps.event.removeListener(googleMapClickListener);
  }
  markerLayer.value?.clear?.();
  if (scaleControl && map.value) map.value.removeControl?.(scaleControl);
  map.value?.destroy?.();

  infoWindow.value = null;
  googleInfoWindow.value = null;
  googlePreviewMarker.value = null;
  googleMap.value = null;
  googleMapsRef.value = null;
  googleMapClickListener = null;
  markerLayer.value = null;
  map.value = null;
  AMapRef.value = null;
  scaleControl = null;
});
</script>

<template>
  <main class="admin-grid" :class="{ 'admin-full-panel-mode': ['bulk', 'authors'].includes(activeModule) }">
    <aside class="admin-panel">
      <header>
        <p class="eyebrow">FOOD MAP ADMIN</p>
        <h1>店铺标记</h1>
      </header>

      <AdminMenu :active="activeModule" @change="setActive" />

      <AdminPlaceList
        v-if="activeModule === 'list'"
        :places="places"
        enable-category-filter
        @new="resetForm"
        @edit="selectPlace"
        @delete="removePlace"
      />
      <AdminPoiSearch
        v-if="activeModule === 'search'"
        :places="places"
        @select-place="selectPlace"
        @select-candidate="selectCandidate"
        @status="setStatus"
        @provider-change="showMapProvider"
      />
      <AdminBulkImport
        v-if="activeModule === 'bulk'"
        :places="places"
        @completed="handleBulkCompleted"
        @status="setStatus"
      />
      <AdminPlaceForm
        v-if="activeModule === 'edit'"
        :form="form"
        :author-options="authorOptions"
        :category-options="categoryOptions"
        @save="savePlace"
        @new="resetForm"
        @delete="removePlace"
      />
      <AdminAuthors
        v-if="activeModule === 'authors'"
        :authors="authors"
        @refresh="refreshAuthors"
        @status="setStatus"
      />
      <AdminSettings
        v-if="activeModule === 'settings'"
        :map-theme="mapTheme"
        @toggle-theme="toggleMapTheme"
      />

      <div class="status-line">{{ statusLine }}</div>
    </aside>
    <section class="map-stage">
      <div class="admin-map-provider">
        <button class="provider-switch-btn" :class="{ 'is-active': mapProvider === 'amap' }" type="button" @click="showMapProvider('amap')">国内高德</button>
        <button class="provider-switch-btn" :class="{ 'is-active': mapProvider === 'google' }" type="button" @click="showMapProvider('google')">国外 Google</button>
      </div>
      <div id="adminMap" v-show="mapProvider === 'amap'" class="map-canvas map-provider-layer"></div>
      <div id="adminGoogleMap" v-show="mapProvider === 'google'" class="map-canvas map-provider-layer"></div>
    </section>
  </main>
</template>
