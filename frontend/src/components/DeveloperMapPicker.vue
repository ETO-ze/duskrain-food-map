<script setup>
import { nextTick, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { getDeveloperPoiDetail, reverseGeocodeForDeveloper } from "../utils/api";
import { fetchGooglePlace, loadGoogleMaps, reverseGeocodeGoogle } from "../utils/google-map";
import { applyMapLabels, loadAmap, mapOptions } from "../utils/map";

const props = defineProps({
  places: { type: Array, required: true },
});

const emit = defineEmits(["select-candidate", "select-place", "status"]);
const provider = ref("amap");
const AMapRef = shallowRef(null);
const amap = shallowRef(null);
const googleMapsRef = shallowRef(null);
const googleMap = shallowRef(null);
let amapHotspotAt = 0;
let googleClickListener = null;

function findExisting(candidate) {
  return props.places.find((place) => {
    const sameProvider = (place.map_provider || "amap") === (candidate.map_provider || "amap");
    if (sameProvider && candidate.provider_poi_id && place.provider_poi_id === candidate.provider_poi_id) return true;
    return sameProvider
      && String(place.name || "").trim().toLowerCase() === String(candidate.name || "").trim().toLowerCase()
      && String(place.address || "").trim().toLowerCase() === String(candidate.address || "").trim().toLowerCase()
      && Math.abs(Number(place.lng) - Number(candidate.lng)) < 0.000001
      && Math.abs(Number(place.lat) - Number(candidate.lat)) < 0.000001;
  });
}

function chooseCandidate(candidate, statusMessage = "") {
  const existing = findExisting(candidate);
  if (existing) {
    emit("status", `你已添加过：${existing.name}，已切换到现有记录。`);
    emit("select-place", existing);
    return;
  }
  emit("select-candidate", candidate);
  emit(
    "status",
    statusMessage || `已选中：${candidate.name || candidate.address || "地图位置"}，请补充评价后保存。`,
  );
}

function distanceScore(candidate, lng, lat) {
  const dx = Number(candidate.lng) - Number(lng);
  const dy = Number(candidate.lat) - Number(lat);
  return ((dx * dx) + (dy * dy)) * 100000000;
}

function poiKindScore(candidate) {
  const text = `${candidate.provider_category || ""} ${candidate.name || ""}`;
  let score = 0;
  if (/餐饮|美食|小吃|甜品|咖啡|茶|酒吧|烧烤|火锅|料理|面包/.test(text)) score -= 80;
  if (/购物|商场|写字楼|住宅|停车场|门|出入口|Shopping|Mall|Building/i.test(text)) score += 90;
  return score;
}

function bestNearbyCandidate(items, lng, lat) {
  return [...(items || [])]
    .filter((item) => Number.isFinite(Number(item.lng)) && Number.isFinite(Number(item.lat)))
    .sort((a, b) => (
      distanceScore(a, lng, lat) + poiKindScore(a)
      - distanceScore(b, lng, lat) - poiKindScore(b)
    ))[0];
}

function manualAmapCandidate(lng, lat, data = {}) {
  return {
    map_provider: "amap",
    country_code: "CN",
    coordinate_system: "gcj02",
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
    provider_detail_url: "",
    cover_image: "",
    image_urls: "",
  };
}

async function selectAmapPoint(event) {
  if (Date.now() - amapHotspotAt < 700) return;
  const lng = Number(event.lnglat?.lng);
  const lat = Number(event.lnglat?.lat);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
  emit("status", "正在读取地图点击位置附近的高德商家...");
  try {
    const data = await reverseGeocodeForDeveloper(lng.toFixed(6), lat.toFixed(6));
    const candidate = bestNearbyCandidate(data.items, lng, lat) || manualAmapCandidate(lng, lat, data);
    chooseCandidate(candidate);
  } catch (error) {
    chooseCandidate(
      manualAmapCandidate(lng, lat),
      `地址读取失败，已保留坐标：${error.message}`,
    );
  }
}

async function selectAmapHotspot(event) {
  amapHotspotAt = Date.now();
  const lng = Number(event.lnglat?.lng);
  const lat = Number(event.lnglat?.lat);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
  emit("status", "正在读取点中的高德店铺详情...");
  try {
    const detail = event.id ? await getDeveloperPoiDetail(event.id) : null;
    chooseCandidate(detail?.item || {
      ...manualAmapCandidate(lng, lat),
      provider_poi_id: event.id || "",
      name: event.name || "",
    });
  } catch (error) {
    chooseCandidate({
      ...manualAmapCandidate(lng, lat),
      provider_poi_id: event.id || "",
      name: event.name || "",
    }, `高德详情读取失败，已保留基础信息：${error.message}`);
  }
}

async function initGoogleMap() {
  if (googleMap.value) return;
  googleMapsRef.value = await loadGoogleMaps();
  const { Map } = await googleMapsRef.value.importLibrary("maps");
  googleMap.value = new Map(document.getElementById("developerGooglePicker"), {
    center: { lat: 20, lng: 0 },
    zoom: 2,
    mapId: "DEMO_MAP_ID",
    streetViewControl: false,
    mapTypeControl: false,
    fullscreenControl: false,
    zoomControl: false,
    clickableIcons: true,
    gestureHandling: "greedy",
  });
  googleClickListener = googleMap.value.addListener("click", async (event) => {
    const lat = Number(event.latLng?.lat());
    const lng = Number(event.latLng?.lng());
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    try {
      if (event.placeId) {
        event.stop?.();
        emit("status", "正在读取点击的 Google 商家详情...");
        chooseCandidate(await fetchGooglePlace(event.placeId));
        return;
      }
      emit("status", "正在解析 Google 地图点击位置...");
      chooseCandidate(await reverseGeocodeGoogle({ lat, lng }));
    } catch (error) {
      chooseCandidate({
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
        cover_image: "",
        image_urls: "",
      }, `Google 地址读取失败，已保留坐标：${error.message}`);
    }
  });
}

async function switchProvider(nextProvider) {
  provider.value = nextProvider === "google" ? "google" : "amap";
  if (provider.value === "google") {
    await nextTick();
    await initGoogleMap();
  }
}

onMounted(async () => {
  try {
    AMapRef.value = await loadAmap();
    amap.value = new AMapRef.value.Map("developerAmapPicker", mapOptions({
      animateEnable: false,
      isHotspot: true,
    }));
    applyMapLabels(amap.value, AMapRef.value, "day");
    amap.value.on("hotspotclick", selectAmapHotspot);
    amap.value.on("click", selectAmapPoint);
  } catch (error) {
    emit("status", error.message);
  }
});

onUnmounted(() => {
  if (amap.value) {
    amap.value.off("hotspotclick", selectAmapHotspot);
    amap.value.off("click", selectAmapPoint);
    amap.value.destroy?.();
  }
  if (googleClickListener && window.google?.maps?.event) {
    window.google.maps.event.removeListener(googleClickListener);
  }
  if (googleMap.value && window.google?.maps?.event) {
    window.google.maps.event.clearInstanceListeners(googleMap.value);
  }
  amap.value = null;
  AMapRef.value = null;
  googleMap.value = null;
  googleMapsRef.value = null;
  googleClickListener = null;
});
</script>

<template>
  <section class="admin-module developer-map-picker">
    <div class="section-title">
      <span>地图选点</span>
      <span class="pill">点击商家或地图位置</span>
    </div>
    <div class="provider-switch">
      <button class="provider-switch-btn" :class="{ 'is-active': provider === 'amap' }" type="button" @click="switchProvider('amap')">国内高德</button>
      <button class="provider-switch-btn" :class="{ 'is-active': provider === 'google' }" type="button" @click="switchProvider('google')">国外 Google</button>
    </div>
    <div class="developer-picker-frame">
      <div id="developerAmapPicker" v-show="provider === 'amap'" class="map-canvas"></div>
      <div id="developerGooglePicker" v-show="provider === 'google'" class="map-canvas"></div>
    </div>
    <p class="subtle">点中地图商家会自动补全资料；点空白位置会读取附近商家或保留坐标，然后进入编辑页面。</p>
  </section>
</template>
